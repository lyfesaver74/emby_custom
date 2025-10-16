# 🎬 Emby Custom Integration for Home Assistant

A comprehensive and feature-rich integration for Emby media servers in Home Assistant. Monitor your server activity, track recordings, view bandwidth usage, control playback, and much more—all with configurable sensors and media players that give you complete control over your home media ecosystem.

---

## 📋 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Media Player Entities](#-media-player-entities)
- [Available Sensors](#-available-sensors)
- [Use Cases and Examples](#-use-cases-and-examples)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

---

## ✨ Features

- **Media player entities** for each active Emby session with playback control
- **Real-time monitoring** of active streams, transcoding sessions, and bandwidth usage
- **Live TV recording tracking** with active, scheduled, and series recording details
- **Multi-session detection** for users watching on multiple devices simultaneously
- **Library statistics** with global media counts (movies, episodes, songs, etc.)
- **Server health and activity** monitoring with recent activities and session details
- **Media lists** for latest movies, latest episodes, and upcoming episodes
- **Fully configurable** via Home Assistant's UI—enable or disable any sensor in the integration options

---

## 🚀 Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations** → **Custom repositories**
3. Add this repository URL
4. Search for "Emby Custom" and install
5. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy the `emby_custom` folder to your `custom_components` directory:
   ```
   /config/custom_components/emby_custom/
   ```
3. Restart Home Assistant

---

## ⚙️ Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Emby (Custom)"**
3. Enter the following information:
   - **Host**: Your Emby server IP or hostname (e.g., `192.168.1.100` or `emby.local`)
   - **Port**: Emby server port (default: `8096`)
   - **API Key**: Generate an API key from your Emby server:
     - Go to **Emby Dashboard** → **Advanced** → **API Keys**
     - Create a new API key with a descriptive name (e.g., "Home Assistant")
   - **Use SSL**: Enable if your Emby server uses HTTPS

4. Click **Submit** to complete the setup

### Configuring Sensors

After the initial setup, you can enable or disable individual sensors:

1. Go to **Settings** → **Devices & Services**
2. Find **Emby (Custom)** in your integrations
3. Click the **three-dot menu (⋮)** → **Configure** (or click the gear icon)
4. Toggle the sensors you want to enable or disable
5. Click **Submit** to save your changes

**Available sensor options:**

- Enable Recordings
- Enable Active Streams
- Enable Multisession Users
- Enable Bandwidth Usage
- Enable Transcoding Load
- Enable Server Stats
- Enable Library Stats
- Enable Latest Movies
- Enable Latest Episodes
- Enable Upcoming Episodes

---

## 🎮 Media Player Entities

In addition to sensors, this integration creates **media player entities** for each active Emby session. These entities appear as `media_player.emby_*` and provide real-time playback control and detailed information about what's currently playing.

### Entity Naming

Media player entities are automatically created with the format:
- `media_player.emby_<device>_<user>` (if user is present)
- `media_player.emby_<device>` (if no user is present)

**Example:** `media_player.emby_chrome_john` or `media_player.emby_roku_living_room`

### Playback Controls

Each media player entity supports the following controls:
- **Play** - Resume playback
- **Pause** - Pause playback
- **Stop** - Stop playback
- **Seek** - Jump to a specific position in the media

### Common Attributes (All Media Types)

These attributes are available for all media player entities, regardless of the media type:

| Attribute | Type | Description |
|-----------|------|-------------|
| `app_name` | string | Client application name (e.g., "Emby Web", "Roku") |
| `user` | string | Username of the person watching |
| `user_img` | string | URL to the user's profile image |
| `friendly_name` | string | Display name: "Device (User)" |
| `custom_name` | string | Formatted as "User on Device" (without parentheticals) |
| `playback_method` | string | "direct" or "transcoding" |
| `playback_percent` | float | Percentage of media watched (0-100) |
| `video_codec` | string | Video codec (e.g., "h264", "hevc") |
| `video_resolution` | string | Video resolution (e.g., "1920x1080") |
| `video_framerate` | float | Video framerate (e.g., 23.976) |
| `video_bitrate` | string | Video bitrate (e.g., "5000kbps") |
| `audio_codec` | string | Audio codec (e.g., "aac", "ac3") |
| `audio_channels` | string | Audio channel configuration (e.g., "6 channels") |
| `audio_bitrate` | string | Audio bitrate (e.g., "384kbps") |

### Transcoding Attributes

When `playback_method` is "transcoding", additional attributes are available:

| Attribute | Type | Description |
|-----------|------|-------------|
| `transcode_video_codec` | string | Target video codec for transcoding |
| `transcode_audio_codec` | string | Target audio codec for transcoding |
| `transcode_bitrate` | string | Target bitrate for transcoding |

---

### Movie Attributes

When watching a **movie**, the following additional attributes are available:

| Attribute | Type | Description |
|-----------|------|-------------|
| `media_title` | string | Movie title |
| `media_content_type` | string | Always "movie" |
| `media_content_id` | string | Emby Item ID |
| `media_duration` | float | Total runtime in seconds |
| `media_position` | float | Current playback position in seconds |
| `entity_picture` | string | URL to movie poster |

**Example Use Case:**  
Display currently playing movies on a dashboard with poster art and playback progress.

```yaml
type: custom:mini-media-player
entity: media_player.emby_chrome_john
artwork: full-cover
```

---

### TV Show (Episode) Attributes

When watching a **TV show episode**, the following additional attributes are available:

| Attribute | Type | Description |
|-----------|------|-------------|
| `media_title` | string | Episode title |
| `media_series_title` | string | TV series name |
| `media_season` | int | Season number |
| `media_episode` | int | Episode number |
| `media_content_type` | string | Always "tvshow" |
| `media_content_id` | string | Emby Item ID |
| `media_duration` | float | Episode runtime in seconds |
| `media_position` | float | Current playback position in seconds |
| `entity_picture` | string | URL to episode thumbnail |

**Example Use Case:**  
Create a "Now Watching" card that shows series, season, and episode information.

```yaml
type: markdown
content: >
  **{{ state_attr('media_player.emby_chrome_john', 'media_series_title') }}**
  
  S{{ state_attr('media_player.emby_chrome_john', 'media_season') }}E{{ state_attr('media_player.emby_chrome_john', 'media_episode') }}
  
  {{ state_attr('media_player.emby_chrome_john', 'media_title') }}
```

---

### Live TV (Channel) Attributes

When watching **Live TV**, the following additional attributes are available:

| Attribute | Type | Description |
|-----------|------|-------------|
| `media_content_type` | string | Always "tvchannel" |
| `channel_name` | string | Channel name (e.g., "HBO", "ESPN") |
| `channel_number` | string | Channel number (e.g., "209") |
| `channel_id` | string | Emby channel ID |
| `program_id` | string | Current program/show ID |
| `program_series` | string | Series name of the current program |
| `program_overview` | string | Description/synopsis of the current program |
| `program_start` | string | Program start time (ISO format) |
| `program_end` | string | Program end time (ISO format) |
| `program_image_url` | string | URL to program thumbnail/poster |
| `program_source` | string | How the program info was retrieved ("program_id", "channel_search", or "none") |
| `media_duration` | float | Program duration in seconds (calculated from start/end times) |
| `media_position` | float | Current position in the program in seconds |

**Note:** For Live TV, `media_title` is hidden. Use the `channel_name` attribute instead for display purposes.

**Example Use Case:**  
Display Live TV information with channel number, program name, and time remaining.

```yaml
type: markdown
content: >
  **Channel {{ state_attr('media_player.emby_roku_living_room', 'channel_number') }}**: {{ state_attr('media_player.emby_roku_living_room', 'channel_name') }}
  
  Now Playing: {{ state_attr('media_player.emby_roku_living_room', 'program_series') }}
  
  {{ state_attr('media_player.emby_roku_living_room', 'program_overview') }}
  
  Ends at: {{ state_attr('media_player.emby_roku_living_room', 'program_end')[:19] }}
```

---

## 📊 Available Sensors

### 1. **Emby Recordings**

**Entity ID:** `sensor.emby_recordings`

**Description:**  
Tracks the status of your Emby Live TV recordings, including active, scheduled, and series recordings.

**State:**  
Number of currently active recordings.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `active_recordings` | list | List of currently recording programs with name, channel, start time, and end time |
| `scheduled_recordings` | list | List of upcoming scheduled recordings |
| `series_recordings` | list | List of series recording rules with recording preferences |
| `active_count` | int | Total number of active recordings |
| `scheduled_count` | int | Total number of scheduled recordings |
| `series_count` | int | Total number of series recording rules |

**Example Use Case:**  
Create an automation to send a notification when a recording starts, or display the number of active recordings on your dashboard.

```yaml
automation:
  - alias: "Notify on Recording Start"
    trigger:
      - platform: state
        entity_id: sensor.emby_recordings
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          message: "Emby started recording: {{ state_attr('sensor.emby_recordings', 'active_recordings')[0].name }}"
```

---

### 2. **Emby Active Streams**

**Entity ID:** `sensor.emby_active_streams`

**Description:**  
Displays the total number of active media streams on your Emby server.

**State:**  
Number of active streams (sessions with media currently playing).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `users` | string | Comma-separated list of users with active streams |
| `total_sessions` | int | Total number of connected sessions (including idle) |

**Example Use Case:**  
Monitor how many people are watching content and create automations based on server load.

```yaml
automation:
  - alias: "Server Load Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.emby_active_streams
        above: 5
    action:
      - service: notify.admin
        data:
          message: "High server load: {{ states('sensor.emby_active_streams') }} active streams"
```

---

### 3. **Emby Multisession Users**

**Entity ID:** `sensor.emby_multisession_users`

**Description:**  
Identifies users who are watching content on multiple devices simultaneously.

**State:**  
Number of users with multiple active sessions.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `users` | list | List of users with multiple sessions, including username, session count, and session IDs |

**Example Use Case:**  
Detect potential account sharing or troubleshoot users with playback issues across multiple devices.

```yaml
automation:
  - alias: "Detect Account Sharing"
    trigger:
      - platform: state
        entity_id: sensor.emby_multisession_users
    condition:
      - condition: numeric_state
        entity_id: sensor.emby_multisession_users
        above: 0
    action:
      - service: notify.admin
        data:
          message: "User {{ state_attr('sensor.emby_multisession_users', 'users')[0].user }} is streaming on {{ state_attr('sensor.emby_multisession_users', 'users')[0].count }} devices"
```

---

### 4. **Emby Bandwidth Usage**

**Entity ID:** `sensor.emby_bandwidth_usage`

**Description:**  
Tracks the total bandwidth usage of all active streams on your Emby server in real-time.

**State:**  
Current bandwidth usage in MB/s (megabytes per second).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `streams` | list | Detailed bandwidth info per stream: user, device, media name, video/audio bitrates |
| `active_streams` | int | Number of streams contributing to bandwidth usage |

**Example Use Case:**  
Monitor network usage and trigger alerts or actions when bandwidth exceeds a threshold.

```yaml
automation:
  - alias: "High Bandwidth Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.emby_bandwidth_usage
        above: 50
    action:
      - service: notify.admin
        data:
          message: "Emby bandwidth usage is {{ states('sensor.emby_bandwidth_usage') }} MB/s"
```

---

### 5. **Emby Transcoding Load**

**Entity ID:** `sensor.emby_transcoding_load`

**Description:**  
Monitors the percentage of active streams that are being transcoded by your Emby server.

**State:**  
Percentage of active streams being transcoded (0-100%).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `transcoding_sessions` | list | Details for each transcoding session: user, device, media, original format, target format, and reason for transcoding |
| `session_count` | int | Total number of transcoding sessions |

**Example Use Case:**  
Monitor server CPU load and identify users who are frequently triggering transcoding. You can also use this to optimize your library's file formats.

```yaml
automation:
  - alias: "Transcoding Load Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.emby_transcoding_load
        above: 50
    action:
      - service: notify.admin
        data:
          message: "{{ state_attr('sensor.emby_transcoding_load', 'session_count') }} streams are transcoding ({{ states('sensor.emby_transcoding_load') }}% load)"
```

---

### 6. **Emby Server Stats**

**Entity ID:** `sensor.emby_server_stats`

**Description:**  
Provides comprehensive server statistics including version, OS, active sessions, unique users, and recent activity logs.

**State:**  
Number of active sessions (sessions with media currently playing).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `version` | string | Emby server version |
| `operating_system` | string | Server operating system |
| `architecture` | string | System architecture (e.g., x64) |
| `active_sessions` | int | Number of sessions actively playing media |
| `total_sessions` | int | Total connected sessions (including idle) |
| `unique_users` | int | Number of unique users connected |
| `unique_devices` | int | Number of unique devices connected |
| `content_types` | dict | Breakdown of content types being played (e.g., Movie: 2, Episode: 3) |
| `recent_activities` | list | Last 5 server activities with date, user, media name, and activity type |

**Example Use Case:**  
Display server health on a dashboard or create automations based on server activity patterns.

```yaml
card:
  type: entities
  title: Emby Server
  entities:
    - entity: sensor.emby_server_stats
      secondary_info: "Version: {{ state_attr('sensor.emby_server_stats', 'version') }}"
    - type: attribute
      entity: sensor.emby_server_stats
      attribute: unique_users
      name: Unique Users
```

---

### 7. **Emby Library Stats**

**Entity ID:** `sensor.emby_library_stats`

**Description:**  
Tracks global statistics for your entire Emby media library, including counts for movies, series, episodes, songs, books, and more.

**State:**  
Total number of libraries on your Emby server.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_movies` | int | Total number of movies in your library |
| `total_series` | int | Total number of TV series |
| `total_episodes` | int | Total number of TV episodes |
| `total_songs` | int | Total number of songs |
| `total_books` | int | Total number of books |
| `total_audiobooks` | int | Total number of audiobooks |
| `total_trailers` | int | Total number of trailers |
| `total_boxsets` | int | Total number of box sets/collections |
| `total_playlists` | int | Total number of playlists |
| `last_updated` | string | Timestamp of last update |

**Example Use Case:**  
Display your library size on a dashboard or track library growth over time.

```yaml
card:
  type: glance
  title: Emby Library
  entities:
    - entity: sensor.emby_library_stats
      name: Libraries
    - entity: sensor.emby_library_stats
      name: Movies
      attribute: total_movies
    - entity: sensor.emby_library_stats
      name: Episodes
      attribute: total_episodes
```

---

### 8. **Emby Latest Movies**

**Entity ID:** `sensor.emby_latest_movies`

**Description:**  
Lists the most recently added movies to your Emby library.

**State:**  
Number of recently added movies (default: 5).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `items` | list | List of recently added movies with details: id, title, premiere date, runtime, rating, genres, tagline, resolution, and image URL |

**Example Use Case:**  
Display newly added movies on your dashboard or send notifications when new content is available.

```yaml
automation:
  - alias: "New Movie Added"
    trigger:
      - platform: state
        entity_id: sensor.emby_latest_movies
    action:
      - service: notify.family
        data:
          message: "New movie added: {{ state_attr('sensor.emby_latest_movies', 'items')[0].title }}"
```

---

### 9. **Emby Latest Episodes**

**Entity ID:** `sensor.emby_latest_episodes`

**Description:**  
Lists the most recently added TV episodes to your Emby library.

**State:**  
Number of recently added episodes (default: 5).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `items` | list | List of recently added episodes with details: id, title, series name, season, episode number, premiere date, runtime, and image URL |

**Example Use Case:**  
Notify users when new episodes of their favorite shows are available.

```yaml
automation:
  - alias: "New Episode Available"
    trigger:
      - platform: state
        entity_id: sensor.emby_latest_episodes
    action:
      - service: notify.family
        data:
          message: "New episode: {{ state_attr('sensor.emby_latest_episodes', 'items')[0].series }} - {{ state_attr('sensor.emby_latest_episodes', 'items')[0].title }}"
```

---

### 10. **Emby Upcoming Episodes**

**Entity ID:** `sensor.emby_upcoming_episodes`

**Description:**  
Lists upcoming TV episodes scheduled to air or be released.

**State:**  
Number of upcoming episodes (default: 5).

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `items` | list | List of upcoming episodes with details: id, title, series name, season, episode number, premiere date, runtime, and image URL |

**Example Use Case:**  
Display a "Coming Soon" card on your dashboard or create reminders for episode releases.

```yaml
card:
  type: markdown
  title: Upcoming Episodes
  content: >
    {% for item in state_attr('sensor.emby_upcoming_episodes', 'items') %}
    - **{{ item.series }}** S{{ item.season }}E{{ item.episode }} - {{ item.premiere_date }}
    {% endfor %}
```

---

## 💡 Use Cases and Examples

### Dashboard Card Example

Create a comprehensive Emby monitoring dashboard:

```yaml
type: vertical-stack
cards:
  - type: glance
    title: Emby Server
    entities:
      - entity: sensor.emby_active_streams
        name: Active Streams
      - entity: sensor.emby_bandwidth_usage
        name: Bandwidth
      - entity: sensor.emby_transcoding_load
        name: Transcoding
      - entity: sensor.emby_recordings
        name: Recordings
  
  - type: entities
    title: Server Details
    entities:
      - sensor.emby_server_stats
      - type: attribute
        entity: sensor.emby_server_stats
        attribute: version
        name: Version
      - type: attribute
        entity: sensor.emby_server_stats
        attribute: unique_users
        name: Users Online
  
  - type: markdown
    title: Latest Movies
    content: >
      {% for item in state_attr('sensor.emby_latest_movies', 'items')[:3] %}
      - **{{ item.title }}** ({{ item.premiere_date[:4] }})
      {% endfor %}
```

### Automation Examples

**Notify when server load is high:**

```yaml
automation:
  - alias: "Emby Server High Load"
    trigger:
      - platform: numeric_state
        entity_id: sensor.emby_active_streams
        above: 5
    action:
      - service: notify.admin
        data:
          title: "Emby Server Alert"
          message: "High load: {{ states('sensor.emby_active_streams') }} streams, {{ states('sensor.emby_bandwidth_usage') }} MB/s"
```

**Pause transcoding-heavy streams during peak hours:**

```yaml
automation:
  - alias: "Reduce Transcoding Load"
    trigger:
      - platform: numeric_state
        entity_id: sensor.emby_transcoding_load
        above: 75
    condition:
      - condition: time
        after: "18:00:00"
        before: "23:00:00"
    action:
      - service: notify.family
        data:
          message: "High transcoding load detected. Consider using direct play for better performance."
```

---

## 🔧 Troubleshooting

### Integration Not Appearing

- Ensure the `emby_custom` folder is in `/config/custom_components/`
- Restart Home Assistant
- Clear your browser cache

### Sensors Not Updating

- Check your API key is valid in the Emby Dashboard
- Verify network connectivity to the Emby server
- Check Home Assistant logs for errors: **Settings** → **System** → **Logs**

### Slow Updates or Timeouts

- Some sensors (like Library Stats) poll less frequently to avoid overloading the server
- Reduce the number of enabled sensors if performance is an issue
- Ensure your Emby server has sufficient resources

### Authentication Errors

- Regenerate your API key in the Emby Dashboard
- Reconfigure the integration with the new API key

---

## 🤝 Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue or submit a pull request.

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Credits

Developed by [@lyfesaver74](https://github.com/lyfesaver74)

Special thanks to the Home Assistant and Emby communities for their support and contributions.

---

**Enjoy your Emby integration! 🎉**
