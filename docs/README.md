# Firewalla Home Assistant Integration

A custom Home Assistant integration for managing Firewalla firewall rules, groups, and parental controls via the MSP (Managed Service Provider) API v2.

## Features

- **Rule switches** — each Firewalla rule becomes an HA switch (toggle pause/resume)
- **Group internet switches** — per-group "Internet Access" switch (ON = internet allowed, OFF = blocked), mirroring the Firewalla app's Controls panel
- **Per-group rule switches** — category/app block rules per group (e.g., "Matt Block Porn", "Harvey Block TikTok")
- **Time limit sensors** — per-user app time limits showing remaining minutes, with quota/used/remaining/reached
- **User activity sensors** — binary sensors detecting active internet usage per user (with 5-minute cooldown to prevent flapping)
- **Rules summary sensor** — overview of total/active/paused rules with breakdown by type
- **Dynamic entity lifecycle** — entities auto-add/remove when Firewalla rules or groups change, no reload needed
- **Optimistic state updates** — UI reflects toggles immediately, confirmed on next poll
- **Configurable polling intervals** — tune API call frequency to balance freshness vs. rate limits
- **Split-polling optimization** — time limit rules (which change frequently) are polled every 30s; full rules refresh happens at a configurable interval (default 3 min), reducing API bandwidth by ~85%

## Prerequisites

- Firewalla device (Gold, Gold SE, Purple, Purple SE, Blue, Red)
- Firewalla MSP account with API access enabled
- Personal Access Token from MSP settings
- Home Assistant 2024.1+

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

### Options (Settings > Integrations > Firewalla > Configure)

After setup, configure these options:

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Include Filters | *(empty)* | — | Only show rules matching these filters (one per line, OR'd). Example: `status:active` |
| Exclude Filters | *(empty)* | — | Hide rules matching these filters (one per line). Example: `-target.type:category` |
| Full Rules Refresh | 180s | 30–900s | How often to fetch ALL rules. Between refreshes, only time limit rules are fetched (much smaller payload). |
| Devices Refresh | 60s | 30–600s | How often to refresh device data (used for activity detection). |
| Users Cache Duration | 600s | 60–3600s | How long to cache user/group name data (names rarely change). |

#### Filter Syntax

Filters use Firewalla's query syntax:

```
status:active           # Only active rules
action:block            # Only block rules
target.type:app         # Only app rules
target.type:category    # Only category rules
target.type:internet    # Only internet rules
```

## Entities

### Switches

| Entity Pattern | Description | UX |
|---------------|-------------|-----|
| `switch.firewalla_*` | Per-rule switch | ON = rule active, OFF = rule paused |
| `switch.firewalla_group_*_internet_access` | Group internet switch | **ON = internet allowed**, OFF = internet blocked (inverted from the underlying block rule) |
| `switch.firewalla_group_*_block_*` | Group rule switch | ON = block active, OFF = block paused |

### Sensors

| Entity Pattern | Description | State |
|---------------|-------------|-------|
| `sensor.firewalla_rules_summary` | Rules overview | Total rule count |
| `sensor.firewalla_timelimit_*` | Per-user app time limit | Minutes remaining |

### Binary Sensors

| Entity Pattern | Description | State |
|---------------|-------------|-------|
| `binary_sensor.firewalla_user_*_active` | User activity detection | ON = actively using internet |

### Entity Attributes

**Rule switches** expose:
- `rule_id`, `rule_type`, `target`, `target_name`, `action`, `status`
- `hit_count`, `last_hit` — how often the rule has been triggered
- `time_quota_minutes`, `time_used_minutes` — for time limit rules
- `schedule_display` — human-readable schedule (e.g., "weekdays at 22:00 for 1h")
- `scope_type`, `scope_value`, `direction`

**Time limit sensors** expose:
- `app`, `quota`, `used`, `remaining`, `reached`
- `schedule_display`, `hit_count`, `paused`

**Activity sensors** expose:
- `online_devices`, `total_devices`, `active_devices`
- `download_delta_bytes` — bytes downloaded since last poll

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Home Assistant                        │
│                                                       │
│  ┌────────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │  switch.py  │  │ sensor.py │  │ binary_sensor.py  │ │
│  │ RuleSwitch  │  │ Summary   │  │ UserActivity      │ │
│  │ GroupInternet│  │ TimeLimit │  │                   │ │
│  │ GroupRule   │  │           │  │                   │ │
│  └──────┬──────┘  └─────┬─────┘  └────────┬──────────┘ │
│         │               │                  │            │
│         └───────────────┼──────────────────┘            │
│                         │                               │
│              ┌──────────▼──────────┐                    │
│              │   coordinator.py     │                    │
│              │ DataUpdateCoordinator│                    │
│              │  + MSP API Client    │                    │
│              └──────────┬──────────┘                    │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │ HTTPS
              ┌───────────▼───────────┐
              │  Firewalla MSP API v2  ���
              │  /v2/rules             │
              │  /v2/devices           │
              │  /v2/users             │
              │  /v2/rules/{id}/pause  │
              │  /v2/rules/{id}/resume │
              └───────────────────────┘
```

### Polling Strategy (Split-Polling)

The coordinator uses a tiered polling strategy to minimize API calls while keeping time-sensitive data fresh:

| Data | Refresh Rate | Payload | Rationale |
|------|-------------|---------|-----------|
| Time limit rules | Every 30s (base poll) | ~5.5 KB (8 rules) | Minutes remaining change constantly |
| All rules | Configurable (default 3 min) | ~55 KB (100 rules) | Rule status changes are rare |
| Devices | Configurable (default 60s) | ~45 KB (176 devices) | Activity detection uses 5-min cooldown |
| Users | Configurable (default 10 min) | ~2 KB (6 users) | Names and group affiliations rarely change |

**Default daily API calls:** ~2,880 timelimit + ~480 full rules + ~1,440 devices + ~144 users = **~4,944 calls/day**
(vs. ~8,640 calls/day without optimization — **43% reduction**)

### Key Patterns

- **Data flow:** Coordinator polls API → processes rules/groups/users → platforms read from `coordinator.data`
- **Dynamic lifecycle:** Coordinator listener callbacks track known entity IDs; new entities are added, removed entities are cleaned from the entity registry
- **Optimistic updates:** Switch toggles update local state immediately via `async_write_ha_state()`, confirmed on next poll
- **Group name resolution:** `/v2/users` returns friendly names with `affiliatedTag` mapping UUID group names to user names (e.g., group "BFB913AE-..." → "Harvey")
- **Activity detection:** Tracks `totalDownload` deltas per group with 10 KB threshold and 5-minute cooldown to filter background noise

## Dashboard

A pre-built parental control dashboard template is included at `custom_components/firewalla/dashboard/firewalla_parental.yaml`.

### Prerequisites

Install the **auto-entities** custom card from HACS (HACS > Frontend > Search "auto-entities" > Install).

### Setup

1. Go to **Settings > Dashboards > Add Dashboard**
2. Choose "New dashboard from scratch", name it "Firewalla"
3. Open the dashboard, click the 3-dots menu > **Edit Dashboard**
4. Click the 3-dots menu again > **Raw Configuration Editor**
5. Paste the contents of `firewalla_parental.yaml` and save

The dashboard auto-discovers all Firewalla user groups and their entities using regex patterns. When you add a new child on Firewalla, their card appears automatically after the next coordinator poll.

## Troubleshooting

### "Failed to pause/resume rule" errors

- Check that your Personal Access Token has write permissions in MSP settings
- Verify the Firewalla box is online and reachable

### Entities not appearing

- Check **Settings > Devices & Services > Firewalla** for error messages
- Enable debug logging: add `custom_components.firewalla: debug` to your `configuration.yaml` logger

### Rate limiting (HTTP 429)

- Increase the polling intervals in the integration options
- The integration automatically retries with exponential backoff (1s, 2s, 4s, 8s)

### Activity sensors showing false positives

- Activity detection uses a 10 KB threshold and 5-minute cooldown
- Background keep-alive traffic from devices can cause brief false positives
- Devices polling at 60s intervals means activity detection has ~60s granularity

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

## License

This project is licensed under the MIT License.
