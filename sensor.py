"""Emby Sensors for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any, List
from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    PERCENTAGE,
    UnitOfInformation,
    UnitOfDataRate,
)

from .const import (
    DOMAIN,
    DEFAULT_OPTIONS,
    OPT_ENABLE_RECORDINGS,
    OPT_ENABLE_ACTIVE_STREAMS,
    OPT_ENABLE_MULTISESSION,
    OPT_ENABLE_BANDWIDTH,
    OPT_ENABLE_TRANSCODING,
    OPT_ENABLE_SERVER_STATS,
    OPT_ENABLE_LIBRARY_STATS,
    OPT_ENABLE_LATEST_MOVIES,
    OPT_ENABLE_LATEST_EPISODES,
    OPT_ENABLE_UPCOMING_EPISODES,
)
from .api import EmbyClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Emby sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: EmbyClient = data["client"]
    sessions_coordinator = data["coordinator"]
    library_coordinator = data["library_coordinator"]
    
    options = {**DEFAULT_OPTIONS, **(entry.options or {})}

    entities: List[SensorEntity] = []

    if options.get(OPT_ENABLE_RECORDINGS, True):
        entities.append(EmbyRecordingSensor(entry, client, None))

    if options.get(OPT_ENABLE_ACTIVE_STREAMS, True):
        entities.append(EmbyActiveStreamsSensor(entry, client, sessions_coordinator))

    if options.get(OPT_ENABLE_MULTISESSION, True):
        entities.append(EmbyMultiSessionUsersSensor(entry, client, sessions_coordinator))

    if options.get(OPT_ENABLE_BANDWIDTH, True):
        entities.append(EmbyBandwidthSensor(entry, client, sessions_coordinator))

    if options.get(OPT_ENABLE_TRANSCODING, True):
        entities.append(EmbyTranscodingSensor(entry, client, sessions_coordinator))

    if options.get(OPT_ENABLE_SERVER_STATS, True):
        entities.append(EmbyServerStatsSensor(entry, client, sessions_coordinator))

    if options.get(OPT_ENABLE_LIBRARY_STATS, True):
        entities.append(EmbyLibraryStatsSensor(entry, client, library_coordinator))

    if options.get(OPT_ENABLE_LATEST_MOVIES, True):
        entities.append(EmbyListSensor(entry, client, library_coordinator, key="latest_movies", title="Latest Movies"))

    if options.get(OPT_ENABLE_LATEST_EPISODES, True):
        entities.append(EmbyListSensor(entry, client, library_coordinator, key="latest_episodes", title="Latest Episodes"))

    if options.get(OPT_ENABLE_UPCOMING_EPISODES, True):
        entities.append(EmbyListSensor(entry, client, library_coordinator, key="upcoming_episodes", title="Upcoming Episodes"))

    async_add_entities(entities)


# ---------------------- Base sensor class ----------------------


class EmbyBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Emby integration."""

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        """Initialize base sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._client = client
        self._attr_available = True
        self._attr_has_entity_name = False

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Emby Server",
            "manufacturer": "Emby",
        }


# ---------------------- Recording sensor ----------------------


class EmbyRecordingSensor(SensorEntity):
    """Sensor for Emby recordings status."""

    _attr_icon = "mdi:record-rec"
    should_poll = True
    _attr_should_poll = True  # Explicitly set polling
    
    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        """Initialize recording sensor."""
        self._entry = entry
        self._client = client
        self._attr_name = "Emby Recordings"
        self._attr_unique_id = f"{entry.entry_id}_recordings"
        self._recording_info = None
        self._attr_has_entity_name = True

    async def async_update(self) -> None:
        """Update recording information."""
        if not self._client:
            self._recording_info = None
            return

        try:
            self._recording_info = await self._client.async_get_recordings()
        except Exception:
            self._recording_info = None

    @property
    def native_value(self) -> int | None:
        """Return the number of active recordings."""
        if not self._recording_info:
            return 0
        return len(self._recording_info.get("active_recordings", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return recording details."""
        if not self._recording_info:
            return {}

        active = []
        for rec in self._recording_info.get("active_recordings", []):
            active.append({
                "name": rec.get("name"),
                "channel": rec.get("channel"),
                "start_time": rec.get("start_time"),
                "end_time": rec.get("end_time"),
            })

        scheduled = []
        for rec in self._recording_info.get("scheduled_recordings", []):
            scheduled.append({
                "name": rec.get("name"),
                "channel": rec.get("channel"),
                "start_time": rec.get("start_time"),
                "end_time": rec.get("end_time"),
            })

        series = []
        for rec in self._recording_info.get("series_recordings", []):
            series.append({
                "name": rec.get("name"),
                "channel": rec.get("channel"),
                "record_any_time": rec.get("record_any_time", True),
                "record_any_channel": rec.get("record_any_channel", True),
            })

        return {
            "active_recordings": active,
            "scheduled_recordings": scheduled,
            "series_recordings": series,
            "active_count": len(active),
            "scheduled_count": len(scheduled),
            "series_count": len(series),
        }


class EmbyActiveStreamsSensor(EmbyBaseSensor):
    """Total number of current active streams; plus summary attributes."""

    _attr_icon = "mdi:play-box-multiple"

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        super().__init__(entry, client, coordinator)
        self._attr_name = "Emby Active Streams"
        self._attr_unique_id = f"{entry.entry_id}_active_streams"

    @property
    def native_value(self) -> int | None:
        sessions: List[dict] = self.coordinator.data or []
        active = [s for s in sessions if isinstance(s.get("NowPlayingItem"), dict)]
        return len(active)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sessions: List[dict] = self.coordinator.data or []
        active = [s for s in sessions if isinstance(s.get("NowPlayingItem"), dict)]
        users = sorted({s.get("UserName") for s in active if s.get("UserName")})
        return {"users": ", ".join(users), "total_sessions": len(sessions)}


class EmbyMultiSessionUsersSensor(EmbyBaseSensor):
    """Users with multiple simultaneously active sessions."""

    _attr_icon = "mdi:account-multiple"

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        super().__init__(entry, client, coordinator)
        self._attr_name = "Emby Multisession Users"
        self._attr_unique_id = f"{entry.entry_id}_multisession_users"

    @property
    def native_value(self) -> int | None:
        users = self._compute_users()
        return len(users)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        users = self._compute_users()
        details = [{"user": u, "count": c, "session_ids": ids} for u, (c, ids) in users.items()]
        return {"users": details}

    def _compute_users(self) -> dict[str, tuple[int, list[str]]]:
        sessions: List[dict] = self.coordinator.data or []
        counts: dict[str, tuple[int, list[str]]] = {}
        for s in sessions:
            npi = s.get("NowPlayingItem")
            if not isinstance(npi, dict):
                continue
            user = s.get("UserName") or "Unknown"
            sid = s.get("Id") or s.get("SessionId")
            if user not in counts:
                counts[user] = (1, [sid] if sid else [])
            else:
                c, ids = counts[user]
                if sid:
                    ids = ids + [sid]
                counts[user] = (c + 1, ids)
        return {u: (c, ids) for u, (c, ids) in counts.items() if c > 1}


# ---------------------- Performance sensors ----------------------


class EmbyBandwidthSensor(EmbyBaseSensor):
    """Sensor for Emby bandwidth usage."""

    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABYTES_PER_SECOND
    _attr_icon = "mdi:network"

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        """Initialize bandwidth sensor."""
        super().__init__(entry, client, coordinator)
        self._attr_name = "Emby Bandwidth Usage"
        self._attr_unique_id = f"{entry.entry_id}_bandwidth"

    @property
    def native_value(self) -> float | None:
        """Return the current bandwidth usage in MB/s."""
        sessions: List[dict] = self.coordinator.data or []
        total_bitrate = 0
        
        for session in sessions:
            if not isinstance(session.get("NowPlayingItem"), dict):
                continue
            playstate = session.get("PlayState", {}) or {}
            tinfo = session.get("TranscodingInfo") or playstate.get("TranscodingInfo") or {}

            # Prefer explicit bitrates in bps
            vbr = (
                playstate.get("VideoBitrate")
                or tinfo.get("VideoBitrate")
                or session.get("VideoBitrate")
                or 0
            )
            abr = (
                playstate.get("AudioBitrate")
                or tinfo.get("AudioBitrate")
                or session.get("AudioBitrate")
                or 0
            )
            if isinstance(vbr, str):
                try:
                    vbr = int(vbr)
                except Exception:
                    vbr = 0
            if isinstance(abr, str):
                try:
                    abr = int(abr)
                except Exception:
                    abr = 0
            stream_total = vbr + abr

            # Fallback: use TargetBitrate if provided (some servers expose it)
            if stream_total == 0:
                tbr = tinfo.get("Bitrate") or session.get("Bitrate") or 0
                if isinstance(tbr, str):
                    try:
                        tbr = int(tbr)
                    except Exception:
                        tbr = 0
                stream_total = tbr

            total_bitrate += stream_total
        
        return round(total_bitrate / 8 / 1024 / 1024, 2)  # Convert to MB/s

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return bandwidth details per stream."""
        sessions: List[dict] = self.coordinator.data or []
        streams_info = []
        
        for session in sessions:
            if not isinstance(session.get("NowPlayingItem"), dict):
                continue
            playstate = session.get("PlayState", {}) or {}
            tinfo = session.get("TranscodingInfo") or playstate.get("TranscodingInfo") or {}
            video_bitrate = (
                playstate.get("VideoBitrate") or tinfo.get("VideoBitrate") or session.get("VideoBitrate") or 0
            )
            audio_bitrate = (
                playstate.get("AudioBitrate") or tinfo.get("AudioBitrate") or session.get("AudioBitrate") or 0
            )
            def _to_mbps(v):
                if isinstance(v, str):
                    try:
                        v = int(v)
                    except Exception:
                        v = 0
                return round(v / 1024 / 1024, 2)

            streams_info.append({
                "user": session.get("UserName", "Unknown"),
                "device": session.get("DeviceName", "Unknown"),
                "media": session["NowPlayingItem"].get("Name", "Unknown"),
                "video_bitrate_mbps": _to_mbps(video_bitrate),
                "audio_bitrate_mbps": _to_mbps(audio_bitrate),
                "total_bitrate_mbps": _to_mbps((video_bitrate or 0) + (audio_bitrate or 0)),
            })

        return {
            "streams": streams_info,
            "active_streams": len(streams_info),
        }


class EmbyTranscodingSensor(EmbyBaseSensor):
    """Sensor for Emby transcoding sessions."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:transcode"

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        """Initialize transcoding sensor."""
        super().__init__(entry, client, coordinator)
        self._attr_name = "Emby Transcoding Load"
        self._attr_unique_id = f"{entry.entry_id}_transcoding"

    @property
    def native_value(self) -> float | None:
        """Return percentage of sessions being transcoded."""
        sessions: List[dict] = self.coordinator.data or []
        active_sessions = [s for s in sessions if isinstance(s.get("NowPlayingItem"), dict)]
        
        if not active_sessions:
            return 0
        
        # Use play_method to detect transcoding (same as media_player)
        transcoding_count = 0
        for s in active_sessions:
            ps = s.get("PlayState", {})
            play_method = (ps.get("PlayMethod") or s.get("PlayMethod") or "").lower()
            if play_method == "transcode":
                transcoding_count += 1
        
        return round((transcoding_count / len(active_sessions)) * 100, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return transcoding session details."""
        sessions: List[dict] = self.coordinator.data or []
        transcoding_info = []
        
        for session in sessions:
            if not isinstance(session.get("NowPlayingItem"), dict):
                continue
            
            # Use play_method to detect transcoding (same as media_player)
            ps = session.get("PlayState", {})
            play_method = (ps.get("PlayMethod") or session.get("PlayMethod") or "").lower()
            
            if play_method == "transcode":
                playstate = session.get("PlayState", {})
                nowplaying = session.get("NowPlayingItem", {})
                tinfo = session.get("TranscodingInfo") or playstate.get("TranscodingInfo") or {}

                # Get original format info and build transcoding reasons
                orig_video_codec = orig_audio_codec = "Unknown"
                orig_video = orig_audio = "Unknown"
                reasons: List[str] = []

                if media_streams := nowplaying.get("MediaStreams", []):
                    for stream in media_streams:
                        if stream.get("Type") == "Video":
                            w = stream.get("Width")
                            h = stream.get("Height")
                            orig_video_codec = (stream.get('Codec') or '').lower()
                            orig_video = f"{w}x{h} {stream.get('Codec', '')}"
                        elif stream.get("Type") == "Audio":
                            orig_audio_codec = (stream.get('Codec') or '').lower()
                            orig_audio = f"{stream.get('Codec', '')} {stream.get('Channels', '')}ch"

                # Target format from TranscodingInfo or PlayState
                transcode_video_codec = (
                    (playstate.get('TranscodingVideoCodec') or tinfo.get('VideoCodec') or '')
                )
                transcode_audio_codec = (
                    (playstate.get('TranscodingAudioCodec') or tinfo.get('AudioCodec') or '')
                )
                video_height = playstate.get('VideoResolution') or tinfo.get('Height') or ''

                # Build reasons
                if transcode_video_codec:
                    if orig_video_codec and transcode_video_codec.lower() != orig_video_codec:
                        reasons.append(f"Video codec: {orig_video_codec} → {transcode_video_codec}")
                    else:
                        reasons.append("Video conversion for compatibility")
                if transcode_audio_codec and (orig_audio_codec and transcode_audio_codec.lower() != orig_audio_codec):
                    reasons.append(f"Audio codec: {orig_audio_codec} → {transcode_audio_codec}")

                # Container/protocol hints
                if tinfo.get('IsHls'):
                    reasons.append("HLS container")
                if tinfo.get('Container') and nowplaying.get('Container') and tinfo.get('Container') != nowplaying.get('Container'):
                    reasons.append(f"Container: {nowplaying.get('Container')} → {tinfo.get('Container')}")

                # Fallback to API reason if available
                api_reasons = playstate.get("TranscodingReason") or tinfo.get("TranscodingReason")
                if api_reasons:
                    if isinstance(api_reasons, list):
                        reasons.extend(api_reasons)
                    elif isinstance(api_reasons, str):
                        reasons.append(api_reasons)

                transcoding_info.append({
                    "user": session.get("UserName", "Unknown"),
                    "device": session.get("DeviceName", "Unknown"),
                    "media": nowplaying.get("Name", "Unknown"),
                    "original_format": {
                        "video": orig_video,
                        "audio": orig_audio,
                    },
                    "target_format": {
                        "video": f"{video_height}p {transcode_video_codec}",
                        "audio": transcode_audio_codec,
                    },
                    "reason": reasons or ["Transcoding for client compatibility"],
                })

        return {
            "transcoding_sessions": transcoding_info,
            "session_count": len(transcoding_info),
        }

# ---------------------- Library-based list sensors ----------------------


# ---------------------- Statistics sensors ----------------------


class EmbyServerStatsSensor(EmbyBaseSensor):
    """Sensor for Emby server statistics."""

    _attr_icon = "mdi:server"
    should_poll = True

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        """Initialize server stats sensor."""
        super().__init__(entry, client, coordinator)
        self._attr_name = "Emby Server Stats"
        self._attr_unique_id = f"{entry.entry_id}_server_stats"
        self._server_info = None

    async def async_update(self) -> None:
        """Update server information."""
        try:
            self._server_info = await self._client.async_get_server_stats()
        except Exception as err:
            _LOGGER.warning("Failed to update server stats: %s", err)
            # Keep previous data if available
            if self._server_info is None:
                self._server_info = {}

    @property
    def native_value(self) -> int | None:
        """Return the number of active sessions."""
        if not self._server_info:
            return 0
        return len([s for s in self._server_info.get("active_sessions", [])
                   if isinstance(s.get("NowPlayingItem"), dict)])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return server statistics."""
        if not self._server_info:
            return {}

        system_info = self._server_info.get("system_info", {})
        sessions = self._server_info.get("active_sessions", [])
        activities = self._server_info.get("recent_activities", [])

        # Process active sessions
        active_sessions = [s for s in sessions if isinstance(s.get("NowPlayingItem"), dict)]
        unique_users = {s.get("UserName") for s in sessions if s.get("UserName")}
        unique_devices = {s.get("DeviceName") for s in sessions if s.get("DeviceName")}

        # Categorize session types
        content_types = {}
        for session in active_sessions:
            if isinstance(session.get("NowPlayingItem"), dict):
                content_type = session["NowPlayingItem"].get("Type", "Unknown")
                content_types[content_type] = content_types.get(content_type, 0) + 1

        return {
            "version": system_info.get("Version"),
            "operating_system": system_info.get("OperatingSystem"),
            "architecture": system_info.get("SystemArchitecture"),
            "active_sessions": len(active_sessions),
            "total_sessions": len(sessions),
            "unique_users": len(unique_users),
            "unique_devices": len(unique_devices),
            "content_types": content_types,
            "recent_activities": [{
                "date": act.get("Date"),
                "user": act.get("UserName"),
                "name": act.get("Name"),
                "type": act.get("Type")
            } for act in activities[:5]],  # Last 5 activities
        }


class EmbyLibraryStatsSensor(EmbyBaseSensor):
    """Sensor for Emby library statistics."""

    _attr_icon = "mdi:library"
    should_poll = True

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator):
        """Initialize library stats sensor."""
        super().__init__(entry, client, coordinator)
        self._attr_name = "Emby Library Stats"
        self._attr_unique_id = f"{entry.entry_id}_library_stats"
        self._library_info = None

    async def async_update(self) -> None:
        """Update library information."""
        try:
            self._library_info = await self._client.async_get_library_stats()
        except Exception as err:
            _LOGGER.warning("Failed to update library stats: %s", err)
            # Keep previous data if available
            if self._library_info is None:
                self._library_info = {}

    @property
    def native_value(self) -> int | None:
        """Return total number of libraries."""
        if not self._library_info:
            return 0
        libraries = self._library_info.get("libraries", [])
        return len(libraries)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return global media counts as attributes."""
        if not self._library_info:
            return {}

        counts = self._library_info.get("counts", {})
        return {
            "total_movies": counts.get("MovieCount", 0),
            "total_series": counts.get("SeriesCount", 0),
            "total_episodes": counts.get("EpisodeCount", 0),
            "total_songs": counts.get("SongCount", 0),
            "total_books": counts.get("BookCount", 0),
            "total_audiobooks": counts.get("AudioBookCount", 0),
            "total_trailers": counts.get("TrailerCount", 0),
            "total_boxsets": counts.get("BoxSetCount", 0),
            "total_playlists": counts.get("PlaylistCount", 0),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


class EmbyListSensor(EmbyBaseSensor):
    """Generic list sensor backed by the shared library coordinator."""

    _attr_icon = "mdi:playlist-star"

    def __init__(self, entry: ConfigEntry, client: EmbyClient, coordinator, key: str, title: str):
        super().__init__(entry, client, coordinator)
        self._key = key  # e.g., 'latest_movies'
        self._attr_has_entity_name = False
        self._attr_name = f"Emby {title}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def native_value(self) -> int | None:
        items: List[dict] = (self.coordinator.data or {}).get(self._key, [])
        return len(items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items: List[dict] = (self.coordinator.data or {}).get(self._key, [])
        return {"items": items}
