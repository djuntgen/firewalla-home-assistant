"""Tests for Firewalla rule statistics sensor entities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.firewalla.sensor import (
    FirewallaRulesSensor,
    FirewallaTimeLimitSensor,
    async_setup_entry,
)
from custom_components.firewalla.const import DOMAIN, ENTITY_ID_FORMATS
from custom_components.firewalla.coordinator import FirewallaDataUpdateCoordinator


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
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert sensor._attr_has_entity_name is True

    def test_unrecorded_attributes(self, mock_coordinator):
        """Test _unrecorded_attributes frozenset is defined."""
        sensor = FirewallaRulesSensor(mock_coordinator)

        assert isinstance(sensor._unrecorded_attributes, frozenset)
        assert "box_name" in sensor._unrecorded_attributes
        assert "box_model" in sensor._unrecorded_attributes
        assert "rules_by_type" in sensor._unrecorded_attributes

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

        assert isinstance(device_info, dict)
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

        assert isinstance(device_info, dict)
        assert device_info["model"] == "Firewalla Unknown"


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
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
    async def test_async_setup_entry_missing_coordinator(
        self, mock_hass, mock_config_entry
    ):
        """Test setup with missing coordinator."""
        # Use an entry_id that does not exist in hass.data
        mock_config_entry.entry_id = "nonexistent_entry"

        async_add_entities = AsyncMock()

        with pytest.raises(HomeAssistantError, match="Coordinator not found"):
            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

    @pytest.mark.asyncio
    async def test_async_setup_entry_sensor_creation_error(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test setup when sensor creation fails."""
        mock_hass.data[DOMAIN][mock_config_entry.entry_id] = mock_coordinator

        async_add_entities = AsyncMock()

        # Mock FirewallaRulesSensor to raise an exception
        with patch(
            "custom_components.firewalla.sensor.FirewallaRulesSensor",
            side_effect=Exception("Test error"),
        ):
            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should still be called with empty list (no True argument)
        async_add_entities.assert_called_once_with([])


class TestFirewallaTimeLimitSensor:
    def _make_coordinator(self, time_limits=None, groups=None):
        coordinator = MagicMock(spec=FirewallaDataUpdateCoordinator)
        coordinator.data = {
            "time_limits": time_limits or {},
            "groups": groups or {},
            "box_info": {"gid": "test-box", "name": "Test Box", "model": "gold"},
        }
        coordinator.last_update_success = True
        coordinator.box_gid = "test-box"
        return coordinator

    def test_init(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {
            "r1": {"app": "roblox", "quota": 60, "used": 61, "remaining": 0, "reached": True,
                   "paused": False, "schedule_display": "daily at 00:00 all day", "hit_count": 8789}}}}
        groups = {"32": {"name": "Bob", "is_user_group": True, "user_id": "box:33",
                         "device_count": 5, "devices": [], "internet_block_rule_id": None,
                         "internet_blocked": False, "rule_count": 0, "download": 0, "upload": 0, "group_rules": {}}}
        coordinator = self._make_coordinator(time_limits=time_limits, groups=groups)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        assert sensor._attr_unique_id == "firewalla_timelimit_33_r1"
        assert sensor._attr_name == "Roblox"
        assert sensor._attr_has_entity_name is True
        assert sensor._attr_has_entity_name is True

    def test_native_value_remaining(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {
            "r1": {"app": "roblox", "quota": 60, "used": 45, "remaining": 15, "reached": False,
                   "paused": False, "schedule_display": None, "hit_count": 0}}}}
        coordinator = self._make_coordinator(time_limits=time_limits)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        assert sensor.native_value == 15

    def test_native_value_missing(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        coordinator = self._make_coordinator(time_limits={})
        sensor = FirewallaTimeLimitSensor(coordinator, "99", "r1")
        assert sensor.native_value == 0

    def test_icon_when_reached(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {
            "r1": {"app": "roblox", "quota": 60, "used": 61, "remaining": 0, "reached": True,
                   "paused": False, "schedule_display": None, "hit_count": 0}}}}
        coordinator = self._make_coordinator(time_limits=time_limits)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        assert sensor.icon == "mdi:timer-alert"

    def test_icon_when_not_reached(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {
            "r1": {"app": "roblox", "quota": 60, "used": 30, "remaining": 30, "reached": False,
                   "paused": False, "schedule_display": None, "hit_count": 0}}}}
        coordinator = self._make_coordinator(time_limits=time_limits)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        assert sensor.icon == "mdi:timer-outline"

    def test_available_true(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {
            "r1": {"app": "roblox", "quota": 60, "used": 45, "remaining": 15, "reached": False,
                   "paused": False, "schedule_display": None, "hit_count": 0}}}}
        coordinator = self._make_coordinator(time_limits=time_limits)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        assert sensor.available is True

    def test_unavailable_when_removed(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {}}}
        coordinator = self._make_coordinator(time_limits=time_limits)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        assert sensor.available is False

    def test_extra_state_attributes(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        time_limits = {"33": {"user_name": "Bob", "user_id": "box:33", "affiliated_group": "32", "limits": {
            "r1": {"app": "roblox", "quota": 60, "used": 61, "remaining": 0, "reached": True,
                   "paused": False, "schedule_display": "daily at 00:00 all day", "hit_count": 8789}}}}
        coordinator = self._make_coordinator(time_limits=time_limits)
        sensor = FirewallaTimeLimitSensor(coordinator, "33", "r1")
        attrs = sensor.extra_state_attributes
        assert attrs["quota_minutes"] == 60
        assert attrs["remaining_minutes"] == 0
        assert attrs["reached"] is True
        assert attrs["schedule"] == "daily at 00:00 all day"
        assert attrs["hit_count"] == 8789
        assert attrs["user_name"] == "Bob"

    def test_attributes_when_missing(self):
        from custom_components.firewalla.sensor import FirewallaTimeLimitSensor
        coordinator = self._make_coordinator(time_limits={})
        sensor = FirewallaTimeLimitSensor(coordinator, "99", "r1")
        attrs = sensor.extra_state_attributes
        assert attrs["user_scope_id"] == "99"
        assert attrs["rule_id"] == "r1"
