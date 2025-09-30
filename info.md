# Firewalla Integration for Home Assistant

Control your Firewalla firewall devices directly from Home Assistant using the MSP API.

## Features

### Device Control
- **Internet Blocking**: Block/unblock internet access for individual devices
- **Gaming Management**: Pause/resume gaming for gaming-capable devices
- **Rule Preservation**: Paused rules are preserved for easy re-activation

### Monitoring
- **Device Status**: Monitor online/offline status of all managed devices
- **Rules Tracking**: Track active integration-managed rules
- **Rich Attributes**: Access detailed device information

### Smart Features
- **Automatic Discovery**: Discover and select from available Firewalla devices
- **Gaming Device Detection**: Automatically identifies gaming consoles
- **Error Recovery**: Robust error handling with automatic retry logic
- **Rate Limiting**: Respects API limits with intelligent caching

## Entity Types

### Switches
- **Block Switches**: Control internet access for devices
- **Gaming Switches**: Control gaming access for gaming devices

### Sensors
- **Device Status**: Online/offline status for each device
- **Rules Count**: Number of active integration rules

## Requirements

- Firewalla MSP (Managed Service Provider) account
- Personal Access Token from MSP account
- Firewalla device accessible via MSP API

## Installation

1. Install via HACS or manually
2. Add integration in Home Assistant
3. Enter MSP API credentials
4. Select your Firewalla device
5. Complete setup

## Configuration

The integration uses a configuration flow to set up:
- MSP API URL (default: https://firewalla.encipher.io)
- Personal Access Token
- Device selection from discovered devices
- Integration name

## Support

For issues and support, visit the [GitHub repository](https://github.com/custom-components/firewalla).