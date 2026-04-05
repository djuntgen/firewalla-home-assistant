# Firewalla Home Assistant Integration

A custom Home Assistant integration for managing Firewalla firewall rules, groups, and parental controls via the MSP (Managed Service Provider) API v2.

## Features

- **Rule switches** — each Firewalla rule becomes an HA switch (toggle pause/resume)
- **Group internet switches** — per-group internet control, derived from `action` + `target.type` API fields
- **Per-group rule switches** — category/app block rules per group, named from API data (`action` + `target.value`)
- **Time limit sensors** — per-user app and internet time limits with remaining minutes, quota, used, usage percentage
- **Per-user bandwidth sensors** — 24h download/upload in GB per user group
- **Per-device online sensors** — online/offline status for each device with IP, MAC vendor, network, last seen
- **User activity sensors** — binary sensors detecting active internet usage per user (10 KB threshold, 5-minute cooldown)
- **Rules summary sensor** — overview of total/active/paused rules with breakdown by type
- **Dynamic entity lifecycle** — entities auto-add/remove when Firewalla rules, groups, or devices change
- **Optimistic state updates** — UI reflects toggles immediately, confirmed on next poll
- **Configurable polling intervals** — tune API call frequency via integration options
- **Split-polling** — time limit rules polled every 30s; full rules at configurable interval (default 3 min)
- **Reconfigure flow** — update MSP credentials without deleting the integration
- **Dynamic naming** — all entity names derived from API data, no hardcoded strings

## Prerequisites

- Firewalla device (Gold, Gold SE, Purple, Purple SE, Blue, Red)
- Firewalla MSP account with API access enabled
- Personal Access Token from MSP settings
- Home Assistant 2026.4+

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Firewalla" and install
3. Restart Home Assistant

### Manual

1. Copy the `custom_components/firewalla/` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for "Firewalla"
3. Enter your MSP domain (e.g., `mydomain.firewalla.net`)
4. Enter your Personal Access Token
5. Select your Firewalla box (auto-selected if you only have one)

### Updating Credentials

Go to **Settings > Integrations > Firewalla > 3-dot menu > Reconfigure** to update your MSP domain or access token without deleting the integration. Useful when tokens expire.

### Options (Settings > Integrations > Firewalla > Configure)

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Include Filters | *(empty)* | — | Only show rules matching these filters (one per line, OR'd) |
| Exclude Filters | *(empty)* | — | Hide rules matching these filters (one per line) |
| Full Rules Refresh | 180s | 30-900s | How often to fetch ALL rules. Time limits are always fetched every 30s. |
| Devices Refresh | 60s | 30-600s | How often to refresh device data for activity detection. |
| Users Cache Duration | 600s | 60-3600s | How long to cache user/group name data. |

#### Filter Syntax

Filters use Firewalla's query syntax:

```
status:active           # Only active rules
action:block            # Only block rules
target.type:app         # Only app rules
target.type:category    # Only category rules
target.type:internet    # Only internet rules
scope.type:group        # Only group-scoped rules
```

## Entities

All entity names are derived from API data. Users can override display names via **Settings > Entities > friendly_name**.

### Switches

| Entity | Name Source | Description |
|--------|------------|-------------|
| Per-rule switch | Rule description/target | ON = rule active, OFF = rule paused |
| Group internet switch | `{action} {target.type}` | ON = internet allowed (inverted), OFF = blocked |
| Group rule switch | `{action} {target.value}` | ON = block active, OFF = block paused |

### Sensors

| Entity | Name Source | State | Key Attributes |
|--------|------------|-------|----------------|
| Rules summary | Static | Total rule count | active, paused, by_type |
| Time limit | `{target.value}` (e.g., "Internet", "Youtube") | Minutes remaining | quota_minutes, used_minutes, usage_percent, reached |
| Bandwidth (download) | "Download" | GB (24h) | bytes, mb |
| Bandwidth (upload) | "Upload" | GB (24h) | bytes, mb |

### Binary Sensors

| Entity | Name Source | State | Key Attributes |
|--------|------------|-------|----------------|
| User activity | "Active" | ON = traffic flowing | online_devices, active_devices, download_delta_bytes |
| Device online | Device name from API | ON = online | ip, mac_vendor, network, last_seen, download_24h_mb, upload_24h_mb |

### Device Grouping

Each Firewalla user group becomes an HA **device** named after the user (e.g., "Alice", "Bob"). All entities for that user are grouped under their device. The device name comes directly from the Firewalla API — no "Firewalla Group:" prefix.

### Entity Attributes

**Rule switches** expose: `rule_id`, `rule_type`, `target`, `action`, `status`, `hit_count`, `last_hit`, `time_quota_minutes`, `time_used_minutes`, `schedule_display`, `scope_type`, `scope_value`, `direction`, `resumeTs` (auto-resume timestamp when paused).

**Time limit sensors** expose: `app`, `quota_minutes`, `used_minutes`, `remaining_minutes`, `usage_percent` (capped at 100), `reached`, `paused`, `schedule`, `hit_count`.

**Device online sensors** expose: `mac`, `ip`, `mac_vendor`, `network`, `last_seen`, `ip_reserved`, `download_24h_mb`, `upload_24h_mb`.

## Architecture

```
Home Assistant
+-----------+  +----------+  +---------------+
| switch.py |  | sensor.py|  | binary_sensor |
| RuleSwitch|  | Summary  |  | UserActivity  |
| GroupInet |  | TimeLimit|  | DeviceOnline  |
| GroupRule |  | Bandwidth|  |               |
+-----+-----+  +----+-----+  +------+--------+
      |              |               |
      +--------------+---------------+
                     |
          +----------v----------+
          |   coordinator.py    |
          | DataUpdateCoordinator|
          |  + MSP API Client   |
          +----------+----------+
                     | HTTPS
          +----------v----------+
          | Firewalla MSP API v2|
          | /v2/rules           |
          | /v2/devices         |
          | /v2/users           |
          | /v2/rules/{id}/pause|
          | /v2/rules/{id}/resume|
          +---------------------+
```

### API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v2/rules` | GET | Fetch all rules (with optional `?query=` filter) |
| `/v2/rules?query=action:timelimit` | GET | Lightweight timelimit-only fetch (split-polling) |
| `/v2/rules/{id}/pause` | POST | Pause a rule |
| `/v2/rules/{id}/resume` | POST | Resume a paused rule |
| `/v2/rules/{id}` | GET | Get individual rule status |
| `/v2/devices` | GET | Fetch all devices (online status, bandwidth, groups) |
| `/v2/users` | GET | Fetch users (names, affiliatedTag for group mapping) |

### Scope Types

Rules can be scoped to different levels:

| `scope.type` | `scope.value` | How it's used |
|---|---|---|
| `group` | Group ID | Group internet switches, group rule switches, Internet time limits |
| `user` | User ID | App time limits (YouTube, Facebook, etc.) |
| `device` | MAC address | Shown as generic rule switch with scope attributes |
| `network` | Network ID | Shown as generic rule switch with scope attributes |
| *(absent)* | — | Global rule, shown as generic rule switch |

### Split-Polling Strategy

| Data | Refresh Rate | Payload | Rationale |
|------|-------------|---------|-----------|
| Time limit rules | Every 30s (base poll) | ~5.5 KB | Minutes remaining change constantly |
| All rules | Configurable (default 3 min) | ~55 KB | Rule status changes are rare |
| Devices | Configurable (default 60s) | ~45 KB | Activity uses 5-min cooldown |
| Users | Configurable (default 10 min) | ~2 KB | Names rarely change |

### Time Limit Detection

Firewalla represents time limits in two ways:
- `action: timelimit` + `scope: user` — app-specific limits (e.g., YouTube 60 min/day)
- `action: block` + `target: internet` + `scope: group` with `timeUsage` — Internet time limits (e.g., 2 hr/day)

Both are detected and surfaced as time limit sensors with `usage_percent` (capped at 100%).

### Key Patterns

- **Dynamic naming:** Entity names derived from API fields (`action`, `target.type`, `target.value`). No hardcoded English strings.
- **Device names:** Group name from API (e.g., "Alice"), resolved via user `affiliatedTag` mapping.
- **Dynamic lifecycle:** Coordinator listener callbacks track known entity IDs; entities auto-add/remove.
- **Optimistic updates:** Switch toggles update local state immediately via `async_write_ha_state()`.
- **Activity detection:** Tracks `totalDownload` deltas per group with 10 KB threshold and 5-minute cooldown.

## Dashboard

### Prerequisites

Install from HACS:
- **auto-entities** — auto-discovers entities by pattern
- **entity-progress-card** — color-coded progress bars for time limits

### Layout

The dashboard uses a per-user column layout with sections view (`max_columns: 3`):

Each user's column contains:
1. **Activity tile** — online/offline with traffic detection
2. **Internet tile** — toggle switch
3. **Bandwidth (24h)** — download and upload in GB
4. **Time limits** — entity-progress-card with usage percentage (green/orange/red)
5. **Devices** — per-device online/offline with last-changed
6. **Blocks** — content block toggles

Time limit progress bars use `usage_percent` attribute with thresholds:
- Green: 0-50% used
- Orange: 50-80% used
- Red: 80-100% used (approaching/reached limit)

### Dashboard Updates

The dashboard is managed via the HA WebSocket API:
```python
ws.send({"type": "lovelace/config/save", "url_path": "dashboard-firewalla", "config": {...}})
```

## Troubleshooting

### "Failed to pause/resume rule" errors

- Check that your Personal Access Token has write permissions
- Verify the Firewalla box is online and reachable

### Token expired / Authentication failed

- Go to **Settings > Integrations > Firewalla > 3-dot menu > Reconfigure**
- Enter a fresh token from your Firewalla MSP portal
- Firewalla MSP tokens (Google OAuth) expire after ~1 hour

### Entities not appearing

- Check **Settings > Devices & Services > Firewalla** for error messages
- Enable debug logging: add `custom_components.firewalla: debug` to `configuration.yaml`
- Time limit sensors only appear for active (non-paused) time limits with quota > 0

### Rate limiting (HTTP 429)

- Increase polling intervals in the integration options
- The integration retries with exponential backoff (1s, 2s, 4s, 8s)

### Orphaned entities

- If Firewalla rules are deleted, the integration removes corresponding HA entities automatically
- Stale entities can be manually removed via **Settings > Entities**

## Development

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/test_coordinator.py -v

# Run tests matching a pattern
pytest tests/ -k "test_split_polling" -v
```

### Test Coverage

- **231+ tests** covering coordinator, switches, sensors, binary sensors, init, and error handling
- Split-polling behavior, configurable intervals, activity detection, group processing
- Dynamic entity lifecycle (add/remove)
- Optimistic state updates
- Internet time limit detection (group-scoped block rules with timeUsage)

## API Reference

- [Firewalla MSP API Docs](https://docs.firewalla.net)
- [MSP API Examples](https://github.com/firewalla/msp-api-examples)
- [Rule Data Model](https://docs.firewalla.net/api/docs/data-models/rule/)
- [Device Data Model](https://docs.firewalla.net/api/docs/data-models/device/)

## License

This project is licensed under the MIT License.
