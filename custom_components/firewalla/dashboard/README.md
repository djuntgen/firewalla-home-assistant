# Firewalla Parental Control Dashboard

A pre-built Home Assistant dashboard for managing Firewalla parental controls.
It auto-discovers all user groups (children) and displays their activity status,
time limits, internet access toggles, and content block switches.

## Prerequisites

- The **Firewalla** custom integration installed and configured
- The [**auto-entities**](https://github.com/thomasloven/lovelace-auto-entities)
  custom card installed via HACS

## Installation

1. Install `auto-entities` from HACS (Frontend > search "auto-entities").
2. In Home Assistant go to **Settings > Dashboards > Add Dashboard**.
3. Choose **New dashboard from scratch** and name it (e.g. "Firewalla").
4. Open the new dashboard, click the three-dot menu > **Edit Dashboard**.
5. Click the three-dot menu again > **Raw Configuration Editor**.
6. Paste the contents of `firewalla_parental.yaml` and save.

## What You Get

| Section          | Entity pattern                              | Description                              |
|------------------|---------------------------------------------|------------------------------------------|
| Activity         | `binary_sensor.firewalla_user_*_active`     | Online/offline status per child          |
| Internet Access  | `switch.firewalla_group_*_internet`         | Toggle internet on/off per child         |
| Time Limits      | `sensor.firewalla_timelimit_*`              | Remaining minutes per app per child      |
| Content Blocks   | `switch.firewalla_group_*_rule_*`           | Category/app block toggles per child     |

All sections update dynamically. When a new child is added in Firewalla, their
entities appear on the dashboard after the next poll cycle (~30 seconds).
