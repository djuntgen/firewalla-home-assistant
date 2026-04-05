# Changelog

## v1.1.0 (2026-04-05)

### New Features

- **Groups and parental controls**
  - Per-group internet control switch, named dynamically from API (`action` + `target.type`)
  - Per-group rule switches for category/app blocks, named from API data
  - Per-user time limit sensors for app-specific limits (YouTube, Facebook, etc.)
  - Internet time limit detection — captures group-scoped block rules with `timeUsage` data
  - `usage_percent` attribute on time limit sensors (capped at 100%)
  - Each group becomes its own HA device, named from the Firewalla user name

- **Per-kid bandwidth sensors**
  - 24h download and upload in GB per user group
  - Attributes: bytes, MB values

- **Per-device online sensors**
  - Binary sensor for each device in user groups
  - Attributes: IP, MAC vendor, network, last seen, IP reserved, 24h bandwidth

- **User activity detection**
  - Binary sensor with 10 KB threshold and 5-minute cooldown
  - Prevents flapping from background keep-alive traffic

- **Dynamic entity naming**
  - All entity names derived from Firewalla API data
  - No hardcoded English strings — users override via HA friendly_name
  - Device names use group/user name directly (no "Firewalla Group:" prefix)

- **Split-polling optimization**
  - Time limit rules fetched every 30s (~5.5 KB payload)
  - Full rules fetched at configurable interval (~55 KB payload)
  - ~85% bandwidth reduction on the rules endpoint

- **Configurable polling intervals**
  - Full rules refresh interval (default 180s, range 30-900s)
  - Devices refresh interval (default 60s, range 30-600s)
  - Users cache TTL (default 600s, range 60-3600s)
  - Configured via Settings > Integrations > Firewalla > Configure

- **Reconfigure flow**
  - Update MSP domain and access token without deleting the integration
  - Settings > Integrations > Firewalla > 3-dot menu > Reconfigure

- **HA 2026.4 compatibility**
  - `config_entry` passed to `DataUpdateCoordinator` (required by newer HA)
  - `OptionsFlow` updated for read-only `config_entry` property

- **Complete API target types**
  - Added `net` (Network CIDR), `remotePort` (Remote Port) to type mappings
  - `resumeTs` (auto-resume timestamp) surfaced in rule switch attributes

- **Dynamic entity lifecycle**
  - Entities auto-add/remove when Firewalla rules, groups, or devices change
  - No reload needed

- **Optimistic state updates**
  - UI reflects toggles immediately, confirmed on next poll

- **Enriched rule data**
  - `hit_count`, `last_hit`, `time_quota_minutes`, `time_used_minutes`
  - `schedule_display` — human-readable schedule
  - `scope_type`, `scope_value`, `direction`, `resumeTs`

- **Parental control dashboard**
  - Per-kid columns with activity, internet, bandwidth, time limits, devices, blocks
  - Uses tile cards, entity-progress-card, and auto-entities
  - Time limit progress bars with color thresholds (green/orange/red)

### Bug Fixes

- Fixed `unpause` to `resume` API endpoint (Firewalla uses POST `/v2/rules/{id}/resume`)
- Fixed closure bug in switch dynamic entity lifecycle (`set -=` to `set.difference_update()`)
- Fixed duplicate internet block entities per group (filter by type, not single rule ID)
- Fixed entity name slug drift ("Time Left" to "Time" to prevent HA regenerating entity IDs)
- Fixed `OptionsFlow.__init__` for HA 2026.4 (read-only `config_entry` property)
- Fixed `DataUpdateCoordinator` missing `config_entry` parameter for HA 2026.4
- Capped `usage_percent` at 100 (used can exceed quota after limit reached)

## v1.0.0 (2026-04-03)

### Initial Release

- Rule discovery from Firewalla MSP API v2
- Per-rule switch entities (pause/resume)
- Rules summary sensor
- Two-step config flow (MSP credentials + box selection)
- Include/exclude rule filters
- Retry with exponential backoff
- Rate limit (429) handling
