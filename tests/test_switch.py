"""Tests for Firewalla switch entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.exceptions import HomeAssistantError

from custom_components.firewalla.switch import (
    FirewallaBlockSwitch,
    FirewallaGamingSwitch,
    _is_gaming_capable_device,
    async_setup_entry,
)
from custom_components.firewalla.const import RULE_TYPES, RULE_ACTIONS


class TestGamingDeviceDetection:
    """Test gaming device detection logic."""

    def test_is_gaming_capable_device_class(self):
        """Test gaming detection by device class."""
        gaming_device = {
            "deviceClass": "gaming_console",
            "name": "Unknown Device",
        }
        assert _is_gaming_capable_device(gaming_device) is True

    def test_is_gaming_capable_device_name(self):
        """Test gaming detection by device name."""
        gaming_device = {
            "deviceClass": "unknown",
            "name": "Xbox Series X",
        }
        assert _is_gaming_capable_device(gaming_device) is True

    def test_is_not_gaming_capable_device(self):
        """Test non-gaming device detection."""
        regular_device = {
            "deviceClass": "laptop",
            "name": "MacBook Pro",
        }
        assert _is_gaming_capable_device(regular_device) is False

    def test_gaming_detection_case_insensitive(self):
        """Test gaming detection is case insensitive."""
        gaming_device = {
            "deviceClass": "GAMING_CONSOLE",
            "name": "PLAYSTATION 5",
        }
        assert _is_gaming_capable_device(gaming_device) is True


class TestAsyncSetupEntry:
    """Test switch platform setup."""

    @pytest.mark.asyncio
    async def test_setup_entry_success(self, mock_hass, mock_config_entry, mock_coordinator_data):
        """Test successful switch platform setup."""
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
        
        # Should have 3 entities: 2 block switches + 1 gaming switch (for gaming console)
        assert len(entities) == 3
        
        # Check entity types
        block_switches = [e for e in entities if isinstance(e, FirewallaBlockSwitch)]
        gaming_switches = [e for e in entities if isinstance(e, FirewallaGamingSwitch)]
        
        assert len(block_switches) == 2  # One for each device
        assert len(gaming_switches) == 1  # Only for gaming console

    @pytest.mark.asyncio
    async def test_setup_entry_no_devices(self, mock_hass, mock_config_entry):
        """Test switch platform setup with no devices."""
        # Mock coordinator with no devices
        mock_coordinator = MagicMock()
        mock_coordinator.devices = {}
        
        # Store coordinator in hass.data
        mock_hass.data = {"firewalla": {mock_config_entry.entry_id: mock_coordinator}}
        
        # Mock async_add_entities
        mock_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
        
        # Verify empty list was passed
        mock_add_entities.assert_called_once_with([], True)

    @pytest.mark.asyncio
    async def test_setup_entry_missing_coordinator(self, mock_hass, mock_config_entry):
        """Test switch platform setup with missing coordinator."""
        # No coordinator in hass.data
        mock_hass.data = {"firewalla": {}}
        
        # Mock async_add_entities
        mock_add_entities = AsyncMock()
        
        with pytest.raises(HomeAssistantError, match="Coordinator not found"):
            await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)


class TestFirewallaBlockSwitch:
    """Test Firewalla block switch entity."""

    @pytest.fixture
    def mock_coordinator(self, mock_coordinator_data):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = mock_coordinator_data
        coordinator.devices = mock_coordinator_data["devices"]
        coordinator.rules = mock_coordinator_data["rules"]
        coordinator.box_info = mock_coordinator_data["box_info"]
        coordinator.last_update_success = True
        coordinator.get_device_by_mac.return_value = mock_coordinator_data["devices"]["aa:bb:cc:dd:ee:ff"]
        coordinator.get_device_friendly_name.return_value = "Test Device 1"
        coordinator.get_device_info_dict.return_value = {
            "identifiers": {("firewalla", "aa:bb:cc:dd:ee:ff")},
            "name": "Test Device 1",
            "manufacturer": "Firewalla",
        }
        return coordinator

    @pytest.fixture
    def block_switch(self, mock_coordinator, mock_devices_data):
        """Create a block switch entity."""
        device_mac = "aa:bb:cc:dd:ee:ff"
        device_info = mock_devices_data[device_mac]
        return FirewallaBlockSwitch(mock_coordinator, device_mac, device_info)

    def test_unique_id(self, block_switch):
        """Test switch unique ID generation."""
        assert block_switch.unique_id == "firewalla_aabbccddeeff_block"

    def test_name(self, block_switch):
        """Test switch name generation."""
        assert "Test Device 1 Block" in block_switch.name

    def test_is_on_active_rule(self, block_switch, mock_coordinator):
        """Test is_on property with active blocking rule."""
        # Mock rules data with active rule
        mock_coordinator.rules = {
            "rule_123": {
                "type": RULE_TYPES["INTERNET_BLOCK"],
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "action": RULE_ACTIONS["BLOCK"],
                "paused": False,
                "disabled": False,
            }
        }
        
        assert block_switch.is_on is True

    def test_is_on_no_active_rule(self, block_switch, mock_coordinator):
        """Test is_on property with no active blocking rule."""
        # Mock rules data with paused rule
        mock_coordinator.rules = {
            "rule_123": {
                "type": RULE_TYPES["INTERNET_BLOCK"],
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "action": RULE_ACTIONS["BLOCK"],
                "paused": True,
                "disabled": False,
            }
        }
        
        assert block_switch.is_on is False

    def test_available_success(self, block_switch, mock_coordinator):
        """Test available property when coordinator has data."""
        mock_coordinator.last_update_success = True
        mock_coordinator.devices = {"aa:bb:cc:dd:ee:ff": {}}
        
        assert block_switch.available is True

    def test_available_no_update(self, block_switch, mock_coordinator):
        """Test available property when coordinator update failed."""
        mock_coordinator.last_update_success = False
        
        assert block_switch.available is False

    def test_available_device_missing(self, block_switch, mock_coordinator):
        """Test available property when device is missing."""
        mock_coordinator.last_update_success = True
        mock_coordinator.devices = {}  # Device not in list
        
        assert block_switch.available is False

    def test_extra_state_attributes(self, block_switch, mock_coordinator, mock_devices_data):
        """Test extra state attributes."""
        device_data = mock_devices_data["aa:bb:cc:dd:ee:ff"]
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        attributes = block_switch.extra_state_attributes
        
        assert attributes["device_mac"] == "aa:bb:cc:dd:ee:ff"
        assert attributes["device_name"] == "Test Device 1"
        assert attributes["device_ip"] == "192.168.1.100"
        assert attributes["device_online"] is True
        assert "last_seen" in attributes

    @pytest.mark.asyncio
    async def test_turn_on_create_new_rule(self, block_switch, mock_coordinator):
        """Test turning on switch creates new rule."""
        # Mock no existing rules
        mock_coordinator.rules = {}
        mock_coordinator.async_create_device_block_rule = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        
        # Mock _find_paused_block_rule to return None
        with patch.object(block_switch, "_find_paused_block_rule", return_value=None):
            await block_switch.async_turn_on()
        
        mock_coordinator.async_create_device_block_rule.assert_called_once()
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_unpause_existing_rule(self, block_switch, mock_coordinator):
        """Test turning on switch unpauses existing rule."""
        mock_coordinator.async_unpause_rule = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        
        # Mock _find_paused_block_rule to return a rule ID
        with patch.object(block_switch, "_find_paused_block_rule", return_value="paused_rule_123"):
            await block_switch.async_turn_on()
        
        mock_coordinator.async_unpause_rule.assert_called_once_with("paused_rule_123")
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_already_active(self, block_switch):
        """Test turning on switch when already active."""
        # Mock is_on to return True
        with patch.object(block_switch, "is_on", True):
            await block_switch.async_turn_on()
        
        # Should return early without making API calls

    @pytest.mark.asyncio
    async def test_turn_off_pause_rule(self, block_switch, mock_coordinator):
        """Test turning off switch pauses rule."""
        mock_coordinator.async_pause_rule = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        
        # Mock _find_active_block_rule to return a rule ID
        with patch.object(block_switch, "_find_active_block_rule", return_value="active_rule_123"):
            await block_switch.async_turn_off()
        
        mock_coordinator.async_pause_rule.assert_called_once_with("active_rule_123")
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_no_active_rule(self, block_switch, mock_coordinator):
        """Test turning off switch with no active rule."""
        # Mock _find_active_block_rule to return None
        with patch.object(block_switch, "_find_active_block_rule", return_value=None):
            await block_switch.async_turn_off()
        
        # Should return early without making API calls

    @pytest.mark.asyncio
    async def test_find_active_block_rule(self, block_switch, mock_coordinator):
        """Test finding active block rule."""
        mock_device_rules = {
            "rule_123": {
                "action": RULE_ACTIONS["BLOCK"],
                "paused": False,
                "disabled": False,
            }
        }
        
        mock_coordinator.async_get_device_rules = AsyncMock(return_value=mock_device_rules)
        
        result = await block_switch._find_active_block_rule()
        
        assert result == "rule_123"
        mock_coordinator.async_get_device_rules.assert_called_once_with(
            "aa:bb:cc:dd:ee:ff", RULE_TYPES["INTERNET_BLOCK"]
        )

    @pytest.mark.asyncio
    async def test_find_paused_block_rule(self, block_switch, mock_coordinator):
        """Test finding paused block rule."""
        mock_device_rules = {
            "rule_456": {
                "action": RULE_ACTIONS["BLOCK"],
                "paused": True,
                "disabled": False,
            }
        }
        
        mock_coordinator.async_get_device_rules = AsyncMock(return_value=mock_device_rules)
        
        result = await block_switch._find_paused_block_rule()
        
        assert result == "rule_456"


class TestFirewallaGamingSwitch:
    """Test Firewalla gaming switch entity."""

    @pytest.fixture
    def mock_coordinator(self, mock_coordinator_data):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = mock_coordinator_data
        coordinator.devices = mock_coordinator_data["devices"]
        coordinator.rules = mock_coordinator_data["rules"]
        coordinator.box_info = mock_coordinator_data["box_info"]
        coordinator.last_update_success = True
        coordinator.get_device_by_mac.return_value = mock_coordinator_data["devices"]["11:22:33:44:55:66"]
        coordinator.get_device_friendly_name.return_value = "Gaming Console"
        coordinator.get_device_info_dict.return_value = {
            "identifiers": {("firewalla", "11:22:33:44:55:66")},
            "name": "Gaming Console",
            "manufacturer": "Firewalla",
        }
        return coordinator

    @pytest.fixture
    def gaming_switch(self, mock_coordinator, mock_devices_data):
        """Create a gaming switch entity."""
        device_mac = "11:22:33:44:55:66"
        device_info = mock_devices_data[device_mac]
        return FirewallaGamingSwitch(mock_coordinator, device_mac, device_info)

    def test_unique_id(self, gaming_switch):
        """Test gaming switch unique ID generation."""
        assert gaming_switch.unique_id == "firewalla_112233445566_gaming"

    def test_name(self, gaming_switch):
        """Test gaming switch name generation."""
        assert "Gaming Console Gaming Pause" in gaming_switch.name

    def test_is_on_active_gaming_rule(self, gaming_switch, mock_coordinator):
        """Test is_on property with active gaming rule."""
        # Mock rules data with active gaming rule
        mock_coordinator.rules = {
            "rule_456": {
                "type": RULE_TYPES["GAMING_PAUSE"],
                "target": "mac:11:22:33:44:55:66",
                "action": RULE_ACTIONS["BLOCK"],
                "paused": False,
                "disabled": False,
            }
        }
        
        assert gaming_switch.is_on is True

    def test_is_on_paused_gaming_rule(self, gaming_switch, mock_coordinator):
        """Test is_on property with paused gaming rule."""
        # Mock rules data with paused gaming rule
        mock_coordinator.rules = {
            "rule_456": {
                "type": RULE_TYPES["GAMING_PAUSE"],
                "target": "mac:11:22:33:44:55:66",
                "action": RULE_ACTIONS["BLOCK"],
                "paused": True,
                "disabled": False,
            }
        }
        
        assert gaming_switch.is_on is False

    def test_available_gaming_capable(self, gaming_switch, mock_coordinator, mock_devices_data):
        """Test available property for gaming-capable device."""
        mock_coordinator.last_update_success = True
        mock_coordinator.devices = {"11:22:33:44:55:66": mock_devices_data["11:22:33:44:55:66"]}
        
        assert gaming_switch.available is True

    def test_extra_state_attributes_gaming(self, gaming_switch, mock_coordinator, mock_devices_data):
        """Test extra state attributes for gaming switch."""
        device_data = mock_devices_data["11:22:33:44:55:66"]
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        attributes = gaming_switch.extra_state_attributes
        
        assert attributes["device_mac"] == "11:22:33:44:55:66"
        assert attributes["device_name"] == "Gaming Console"
        assert attributes["gaming_capable"] is True

    @pytest.mark.asyncio
    async def test_turn_on_create_gaming_rule(self, gaming_switch, mock_coordinator):
        """Test turning on gaming switch creates gaming rule."""
        # Mock no existing rules
        mock_coordinator.rules = {}
        mock_coordinator.async_create_gaming_pause_rule = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        
        # Mock _find_paused_gaming_rule to return None
        with patch.object(gaming_switch, "_find_paused_gaming_rule", return_value=None):
            await gaming_switch.async_turn_on()
        
        mock_coordinator.async_create_gaming_pause_rule.assert_called_once()
        mock_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_pause_gaming_rule(self, gaming_switch, mock_coordinator):
        """Test turning off gaming switch pauses gaming rule."""
        mock_coordinator.async_pause_rule = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()
        
        # Mock _find_active_gaming_rule to return a rule ID
        with patch.object(gaming_switch, "_find_active_gaming_rule", return_value="gaming_rule_456"):
            await gaming_switch.async_turn_off()
        
        mock_coordinator.async_pause_rule.assert_called_once_with("gaming_rule_456")
        mock_coordinator.async_request_refresh.assert_called_once()