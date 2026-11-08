# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration (`custom_components/firewalla`) for managing Firewalla firewall rules via the MSP (Managed Service Provider) API v2. Users authenticate with an MSP domain + personal access token, select a Firewalla box, and get switch entities for each rule (pause/resume) and group, plus group, device and box sensors and a rules summary sensor.

## Commands

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
python run_tests.py
# or directly:
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/test_coordinator.py -v

# Run tests matching a pattern
python run_tests.py "test_pattern_name"
# or:
pytest tests/ -k "test_pattern_name" -v

# Live Firewalla API tests are skipped unless opted in (credentials from env only;
# FIREWALLA_REAL_API_WRITE=1 additionally allows pausing/resuming a live rule):
FIREWALLA_REAL_API=1 FIREWALLA_MSP_DOMAIN=... FIREWALLA_ACCESS_TOKEN=... pytest tests/test_real_api.py -v
```

No build step — this is a pure Python HA integration installed by copying `custom_components/firewalla/` into a Home Assistant instance.

## Architecture

All integration code lives under `custom_components/firewalla/`:

- **`coordinator.py`** — Contains two classes:
  - `FirewallaMSPClient` — Low-level HTTP client for the MSP API v2 (`/v2/rules`, `/v2/rules/{id}/pause`, `/v2/rules/{id}/resume`, `/v2/devices`, `/v2/users`, `/v2/boxes`, `/v2/trends/flows`). Handles auth headers, retries with exponential backoff, rate-limit (429) handling; `quiet=True` makes a single attempt for optional calls.
  - `FirewallaDataUpdateCoordinator` — HA `DataUpdateCoordinator` subclass with a base poll of 45s (configurable). Split polling: time-limit rules every poll; full rules, devices (and box status) and users at their own configurable intervals; flow trends at most every 15 min. Owns the MSP client, applies include/exclude rule filters, detects rule additions/removals/modifications between polls, and calculates statistics. This is the central data hub — platforms read from `coordinator.data`.
- **`switch.py`** — `FirewallaRuleSwitch` (one per rule not handled by a group switch). `is_on` = rule active (not paused). `turn_on` calls `coordinator.async_resume_rule()`, `turn_off` calls `coordinator.async_pause_rule()`. Entity names are auto-generated from rule description/type/target. Also `FirewallaGroupInternetSwitch` (a group's internet block rule) and `FirewallaGroupRuleSwitch` (a group's other rules, including user-scoped App Controls).
- **`sensor.py`** — `FirewallaRulesSensor` (total rule count, with active/paused counts and rules-by-type), `FirewallaTimeLimitSensor` (per-user time limits), `FirewallaBandwidthSensor` (24h download/upload per group), and the box status sensors (`FirewallaBoxStatSensor`, `FirewallaFirmwareSensor`, `FirewallaBlockedFlowsSensor`).
- **`binary_sensor.py`** — `FirewallaUserActivitySensor` (per group, user or device group), `FirewallaDeviceOnlineSensor` (per device), `FirewallaBoxOnlineSensor`.
- **`button.py`** — `FirewallaRefreshButton` (full refresh on demand).
- **`config_flow.py`** — Two-step setup: MSP credentials → box selection (skipped if only one box). Also has `OptionsFlowHandler` for include/exclude rule filters, polling intervals and dashboard users.
- **`__init__.py`** — `async_setup_entry` wires up the coordinator, forwards to the switch, sensor, binary_sensor and button platforms, and generates the parental-control dashboard when dashboard users are configured. Handles reload via options update listener.
- **`const.py`** — All constants: API endpoints, timeouts (30s API, 45s default base poll, 3 retries), config keys, rule type mappings, error messages.

## Key Patterns

- The coordinator stores processed data as `{"rules": {rule_id: {...}}, "rule_count": {...}, "rule_changes": {...}, "box_info": {...}, "groups": {...}, "time_limits": {...}, "box_stats": {...} | None}`. Platforms access rules via `coordinator.data["rules"][rule_id]`.
- Rule filters use Firewalla's query syntax (e.g., `status:active`, `target.type:app`). Include filters are OR'd (union), exclude filters remove from the result set.
- Auth uses `Token {token}` header format, not Bearer.
- Tests use `pytest-asyncio` with `asyncio_mode = auto` and `pytest-homeassistant-custom-component` for HA test fixtures.
