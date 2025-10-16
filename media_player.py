from __future__ import annotations
import re
from typing import Any, Optional
from datetime import datetime, timezone

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerEntityFeature
from homeassistant.components.media_player.const import MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify as ha_slugify


from .const import DOMAIN
from . import _LOGGER

# ──────────────────────────────────────────────────────────────────────────────
# Emby sessions → HA Media Players
# This file watches Emby sessions and turns them into media_player entities.
# Think of it like translating "Now Playing" into "Now Home-Assisting".
# ──────────────────────────────────────────────────────────────────────────────


def _summarize_json(data: Any) -> str:
    """Shrink a JSON tree to a bonsai (for logs). No pruning shears required."""
    try:
        if data is None:
            return "None"
        if isinstance(data, dict):
            keys = list(data.keys())
            return f"dict(len={len(keys)}, keys={keys[:8]}{'...' if len(keys) > 8 else ''})"
        if isinstance(data, list):
            head = data[0] if data else None
            if isinstance(head, dict):
                hkeys = list(head.keys())
                return f"list(len={len(data)}, first=dict(keys={hkeys[:8]}{'...' if len(hkeys) > 8 else ''}))"
            return f"list(len={len(data)}, first_type={type(head).__name__})"
        return f"{type(data).__name__}"
    except Exception as e:
        return f"<summarize_error: {e!r}>"


def _ticks_to_seconds(ticks: Optional[int]) -> Optional[float]:
    """Emby ticks → seconds. 10,000,000 ticks per sec (no, not the bug kind)."""
    if not isinstance(ticks, (int, float)):
        return None
    return float(ticks) / 10_000_000.0


def _content_type_from_item_type(item_type: Optional[str]) -> Optional[str]:
    """Normalize Emby item types into HA-friendly flavors. 31 flavors not included."""
    if not item_type:
        return None
    it = item_type.lower()
    if it in ("episode",):
        return "tvshow"
    if it in ("movie",):
        return "movie"
    if it in ("audio", "audiofile", "music", "musicvideo"):
        return "music"
    if it in ("livetvchannel", "tvchannel", "program"):
        return "tvchannel"
    return it


def _epg_series_from(item: dict[str, Any]) -> Optional[str]:
    """Find a series-ish title. If all else fails, call it by its Name (classic)."""
    if not isinstance(item, dict):
        return None
    return (
        item.get("SeriesName")
        or item.get("SeriesTitle")
        or item.get("ProgramSeriesTitle")
        or item.get("ShowName")
        or item.get("Program")
        or item.get("Name")
    )


def _strip_parentheticals(text: Optional[str]) -> Optional[str]:
    """Remove '(extra info)' from names. Parentheses? We call them 'aside hustles'."""
    if not text:
        return text
    cleaned = re.sub(r"\s*\([^)]*\)", "", text).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Spin up entities for each live Emby session (like a DJ for devices)."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]

    entities: dict[str, EmbySessionEntity] = {}

    @callback
    def _sync_entities() -> None:
        """Bring the entity list in sync with Emby sessions. No FOMO."""
        sessions: list[dict[str, Any]] = coordinator.data or []
        seen: set[str] = set()
        new_entities: list[EmbySessionEntity] = []

        for s in sessions:
            sid = s.get("Id") or s.get("SessionId")
            if not sid:
                continue
            seen.add(sid)
            if sid not in entities:
                # New session just dropped a beat → make a new entity.
                ent = EmbySessionEntity(coordinator, client, s)
                entities[sid] = ent
                new_entities.append(ent)
            else:
                # Existing session, just remix the metadata.
                entities[sid]._apply_session(s)

        # Any entities not seen? They ghosted. Mark 'em as gone.
        for sid in (set(entities.keys()) - seen):
            entities[sid].mark_gone()

        if new_entities:
            # Drop the bass and the new entities at the same time.
            async_add_entities(new_entities, True)

    _sync_entities()
    coordinator.async_add_listener(_sync_entities)


class EmbySessionEntity(CoordinatorEntity, MediaPlayerEntity):
    """One Emby session, one Home Assistant media_player. Party of one? Party on."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.SEEK
    )

    def __init__(self, coordinator, client, session: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._client = client
        self._session_id: str = session.get("Id") or session.get("SessionId")

        # Stable id → stable relationship. We’re in it for the long haul.
        self._attr_unique_id = f"emby_{self._session_id}"
        self._attr_has_entity_name = True
        # Ensure name always starts with emby_
        self._attr_name = f"emby_{self._session_id}"

        # New entities get tasty object_ids like media_player.emby_my_device.
        self._suggested_object_id = self._compute_object_id(session)
        if not self._suggested_object_id.startswith("emby_"):
            self._suggested_object_id = f"emby_{self._suggested_object_id}"

        self._attr_available = True

        # Cached state (because asking every second is clingy).
        self._name_prefix: Optional[str] = None
        self._user: Optional[str] = None
        self._media_title: Optional[str] = None
        self._artist: Optional[str] = None
        self._series: Optional[str] = None
        self._state: MediaPlayerState | None = MediaPlayerState.IDLE
        self._duration_s: Optional[float] = None
        self._position_s: Optional[float] = None
        self._position_updated_at: Optional[datetime] = None
        self._content_id: Optional[str] = None
        self._content_type: Optional[str] = None
        self._season: Optional[int] = None
        self._episode: Optional[int] = None
        self._entity_picture: Optional[str] = None
        self._app_name: Optional[str] = None

        # Live TV / program intel (because channels like to keep things current).
        self._channel_id: Optional[str] = None          # Emby internal ItemId
        self._channel_number: Optional[str] = None      # Guide/tuner number (e.g., "209")
        self._program_id: Optional[str] = None
        self._epg: Optional[dict[str, Any]] = None
        self._epg_source: Optional[str] = None
        self._last_epg_fetch: Optional[datetime] = None

        self._apply_session(session)

    def _compute_object_id(self, session: dict[str, Any]) -> str:
        """Make a readable, stable, 'emby_'-prefixed object_id. Slugs not slugs."""
        base = session.get("DeviceName") or session.get("Client") or "emby"
        user = session.get("UserName")
        parts = ["emby", base, user] if user else ["emby", base]
        object_id = ha_slugify("_".join([p for p in parts if p]))
        if not object_id.startswith("emby_"):
            object_id = f"emby_{object_id}"
        return object_id

    @callback
    def _handle_coordinator_update(self) -> None:
        """When the coordinator drops new data, we pick it up like hot gossip."""
        sessions: list[dict[str, Any]] = self.coordinator.data or []
        for s in sessions:
            sid = s.get("Id") or s.get("SessionId")
            if sid == self._session_id:
                self._apply_session(s)
                self._attr_available = True
                break
        else:
            # Session left the chat.
            self._attr_available = False
        super()._handle_coordinator_update()

    def _get_playback_info(self, session: dict[str, Any]) -> dict[str, Any]:
        """Extract detailed playback information from the session."""
        np = session.get("NowPlayingItem") or {}
        ps = session.get("PlayState") or {}
        # Extract video information
        video_info = {}
        if media_streams := np.get("MediaStreams", []):
            for stream in media_streams:
                if stream.get("Type") == "Video":
                    video_info = {
                        "codec": stream.get("Codec", "Unknown"),
                        "width": stream.get("Width"),
                        "height": stream.get("Height"),
                        "bitrate": stream.get("BitRate"),
                        "framerate": stream.get("RealFrameRate"),
                        "aspect_ratio": stream.get("AspectRatio"),
                    }
                    break
        # Extract audio information
        audio_info = {}
        if media_streams := np.get("MediaStreams", []):
            for stream in media_streams:
                if stream.get("Type") == "Audio":
                    audio_info = {
                        "codec": stream.get("Codec", "Unknown"),
                        "channels": stream.get("Channels"),
                        "bitrate": stream.get("BitRate"),
                        "sample_rate": stream.get("SampleRate"),
                        "language": stream.get("Language"),
                    }
                    break

        # Get transcoding information
        # Robust detection using TranscodingInfo, PlayState and common hints
        play_method = (ps.get("PlayMethod") or session.get("PlayMethod") or "").lower()
        is_transcoding = play_method == "transcode"
        transcoding = {
            "is_transcoding": is_transcoding,
            "video_codec": ps.get("TranscodingVideoCodec"),
            "audio_codec": ps.get("TranscodingAudioCodec"),
            "reason": ps.get("TranscodingReason", []),
            "bitrate": ps.get("Bitrate"),
            "play_method": play_method,
        }

        # Calculate playback percentage
        position_ticks = ps.get("PositionTicks")
        runtime_ticks = np.get("RunTimeTicks")
        if position_ticks is not None and runtime_ticks:
            percentage = (float(position_ticks) / float(runtime_ticks)) * 100
            playback_percent = round(percentage, 1)
        else:
            playback_percent = None

        return {
            "video": video_info,
            "audio": audio_info,
            "transcoding": transcoding,
            "playback_percent": playback_percent,
        }

    def _apply_session(self, session: dict[str, Any]) -> None:
        """Update our view of the session. Less 'stale', more 'play'."""
        np = session.get("NowPlayingItem") or {}
        ps = session.get("PlayState") or {}

        self._name_prefix = session.get("DeviceName") or session.get("Client") or "Emby Client"
        self._user = session.get("UserName")
        self._app_name = session.get("Client") or session.get("Application") or "Emby"

        # Media identity: who are you and what do you do?
        self._content_id = str(np.get("Id")) if np.get("Id") is not None else None
        self._content_type = _content_type_from_item_type(np.get("Type"))
        self._media_title = np.get("Name")
        self._series = np.get("SeriesName")
        self._artist = np.get("AlbumArtist") or np.get("Artist")
        self._season = np.get("ParentIndexNumber")
        self._episode = np.get("IndexNumber")

        # Poster child.
        self._entity_picture = self._client.item_primary_image_url(self._content_id) if self._content_id else None

        # Time flies like an arrow; playback ticks like a clock.
        self._duration_s = _ticks_to_seconds(np.get("RunTimeTicks"))
        self._position_s = _ticks_to_seconds(ps.get("PositionTicks"))
        self._position_updated_at = datetime.now(timezone.utc) if self._position_s is not None else None

        # State of the (home) union.
        is_paused = bool(ps.get("IsPaused"))
        is_playing_flag = bool(ps.get("IsPlaying")) or (ps.get("PlaybackStatus") == "Playing")
        has_now_playing = bool(np)
        if is_paused:
            self._state = MediaPlayerState.PAUSED
        elif is_playing_flag or (has_now_playing and not is_paused):
            self._state = MediaPlayerState.PLAYING
        else:
            self._state = MediaPlayerState.IDLE

        # Live TV: keep the number, keep the peace.
        self._program_id = None
        self._channel_id = None
        if self._content_type == "tvchannel":
            self._channel_id = (
                str(np.get("ChannelId"))
                if np.get("ChannelId") is not None
                else (self._content_id if self._content_id is not None else None)
            )
            self._program_id = (
                (str(np.get("ProgramId")) if np.get("ProgramId") is not None else None)
                or (str((session.get("NowPlayingProgram") or {}).get("Id"))
                    if isinstance(session.get("NowPlayingProgram"), dict)
                    and (session.get("NowPlayingProgram") or {}).get("Id") is not None else None)
                or (str((np.get("CurrentProgram") or {}).get("Id"))
                    if isinstance(np.get("CurrentProgram"), dict)
                    and (np.get("CurrentProgram") or {}).get("Id") is not None else None)
                or (str(session.get("NowPlayingProgramId")) if session.get("NowPlayingProgramId") is not None else None)
            )
            # If Emby hands us a channel number, we won’t channel our inner skeptic.
            cn = np.get("ChannelNumber") or np.get("Number")
            if cn is not None:
                self._channel_number = str(cn)



            if self._channel_id or self._program_id:
                self._maybe_schedule_epg_refresh()
        else:
            # Not live TV? Then we live free.
            self._channel_id = None
            self._program_id = None
            self._epg = None
            self._epg_source = None
            self._channel_number = None

    def _maybe_schedule_epg_refresh(self) -> None:
        """Be cool: don’t spam the EPG. Throttle like a pro."""
        now = datetime.now(timezone.utc)
        if self._last_epg_fetch and (now - self._last_epg_fetch).total_seconds() < 20:
            return
        self._last_epg_fetch = now
        if self.hass:
            self.hass.async_create_task(self._async_refresh_epg())

    async def _async_refresh_epg(self) -> None:
        """Fetch program info. It’s like a guide, but guiding our attributes."""
        try:
            epg = await self._client.async_get_program_for_session(
                channel_id=self._channel_id, program_id=self._program_id
            )
            if not epg and self._channel_id:
                epg = await self._client.async_get_current_program(self._channel_id)

            # Adopt channel id/number from program or channel object (adoption is beautiful).
            if isinstance(epg, dict):
                if epg.get("ChannelId"):
                    self._channel_id = str(epg.get("ChannelId"))
                cn = epg.get("ChannelNumber") or epg.get("Number")
                if cn is not None:
                    self._channel_number = str(cn)
                if self._channel_number is None and self._channel_id:
                    ch = await self._client.async_get_channel(self._channel_id)
                    if isinstance(ch, dict):
                        cn2 = ch.get("Number") or ch.get("ChannelNumber")
                        if cn2 is not None:
                            self._channel_number = str(cn2)

            self._epg = epg
            if epg and isinstance(epg, dict):
                self._epg_source = "program_id" if (self._program_id and epg.get("Id") == self._program_id) else "channel_search"
            else:
                self._epg_source = "none"


        except Exception as exc:
            # If EPG fails, we keep calm and stream on.
            self._epg = None
            self._epg_source = "error"
        finally:
            if self.hass:
                self.async_write_ha_state()

    def mark_gone(self) -> None:
        """Session disappeared. We do too (politely)."""
        self._attr_available = False
        if self.hass:
            self.async_write_ha_state()

    # ----- Name & core props ---------------------------------------------------

    @property
    def name(self) -> str | None:
        """Display name: DeviceName (User). Two names, one entity, zero confusion."""
        if self._user:
            return f"{self._name_prefix} ({self._user})"
        return self._name_prefix

    @property
    def state(self) -> str | None:
        """Playing, paused, idle—like states of matter, but with more vibes."""
        return self._state

    @property
    def media_title(self) -> Optional[str]:
        """For tvchannel we hide media_title (use channel_name attribute instead)."""
        if self._content_type == "tvchannel":
            return None
        return self._media_title

    @property
    def media_artist(self) -> Optional[str]:
        """If it sings, we bring the artist."""
        return self._artist

    @property
    def media_series_title(self) -> Optional[str]:
        """Series title for shows (we’ve got seasons, not seasoning)."""
        if self._series:
            return self._series
        if self._content_type == "tvchannel" and self._epg:
            return self._epg.get("SeriesName")
        return None

    @property
    def media_duration(self) -> Optional[float]:
        """How long is this party? (Seconds, not vibes.)"""
        if self._duration_s is not None:
            return self._duration_s
        if self._content_type == "tvchannel" and self._epg:
            start = self._epg.get("StartDate")
            end = self._epg.get("EndDate")
            try:
                if start and end:
                    s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    e = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    return max(0.0, (e - s).total_seconds())
            except Exception:
                pass
        return None

    @property
    def media_position(self) -> Optional[float]:
        """Where are we now? (Time, not geography.)"""
        return self._position_s

    @property
    def media_position_updated_at(self) -> Optional[datetime]:
        """Freshness date for media_position. Best served UTC."""
        return self._position_updated_at

    @property
    def media_content_id(self) -> Optional[str]:
        """Emby ItemId. Like a backstage pass."""
        return self._content_id

    @property
    def media_content_type(self) -> Optional[str]:
        """movie / tvshow / music / tvchannel. Pop, lock, and type it."""
        return self._content_type

    @property
    def entity_picture(self) -> Optional[str]:
        """Poster/fanart URL. We frame it so you don’t have to."""
        return self._entity_picture

    # ----- Extra attributes (aka the liner notes) -----------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Bonus metadata: small, punchy, and surprisingly useful."""
        attrs: dict[str, Any] = {}
        attrs["app_name"] = self._app_name
        attrs["user"] = self._user
        attrs["friendly_name"] = self.name

        # Add user profile image if available
        session_data = next(
            (s for s in (self.coordinator.data or [])
             if (s.get("Id") or s.get("SessionId")) == self._session_id),
            {}
        )
        user_id = session_data.get("UserId")
        if user_id:
            attrs["user_img"] = self._client.user_profile_image_url(user_id)
        else:
            attrs["user_img"] = None

        # custom_name = "<user> on <friendly_name-without-(...)>"
        base_friendly = self.name or ""
        clean_friendly = _strip_parentheticals(base_friendly) or base_friendly
        if self._user and clean_friendly:
            attrs["custom_name"] = f"{self._user} on {clean_friendly}"
        elif clean_friendly:
            attrs["custom_name"] = clean_friendly
        elif self._user:
            attrs["custom_name"] = self._user

        # Get playback info for current session
        session_data = next(
            (s for s in (self.coordinator.data or [])
             if (s.get("Id") or s.get("SessionId")) == self._session_id),
            {}
        )
        if session_data:
            playback_info = self._get_playback_info(session_data)
            
            # Add video details
            if video_info := playback_info["video"]:
                attrs["video_codec"] = video_info["codec"]
                if video_info["height"] and video_info["width"]:
                    attrs["video_resolution"] = f"{video_info['width']}x{video_info['height']}"
                attrs["video_framerate"] = video_info["framerate"]
                if video_info["bitrate"]:
                    attrs["video_bitrate"] = f"{video_info['bitrate'] // 1000}kbps"

            # Add audio details
            if audio_info := playback_info["audio"]:
                attrs["audio_codec"] = audio_info["codec"]
                if audio_info["channels"]:
                    attrs["audio_channels"] = f"{audio_info['channels']} channels"
                if audio_info["bitrate"]:
                    attrs["audio_bitrate"] = f"{audio_info['bitrate'] // 1000}kbps"

            # Add playback method (direct or transcoding)
            if trans_info := playback_info["transcoding"]:
                attrs["playback_method"] = "transcoding" if trans_info["is_transcoding"] else "direct"
                if trans_info["is_transcoding"]:
                    if trans_info["video_codec"]:
                        attrs["transcode_video_codec"] = trans_info["video_codec"]
                    if trans_info["audio_codec"]:
                        attrs["transcode_audio_codec"] = trans_info["audio_codec"]
                    if trans_info["bitrate"]:
                        attrs["transcode_bitrate"] = f"{trans_info['bitrate'] // 1000}kbps"

            # Add playback percentage
            if playback_info["playback_percent"] is not None:
                attrs["playback_percent"] = playback_info["playback_percent"]

        # VOD extras
        if self._content_type != "tvchannel":
            if self._series is not None:
                attrs["media_series_title"] = self._series
            if self._season is not None:
                attrs["media_season"] = self._season
            if self._episode is not None:
                attrs["media_episode"] = self._episode

        # Live TV attributes (freshly renamed so they read like a program guide)
        if self._content_type == "tvchannel":
            epg = self._epg or {}
            attrs["program_series"] = _epg_series_from(epg)
            attrs["program_overview"] = epg.get("Overview")
            attrs["program_start"] = epg.get("StartDate")
            attrs["program_end"] = epg.get("EndDate")
            attrs["channel_id"] = self._channel_id
            attrs["channel_number"] = self._channel_number
            attrs["program_id"] = self._program_id
            if self._epg_source:
                attrs["program_source"] = self._epg_source
            # Prefer NowPlaying channel name (because channel_name pops on dashboards).
            attrs["channel_name"] = self._media_title or epg.get("ChannelName")
            
            # Add program image if available
            if program_id := epg.get("Id"):
                attrs["program_image_url"] = self._client.item_primary_image_url(program_id)
            elif self._program_id:
                attrs["program_image_url"] = self._client.item_primary_image_url(self._program_id)

        return attrs

    # ----- Controls (play nice) -----------------------------------------------

    async def async_media_play(self) -> None:
        """Unpause. Resume. Hit it."""
        await self._client.async_unpause(self._session_id)
        await self.coordinator.async_request_refresh()

    async def async_media_pause(self) -> None:
        """Pause like a pro. (We’ll call back soon.)"""
        await self._client.async_pause(self._session_id)
        await self.coordinator.async_request_refresh()

    async def async_media_stop(self) -> None:
        """Party’s over. (Or intermission.)"""
        await self._client.async_stop(self._session_id)
        await self.coordinator.async_request_refresh()

    async def async_media_seek(self, position: float) -> None:
        """Seek to `position` seconds. Time travel without paradoxes."""
        await self._client.async_seek(self._session_id, position)
        await self.coordinator.async_request_refresh()
