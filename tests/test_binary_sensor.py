"""Tests for Firewalla user activity binary sensor."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from custom_components.firewalla.binary_sensor import FirewallaUserActivitySensor
from custom_components.firewalla.coordinator import FirewallaDataUpdateCoordinator


class TestFirewallaUserActivitySensor:
    def _make_coordinator(self, groups=None):
        coordinator = MagicMock(spec=FirewallaDataUpdateCoordinator)
        coordinator.data = {
            "groups": groups or {},
            "box_info": {"gid": "test-box", "name": "Test Box", "model": "gold"},
        }
        coordinator.last_update_success = True
        coordinator.box_gid = "test-box"
        return coordinator

    def test_init(self):
        groups = {"28": {"name": "Alice", "is_user_group": True, "active": True,
                         "devices": [], "total_download": 1000, "download_delta": 500,
                         "device_count": 5, "user_id": "box:29", "internet_block_rule_id": None,
                         "internet_blocked": False, "rule_count": 0, "download": 0, "upload": 0, "group_rules": {}}}
        coordinator = self._make_coordinator(groups=groups)
        sensor = FirewallaUserActivitySensor(coordinator, "28")
        assert sensor._attr_unique_id == "firewalla_user_28_active"
        assert sensor._attr_name == "Active"
        assert sensor._attr_has_entity_name is True

    def test_is_on_when_active(self):
        groups = {"28": {"name": "Alice", "is_user_group": True, "active": True,
                         "devices": [{"name": "Phone", "online": True, "total_download": 1000}],
                         "total_download": 1000, "download_delta": 5000,
                         "device_count": 1, "user_id": None, "internet_block_rule_id": None,
                         "internet_blocked": False, "rule_count": 0, "download": 0, "upload": 0, "group_rules": {}}}
        coordinator = self._make_coordinator(groups=groups)
        sensor = FirewallaUserActivitySensor(coordinator, "28")
        assert sensor.is_on is True

    def test_is_off_when_idle(self):
        groups = {"28": {"name": "Alice", "is_user_group": True, "active": False,
                         "devices": [{"name": "Phone", "online": True, "total_download": 1000}],
                         "total_download": 1000, "download_delta": 0,
                         "device_count": 1, "user_id": None, "internet_block_rule_id": None,
                         "internet_blocked": False, "rule_count": 0, "download": 0, "upload": 0, "group_rules": {}}}
        coordinator = self._make_coordinator(groups=groups)
        sensor = FirewallaUserActivitySensor(coordinator, "28")
        assert sensor.is_on is False

    def test_available(self):
        groups = {"28": {"name": "Alice", "is_user_group": True, "active": False,
                         "devices": [], "total_download": 0, "download_delta": 0,
                         "device_count": 0, "user_id": None, "internet_block_rule_id": None,
                         "internet_blocked": False, "rule_count": 0, "download": 0, "upload": 0, "group_rules": {}}}
        coordinator = self._make_coordinator(groups=groups)
        sensor = FirewallaUserActivitySensor(coordinator, "28")
        assert sensor.available is True

    def test_unavailable_missing_group(self):
        coordinator = self._make_coordinator(groups={})
        sensor = FirewallaUserActivitySensor(coordinator, "99")
        assert sensor.available is False

    def test_extra_state_attributes(self):
        devices = [
            {"name": "Phone", "online": True, "mac": "AA:BB", "type": "phone", "ip": "1.1.1.1", "total_download": 1000},
            {"name": "Tablet", "online": False, "mac": "CC:DD", "type": "tablet", "ip": "1.1.1.2", "total_download": 500},
        ]
        groups = {"28": {"name": "Alice", "is_user_group": True, "active": True,
                         "devices": devices, "total_download": 1500, "download_delta": 2048,
                         "device_count": 2, "user_id": None, "internet_block_rule_id": None,
                         "internet_blocked": False, "rule_count": 0, "download": 0, "upload": 0, "group_rules": {}}}
        coordinator = self._make_coordinator(groups=groups)
        sensor = FirewallaUserActivitySensor(coordinator, "28")
        attrs = sensor.extra_state_attributes
        assert attrs["online_devices"] == 1
        assert attrs["total_devices"] == 2
        assert attrs["active_devices"] == ["Phone"]
        assert attrs["download_delta_bytes"] == 2048
