#!/usr/bin/env python3
"""Test coordinator with real API data structure."""
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_coordinator_processing():
    """Test coordinator rule processing with real API data."""
    print("🔧 Testing coordinator data processing with real API structure...")
    
    # Import our coordinator (without Home Assistant dependencies)
    try:
        from custom_components.firewalla.coordinator import FirewallaDataUpdateCoordinator
        print("✅ Successfully imported FirewallaDataUpdateCoordinator")
    except ImportError as e:
        print(f"❌ Failed to import coordinator: {e}")
        return False
    
    # Real API response structure (from the test output)
    real_api_response = {
        "results": [
            {
                "id": "844a31a7-7ccd-4096-a610-9fb56b110edc",
                "action": "block",
                "direction": "bidirection",
                "gid": "2cd09491-7385-479b-899e-51dd5c731b10",
                "status": "active",
                "ts": 1759272617.753,
                "updateTs": 1759272648.309,
                "target": {"type": "internet"},
                "scope": {"type": "group", "value": "36"},
                "schedule": {"cronTime": "0 19 * * 0,1,2,3,4", "duration": 7200},
                "hit": {"count": 94714, "lastHitTs": 1759280399.57}
            },
            {
                "id": "acdcdb72-ced6-40cf-8ce4-50ac6d376dbe",
                "action": "block",
                "direction": "bidirection",
                "gid": "2cd09491-7385-479b-899e-51dd5c731b10",
                "status": "active",
                "ts": 1749525569.422,
                "updateTs": 1759193622.034,
                "target": {"type": "app", "value": "youtube", "dnsOnly": True},
                "scope": {"type": "group", "value": "36"},
                "hit": {"count": 8147, "lastHitTs": 1759266313}
            },
            {
                "id": "0314a387-2bc4-4bae-a69f-d81f19500c65",
                "action": "block",
                "direction": "bidirection",
                "gid": "2cd09491-7385-479b-899e-51dd5c731b10",
                "status": "paused",
                "ts": 1759024328.736,
                "updateTs": 1759184321.724,
                "target": {"type": "category", "value": "av", "dnsOnly": True},
                "scope": {"type": "device", "value": "FC:34:97:A5:9F:91"},
                "hit": {"count": 182, "lastHitTs": 1759178343}
            },
        ],
        "count": 3
    }
    
    # Create a mock coordinator instance
    class MockHass:
        pass
    
    mock_hass = MockHass()
    
    # Create coordinator (without session for this test)
    coordinator = FirewallaDataUpdateCoordinator(
        hass=mock_hass,
        session=None,
        msp_domain="test.firewalla.net",
        access_token="test-token",
        box_gid="test-box",
    )
    
    # Test rule processing
    print("🔍 Testing rule data processing with real API structure...")
    processed_rules = coordinator._process_rules_data(real_api_response)
    
    print(f"✅ Processed {len(processed_rules)} rules")
    
    # Validate processed data
    expected_rules = 3
    if len(processed_rules) != expected_rules:
        print(f"❌ Expected {expected_rules} rules, got {len(processed_rules)}")
        return False
    
    # Check each processed rule
    for rule_id, rule_data in processed_rules.items():
        print(f"\nRule {rule_id}:")
        print(f"  Type: {rule_data.get('type')}")
        print(f"  Value: {rule_data.get('value')}")
        print(f"  Status: {rule_data.get('status')}")
        print(f"  Paused: {rule_data.get('paused')}")
        print(f"  Action: {rule_data.get('action')}")
        print(f"  Scope Type: {rule_data.get('scope_type')}")
        print(f"  Scope Value: {rule_data.get('scope_value')}")
        print(f"  DNS Only: {rule_data.get('dnsOnly')}")
        
        # Validate required fields
        required_fields = ["rid", "id", "type", "action", "paused", "status"]
        for field in required_fields:
            if field not in rule_data:
                print(f"❌ Missing required field: {field}")
                return False
    
    # Test specific rule mappings
    # Rule 1: Internet blocking rule
    rule1 = processed_rules["844a31a7-7ccd-4096-a610-9fb56b110edc"]
    if rule1["type"] != "internet":
        print(f"❌ Rule 1 type mismatch: expected 'internet', got '{rule1['type']}'")
        return False
    if rule1["status"] != "active":
        print(f"❌ Rule 1 status mismatch: expected 'active', got '{rule1['status']}'")
        return False
    if rule1["paused"] != False:
        print(f"❌ Rule 1 paused mismatch: expected False, got {rule1['paused']}")
        return False
    
    # Rule 2: YouTube app blocking rule
    rule2 = processed_rules["acdcdb72-ced6-40cf-8ce4-50ac6d376dbe"]
    if rule2["type"] != "app":
        print(f"❌ Rule 2 type mismatch: expected 'app', got '{rule2['type']}'")
        return False
    if rule2["value"] != "youtube":
        print(f"❌ Rule 2 value mismatch: expected 'youtube', got '{rule2['value']}'")
        return False
    if rule2["dnsOnly"] != True:
        print(f"❌ Rule 2 dnsOnly mismatch: expected True, got {rule2['dnsOnly']}")
        return False
    
    # Rule 3: Paused category rule
    rule3 = processed_rules["0314a387-2bc4-4bae-a69f-d81f19500c65"]
    if rule3["status"] != "paused":
        print(f"❌ Rule 3 status mismatch: expected 'paused', got '{rule3['status']}'")
        return False
    if rule3["paused"] != True:
        print(f"❌ Rule 3 paused mismatch: expected True, got {rule3['paused']}")
        return False
    if rule3["type"] != "category":
        print(f"❌ Rule 3 type mismatch: expected 'category', got '{rule3['type']}'")
        return False
    if rule3["value"] != "av":
        print(f"❌ Rule 3 value mismatch: expected 'av', got '{rule3['value']}'")
        return False
    
    # Test statistics calculation
    print("\n🔍 Testing rule statistics calculation...")
    stats = coordinator._calculate_rule_statistics(processed_rules)
    
    print(f"✅ Statistics calculated:")
    print(f"  Total: {stats['total']}")
    print(f"  Active: {stats['active']}")
    print(f"  Paused: {stats['paused']}")
    print(f"  By type: {stats['by_type']}")
    
    # Validate statistics
    if stats["total"] != 3:
        print(f"❌ Total count mismatch: expected 3, got {stats['total']}")
        return False
    if stats["active"] != 2:
        print(f"❌ Active count mismatch: expected 2, got {stats['active']}")
        return False
    if stats["paused"] != 1:
        print(f"❌ Paused count mismatch: expected 1, got {stats['paused']}")
        return False
    
    expected_by_type = {"internet": 1, "app": 1, "category": 1}
    if stats["by_type"] != expected_by_type:
        print(f"❌ By type mismatch: expected {expected_by_type}, got {stats['by_type']}")
        return False
    
    print("\n✅ All coordinator processing tests passed!")
    return True

def main():
    """Run the test."""
    print("🚀 Testing Firewalla Coordinator with Real API Data")
    print("="*60)
    
    success = test_coordinator_processing()
    
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    print(f"Coordinator Processing: {'✅ PASS' if success else '❌ FAIL'}")
    
    if success:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)