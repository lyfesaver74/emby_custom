# custom_components/emby_custom/api.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict
from aiohttp import ClientSession
from datetime import datetime, timedelta, timezone
import logging

from .const import DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)
EMBY_HEADER_TOKEN = "X-Emby-Token"


class EmbyAuthError(Exception):
    pass


@dataclass
class EmbyClient:
    session: ClientSession
    host: str
    port: int = DEFAULT_PORT
    use_ssl: bool = False
    api_key: str = ""
    _user_id: Optional[str] = field(default=None, init=False, repr=False)

    # ------------------------ Core HTTP ------------------------

    @property
    def _base(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        base_url = f"{scheme}://{self.host}:{self.port}"
        return base_url

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers[EMBY_HEADER_TOKEN] = self.api_key
        return headers

    async def _get(self, path: str) -> Any:
        async with self.session.get(f"{self._base}{path}", headers=self._headers(), timeout=15) as resp:
            if resp.status == 401:
                raise EmbyAuthError("Unauthorized")
            resp.raise_for_status()
            try:
                return await resp.json(content_type=None)
            except ValueError:
                return await resp.text()

    async def _post(self, path: str, json: dict | None = None) -> Any:
        async with self.session.post(f"{self._base}{path}", headers=self._headers(), json=json or {}, timeout=15) as resp:
            if resp.status == 401:
                raise EmbyAuthError("Unauthorized")
            resp.raise_for_status()
            try:
                return await resp.json(content_type=None)
            except ValueError:
                return await resp.text()

    # ------------------------ Identity / Info ------------------------

    async def async_get_system_info(self) -> dict:
        data = await self._get("/System/Info")
        return data if isinstance(data, dict) else {}

    async def async_get_user_id(self) -> Optional[str]:
        """
        Robust user-id resolution:
          1) /Users/Me
          2) /Users -> admin else first user
        """
        if self._user_id:
            return self._user_id

        try:
            data = await self._get("/Users/Me")
            if isinstance(data, dict):
                uid = data.get("Id")
                if uid:
                    self._user_id = uid
                    return uid
        except Exception:
            pass

        try:
            users = await self._get("/Users")
            if isinstance(users, list) and users:
                admin = next((u for u in users if u.get("Policy", {}).get("IsAdministrator")), None)
                candidate = admin or users[0]
                uid = candidate.get("Id")
                if uid:
                    self._user_id = uid
                    return uid
        except Exception:
            pass

        return None

    # ------------------------ Sessions ------------------------

    async def async_get_sessions(self) -> list[dict]:
        params = (
            "IncludeDeviceInformation=true"
            "&IncludePlaybackState=true"
            "&ExcludeInactive=false"
            "&ActiveWithinSeconds=86400"
        )
        data = await self._get(f"/Sessions?{params}")
        sessions = data if isinstance(data, list) else []

        # Fall back to "controllable by me" if server only returns 0–1 session
        if len(sessions) <= 1:
            uid = await self.async_get_user_id()
            if uid:
                data2 = await self._get(f"/Sessions?{params}&ControllableByUserId={uid}")
                sessions2 = data2 if isinstance(data2, list) else []
                if len(sessions2) > len(sessions):
                    sessions = sessions2
        return sessions

    # ------------------------ Playback controls ------------------------

    async def async_pause(self, session_id: str) -> None:
        await self._post(f"/Sessions/{session_id}/Playing/Pause")

    async def async_unpause(self, session_id: str) -> None:
        await self._post(f"/Sessions/{session_id}/Playing/Unpause")

    async def async_stop(self, session_id: str) -> None:
        await self._post(f"/Sessions/{session_id}/Playing/Stop")

    async def async_seek(self, session_id: str, position_seconds: float) -> None:
        ticks = int(position_seconds * 10_000_000)
        await self._post(f"/Sessions/{session_id}/Playing/Seek?PositionTicks={ticks}")

    async def async_command(self, session_id: str, command: str, payload: dict | None = None) -> Any:
        return await self._post(f"/Sessions/{session_id}/Command/{command}", payload or {})

    # ------------------------ Images ------------------------

    def item_primary_image_url(self, item_id: str) -> str:
        return f"{self._base}/Items/{item_id}/Images/Primary?api_key={self.api_key}"

    def user_profile_image_url(self, user_id: str) -> str:
        """Return the profile image URL for a user."""
        return f"{self._base}/Users/{user_id}/Images/Primary?api_key={self.api_key}"

    # ------------------------ Live TV / EPG ------------------------

    async def async_get_program_for_session(
        self, channel_id: Optional[str], program_id: Optional[str]
    ) -> Optional[dict]:
        uid = await self.async_get_user_id()
        user_q = f"&UserId={uid}" if uid else ""
        fields = "Overview,Genres,StartDate,EndDate,SeriesName,SeasonNumber,EpisodeNumber,ChannelName,ChannelNumber"

        if program_id:
            try:
                data = await self._get(f"/LiveTv/Programs/{program_id}?Fields={fields}{user_q}")
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        if channel_id:
            return await self.async_get_current_program(channel_id)
        return None

    async def async_get_current_program(self, channel_id: str) -> Optional[dict]:
        uid = await self.async_get_user_id()
        user_q = f"&UserId={uid}" if uid else ""
        fields = "Overview,Genres,StartDate,EndDate,SeriesName,SeasonNumber,EpisodeNumber,ChannelName,ChannelNumber"

        params = f"ChannelIds={channel_id}&IsAiring=true&Limit=1&Fields={fields}{user_q}"
        data = await self._get(f"/LiveTv/Programs?{params}")
        item = None
        if isinstance(data, dict) and isinstance(data.get("Items"), list) and data["Items"]:
            item = data["Items"][0]
        elif isinstance(data, list) and data:
            item = data[0]

        if item is None:
            data2 = await self._get(
                f"/LiveTv/Channels/{channel_id}/Programs?IsAiring=true&Limit=1&Fields={fields}{user_q}"
            )
            if isinstance(data2, dict) and isinstance(data2.get("Items"), list) and data2["Items"]:
                item = data2["Items"][0]
            elif isinstance(data2, list) and data2:
                item = data2[0]
        return item

    async def async_get_channel(self, channel_id: str) -> Optional[dict]:
        try:
            data = await self._get(f"/LiveTv/Channels/{channel_id}")
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    # ------------------------ Server Status ------------------------

    async def async_get_server_stats(self) -> dict:
        """Get server statistics and status information."""
        info = await self.async_get_system_info()
        activities = {"Items": []}
        sessions = []
        
        try:
            activities_data = await self._get("/System/ActivityLog/Entries")
            if isinstance(activities_data, dict):
                activities = activities_data
        except Exception:
            pass
            
        try:
            sessions = await self.async_get_sessions()
        except Exception:
            pass

        return {
            "system_info": info,
            "recent_activities": activities.get("Items", [])[:10],
            "active_sessions": sessions,
        }

    async def async_get_recordings(self) -> dict:
        """Get recording status and scheduled recordings."""
        uid = await self.async_get_user_id()
        user_q = f"&UserId={uid}" if uid else ""
        
        result = {
            "active_recordings": [],
            "scheduled_recordings": [],
            "series_recordings": []
        }

        try:
            now = datetime.now(timezone.utc)

            # Get all current timers first - these have the most up-to-date status
            timers = await self._get(f"/LiveTv/Timers?{user_q}")
            
            # Process timers for both active and scheduled recordings
            if isinstance(timers, dict) and isinstance(timers.get("Items"), list):
                for timer in timers["Items"]:
                    prog = timer.get("ProgramInfo")
                    if prog:
                        name = prog.get("Name")
                        channel = prog.get("ChannelName")
                        start_time_val = prog.get("StartDate")
                        end_time_val = prog.get("EndDate")
                    else:
                        name = timer.get("Name")
                        channel = timer.get("ChannelName")
                        start_time_val = timer.get("StartDate")
                        end_time_val = timer.get("EndDate")
                    status = timer.get("Status")
                    start_time = self._parse_iso(start_time_val)
                    end_time = self._parse_iso(end_time_val)
                    recording_info = {
                        "name": name,
                        "channel": channel,
                        "start_time": start_time_val,
                        "end_time": end_time_val
                    }
                    # Check if this is an active recording
                    is_active = False
                    if status in ["InProgress", "Recording"]:
                        is_active = True
                    elif start_time and end_time and start_time <= now <= end_time:
                        is_active = True
                    if is_active:
                        result["active_recordings"].append(recording_info)
                    elif start_time and start_time > now:
                        result["scheduled_recordings"].append(recording_info)
            
                # Also check /LiveTv/Recordings/Active as a backup
                try:
                    active = await self._get("/LiveTv/Recordings/Active")
                    if isinstance(active, dict) and isinstance(active.get("Items"), list):
                        for item in active["Items"]:
                            name = item.get("Name", "")
                            # Only add if we don't already have it
                            if not any(r["name"] == name for r in result["active_recordings"]):
                                recording_info = {
                                    "name": item.get("Name") or item.get("ProgramName") or "",
                                    "channel": item.get("ChannelName") or item.get("ChannelId") or "",
                                    "start_time": item.get("StartDate") or "",
                                    "end_time": item.get("EndDate") or ""
                                }
                                result["active_recordings"].append(recording_info)
                except Exception:
                    pass
            
            # Process timers for scheduled recordings
            if isinstance(timers, dict) and isinstance(timers.get("Items"), list):
                for timer in timers["Items"]:
                    name = timer.get("Name")
                    if not name:
                        continue
                        
                    start_time = self._parse_iso(timer.get("StartDate"))
                    if not start_time or start_time <= now:
                        continue  # Skip if no start time or already started
                        
                    recording_info = {
                        "name": name,
                        "channel": timer.get("ChannelName", ""),
                        "start_time": timer.get("StartDate", ""),
                        "end_time": timer.get("EndDate", "")
                    }
                    
                    # Only add to scheduled if we don't already have it
                    if not any(r["name"] == name for r in result["scheduled_recordings"]):
                        result["scheduled_recordings"].append(recording_info)

        except Exception as err:
            _LOGGER.error("Error fetching recordings: %r", err)

        # Get series recordings
        try:
            series_items = await self._get(f"/LiveTv/SeriesTimers?{user_q}")
            if isinstance(series_items, dict) and isinstance(series_items.get("Items"), list):
                for item in series_items["Items"]:
                    name = item.get("Name") or ""
                    channel = item.get("ChannelName") or item.get("ChannelId") or ""
                    series_info = {
                        "name": name if name is not None else "",
                        "channel": channel if channel is not None else "",
                        "record_any_time": item.get("RecordAnyTime", True),
                        "record_any_channel": item.get("RecordAnyChannel", False)
                    }
                    result["series_recordings"].append(series_info)
        except Exception as err:
            _LOGGER.error("Error fetching series timers: %r", err)

        return result

    async def async_get_library_stats(self) -> dict:
        """Get library statistics."""
        uid = await self.async_get_user_id()
        if not uid:
            return {}

        items = {}
        views = {"Items": []}

        try:
            items_data = await self._get(f"/Items/Counts?UserId={uid}")
            if isinstance(items_data, dict):
                items = items_data
        except Exception:
            pass
            
        try:
            views_data = await self._get(f"/Users/{uid}/Views")
            if isinstance(views_data, dict):
                views = views_data
        except Exception:
            pass

        return {
            "counts": items,
            "libraries": views.get("Items", []),
        }

    # ------------------------ Library helpers ------------------------

    @staticmethod
    def _parse_iso(s: Optional[str]) -> Optional[datetime]:
        if not s or not isinstance(s, str):
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _first_video_height(item: dict) -> Optional[int]:
        streams = item.get("MediaStreams") or []
        for st in streams:
            if isinstance(st, dict) and st.get("Type") == "Video":
                h = st.get("Height")
                if isinstance(h, int):
                    return h
        return None

    @staticmethod
    def _compact(d: Dict[str, Any]) -> Dict[str, Any]:
        """Remove keys with falsy values (None, '', [], {})."""
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}

    def _normalize_episode(self, item: dict) -> dict:
        out: dict = {
            "id": item.get("Id"),
            "title": item.get("Name"),
            "series": item.get("SeriesName"),
            "season": item.get("ParentIndexNumber") or item.get("SeasonNumber"),
            "episode": item.get("IndexNumber") or item.get("EpisodeNumber"),
            "premiere_date": item.get("PremiereDate"),
            "runtime": int(item.get("RunTimeTicks") / 10_000_000) if isinstance(item.get("RunTimeTicks"), (int, float)) else None,
            "image": self.item_primary_image_url(item["Id"]) if item.get("Id") else None,
        }
        return self._compact(out)

    def _normalize_movie(self, item: dict) -> dict:
        prov = item.get("ProviderIds") or {}
        out: dict = {
            "id": item.get("Id"),
            "title": item.get("Name"),
            "premiere_date": item.get("PremiereDate") or item.get("ReleaseDate"),
            "runtime": int(item.get("RunTimeTicks") / 10_000_000) if isinstance(item.get("RunTimeTicks"), (int, float)) else None,
            "rating": item.get("CommunityRating"),
            "imdb_id": prov.get("Imdb") or prov.get("ImdbId"),
            "genres": item.get("Genres") or None,
            "tagline": (item.get("Taglines")[0] if isinstance(item.get("Taglines"), list) and item["Taglines"] else None) or item.get("OriginalTitle"),
            "resolution_height": self._first_video_height(item),
            "image": self.item_primary_image_url(item["Id"]) if item.get("Id") else None,
        }
        return self._compact(out)

    async def _user_items(
        self,
        include_types: str,
        sort_by: str,
        sort_order: str = "Descending",
        limit: int = 5,
        filters: Optional[str] = None,
        add_fields: str = (
            "PremiereDate,ReleaseDate,DateCreated,SeriesName,RunTimeTicks,Genres,Taglines,OriginalTitle,"
            "MediaStreams,ProviderIds,IndexNumber,ParentIndexNumber"
        ),
        extra: str = "",
        recursive: bool = True,
        exclude_types: str = "CollectionFolder,Folder,Playlist,BoxSet",
    ) -> List[dict]:
        """Generic /Users/{uid}/Items query with sane defaults for real media (not folders)."""
        uid = await self.async_get_user_id()
        if not uid:
            return []
        path = (
            f"/Users/{uid}/Items?"
            f"IncludeItemTypes={include_types}"
            f"&SortBy={sort_by}&SortOrder={sort_order}"
            f"&Limit={limit}"
            f"&Fields={add_fields}"
        )
        if recursive:
            path += "&Recursive=true"
        if exclude_types:
            path += f"&ExcludeItemTypes={exclude_types}"
        if filters:
            path += f"&Filters={filters}"
        if extra:
            path += f"&{extra.lstrip('&')}"
        data = await self._get(path)
        if isinstance(data, dict) and isinstance(data.get("Items"), list):
            return data["Items"]
        if isinstance(data, list):
            return data
        return []

    # ---- Latest ----

    async def async_get_latest_movies(self, limit: int = 5) -> List[dict]:
        items = await self._user_items("Movie", sort_by="DateCreated", sort_order="Descending", limit=limit * 2)
        return [self._normalize_movie(x) for x in items[:limit]]

    async def async_get_latest_episodes(self, limit: int = 5) -> List[dict]:
        items = await self._user_items("Episode", sort_by="DateCreated", sort_order="Descending", limit=limit * 2)
        return [self._normalize_episode(x) for x in items[:limit]]

    # ---- Upcoming ----

    async def async_get_upcoming_episodes(self, limit: int = 5) -> List[dict]:
        """
        Preferred: /Shows/Upcoming (schedule entries may lack Ids).
        Fallback: Items (Episode) with MinPremiereDate=now, IsUnaired=true.
        """
        uid = await self.async_get_user_id()
        if not uid:
            return []
        fields = "PremiereDate,SeriesName,RunTimeTicks,IndexNumber,ParentIndexNumber"

        data = await self._get(f"/Shows/Upcoming?UserId={uid}&Limit={limit*8}&Fields={fields}")
        items: List[dict] = []
        if isinstance(data, dict) and isinstance(data.get("Items"), list):
            items = data["Items"]
        elif isinstance(data, list):
            items = data

        if not items:
            now = datetime.now(timezone.utc)
            horizon = now + timedelta(days=365)
            extra = f"MinPremiereDate={now.isoformat()}&MaxPremiereDate={horizon.isoformat()}&IsUnaired=true"
            items = await self._user_items(
                "Episode",
                sort_by="PremiereDate",
                sort_order="Ascending",
                limit=limit * 12,
                add_fields=fields,
                extra=extra,
            )

        now = datetime.now(timezone.utc)
        normed = []
        for x in items:
            if not isinstance(x, dict):
                continue
            dt = self._parse_iso(x.get("PremiereDate"))
            if dt and dt >= now:
                normed.append(self._normalize_episode(x))
        normed.sort(key=lambda i: i.get("premiere_date") or "9999")
        return normed[:limit]
