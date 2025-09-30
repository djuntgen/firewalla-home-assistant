"""Common test fixtures for Firewalla integration tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
import aiohttp

from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DOMAIN,
)


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Firewalla",
        data={
            CONF_MSP_URL: "https://test.firewalla.com",
            CONF_ACCESS_TOKEN: "test_token_123",
            CONF_BOX_GID: "test_box_gid_456",
            CONF_NAME: "Test Firewalla",
        },
        source="user",
        entry_id="test_entry_id",
        unique_id="test_box_gid_456",
    )


@pytest.fixture
def mock_box_info():
    """Return mock box info data."""
    return {
        "gid": "test_box_gid_456",
        "name": "Test Firewalla Gold",
        "model": "gold",
        "online": True,
        "version": "1.975",
        "lastSeen": 1648632679193,
        "firmwareVersion": "1.975",
    }


@pytest.fixture
def mock_devices_data():
    """Return mock devices data."""
    return {
        "aa:bb:cc:dd:ee:ff": {
            "mac": "aa:bb:cc:dd:ee:ff",
            "name": "Test Device 1",
            "hostname": "test-device-1",
            "ip": "192.168.1.100",
            "online": True,
            "lastActiveTimestamp": 1648632679.193,
            "deviceClass": "laptop",
        },
        "11:22:33:44:55:66": {
            "mac": "11:22:33:44:55:66",
            "name": "Gaming Console",
            "hostname": "xbox-series-x",
            "ip": "192.168.1.101",
            "online": False,
            "lastActiveTimestamp": 1648632000.000,
            "deviceClass": "gaming_console",
        },
    }


@pytest.fixture
def mock_rules_data():
    """Return mock rules data."""
    return {
        "rule_123": {
            "rid": "rule_123",
            "type": "internet",
            "target": "mac:aa:bb:cc:dd:ee:ff",
            "disabled": False,
            "paused": False,
            "action": "block",
            "description": "Block internet for Test Device 1",
            "created": "2024-01-01T12:00:00Z",
        },
        "rule_456": {
            "rid": "rule_456",
            "type": "gaming",
            "target": "mac:11:22:33:44:55:66",
            "disabled": False,
            "paused": True,
            "action": "block",
            "description": "Gaming pause for Gaming Console",
            "created": "2024-01-01T13:00:00Z",
        },
    }


@pytest.fixture
def mock_coordinator_data(mock_box_info, mock_devices_data, mock_rules_data):
    """Return mock coordinator data."""
    return {
        "box_info": mock_box_info,
        "devices": mock_devices_data,
        "rules": mock_rules_data,
        "last_updated": "2024-01-01T14:00:00Z",
    }


@pytest.fixture
def mock_aiohttp_session():
    """Return a mock aiohttp session."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    
    # Mock successful API responses
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock()
    mock_response.text = AsyncMock(return_value="")
    
    session.request = AsyncMock(return_value=mock_response)
    return session


@pytest.fixture
def mock_hass():
    """Return a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {}}
    return hass


@pytest.fixture
def mock_api_responses():
    """Return mock API response data."""
    return {
        "boxes": {
            "success": True,
            "data": {
                "test_box_gid_456": {
                    "gid": "test_box_gid_456",
                    "name": "Test Firewalla Gold",
                    "model": "gold",
                    "online": True,
                    "version": "1.975",
                }
            }
        },
        "box_info": {
            "success": True,
            "data": {
                "gid": "test_box_gid_456",
                "name": "Test Firewalla Gold",
                "model": "gold",
                "online": True,
                "version": "1.975",
                "lastSeen": 1648632679193,
            }
        },
        "devices": {
            "success": True,
            "data": {
                "aa:bb:cc:dd:ee:ff": {
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "name": "Test Device 1",
                    "ip": "192.168.1.100",
                    "online": True,
                    "lastActiveTimestamp": 1648632679.193,
                    "deviceClass": "laptop",
                }
            }
        },
        "rules": {
            "success": True,
            "data": {
                "rule_123": {
                    "rid": "rule_123",
                    "type": "internet",
                    "target": "mac:aa:bb:cc:dd:ee:ff",
                    "disabled": False,
                    "paused": False,
                    "action": "block",
                    "description": "Block internet for Test Device 1",
                }
            }
        },
        "create_rule": {
            "success": True,
            "data": {
                "id": "new_rule_789",
                "rid": "new_rule_789",
                "type": "internet",
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "disabled": False,
                "paused": False,
                "action": "block",
                "description": "New block rule",
            }
        },
        "pause_rule": {
            "success": True,
            "data": {"message": "Rule paused successfully"}
        },
        "unpause_rule": {
            "success": True,
            "data": {"message": "Rule unpaused successfully"}
        },
    }