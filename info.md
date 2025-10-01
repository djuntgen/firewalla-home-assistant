# Firewalla Rule Management Integration

Control your existing Firewalla firewall rules directly from Home Assistant using the MSP API.

## Features

### Automatic Rule Discovery
- **Rule Detection**: Automatically discovers all existing Firewalla rules
- **Dynamic Updates**: Automatically adds new rules and removes deleted ones
- **Real-time Sync**: Keeps Home Assistant entities synchronized with Firewalla

### Rule Control
- **Pause/Unpause Rules**: Turn switches ON to activate rules, OFF to pause them
- **Rule Preservation**: Paused rules retain all configuration for easy re-activation
- **Instant Control**: Immediate rule state changes through Home Assistant

### Rich Information
- **Rule Metadata**: View rule type, target, description, priority, and schedule
- **Rule Statistics**: Monitor total, active, and paused rule counts
- **Integration Health**: Monitor API connectivity and synchronization status

### Smart Features
- **MSP API Integration**: Full integration with Firewalla's MSP API v2
- **Error Recovery**: Robust error handling with automatic retry logic
- **Rate Limiting**: Respects API limits with intelligent caching and batching

## Entity Types

### Switches (Rule Control)
- **Rule Switches**: One switch per discovered Firewalla rule
- **Descriptive Names**: Uses rule descriptions or rule type and target
- **Rich Attributes**: Complete rule metadata as entity attributes

### Sensors
- **Rules Summary**: Total rule count with detailed statistics
- **Integration Health**: API connectivity and synchronization status

## Requirements

- Firewalla MSP (Managed Service Provider) account
- Personal Access Token from MSP account
- Existing Firewalla rules to manage
- Firewalla box accessible via MSP API

## Installation

1. Install via HACS or manually
2. Add integration in Home Assistant
3. Enter MSP domain and access token
4. Select your Firewalla box (if multiple)
5. Wait for rule discovery to complete

## Configuration

The integration uses a configuration flow to set up:
- MSP Domain (e.g., mydomain.firewalla.net or https://mydomain.firewalla.net)
- Personal Access Token
- Box selection from discovered boxes
- Automatic rule discovery and entity creation

## Use Cases

- **Parental Controls**: Pause/unpause internet restrictions for kids
- **Work Hours**: Activate productivity rules during work hours
- **Gaming Management**: Control gaming access based on schedules
- **Automation Integration**: Include rule control in complex automations

## Support

For issues and support, visit the [GitHub repository](https://github.com/djuntgen/firewalla-home-assistant).