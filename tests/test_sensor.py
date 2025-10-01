"""Tests for Firewalla rule statistics sensor entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.firewalla.sensor import (
    FirewallaRulesSensor,
    async_setup_entry,
)
from custom_components.firewalla.const import DOMAIN, ENTITY_ID_FORMATS


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with rule statistics data."""
    coordinator = MagicMock(spec=DataUpdateCoordinator)
    coordinator.data = {
        "rules": {
            "rule-123": {
                "rid": "rule-123",
                "type": "internet",
                "disabled": False,
                "paused": False,
                "action": "block",
                "description": "Active rule",
            },
            "rule-456": {
                "rid": "rule-456",
                "type": "category",
                "disabled": False,
                "paused": True,
                "action": "block",
                "description": "Paused rule",
            },
            "rule-789": {
                "rid": "rule-789",
                "type": "domain",
                "disabled": True,
                "paused": False,
                "action": "block",
                "description": "Disabled rule",
            },
        },
        "rule_count": {
            "total": 3,
            "active": 1,
            "paused": 1,
            "by_type": {
                "internet": 1,
                "category": 1,
                "domain": 1,
            },
        },
        "box_info": {
            "gid": "box-123",
            "name": "Firewalla Gold",
            "model": "gold",
            "online": True,
            "version": "1.975",
        },
        "last_updated": "2023-01-01T12:00:00",
    }
    coordinator.box_gid = "box-123"
    coordinator.last_update_success = True
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


class TestFirewallaRulesSensor:
    """Test Firewalla rules summary sensor entity."""

    def test_init(self, mock_coordinator):
        """Test sensor initialization."""
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.unique_id == ENTITY_ID_FORMATS["rules_sensor"]
        assert sensor.name == "Firewalla Rules Summary"
        assert sensor.native_unit_of_measurement == "rules"

    def test_native_value_with_data(self, mock_coordinator):
        """Test native value with rule count data."""
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.native_value == 3  # Total rules

    def test_native_value_no_data(self, mock_coordinator):
        """Test native value with no data."""
        mock_coordinator.data = None
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.native_value == 0

    def test_native_value_no_rule_count(self, mock_coordinator):
        """Test native value with no rule count data."""
        mock_coordinator.data = {"rules": {}}
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.native_value == 0

    def test_available_success(self, mock_coordinator):
        """Test available property when coordinator has successful data."""
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.available is True

    def test_available_failure(self, mock_coordinator):
        """Test available property when coordinator has failed."""
        mock_coordinator.last_update_success = False
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.available is False

    def test_extra_state_attributes_with_data(self, mock_coordinator):
        """Test extra state attributes with full data."""
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        attributes = sensor.extra_state_attributes
        
        assert attributes["total_rules"] == 3
        assert attributes["active_rules"] == 1
        assert attributes["paused_rules"] == 1
        assert attributes["by_type"]["internet"] == 1
        assert attributes["by_type"]["category"] == 1
        assert attributes["by_type"]["domain"] == 1
        assert attributes["last_updated"] == "2023-01-01T12:00:00"
        assert attributes["api_status"] == "connected"
        assert attributes["box_name"] == "Firewalla Gold"
        assert attributes["box_model"] == "gold"
        assert attributes["box_online"] is True

    def test_extra_state_attributes_no_data(self, mock_coordinator):
        """Test extra state attributes with no data."""
        mock_coordinator.data = None
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        attributes = sensor.extra_state_attributes
        
        assert attributes["status"] == "No data available"

    def test_extra_state_attributes_disconnected(self, mock_coordinator):
        """Test extra state attributes when disconnected."""
        mock_coordinator.last_update_success = False
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        attributes = sensor.extra_state_attributes
        
        assert attributes["api_status"] == "disconnected"

    def test_extra_state_attributes_with_changes(self, mock_coordinator):
        """Test extra state attributes with rule changes."""
        mock_coordinator.data["rule_changes"] = {
            "added": ["rule-new"],
            "removed": ["rule-old"],
            "modified": ["rule-123", "rule-456"],
        }
        
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        attributes = sensor.extra_state_attributes
        
        assert "recent_changes" in attributes
        assert attributes["recent_changes"]["added"] == 1
        assert attributes["recent_changes"]["removed"] == 1
        assert attributes["recent_changes"]["modified"] == 2

    def test_icon_no_data(self, mock_coordinator):
        """Test icon with no data."""
        mock_coordinator.data = None
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.icon == "mdi:shield-outline"

    def test_icon_no_rules(self, mock_coordinator):
        """Test icon with no rules."""
        mock_coordinator.data = {"rule_count": {"total": 0, "active": 0}}
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.icon == "mdi:shield-outline"

    def test_icon_no_active_rules(self, mock_coordinator):
        """Test icon with no active rules."""
        mock_coordinator.data = {"rule_count": {"total": 5, "active": 0}}
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.icon == "mdi:shield-off"

    def test_icon_few_active_rules(self, mock_coordinator):
        """Test icon with few active rules."""
        mock_coordinator.data = {"rule_count": {"total": 10, "active": 3}}
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.icon == "mdi:shield-check"

    def test_icon_many_active_rules(self, mock_coordinator):
        """Test icon with many active rules."""
        mock_coordinator.data = {"rule_count": {"total": 10, "active": 8}}
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        assert sensor.icon == "mdi:shield"

    def test_device_info(self, mock_coordinator):
        """Test device info generation."""
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        device_info = sensor._get_device_info()
        
        assert device_info["identifiers"] == {(DOMAIN, "box-123")}
        assert device_info["name"] == "Firewalla Gold"
        assert device_info["manufacturer"] == "Firewalla"
        assert device_info["model"] == "Firewalla Gold"
        assert device_info["sw_version"] == "1.975"

    def test_device_info_unknown_model(self, mock_coordinator):
        """Test device info with unknown model."""
        mock_coordinator.data["box_info"]["model"] = "unknown"
        sensor = FirewallaRulesSensor(mock_coordinator)
        
        device_info = sensor._get_device_info()
        
        assert device_info["model"] == "Firewalla Unknown"


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(self, mock_hass, mock_config_entry, mock_coordinator):
        """Test successful setup of sensor entities."""
        mock_hass.data[DOMAIN][mock_config_entry.entry_id] = mock_coordinator
        
        async_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        # Should be called with list containing one sensor entity
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        
        assert len(entities) == 1
        assert isinstance(entities[0], FirewallaRulesSensor)

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_coordinator(self, mock_hass, mock_config_entry):
        """Test setup with missing coordinator."""
        # Don't add coordinator to hass.data
        
        async_add_entities = AsyncMock()
        
        with pytest.raises(HomeAssistantError, match="Coordinator not found"):
            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

    @pytest.mark.asyncio
    async def test_async_setup_entry_sensor_creation_error(self, mock_hass, mock_config_entry, mock_coordinator):
        """Test setup when sensor creation fails."""
        mock_hass.data[DOMAIN][mock_config_entry.entry_id] = mock_coordinator
        
        async_add_entities = AsyncMock()
        
        # Mock FirewallaRulesSensor to raise an exception
        with patch('custom_components.firewalla.sensor.FirewallaRulesSensor', side_effect=Exception("Test error")):
            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        # Should still be called with empty list
        async_add_entities.assert_called_once_with([], True)