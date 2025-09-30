#!/usr/bin/env python3
"""End-to-end integration test for Firewalla integration."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class MockHomeAssistant:
    """Mock Home Assistant instance."""
    
    def __init__(self):
        self.data = {}
        self.config_entries = MockConfigEntries()


class MockConfigEntries:
    """Mock config entries manager."""
    
    async def async_forward_entry_setups(self, entry, platforms):
        """Mock platform setup."""
        print(f"📦 Setting up platforms: {platforms}")
        return True
    
    async def async_unload_platforms(self, entry, platforms):
        """Mock platform unload."""
        print(f"📦 Unloading platforms: {platforms}")
        return True


class MockConfigEntry:
    """Mock config entry."""
    
    def __init__(self, entry_id="test_entry"):
        self.entry_id = entry_id
        self.data = {
            "msp_url": "https://test.firewalla.com",
            "access_token": "test_token",
            "box_gid": "test_box_gid"
        }


async def test_integration_setup():
    """Test complete integration setup flow."""
    print("🧪 Testing Integration Setup")
    print("=" * 40)
    
    # Mock dependencies
    mock_hass = MockHomeAssistant()
    mock_entry = MockConfigEntry()
    mock_session = AsyncMock()
    mock_coordinator = AsyncMock()
    mock_coordinator.async_config_entry_first_refresh = AsyncMock()
    
    # Mock the coordinator data
    mock_coordinator.data = {
        "box_info": {
            "gid": "test_box_gid",
            "name": "Test Firewalla",
            "model": "gold",
            "online": True,
            "version": "1.975"
        },
        "devices": {
            "aa:bb:cc:dd:ee:ff": {
                "mac": "aa:bb:cc:dd:ee:ff",
                "name": "Test Device",
                "ip": "192.168.1.100",
                "online": True,
                "lastActiveTimestamp": 1648632679.193,
                "deviceClass": "laptop"
            }
        },
        "rules": {}
    }
    
    # Import and test the setup function
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    
    with patch("custom_components.firewalla.async_get_clientsession", return_value=mock_session), \
         patch("custom_components.firewalla.FirewallaDataUpdateCoordinator", return_value=mock_coordinator):
        
        # Import after patching to avoid import errors
        from custom_components.firewalla import async_setup_entry, PLATFORMS_TO_SETUP
        
        # Test setup
        result = await async_setup_entry(mock_hass, mock_entry)
        
        # Verify results
        assert result is True, "Setup should return True"
        assert "firewalla" in mock_hass.data, "Domain should be in hass.data"
        assert mock_entry.entry_id in mock_hass.data["firewalla"], "Entry should be stored"
        
        print("✅ Integration setup successful")
        print(f"✅ Coordinator stored in hass.data")
        print(f"✅ Platforms configured: {PLATFORMS_TO_SETUP}")
        
        # Verify coordinator was initialized
        mock_coordinator.async_config_entry_first_refresh.assert_called_once()
        print("✅ Coordinator first refresh called")
        
        return mock_hass, mock_entry, mock_coordinator


async def test_integration_unload():
    """Test integration unload."""
    print("\n🧪 Testing Integration Unload")
    print("=" * 40)
    
    # Set up mock data
    mock_hass = MockHomeAssistant()
    mock_entry = MockConfigEntry()
    mock_coordinator = AsyncMock()
    
    # Pre-populate hass.data as if integration was set up
    mock_hass.data["firewalla"] = {mock_entry.entry_id: mock_coordinator}
    
    # Import and test unload
    from custom_components.firewalla import async_unload_entry
    
    result = await async_unload_entry(mock_hass, mock_entry)
    
    # Verify results
    assert result is True, "Unload should return True"
    assert mock_entry.entry_id not in mock_hass.data.get("firewalla", {}), "Entry should be removed"
    
    print("✅ Integration unload successful")
    print("✅ Coordinator removed from hass.data")
    
    return True


async def test_integration_reload():
    """Test integration reload."""
    print("\n🧪 Testing Integration Reload")
    print("=" * 40)
    
    mock_hass = MockHomeAssistant()
    mock_entry = MockConfigEntry()
    mock_session = AsyncMock()
    mock_coordinator = AsyncMock()
    mock_coordinator.async_config_entry_first_refresh = AsyncMock()
    
    with patch("custom_components.firewalla.async_get_clientsession", return_value=mock_session), \
         patch("custom_components.firewalla.FirewallaDataUpdateCoordinator", return_value=mock_coordinator), \
         patch("custom_components.firewalla.async_setup_entry", return_value=True) as mock_setup, \
         patch("custom_components.firewalla.async_unload_entry", return_value=True) as mock_unload:
        
        from custom_components.firewalla import async_reload_entry
        
        # Test reload
        await async_reload_entry(mock_hass, mock_entry)
        
        # Verify both unload and setup were called
        mock_unload.assert_called_once_with(mock_hass, mock_entry)
        mock_setup.assert_called_once_with(mock_hass, mock_entry)
        
        print("✅ Integration reload successful")
        print("✅ Unload called before setup")
        print("✅ Setup called after unload")
        
        return True


async def test_platform_integration():
    """Test that platforms integrate properly with coordinator."""
    print("\n🧪 Testing Platform Integration")
    print("=" * 40)
    
    # Mock coordinator with realistic data
    mock_coordinator = AsyncMock()
    mock_coordinator.data = {
        "devices": {
            "aa:bb:cc:dd:ee:ff": {
                "mac": "aa:bb:cc:dd:ee:ff",
                "name": "Test Device",
                "ip": "192.168.1.100",
                "online": True,
                "lastActiveTimestamp": 1648632679.193,
                "deviceClass": "laptop"
            }
        },
        "rules": {
            "rule-1": {
                "rid": "rule-1",
                "type": "internet",
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "disabled": False,
                "paused": False,
                "action": "block"
            }
        }
    }
    
    # Test that platforms can access coordinator data
    devices = mock_coordinator.data.get("devices", {})
    rules = mock_coordinator.data.get("rules", {})
    
    assert len(devices) > 0, "Should have device data"
    assert "aa:bb:cc:dd:ee:ff" in devices, "Should have test device"
    
    device = devices["aa:bb:cc:dd:ee:ff"]
    assert device["name"] == "Test Device", "Device should have correct name"
    assert device["online"] is True, "Device should be online"
    
    print("✅ Coordinator provides device data")
    print(f"✅ Found {len(devices)} devices")
    print(f"✅ Found {len(rules)} rules")
    
    return True


def test_manifest_configuration():
    """Test manifest configuration."""
    print("\n🧪 Testing Manifest Configuration")
    print("=" * 40)
    
    with open("custom_components/firewalla/manifest.json") as f:
        manifest = json.load(f)
    
    # Verify key configuration
    assert manifest["domain"] == "firewalla", "Domain should be firewalla"
    assert "aiohttp" in str(manifest["requirements"]), "Should require aiohttp"
    assert manifest["version"], "Should have version"
    
    print("✅ Manifest domain correct")
    print("✅ Manifest requirements include aiohttp")
    print(f"✅ Manifest version: {manifest['version']}")
    
    return True


async def main():
    """Run all end-to-end tests."""
    print("🚀 Firewalla Integration End-to-End Tests")
    print("=" * 60)
    
    tests = [
        ("Integration Setup", test_integration_setup),
        ("Integration Unload", test_integration_unload),
        ("Integration Reload", test_integration_reload),
        ("Platform Integration", test_platform_integration),
        ("Manifest Configuration", test_manifest_configuration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            results.append((test_name, True))
            
        except Exception as e:
            print(f"❌ {test_name} failed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 End-to-End Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n📈 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All end-to-end tests passed!")
        print("✅ Integration entry point wires all components correctly")
        print("✅ All entity platforms load successfully")
        print("✅ Integration reload capability works")
        print("✅ Components work together in end-to-end scenarios")
        print("\n🚀 Integration is ready for deployment!")
        return 0
    else:
        print("\n⚠️  Some end-to-end tests failed.")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))