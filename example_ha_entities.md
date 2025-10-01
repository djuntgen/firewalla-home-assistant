# Home Assistant Entities Created by Firewalla Integration

Based on the real API test with 83 rules, here are examples of the entities that will be created:

## Switch Entities (Rule Controls)

Each Firewalla rule becomes a switch entity that can be toggled to pause/unpause the rule.

### Example 1: YouTube App Block
```yaml
Entity ID: switch.firewalla_rule_youtube
Name: "Block Youtube"
State: ON (rule is active)
Device: Firewalla Box 2cd09491

Attributes:
  rule_id: "acdcdb72-ced6-40cf-8ce4-50ac6d376dbe"
  rule_type: "app"
  rule_value: "youtube"
  target: "youtube"
  action: "block"
  priority: 0
  dns_only: true
  direction: "bidirection"
  scope_type: "group"
  scope_value: "36"
  created_at: "2025-06-28T15:32:49.422000"
  modified_at: "2025-01-10T15:13:42.034000"
  rule_type_display: "Application Block"
  rule_status: "active"
  rule_disabled: false
  rule_paused: false
  hit_count: 8147
  last_hit: "2025-01-10T13:31:53.000000"
```

### Example 2: Internet Access Schedule
```yaml
Entity ID: switch.firewalla_rule_internet_access
Name: "Block Internet Access"
State: ON (rule is active)
Device: Firewalla Box 2cd09491

Attributes:
  rule_id: "844a31a7-7ccd-4096-a610-9fb56b110edc"
  rule_type: "internet"
  rule_value: ""
  target: ""
  action: "block"
  priority: 0
  direction: "bidirection"
  scope_type: "group"
  scope_value: "36"
  schedule:
    cronTime: "0 19 * * 0,1,2,3,4"
    duration: 7200
  created_at: "2025-01-10T17:03:37.753000"
  modified_at: "2025-01-10T17:04:08.309000"
  rule_type_display: "Internet Access"
  rule_status: "active"
  rule_disabled: false
  rule_paused: false
  hit_count: 94714
  last_hit: "2025-01-10T19:13:19.570000"
```

### Example 3: Category Block (Paused)
```yaml
Entity ID: switch.firewalla_rule_av_category
Name: "Block Av Category"
State: OFF (rule is paused)
Device: Firewalla Box 2cd09491

Attributes:
  rule_id: "0314a387-2bc4-4bae-a69f-d81f19500c65"
  rule_type: "category"
  rule_value: "av"
  target: "av"
  action: "block"
  priority: 0
  dns_only: true
  direction: "bidirection"
  scope_type: "device"
  scope_value: "FC:34:97:A5:9F:91"
  created_at: "2025-01-09T17:25:28.736000"
  modified_at: "2025-01-10T14:52:01.724000"
  rule_type_display: "Category Block"
  rule_status: "paused"
  rule_disabled: false
  rule_paused: true
  hit_count: 182
  last_hit: "2025-01-10T13:12:23.000000"
```

### Example 4: Domain Block with Custom Description
```yaml
Entity ID: switch.firewalla_rule_don_t_let_this_device_talk_to_nintendo_i
Name: "Don't let this device talk to Nintendo, its hacked."
State: ON (rule is active)
Device: Firewalla Box 2cd09491

Attributes:
  rule_id: "da599cd4-f01b-4325-bb8f-151e57aa35b1"
  rule_type: "domain"
  rule_value: "nintendo.net"
  target: "nintendo.net"
  action: "block"
  priority: 0
  dns_only: true
  direction: "bidirection"
  scope_type: "device"
  scope_value: "5C:52:1E:65:0B:8D"
  description: "Don't let this device talk to Nintendo, its hacked."
  created_at: "2025-08-10T15:31:41.319000"
  modified_at: "2025-08-10T17:10:23.536000"
  rule_type_display: "Domain Block"
  rule_status: "active"
  rule_disabled: false
  rule_paused: false
  hit_count: 123
  last_hit: "2025-08-10T17:42:15.930000"
```

### Example 5: IP Allow Rule
```yaml
Entity ID: switch.firewalla_rule_192_168_1_65
Name: "Block 192.168.1.65"
State: ON (rule is active)
Device: Firewalla Box 2cd09491

Attributes:
  rule_id: "1234fc2e-1497-423f-9301-fecc4d18c35b"
  rule_type: "ip"
  rule_value: "192.168.1.65"
  target: "192.168.1.65"
  action: "allow"
  priority: 0
  direction: "outbound"
  scope_type: "device"
  scope_value: "BC:24:11:19:23:DE"
  created_at: "2025-08-11T11:55:11.206000"
  modified_at: "2025-08-11T11:56:04.676000"
  rule_type_display: "IP Address"
  rule_status: "active"
  rule_disabled: false
  rule_paused: false
  hit_count: 249
  last_hit: "2025-08-11T21:30:07.541000"
```

## Sensor Entity (Rules Summary)

One sensor entity provides overall statistics:

```yaml
Entity ID: sensor.firewalla_rules_summary
Name: "Firewalla Rules Summary"
State: 83 (total number of rules)
Device: Firewalla Box 2cd09491

Attributes:
  total_rules: 83
  active_rules: 72
  paused_rules: 11
  rules_by_type:
    internet: 6
    app: 13
    category: 34
    intranet: 18
    ip: 8
    domain: 4
  last_updated: "2025-01-10T19:15:00.000000"
  api_status: "connected"
```

## Device Information

All entities are grouped under a single Firewalla device:

```yaml
Device:
  Name: "Firewalla Box 2cd09491"
  Manufacturer: "Firewalla"
  Model: "Firewalla Unknown"
  Identifiers: ["firewalla", "2cd09491-7385-479b-899e-51dd5c731b10"]
  Entities: 84 (83 switches + 1 sensor)
```

## Entity Behavior

### Switch States:
- **ON**: Rule is active (not paused) - blocking/allowing traffic as configured
- **OFF**: Rule is paused - temporarily disabled but configuration preserved

### Actions:
- **Turn ON**: Unpause the rule (activate it)
- **Turn OFF**: Pause the rule (temporarily disable it)

### Attributes Include:
- Rule metadata (type, target, action, priority)
- Timestamps (created, modified, last hit)
- Hit statistics (how many times rule was triggered)
- Scope information (which devices/groups the rule applies to)
- Schedule information (for time-based rules)
- Custom descriptions/notes

## 🔧 **Rule Filtering (New Feature!)**

You can now configure which rules appear in Home Assistant using Firewalla's query syntax:

### **Configuration Options:**
- **Include Filters**: Only show rules matching these criteria
- **Exclude Filters**: Hide rules matching these criteria  

### **Example Filter Configurations:**

**Show only active app blocking rules:**
```
Include Filters:
status:active
action:block
target.type:app
```
*Result: 13 app rules → 8 active blocking app rules*

**Hide paused and allow rules:**
```
Exclude Filters:
-status:paused
-action:allow
```
*Result: 83 rules → 60 rules (only active block rules)*

**Show only rules for specific device:**
```
Include Filters:
device.id:"FC:34:97:A5:9F:91"
```

### **Available Filter Types:**
- **Status**: `status:active`, `status:paused`
- **Action**: `action:block`, `action:allow`
- **Type**: `target.type:app`, `target.type:category`, `target.type:internet`
- **Device**: `device.id:"MAC:ADDRESS"`, `device.name:*iphone*`

### **Filter Results from Your 83 Rules:**
- All Rules: 83
- Active Only: 71 rules
- Block Only: 60 rules  
- App Rules: 13 rules
- Category Rules: 34 rules
- Internet Rules: 6 rules

## Total Entities Created:
- **Variable entities** (depends on filters, up to 84 total)
- **83 rule switches + 1 summary sensor** (without filters)
- All grouped under **1 Firewalla device**
- Real-time status updates every 30+ seconds
- Full pause/unpause control through Home Assistant UI
- **Configurable rule filtering** to show only what you need