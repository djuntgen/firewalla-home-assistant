# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration (`custom_components/firewalla`) for managing Firewalla firewall rules via the MSP (Managed Service Provider) API v2. Users authenticate with an MSP domain + personal access token, select a Firewalla box, and get switch entities for each rule (pause/unpause) plus a summary sensor.

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
```

No build step — this is a pure Python HA integration installed by copying `custom_components/firewalla/` into a Home Assistant instance.

## Architecture

All integration code lives under `custom_components/firewalla/`:

- **`coordinator.py`** — Contains two classes:
  - `FirewallaMSPClient` — Low-level HTTP client for the MSP API v2 (`/v2/rules`, `/v2/rules/{id}/pause`, `/v2/rules/{id}/unpause`). Handles auth headers, retries with exponential backoff, rate-limit (429) handling.
  - `FirewallaDataUpdateCoordinator` — HA `DataUpdateCoordinator` subclass that polls every 30s. Owns the MSP client, applies include/exclude rule filters, detects rule additions/removals/modifications between polls, and calculates statistics. This is the central data hub — platforms read from `coordinator.data`.
- **`switch.py`** — `FirewallaRuleSwitch` (one per discovered rule). `is_on` = rule active (not paused). `turn_on` calls `coordinator.async_unpause_rule()`, `turn_off` calls `coordinator.async_pause_rule()`. Entity names are auto-generated from rule description/type/target.
- **`sensor.py`** — `FirewallaRulesSensor` — single sensor whose state is total rule count, with attributes for active/paused counts, rules-by-type breakdown, box info, and API status.
- **`config_flow.py`** — Two-step setup: MSP credentials → box selection (skipped if only one box). Also has `OptionsFlowHandler` for configuring include/exclude rule filters post-setup.
- **`__init__.py`** — `async_setup_entry` wires up the coordinator and forwards to switch+sensor platforms. Handles reload via options update listener.
- **`const.py`** — All constants: API endpoints, timeouts (30s API, 30s poll interval, 3 retries), config keys, rule type mappings, error messages.

## Key Patterns

- The coordinator stores processed data as `{"rules": {rule_id: {...}}, "rule_count": {...}, "rule_changes": {...}, "box_info": {...}}`. Platforms access rules via `coordinator.data["rules"][rule_id]`.
- Rule filters use Firewalla's query syntax (e.g., `status:active`, `target.type:app`). Include filters are OR'd (union), exclude filters remove from the result set.
- Auth uses `Token {token}` header format, not Bearer.
- Tests use `pytest-asyncio` with `asyncio_mode = auto` and `pytest-homeassistant-custom-component` for HA test fixtures.
