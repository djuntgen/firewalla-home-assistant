"""Tests for Firewalla sensor entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from custom_components.firewalla.sensor import (
    FirewallaDeviceStatusSensor,
    FirewallaRulesSensor,
    async_setup_entry,
)


class TestAsyncSetupEntry:
    """Test sensor platform setup."""

    @pytest.mark.asyncio
    async def test_setup_entry_success(self, mock_hass, mock_config_entry, mock_coordinator_data):
        """Test successful sensor platform setup."""
        # Mock coordinator
        mock_coordinator = MagicMock()
        mock_coordinator.devices = mock_coordinator_data["devices"]
        mock_coordinator.get_device_friendly_name.return_value = "Test Device"
        mock_coordinator.get_device_info_dict.return_value = {"name": "Test Device"}
        
        # Store coordinator in hass.data
        mock_hass.data = {"firewalla": {mock_config_entry.entry_id: mock_coordinator}}
        
        # Mock async_add_entities
        mock_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
        
        # Verify entities were added
        mock_add_entities.assert_called_once()
        entities = mock_add_entities.call_args[0][0]
        
        # Should have 3 entities: 2 device sensors + 1 rules sensor
        assert len(entities) == 3
        
        # Check entity types
        device_sensors = [e for e in entities if isinstance(e, FirewallaDeviceStatusSensor)]
        rules_sensors = [e for e in entities if isinstance(e, FirewallaRulesSensor)]
        
        assert len(device_sensors) == 2  # One for each device
        assert len(rules_sensors) == 1   # One rules sensor

    @pytest.mark.asyncio
    async def test_setup_entry_no_devices(self, mock_hass, mock_config_entry):
        """Test sensor platform setup with no devices."""
        # Mock coordinator with no devices
        mock_coordinator = MagicMock()
        mock_coordinator.devices = {}
        
        # Store coordinator in hass.data
        mock_hass.data = {"firewalla": {mock_config_entry.entry_id: mock_coordinator}}
        
        # Mock async_add_entities
        mock_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
        
        # Verify only rules sensor was added
        mock_add_entities.assert_called_once()
        entities = mock_add_entities.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], FirewallaRulesSensor)

    @pytest.mark.asyncio
    async def test_setup_entry_missing_coordinator(self, mock_hass, mock_config_entry):
        """Test sensor platform setup with missing coordinator."""
        # No coordinator in hass.data
        mock_hass.data = {"firewalla": {}}
        
        # Mock async_add_entities
        mock_add_entities = AsyncMock()
        
        with pytest.raises(HomeAssistantError, match="Coordinator not found"):
            await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)


class TestFirewallaDeviceStatusSensor:
    """Test Firewalla device status sensor entity."""

    @pytest.fixture
    def mock_coordinator(self, mock_coordinator_data):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = mock_coordinator_data
        coordinator.devices = mock_coordinator_data["devices"]
        coordinator.box_info = mock_coordinator_data["box_info"]
        coordinator.last_update_success = True
        coordinator.get_device_by_mac.return_value = mock_coordinator_data["devices"]["aa:bb:cc:dd:ee:ff"]
        coordinator.get_device_friendly_name.return_value = "Test Device 1"
        coordinator.get_device_info_dict.return_value = {
            "identifiers": {("firewalla", "aa:bb:cc:dd:ee:ff")},
            "name": "Test Device 1",
            "manufacturer": "Firewalla",
            "model": "Gold",
            "sw_version": "1.975",
        }
        return coordinator

    @pytest.fixture
    def device_sensor(self, mock_coordinator, mock_devices_data):
        """Create a device status sensor entity."""
        device_mac = "aa:bb:cc:dd:ee:ff"
        device_data = mock_devices_data[device_mac]
        return FirewallaDeviceStatusSensor(mock_coordinator, device_mac, device_data)

    def test_unique_id(self, device_sensor):
        """Test sensor unique ID generation."""
        assert device_sensor.unique_id == "firewalla_aabbccddeeff_status"

    def test_name(self, device_sensor):
        """Test sensor name generation."""
        assert "Test Device 1 Status" in device_sensor.name

    def test_device_info(self, device_sensor, mock_coordinator):
        """Test device info property."""
        device_info = device_sensor.device_info
        
        assert isinstance(device_info, DeviceInfo)
        # DeviceInfo should be created from the dict returned by coordinator
        mock_coordinator.get_device_info_dict.assert_called()

    def test_native_value_online(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test native value for online device."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        device_data["online"] = True
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        assert device_sensor.native_value == "online"

    def test_native_value_offline(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test native value for offline device."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        device_data["online"] = False
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        assert device_sensor.native_value == "offline"

    def test_native_value_device_not_found(self, device_sensor, mock_coordinator):
        """Test native value when device not found."""
        mock_coordinator.get_device_by_mac.return_value = None
        
        assert device_sensor.native_value == "unknown"

    def test_available_success(self, device_sensor, mock_coordinator):
        """Test available property when coordinator has data."""
        mock_coordinator.last_update_success = True
        mock_coordinator.get_device_by_mac.return_value = {"online": True}
        
        assert device_sensor.available is True

    def test_available_no_update(self, device_sensor, mock_coordinator):
        """Test available property when coordinator update failed."""
        mock_coordinator.last_update_success = False
        
        assert device_sensor.available is False

    def test_available_device_missing(self, device_sensor, mock_coordinator):
        """Test available property when device is missing."""
        mock_coordinator.last_update_success = True
        mock_coordinator.get_device_by_mac.return_value = None
        
        assert device_sensor.available is False

    def test_extra_state_attributes(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test extra state attributes."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        attributes = device_sensor.extra_state_attributes
        
        assert attributes["mac_address"] == "aa:bb:cc:dd:ee:ff"
        assert attributes["device_name"] == "Test Device 1"
        assert attributes["ip_address"] == "192.168.1.100"
        assert attributes["device_class"] == "laptop"
        assert "last_seen" in attributes

    def test_extra_state_attributes_with_timestamp(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test extra state attributes with timestamp conversion."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        device_data["lastActiveTimestamp"] = 1648632679.193
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        attributes = device_sensor.extra_state_attributes
        
        assert "last_seen" in attributes
        # Should be ISO format datetime string
        assert "T" in attributes["last_seen"]

    def test_extra_state_attributes_with_millisecond_timestamp(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test extra state attributes with millisecond timestamp."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        device_data["lastActiveTimestamp"] = 1648632679193  # Milliseconds
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        attributes = device_sensor.extra_state_attributes
        
        assert "last_seen" in attributes
        # Should be converted to seconds and formatted
        assert "T" in attributes["last_seen"]

    def test_extra_state_attributes_device_not_found(self, device_sensor, mock_coordinator):
        """Test extra state attributes when device not found."""
        mock_coordinator.get_device_by_mac.return_value = None
        
        attributes = device_sensor.extra_state_attributes
        
        assert attributes == {}

    def test_icon_online(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test icon for online device."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        device_data["online"] = True
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        assert device_sensor.icon == "mdi:check-network"

    def test_icon_offline(self, device_sensor, mock_coordinator, mock_devices_data):
        """Test icon for offline device."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        device_data["online"] = False
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        assert device_sensor.icon == "mdi:close-network"

    def test_icon_device_not_found(self, device_sensor, mock_coordinator):
        """Test icon when device not found."""
        mock_coordinator.get_device_by_mac.return_value = None
        
        assert device_sensor.icon == "mdi:help-network"


class TestFirewallaRulesSensor:
    """Test Firewalla rules count sensor entity."""

    @pytest.fixture
    def mock_coordinator(self, mock_coordinator_data):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = mock_coordinator_data
        coordinator.rules = mock_coordinator_data["rules"]
        coordinator.box_info = mock_coordinator_data["box_info"]
        coordinator.box_gid = "test_box_gid_456"
        coordinator.last_update_success = True
        coordinator.last_update_success_time = datetime.fromisoformat("2024-01-01T14:00:00")
        return coordinator

    @pytest.fixture
    def rules_sensor(self, mock_coordinator):
        """Create a rules count sensor entity."""
        return FirewallaRulesSensor(mock_coordinator)

    def test_unique_id(self, rules_sensor):
        """Test rules sensor unique ID."""
        assert rules_sensor.unique_id == "firewalla_rules_active"

    def test_name(self, rules_sensor):
        """Test rules sensor name."""
        assert rules_sensor.name == "Firewalla Active Rules"

    def test_device_info(self, rules_sensor, mock_coordinator):
        """Test device info for rules sensor."""
        device_info = rules_sensor.device_info
        
        assert isinstance(device_info, DeviceInfo)
        assert device_info.name == "Test Firewalla Gold"
        assert device_info.manufacturer == "Firewalla"
        assert device_info.model == "Gold"
        assert device_info.sw_version == "1.975"

    def test_native_value_active_rules(self, rules_sensor, mock_coordinator, mock_rules_data):
        """Test native value counting active rules."""
        # Mock rules: rule_123 is active, rule_456 is paused
        mock_coordinator.rules = mock_rules_data
        
        # Only rule_123 should be counted as active (not paused, not disabled)
        assert rules_sensor.native_value == 1

    def test_native_value_no_rules(self, rules_sensor, mock_coordinator):
        """Test native value with no rules."""
        mock_coordinator.rules = {}
        
        assert rules_sensor.native_value == 0

    def test_native_value_all_paused_disabled(self, rules_sensor, mock_coordinator):
        """Test native value with all rules paused or disabled."""
        mock_coordinator.rules = {
            "rule_1": {"disabled": True, "paused": False},
            "rule_2": {"disabled": False, "paused": True},
            "rule_3": {"disabled": True, "paused": True},
        }
        
        assert rules_sensor.native_value == 0

    def test_native_value_mixed_rules(self, rules_sensor, mock_coordinator):
        """Test native value with mixed rule states."""
        mock_coordinator.rules = {
            "rule_1": {"disabled": False, "paused": False},  # Active
            "rule_2": {"disabled": False, "paused": False},  # Active
            "rule_3": {"disabled": True, "paused": False},   # Disabled
            "rule_4": {"disabled": False, "paused": True},   # Paused
        }
        
        assert rules_sensor.native_value == 2

    def test_native_value_invalid_rules(self, rules_sensor, mock_coordinator):
        """Test native value with some invalid rule data."""
        mock_coordinator.rules = {
            "rule_1": {"disabled": False, "paused": False},  # Valid active rule
            "rule_2": "invalid_string",  # Invalid rule data
            "rule_3": {"disabled": False, "paused": False},  # Valid active rule
        }
        
        # Should count only valid active rules
        assert rules_sensor.native_value == 2

    def test_available_success(self, rules_sensor, mock_coordinator):
        """Test available property when coordinator has data."""
        mock_coordinator.last_update_success = True
        
        assert rules_sensor.available is True

    def test_available_no_update(self, rules_sensor, mock_coordinator):
        """Test available property when coordinator update failed."""
        mock_coordinator.last_update_success = False
        
        assert rules_sensor.available is False

    def test_extra_state_attributes(self, rules_sensor, mock_coordinator):
        """Test extra state attributes."""
        mock_coordinator.rules = {
            "rule_1": {"disabled": False, "paused": False},  # Active
            "rule_2": {"disabled": False, "paused": True},   # Paused
            "rule_3": {"disabled": True, "paused": False},   # Disabled
        }
        
        attributes = rules_sensor.extra_state_attributes
        
        assert attributes["total_rules"] == 3
        assert attributes["active_rules"] == 1
        assert attributes["paused_rules"] == 1
        assert attributes["disabled_rules"] == 1
        assert "last_updated" in attributes

    def test_extra_state_attributes_no_rules(self, rules_sensor, mock_coordinator):
        """Test extra state attributes with no rules."""
        mock_coordinator.rules = {}
        
        attributes = rules_sensor.extra_state_attributes
        
        assert attributes["total_rules"] == 0
        assert attributes["active_rules"] == 0
        assert attributes["paused_rules"] == 0
        assert attributes["disabled_rules"] == 0

    def test_extra_state_attributes_with_timestamp(self, rules_sensor, mock_coordinator):
        """Test extra state attributes with last update timestamp."""
        mock_coordinator.rules = {}
        
        attributes = rules_sensor.extra_state_attributes
        
        assert "last_updated" in attributes
        assert "T" in attributes["last_updated"]  # ISO format

    def test_icon_no_rules(self, rules_sensor, mock_coordinator):
        """Test icon with no active rules."""
        mock_coordinator.rules = {}
        
        assert rules_sensor.icon == "mdi:shield-outline"

    def test_icon_few_rules(self, rules_sensor, mock_coordinator):
        """Test icon with few active rules."""
        mock_coordinator.rules = {
            "rule_1": {"disabled": False, "paused": False},
            "rule_2": {"disabled": False, "paused": False},
        }
        
        assert rules_sensor.icon == "mdi:shield-check"

    def test_icon_many_rules(self, rules_sensor, mock_coordinator):
        """Test icon with many active rules."""
        mock_coordinator.rules = {
            f"rule_{i}": {"disabled": False, "paused": False}
            for i in range(6)  # 6 active rules (>= 5)
        }
        
        assert rules_sensor.icon == "mdi:shield-alert"