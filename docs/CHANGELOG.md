# Changelog

## v1.1.0 (2026-04-04)

### New Features

- **Groups and parental controls**
  - Per-group "Internet Access" switch (ON = allowed, OFF = blocked)
  - Per-group rule switches for category/app blocks (e.g., "Matt Block Porn", "Harvey Block TikTok")
  - Per-user time limit sensors showing remaining minutes for each app
  - User activity binary sensors with 5-minute cooldown and 10 KB threshold
  - Each group becomes its own HA device, organized under the main Firewalla box

- **Dynamic entity lifecycle**
  - Entities auto-add when new rules/groups appear on Firewalla
  - Entities auto-remove from HA entity registry when rules/groups are deleted
  - No integration reload needed

- **Optimistic state updates**
  - Switch toggles reflect immediately in the UI
  - Confirmed on next poll cycle

- **Enriched rule data**
  - `hit_count` and `last_hit` for rule trigger tracking
  - `time_quota_minutes` and `time_used_minutes` for time limit rules
  - `schedule_display` — human-readable schedule (e.g., "weekdays at 22:00 for 1h")
  - `scope_type`, `scope_value`, `direction` attributes

- **Action-aware naming**
  - Allow rules say "Allow", time limit rules say "Limit"
  - Block rules say "Block" (default)

- **Configurable polling intervals**
  - Full rules refresh interval (default 180s, range 30-900s)
  - Devices refresh interval (default 60s, range 30-600s)
  - Users cache TTL (default 600s, range 60-3600s)
  - Configured via Settings > Integrations > Firewalla > Configure

- **Split-polling optimization**
  - Time limit rules fetched every 30s (~5.5 KB payload)
  - Full rules fetched at configurable interval (~55 KB payload)
  - ~85% bandwidth reduction on the rules endpoint
  - Overall ~43% reduction in daily API calls

- **Modern HA patterns**
  - `has_entity_name`, `DeviceInfo` dataclass
  - `_unrecorded_attributes` for static metadata
  - `EntityCategory.DIAGNOSTIC` for summary sensor

- **Parental control dashboard template**
  - Pre-built Lovelace dashboard using auto-entities
  - Auto-discovers all user groups and their entities

### Bug Fixes

- Fixed `unpause` → `resume` API endpoint (Firewalla uses POST `/v2/rules/{id}/resume`)
- Fixed closure bug in switch dynamic entity lifecycle (`set -=` → `set.difference_update()`)
- Fixed duplicate internet block entities per group (filter by type, not single rule ID)
- Completed RULE_TYPES (added intranet, targetlist, region, ip) and RULE_ACTIONS (added timelimit)

## v1.0.0 (2026-04-03)

### Initial Release

- Rule discovery from Firewalla MSP API v2
- Per-rule switch entities (pause/resume)
- Rules summary sensor
- Two-step config flow (MSP credentials + box selection)
- Include/exclude rule filters
- Retry with exponential backoff
- Rate limit (429) handling
