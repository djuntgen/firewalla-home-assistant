
---
inclusion: always
---

# Home Assistant Firewalla Integration Development Guide

## Project Context
Custom Home Assistant integration for Firewalla firewall devices. Provides device control (blocking/pausing) and status monitoring via Firewalla MSP API.

## Critical References
- **Firewalla MSP API Examples**: https://github.com/firewalla/msp-api-examples
- **Firewalla API Documentation**: https://dn-k6y7bj.firewalla.net/api/docs/
- **Home Assistant Integration Guide**: https://developers.home-assistant.io/docs/creating_component_index/

## Required File Structure
```
custom_components/firewalla/
├── __init__.py          # Integration setup, coordinator initialization
├── config_flow.py       # User configuration flow with validation
├── const.py            # Constants, domain, API endpoints
├── coordinator.py      # DataUpdateCoordinator + FirewallaAPI class
├── switch.py           # Block/pause switch entities
├── sensor.py           # Status monitoring sensors
└── manifest.json       # Integration metadata
```

## Code Standards

### Async Requirements
- ALL API calls MUST use `async`/`await`
- Use `aiohttp.ClientSession` with `aiohttp.ClientTimeout(total=30)`
- Follow MSP API examples for authentication patterns

### Error Handling Pattern
```python
try:
    response = await self._api_call()
except aiohttp.ClientError as err:
    _LOGGER.error("API connection failed: %s", err)
    raise HomeAssistantError(f"Cannot connect to Firewalla: {err}")
except Exception as err:
    _LOGGER.exception("Unexpected error: %s", err)
    raise
```

### Logging Standards
- Use `_LOGGER = logging.getLogger(__name__)` in each file
- Debug: API requests/responses
- Info: Entity state changes
- Error: Connection/authentication failures

## Architecture Requirements

### DataUpdateCoordinator
- Inherit from `DataUpdateCoordinator`
- Update intervals: 30+ seconds minimum
- Handle authentication refresh automatically
- Cache API responses

### Entity Implementation
- Inherit from `CoordinatorEntity` + base class (`SwitchEntity`, `SensorEntity`)
- Unique ID format: `firewalla_{mac_address}_{entity_type}`
- Device info: manufacturer="Firewalla", include model and sw_version

### API Client
- Implement `FirewallaAPI` class in `coordinator.py`
- Handle session management and rate limiting
- Return structured data, not raw API responses

## Firewalla API Patterns

### Authentication
- Use MSP API credentials pattern from examples
- Implement automatic token refresh
- Store session state in coordinator

### Rate Limiting
- Exponential backoff: 1s, 2s, 4s, 8s
- Max 10 requests/minute per device
- Cache responses for 30+ seconds

### Entity Naming Convention
- Switches: `firewalla_block_{device_name}`, `firewalla_gaming_{device_name}`
- Sensors: `firewalla_{device_name}_status`, `firewalla_rules_count`
- Use MAC addresses for unique IDs
- Sanitize names: lowercase, underscores only

## Configuration Flow Requirements
- Validate Firewalla host during setup
- Test API connectivity before completion
- Support both IP addresses and hostnames
- Provide clear error messages for common failures
- Store minimal configuration (host, credentials only)