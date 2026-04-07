<p align="center">
  <img src="custom_components/firewalla/icon.svg" alt="Firewalla for Home Assistant" width="200">
</p>

<h1 align="center">Firewalla Home Assistant Integration</h1>

<p align="center">
  <a href="https://github.com/custom-components/hacs"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/djuntgen/firewalla-home-assistant/releases"><img src="https://img.shields.io/github/release/djuntgen/firewalla-home-assistant.svg" alt="GitHub release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/djuntgen/firewalla-home-assistant.svg" alt="License"></a>
</p>

A Home Assistant custom integration for managing Firewalla firewall rules, groups, and parental controls via the MSP (Managed Service Provider) API v2.

## Features

- **Rule switches** — each Firewalla rule becomes an HA switch (toggle pause/resume)
- **Group internet switches** — per-group internet control, derived from API data
- **Per-group rule switches** — category/app block rules per group
- **Time limit sensors** — per-user app and internet time limits with remaining minutes, quota, usage percentage
- **Per-user bandwidth sensors** — 24h download/upload in GB per user group
- **Per-device online sensors** — online/offline status with IP, MAC vendor, network, last seen
- **User activity sensors** — binary sensors detecting active internet usage per user
- **Rules summary sensor** — overview of total/active/paused rules with breakdown by type
- **Manual refresh button** — on-demand full data refresh from the Firewalla device page
- **Dynamic entity lifecycle** — entities auto-add/remove when Firewalla rules, groups, or devices change
- **Optimistic state updates** — UI reflects toggles immediately, confirmed on next poll
- **Split-polling** — time-sensitive data polled frequently; bulk data less often
- **Configurable polling intervals** — tune API call frequency via integration options
- **Dynamic naming** — all entity names derived from API data, no hardcoded strings
- **Reconfigure flow** — update MSP credentials without deleting the integration

## Prerequisites

- Firewalla device (Gold, Gold SE, Purple, Purple SE, Blue, Red)
- Firewalla MSP account with API access enabled
- Personal Access Token from MSP settings
- Home Assistant 2026.4+

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > three-dot menu > **Custom repositories**
3. Add this repository URL: `https://github.com/djuntgen/firewalla-home-assistant`
4. Select **Integration** as the category and click **Add**
5. Find "Firewalla" in the integration list and install it
6. Restart Home Assistant

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

### Polling Intervals (Settings > Integrations > Firewalla > Configure)

The integration polls the Firewalla API at configurable intervals. Lower values give faster updates but consume more of your API rate limit budget.

| Option | Default | Range | What it controls |
|--------|---------|-------|------------------|
| Base Poll Interval | 45s | 30-300s | How often the integration calls the Firewalla API. Each poll fetches **time limit data** (~5 KB) — minutes remaining, usage percentage. All other data types refresh at their own intervals below. A manual **Refresh** button is also available on the Firewalla device page. |
| Full Rules Refresh | 300s | 60-900s | How often to fetch **all firewall rules** — block/allow status, hit counts, schedules (~55 KB). Between full refreshes, only lightweight time limit data is fetched. |
| Devices Refresh | 600s | 60-600s | How often to fetch **device data** — online/offline status, IP addresses, bandwidth usage, activity detection (~45 KB). Higher values reduce API calls but delay device status updates. |
| Users Cache Duration | 1800s | 60-3600s | How long to cache **user and group names** (~2 KB). Names rarely change, so this can be set high. |

**API calls per minute at defaults:** ~1.7 (well within Firewalla's rate limits).

### Rule Filters (Settings > Integrations > Firewalla > Configure)

| Option | Description |
|--------|-------------|
| Include Filters | Only show rules matching these filters (one per line, OR logic). **Each filter adds an extra API call per full rules refresh.** |
| Exclude Filters | Hide rules matching these filters (one per line). **Each filter adds an extra API call per full rules refresh.** |

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

### Buttons

| Entity | Description |
|--------|-------------|
| Refresh | Triggers an immediate full data refresh from the Firewalla API. Clears cached data so the next poll fetches everything fresh. |

### Device Grouping

Each Firewalla user group becomes an HA **device** named after the user (e.g., "Alice", "Bob"). All entities for that user are grouped under their device. The main Firewalla box is also a device, hosting the rules summary sensor and refresh button.

## Architecture

```
Home Assistant
+-----------+  +----------+  +---------------+  +----------+
| switch.py |  | sensor.py|  | binary_sensor |  | button.py|
| RuleSwitch|  | Summary  |  | UserActivity  |  | Refresh  |
| GroupInet |  | TimeLimit|  | DeviceOnline  |  |          |
| GroupRule |  | Bandwidth|  |               |  |          |
+-----+-----+  +----+-----+  +------+--------+  +----+-----+
      |              |               |                |
      +--------------+---------------+----------------+
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

### Split-Polling Strategy

The integration uses split-polling to minimize API calls while keeping time-sensitive data fresh:

| Data | Refresh Rate | Payload | What it provides |
|------|-------------|---------|------------------|
| Time limit rules | Every base poll (default 45s) | ~5.5 KB | Minutes remaining, usage percentage — changes constantly |
| All rules | Configurable (default 5 min) | ~55 KB | Block/allow status, hit counts, schedules — changes rarely |
| Devices | Configurable (default 10 min) | ~45 KB | Online/offline, IPs, bandwidth, activity detection |
| Users | Configurable (default 30 min) | ~2 KB | User/group names — almost never changes |

### Time Limit Detection

Firewalla represents time limits in two ways:
- `action: timelimit` + `scope: user` — app-specific limits (e.g., YouTube 60 min/day)
- `action: block` + `target: internet` + `scope: group` with `timeUsage` — Internet time limits (e.g., 2 hr/day)

Both are detected and surfaced as time limit sensors with `usage_percent` (capped at 100%).

## Usage

### Dashboard

#### Prerequisites

Install from HACS:
- **auto-entities** — auto-discovers entities by pattern
- **entity-progress-card** — color-coded progress bars for time limits

#### Layout

The included dashboard template (`custom_components/firewalla/dashboard/firewalla_parental.yaml`) uses a per-user column layout:

1. **Activity tile** — online/offline with traffic detection
2. **Internet tile** — toggle switch
3. **Bandwidth (24h)** — download and upload in GB
4. **Time limits** — entity-progress-card with usage percentage (green/orange/red)
5. **Devices** — per-device online/offline with last-changed
6. **Blocks** — content block toggles

### Automation Examples

#### Activate Rules During Work Hours
```yaml
automation:
  - alias: "Block Gaming During Work Hours"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.firewalla_rule_gaming_category
```

#### Time Limit Notification
```yaml
automation:
  - alias: "Warn When Time Limit Almost Reached"
    trigger:
      - platform: numeric_state
        entity_id: sensor.alice_internet
        attribute: usage_percent
        above: 80
    action:
      - service: notify.mobile_app
        data:
          message: "Internet time limit is at {{ state_attr('sensor.alice_internet', 'usage_percent') }}%"
```

## FAQ

### What is the MSP API?

The MSP (Managed Service Provider) API is Firewalla's cloud API for managing devices and rules. It's separate from the local API on the box. You need an MSP account and a Personal Access Token to use it.

### What are the API rate limits?

Firewalla enforces two rate limits:
- **Short-term:** 100 requests per 5 minutes per token
- **Long-term:** 3,000 requests per day per token

At default settings, this integration uses ~1.7 calls/min (~2,448/day), which is 82% of the daily budget. This leaves room for manual refreshes, filter queries, and rule toggles.

### How do I avoid hitting rate limits?

- Increase the **Base Poll Interval** and **Devices Refresh** in integration options
- Remove include/exclude filters you don't need — each filter adds an API call per full rules refresh
- Use the **Refresh** button for on-demand updates instead of lowering poll intervals
- If you see HTTP 429 errors, the integration retries automatically with exponential backoff (1s, 2s, 4s, 8s)

### How do I update my API token?

Go to **Settings > Integrations > Firewalla > 3-dot menu > Reconfigure**. Enter your new token and save. The integration reloads automatically. Firewalla MSP tokens (Google OAuth) can expire after ~1 hour.

### Why don't I see time limit sensors?

Time limit sensors only appear for:
- Active (non-paused) time limits
- Rules with `quota > 0`
- App time limits (`action: timelimit` + `scope: user`) or Internet time limits (`action: block` + `scope: group` with `timeUsage` data)

### Why are my device sensors slow to update?

Device data (online/offline, bandwidth) refreshes at the **Devices Refresh** interval (default 10 min). This is intentional to reduce API calls — device data is ~45 KB per fetch. Lower this interval if you need faster updates, but watch your daily API budget.

### How do I rename entities?

All entity names come from the Firewalla API. To customize display names, go to **Settings > Entities**, find the entity, and set a **friendly_name**. This doesn't affect the entity ID.

### Can I create new Firewalla rules from Home Assistant?

No. This integration manages existing rules only (pause/resume). Rule creation must be done in the Firewalla app.

### How do I trigger a manual refresh?

Press the **Refresh** button on the Firewalla device page, or call the `button.press` service on `button.firewalla_refresh`. This clears all cached data and triggers an immediate full fetch.

### What happens if I have multiple Firewalla boxes?

Each box is set up as a separate integration instance. During setup, you'll be prompted to select which box to manage. Each box has its own coordinator, entities, and polling intervals.

## Troubleshooting

### "Failed to pause/resume rule" errors

- Check that your Personal Access Token has write permissions
- Verify the Firewalla box is online and reachable

### Token expired / Authentication failed

- Go to **Settings > Integrations > Firewalla > 3-dot menu > Reconfigure**
- Enter a fresh token from your Firewalla MSP portal

### Entities not appearing

- Check **Settings > Devices & Services > Firewalla** for error messages
- Enable debug logging: add `custom_components.firewalla: debug` to `configuration.yaml`

### Rate limiting (HTTP 429)

- Increase polling intervals in the integration options
- The integration retries with exponential backoff (1s, 2s, 4s, 8s)

### Debug Logging

```yaml
logger:
  default: warning
  logs:
    custom_components.firewalla: debug
```

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

## API Reference

- [Firewalla MSP API Docs](https://docs.firewalla.net)
- [MSP API Examples](https://github.com/firewalla/msp-api-examples)

## Changelog

See [CHANGELOG.md](docs/CHANGELOG.md) for version history.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
