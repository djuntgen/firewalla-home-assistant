"""Tests for Firewalla rule control switch entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.firewalla.switch import (
    FirewallaRuleSwitch,
    async_setup_entry,
)
from custom_components.firewalla.const import DOMAIN, ENTITY_ID_FORMATS


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with rule data."""
    coordinator = MagicMock(spec=DataUpdateCoordinator)
    coordinator.data = {
        "rules": {
            "rule-123": {
                "rid": "rule-123",
                "type": "internet",
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "target_name": "John's Laptop",
                "disabled": False,
                "paused": False,
                "action": "block",
                "description": "Block internet during study time",
                "priority": 1000,
                "created_at": 1648632679193,
                "modified_at": 1648632679193,
                "schedule": None,
            },
            "rule-456": {
                "rid": "rule-456",
                "type": "category",
                "target": "category:gaming",
                "target_name": "Gaming Category",
                "disabled": False,
                "paused": True,
                "action": "block",
                "description": "Block gaming websites",
                "priority": 500,
                "created_at": 1648632679193,
                "modified_at": 1648632679193,
                "schedule": None,
            },
        },
        "rule_count": {
            "total": 2,
            "active": 1,
            "paused": 1,
            "by_type": {"internet": 1, "category": 1},
        },
        "box_info": {
            "gid": "box-123",
            "name": "Firewalla Gold",
            "model": "gold",
            "online": True,
            "version": "1.975",
        },
    }
    coordinator.box_gid = "box-123"
    coordinator.last_update_success = True
    coordinator.async_unpause_rule = AsyncMock(return_value=True)
    coordinator.async_pause_rule = AsyncMock(return_value=True)
    return coordinator


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {DOMAIN: {"test_entry": MagicMock()}}
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


class TestFirewallaRuleSwitch:
    """Test Firewalla rule control switch entity."""

    def test_init(self, mock_coordinator):
        """Test switch initialization."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        assert switch._rule_id == rule_id
        assert switch._rule_data == rule_data
        assert switch.unique_id == ENTITY_ID_FORMATS["rule_switch"].format(rule_id=rule_id)
        assert switch.name == "Block internet during study time"

    def test_name_generation_with_description(self, mock_coordinator):
        """Test entity name generation using rule description."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        assert switch.name == "Block internet during study time"

    def test_name_generation_without_description(self, mock_coordinator):
        """Test entity name generation without description."""
        rule_id = "rule-123"
        rule_data = {
            "rid": "rule-123",
            "type": "internet",
            "target": "mac:aa:bb:cc:dd:ee:ff",
            "target_name": "John's Laptop",
            "action": "block",
            "description": "",
        }
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        assert switch.name == "Internet Access - John's Laptop"

    def test_is_on_active_rule(self, mock_coordinator):
        """Test is_on property for active rule."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return active rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": False})
        
        assert switch.is_on is True

    def test_is_on_paused_rule(self, mock_coordinator):
        """Test is_on property for paused rule."""
        rule_id = "rule-456"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return paused rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": True})
        
        assert switch.is_on is False

    def test_is_on_rule_not_found(self, mock_coordinator):
        """Test is_on property when rule is not found."""
        rule_id = "rule-999"
        rule_data = {"rid": "rule-999", "description": "Test rule"}
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return None (rule not found)
        switch._get_current_rule_data = MagicMock(return_value=None)
        
        assert switch.is_on is False

    def test_available_with_rule(self, mock_coordinator):
        """Test available property when rule exists."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return rule data
        switch._get_current_rule_data = MagicMock(return_value=rule_data)
        
        assert switch.available is True

    def test_available_without_rule(self, mock_coordinator):
        """Test available property when rule doesn't exist."""
        rule_id = "rule-999"
        rule_data = {"rid": "rule-999", "description": "Test rule"}
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return None
        switch._get_current_rule_data = MagicMock(return_value=None)
        
        assert switch.available is False

    def test_extra_state_attributes(self, mock_coordinator):
        """Test extra state attributes."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return rule data
        switch._get_current_rule_data = MagicMock(return_value=rule_data)
        
        attributes = switch.extra_state_attributes
        
        assert attributes["rule_id"] == rule_id
        assert attributes["rule_type"] == "internet"
        assert attributes["target"] == "mac:aa:bb:cc:dd:ee:ff"
        assert attributes["target_name"] == "John's Laptop"
        assert attributes["action"] == "block"
        assert attributes["description"] == "Block internet during study time"
        assert attributes["rule_status"] == "active"
        assert attributes["rule_disabled"] is False

    @pytest.mark.asyncio
    async def test_async_turn_on_paused_rule(self, mock_coordinator):
        """Test turning on a paused rule."""
        rule_id = "rule-456"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return paused rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": True})
        
        await switch.async_turn_on()
        
        mock_coordinator.async_unpause_rule.assert_called_once_with(rule_id)

    @pytest.mark.asyncio
    async def test_async_turn_on_active_rule(self, mock_coordinator):
        """Test turning on an already active rule."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return active rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": False})
        
        await switch.async_turn_on()
        
        # Should not call unpause for already active rule
        mock_coordinator.async_unpause_rule.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_turn_on_rule_not_found(self, mock_coordinator):
        """Test turning on a rule that doesn't exist."""
        rule_id = "rule-999"
        rule_data = {"rid": "rule-999", "description": "Test rule"}
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return None
        switch._get_current_rule_data = MagicMock(return_value=None)
        
        with pytest.raises(HomeAssistantError, match="Rule rule-999 not found"):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_async_turn_off_active_rule(self, mock_coordinator):
        """Test turning off an active rule."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return active rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": False})
        
        await switch.async_turn_off()
        
        mock_coordinator.async_pause_rule.assert_called_once_with(rule_id)

    @pytest.mark.asyncio
    async def test_async_turn_off_paused_rule(self, mock_coordinator):
        """Test turning off an already paused rule."""
        rule_id = "rule-456"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return paused rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": True})
        
        await switch.async_turn_off()
        
        # Should not call pause for already paused rule
        mock_coordinator.async_pause_rule.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_turn_off_coordinator_failure(self, mock_coordinator):
        """Test turning off rule when coordinator fails."""
        rule_id = "rule-123"
        rule_data = mock_coordinator.data["rules"][rule_id]
        
        switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)
        
        # Mock _get_current_rule_data to return active rule
        switch._get_current_rule_data = MagicMock(return_value={"paused": False})
        
        # Mock coordinator to return failure
        mock_coordinator.async_pause_rule.return_value = False
        
        with pytest.raises(HomeAssistantError, match="Failed to pause rule"):
            await switch.async_turn_off()


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(self, mock_hass, mock_config_entry, mock_coordinator):
        """Test successful setup of switch entities."""
        mock_hass.data[DOMAIN][mock_config_entry.entry_id] = mock_coordinator
        
        async_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        # Should be called with list of switch entities
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        
        assert len(entities) == 2  # Two rules in mock data
        assert all(isinstance(entity, FirewallaRuleSwitch) for entity in entities)

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_rules(self, mock_hass, mock_config_entry, mock_coordinator):
        """Test setup with no rules."""
        mock_coordinator.data = {"rules": {}}
        mock_hass.data[DOMAIN][mock_config_entry.entry_id] = mock_coordinator
        
        async_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        # Should be called with empty list
        async_add_entities.assert_called_once_with([], True)

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_coordinator(self, mock_hass, mock_config_entry):
        """Test setup with missing coordinator."""
        # Don't add coordinator to hass.data
        
        async_add_entities = AsyncMock()
        
        with pytest.raises(HomeAssistantError, match="Coordinator not found"):
            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)