# Firewalla Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/djuntgen/firewalla-home-assistant.svg)](https://github.com/djuntgen/firewalla-home-assistant/releases)
[![License](https://img.shields.io/github/license/djuntgen/firewalla-home-assistant.svg)](LICENSE)

A Home Assistant integration for Firewalla firewall devices that provides **rule management and control** through the MSP (Managed Service Provider) API. Automatically discover your existing Firewalla rules and control them (pause/unpause) directly from Home Assistant.

## Features

### 🛡️ Automatic Rule Discovery
- **Rule Detection**: Automatically discovers all existing Firewalla rules
- **Switch Entities**: Creates a switch entity for each controllable rule
- **Dynamic Updates**: Automatically adds new rules and removes deleted ones
- **Real-time Sync**: Keeps Home Assistant entities synchronized with Firewalla

### 🎛️ Rule Control
- **Pause/Unpause Rules**: Turn switches ON to activate rules, OFF to pause them
- **Rule Preservation**: Paused rules retain all configuration for easy re-activation
- **Instant Control**: Immediate rule state changes through Home Assistant
- **Bulk Management**: Control multiple rules through automations and scripts

### 📊 Rich Rule Information
- **Rule Metadata**: View rule type, target, description, priority, and schedule
- **Rule Statistics**: Monitor total, active, and paused rule counts
- **Rule History**: Track rule creation and modification timestamps
- **Integration Health**: Monitor API connectivity and rule synchronization status

### 🔧 Advanced Features
- **Rule Filtering**: Configure which rules appear in Home Assistant using Firewalla's query syntax
- **MSP API Integration**: Full integration with Firewalla's MSP API v2
- **Automatic Discovery**: Discover and select from available Firewalla boxes
- **Error Recovery**: Robust error handling with automatic retry logic
- **Rate Limiting**: Respects API rate limits with intelligent caching and batching

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/djuntgen/firewalla-home-assistant`
6. Select "Integration" as the category
7. Click "Add"
8. Find "Firewalla" in the integration list and install it
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/djuntgen/firewalla-home-assistant/releases)
2. Extract the `custom_components/firewalla` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Prerequisites

1. **Firewalla MSP Account**: You need access to Firewalla's MSP (Managed Service Provider) API
2. **Personal Access Token**: Generate a personal access token from your MSP account settings
3. **MSP Domain**: Your MSP domain (e.g., `mydomain.firewalla.net` or `https://mydomain.firewalla.net`)
4. **Existing Rules**: The integration manages existing Firewalla rules (it doesn't create new ones)

### Setup Steps

1. Go to **Configuration** → **Integrations** in Home Assistant
2. Click **Add Integration** and search for "Firewalla"
3. Enter your MSP credentials:
   - **MSP Domain**: Your Firewalla MSP domain (e.g., `mydomain.firewalla.net` or `https://mydomain.firewalla.net`)
   - **Personal Access Token**: Your MSP API access token
4. Select your Firewalla box (if you have multiple boxes)
5. (Optional) Configure rule filters to show only specific rules
6. Complete the setup and wait for rule discovery

### Configuration Options

| Field | Description | Required | Example |
|-------|-------------|----------|---------|
| MSP Domain | Firewalla MSP domain | Yes | `mydomain.firewalla.net` or `https://mydomain.firewalla.net` |
| Personal Access Token | Your MSP API access token | Yes | `msp_token_abc123...` |
| Firewalla Box | Select from discovered boxes | Yes | Auto-selected if only one |

## Rule Filtering

### Overview
Configure which Firewalla rules appear in Home Assistant using powerful filtering options. This allows you to show only the rules you need, reducing clutter and improving organization.

### Configuration
1. Go to **Configuration** → **Integrations**
2. Find your Firewalla integration and click **Configure**
3. Add include/exclude filters using Firewalla's query syntax
4. Save and the integration will reload with filtered rules

### Filter Examples

#### Include Filters (show only these)
- `status:active` - Show only active rules (71 of 83 rules)
- `target.type:app` - Show only app rules (13 rules: YouTube, Facebook, TikTok)
- `action:block` - Show only blocking rules (60 rules)
- `scope.value:"FC:34:97:A5:9F:91"` - Show rules for specific device (8 rules)

#### Exclude Filters (hide these)
- `-status:paused` - Hide paused rules (show 71 instead of 83)
- `-action:allow` - Hide allow rules (show 60 instead of 83)
- `-target.type:category` - Hide category rules (show 49 instead of 83)

#### Combined Examples
**Parent Dashboard**: Show only kids' device rules
```
Include: scope.value:"FC:34:97:A5:9F:91"
Result: 8 device-specific rules (av, social, facebook)
```

**IT Admin View**: Show only active security rules
```
Include: status:active, action:block
Result: 48 active blocking rules
```

**Home User**: Show only app controls
```
Include: target.type:app
Result: 13 app rules (YouTube, Facebook, TikTok, etc.)
```

### Available Filter Types
- **Status**: `status:active`, `status:paused`
- **Action**: `action:block`, `action:allow`
- **Type**: `target.type:app`, `target.type:category`, `target.type:internet`, `target.type:ip`, `target.type:domain`
- **Device**: `scope.value:"MAC:ADDRESS"`, `device.name:*iphone*`

## Entities

### Switch Entities (Rule Control)

#### Rule Control Switches
- **Entity ID**: `switch.firewalla_rule_{rule_name}` (e.g., `switch.firewalla_rule_youtube`, `switch.firewalla_rule_internet_access`)
- **Purpose**: Control individual Firewalla rules (pause/unpause)
- **States**: 
  - `on`: Rule is active (unpaused)
  - `off`: Rule is paused (temporarily disabled)
- **Naming**: Uses human-readable names based on rule description or rule type/target
- **Attributes**: 
  - `rule_id`: Firewalla rule identifier
  - `rule_type`: Type of rule (internet, category, domain, etc.)
  - `target`: Rule target (MAC address, category, domain, etc.)
  - `target_name`: Human-readable target name
  - `action`: Rule action (block, allow, etc.)
  - `priority`: Rule priority level
  - `schedule`: Rule schedule information (if applicable)
  - `created_at`: Rule creation timestamp
  - `modified_at`: Rule last modification timestamp
  - `description`: Rule description

### Sensor Entities

#### Rules Summary Sensor
- **Entity ID**: `sensor.firewalla_rules_summary`
- **Purpose**: Monitor overall rule statistics and integration health
- **State**: Total number of discovered rules
- **Attributes**: 
  - `total_rules`: Total number of discovered rules
  - `active_rules`: Number of active (unpaused) rules
  - `paused_rules`: Number of paused rules
  - `rules_by_type`: Breakdown of rules by type (internet, category, domain, etc.)
  - `last_updated`: Last successful rule discovery timestamp
  - `api_status`: Current API connectivity status
  - `box_name`: Firewalla box name
  - `box_model`: Firewalla box model
  - `box_online`: Firewalla box online status

## Usage Examples

### Automations

#### Activate Rules During Work Hours
```yaml
automation:
  - alias: "Activate Gaming Block During Work Hours"
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
          entity_id: switch.firewalla_rule_gaming_category
```

#### Pause Rules in the Evening
```yaml
automation:
  - alias: "Pause Internet Restrictions in Evening"
    trigger:
      - platform: time
        at: "18:00:00"  # 6 PM
    action:
      - service: switch.turn_off
        target:
          entity_id: 
            - switch.firewalla_rule_internet_access
            - switch.firewalla_rule_gaming_category
```

#### Rule Status Notifications
```yaml
automation:
  - alias: "Notify When Rules Change"
    trigger:
      - platform: state
        entity_id: sensor.firewalla_rules_summary
        attribute: active_rules
    action:
      - service: notify.mobile_app
        data:
          message: "Firewalla active rules changed to {{ trigger.to_state.attributes.active_rules }}"
```

#### Weekend Rule Management
```yaml
automation:
  - alias: "Weekend Rule Relaxation"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday:
          - sat
          - sun
    action:
      - service: switch.turn_off
        target:
          entity_id: 
            - switch.firewalla_rule_internet_access
            - switch.firewalla_rule_gaming_category
```

### Dashboard Cards

#### Rule Control Card
```yaml
type: entities
title: Firewalla Rule Control
entities:
  - switch.firewalla_rule_internet_access
  - switch.firewalla_rule_gaming_category
  - switch.firewalla_rule_social_category
  - switch.firewalla_rule_youtube
  - switch.firewalla_rule_facebook
  - sensor.firewalla_rules_summary
```

#### Rule Statistics Card
```yaml
type: glance
title: Rule Statistics
entities:
  - entity: sensor.firewalla_rules_summary
    name: Total Rules
  - entity: sensor.firewalla_rules_summary
    name: Active Rules
    attribute: active_rules
  - entity: sensor.firewalla_rules_summary
    name: Paused Rules
    attribute: paused_rules
```

#### Rule Management Card
```yaml
type: custom:auto-entities
card:
  type: entities
  title: All Firewalla Rules
filter:
  include:
    - entity_id: "switch.firewalla_rule_*"
  exclude: []
sort:
  method: name
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

#### No Boxes Found
- **Problem**: "No Firewalla boxes found in your MSP account"
- **Solution**: Ensure your MSP account has access to at least one Firewalla box

#### Rule Access Failed
- **Problem**: "Cannot access rules. Please check your MSP permissions"
- **Solution**: Verify your MSP account has permissions to view and manage rules

#### No Rules Discovered
- **Problem**: Integration sets up but no rule entities are created
- **Solutions**:
  - Ensure you have existing rules in your Firewalla configuration
  - Check that rules are not disabled or system-managed
  - Verify API permissions allow rule access

#### Entities Not Updating
- **Problem**: Rule entity states not reflecting current status
- **Solutions**:
  - Check Home Assistant logs for API errors
  - Verify Firewalla box is online and accessible
  - Try reloading the integration
  - Check if rules were modified outside of Home Assistant

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

- **Issues**: [GitHub Issues](https://github.com/djuntgen/firewalla-home-assistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/djuntgen/firewalla-home-assistant/discussions)
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