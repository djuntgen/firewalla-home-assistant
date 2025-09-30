# Firewalla Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/custom-components/firewalla.svg)](https://github.com/custom-components/firewalla/releases)
[![License](https://img.shields.io/github/license/custom-components/firewalla.svg)](LICENSE)

A comprehensive Home Assistant integration for Firewalla firewall devices using the MSP (Managed Service Provider) API. Control device internet access, manage gaming pause rules, and monitor device status directly from Home Assistant.

## Features

### 🛡️ Internet Blocking Controls
- **Device Blocking Switches**: Block/unblock internet access for individual devices
- **Rule Preservation**: Paused rules are preserved for easy re-activation
- **Real-time Status**: Immediate feedback on rule activation status

### 🎮 Gaming Management
- **Gaming Pause Switches**: Temporarily pause gaming for gaming-capable devices
- **Smart Device Detection**: Automatically identifies gaming consoles and devices
- **Flexible Control**: Pause and resume gaming access as needed

### 📊 Device Monitoring
- **Device Status Sensors**: Monitor online/offline status of all managed devices
- **Rich Attributes**: Access device information including IP, MAC, hostname, and device class
- **Rules Count Sensor**: Track active integration-managed rules

### 🔧 Advanced Features
- **MSP API Integration**: Full integration with Firewalla's MSP API
- **Automatic Discovery**: Discover and select from available Firewalla devices
- **Error Recovery**: Robust error handling with automatic retry logic
- **Rate Limiting**: Respects API rate limits with intelligent caching

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/custom-components/firewalla`
6. Select "Integration" as the category
7. Click "Add"
8. Find "Firewalla" in the integration list and install it
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/custom-components/firewalla/releases)
2. Extract the `custom_components/firewalla` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Prerequisites

1. **Firewalla MSP Account**: You need access to Firewalla's MSP (Managed Service Provider) API
2. **Personal Access Token**: Generate a personal access token from your MSP account
3. **MSP API URL**: Usually `https://firewalla.encipher.io` (default)

### Setup Steps

1. Go to **Configuration** → **Integrations** in Home Assistant
2. Click **Add Integration** and search for "Firewalla"
3. Enter your MSP API credentials:
   - **MSP API URL**: Your Firewalla MSP API endpoint
   - **Personal Access Token**: Your MSP API token
4. Select your Firewalla device from the discovered devices
5. Choose a name for the integration instance
6. Complete the setup

### Configuration Options

| Field | Description | Required | Default |
|-------|-------------|----------|---------|
| MSP API URL | Firewalla MSP API endpoint | Yes | `https://firewalla.encipher.io` |
| Personal Access Token | Your MSP API access token | Yes | - |
| Firewalla Device | Select from discovered devices | Yes | - |
| Integration Name | Name for this integration instance | Yes | Auto-generated |

## Entities

### Switch Entities

#### Internet Blocking Switches
- **Entity ID**: `switch.firewalla_{device_name}_block`
- **Purpose**: Block/unblock internet access for specific devices
- **States**: 
  - `on`: Internet access is blocked
  - `off`: Internet access is allowed
- **Attributes**: Device MAC, IP, hostname, rule status, last updated

#### Gaming Pause Switches
- **Entity ID**: `switch.firewalla_{device_name}_gaming`
- **Purpose**: Pause/resume gaming for gaming-capable devices
- **States**:
  - `on`: Gaming is paused
  - `off`: Gaming is allowed
- **Attributes**: Device MAC, IP, hostname, rule status, gaming device class
- **Note**: Only created for devices identified as gaming-capable

### Sensor Entities

#### Device Status Sensors
- **Entity ID**: `sensor.firewalla_{device_name}_status`
- **Purpose**: Monitor device online/offline status
- **States**: `online`, `offline`, `unknown`
- **Attributes**: MAC address, IP address, hostname, device class, last seen timestamp

#### Rules Count Sensor
- **Entity ID**: `sensor.firewalla_rules_active`
- **Purpose**: Track active integration-managed rules
- **State**: Number of active rules
- **Attributes**: Total rules, rule types breakdown, last updated timestamp

## Usage Examples

### Automations

#### Block Device During Work Hours
```yaml
automation:
  - alias: "Block Gaming Device During Work Hours"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.firewalla_gaming_console_block
```

#### Gaming Time Limits
```yaml
automation:
  - alias: "Gaming Time Limit"
    trigger:
      - platform: time
        at: "21:00:00"  # 9 PM
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.firewalla_xbox_gaming
```

#### Device Status Notifications
```yaml
automation:
  - alias: "Notify When Device Goes Offline"
    trigger:
      - platform: state
        entity_id: sensor.firewalla_laptop_status
        to: "offline"
        for:
          minutes: 5
    action:
      - service: notify.mobile_app
        data:
          message: "Laptop has been offline for 5 minutes"
```

### Dashboard Cards

#### Device Control Card
```yaml
type: entities
title: Firewalla Device Control
entities:
  - switch.firewalla_laptop_block
  - switch.firewalla_gaming_console_block
  - switch.firewalla_gaming_console_gaming
  - sensor.firewalla_rules_active
```

#### Device Status Card
```yaml
type: glance
title: Device Status
entities:
  - sensor.firewalla_laptop_status
  - sensor.firewalla_phone_status
  - sensor.firewalla_gaming_console_status
```

## Troubleshooting

### Common Issues

#### Authentication Errors
- **Problem**: "Invalid MSP API credentials"
- **Solution**: Verify your personal access token is correct and has proper permissions

#### Connection Errors
- **Problem**: "Cannot connect to Firewalla MSP API"
- **Solutions**:
  - Check your MSP API URL
  - Verify network connectivity
  - Ensure firewall allows outbound HTTPS connections

#### No Devices Found
- **Problem**: "No Firewalla devices found in your MSP account"
- **Solution**: Ensure your MSP account has access to at least one Firewalla device

#### Entities Not Updating
- **Problem**: Entity states not reflecting current status
- **Solutions**:
  - Check Home Assistant logs for API errors
  - Verify Firewalla device is online and accessible
  - Try reloading the integration

### Debug Logging

Enable debug logging to troubleshoot issues:

```yaml
logger:
  default: warning
  logs:
    custom_components.firewalla: debug
```

### API Rate Limits

The integration respects Firewalla's API rate limits:
- Maximum 10 requests per minute per device
- Automatic retry with exponential backoff
- Intelligent caching to minimize API calls

## Development

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

### Running Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
python run_tests.py

# Run specific tests
pytest tests/test_coordinator.py -v
```

### Code Quality

The project maintains high code quality standards:
- Type hints throughout the codebase
- Comprehensive error handling
- Extensive test coverage
- Home Assistant coding standards compliance

## Support

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/custom-components/firewalla/issues)
- **Discussions**: [GitHub Discussions](https://github.com/custom-components/firewalla/discussions)
- **Home Assistant Community**: [Community Forum](https://community.home-assistant.io/)

### Reporting Bugs

When reporting bugs, please include:
- Home Assistant version
- Integration version
- Firewalla device model
- Relevant log entries
- Steps to reproduce

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Firewalla](https://firewalla.com/) for providing the MSP API
- [Home Assistant](https://www.home-assistant.io/) community for integration standards
- [HACS](https://hacs.xyz/) for custom component distribution

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and breaking changes.