"""Tests for Firewalla config flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.firewalla.config_flow import (
    ConfigFlow,
    CannotConnect,
    InvalidAuth,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_NO_DEVICES,
    ERROR_UNKNOWN,
)
from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DEFAULT_MSP_URL,
    DOMAIN,
)


class TestConfigFlow:
    """Test the Firewalla config flow."""

    @pytest.fixture
    def mock_setup_entry(self):
        """Mock setup entry."""
        with patch(
            "custom_components.firewalla.async_setup_entry", return_value=True
        ) as mock_setup:
            yield mock_setup

    @pytest.fixture
    def flow(self, hass):
        """Create a config flow instance."""
        return ConfigFlow()

    @pytest.mark.asyncio
    async def test_user_step_form(self, hass):
        """Test the user step shows the form."""
        flow = ConfigFlow()
        flow.hass = hass
        
        result = await flow.async_step_user()
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert CONF_MSP_URL in result["data_schema"].schema
        assert CONF_ACCESS_TOKEN in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_user_step_invalid_auth(self, hass):
        """Test user step with invalid authentication."""
        flow = ConfigFlow()
        flow.hass = hass
        
        with patch.object(flow, "_authenticate_msp", side_effect=InvalidAuth("Invalid token")):
            result = await flow.async_step_user({
                CONF_MSP_URL: "https://test.firewalla.com",
                CONF_ACCESS_TOKEN: "invalid_token",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == ERROR_INVALID_AUTH

    @pytest.mark.asyncio
    async def test_user_step_cannot_connect(self, hass):
        """Test user step with connection error."""
        flow = ConfigFlow()
        flow.hass = hass
        
        with patch.object(flow, "_authenticate_msp", side_effect=CannotConnect("Connection failed")):
            result = await flow.async_step_user({
                CONF_MSP_URL: "https://test.firewalla.com",
                CONF_ACCESS_TOKEN: "valid_token",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == ERROR_CANNOT_CONNECT

    @pytest.mark.asyncio
    async def test_user_step_no_devices(self, hass):
        """Test user step with no devices found."""
        flow = ConfigFlow()
        flow.hass = hass
        
        with patch.object(flow, "_authenticate_msp"), \
             patch.object(flow, "_get_available_devices"):
            flow._available_devices = {}  # No devices
            
            result = await flow.async_step_user({
                CONF_MSP_URL: "https://test.firewalla.com",
                CONF_ACCESS_TOKEN: "valid_token",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == ERROR_NO_DEVICES

    @pytest.mark.asyncio
    async def test_user_step_success_with_devices(self, hass):
        """Test user step success with devices found."""
        flow = ConfigFlow()
        flow.hass = hass
        
        mock_devices = {
            "box_gid_1": {"name": "Firewalla Gold", "model": "gold"},
            "box_gid_2": {"name": "Firewalla Purple", "model": "purple"},
        }
        
        with patch.object(flow, "_authenticate_msp"), \
             patch.object(flow, "_get_available_devices"):
            flow._available_devices = mock_devices
            
            result = await flow.async_step_user({
                CONF_MSP_URL: "https://test.firewalla.com",
                CONF_ACCESS_TOKEN: "valid_token",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "device_selection"

    @pytest.mark.asyncio
    async def test_user_step_empty_token(self, hass):
        """Test user step with empty access token."""
        flow = ConfigFlow()
        flow.hass = hass
        
        result = await flow.async_step_user({
            CONF_MSP_URL: "https://test.firewalla.com",
            CONF_ACCESS_TOKEN: "",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == ERROR_INVALID_AUTH

    @pytest.mark.asyncio
    async def test_user_step_short_token(self, hass):
        """Test user step with too short access token."""
        flow = ConfigFlow()
        flow.hass = hass
        
        result = await flow.async_step_user({
            CONF_MSP_URL: "https://test.firewalla.com",
            CONF_ACCESS_TOKEN: "short",  # Less than 10 characters
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == ERROR_INVALID_AUTH

    @pytest.mark.asyncio
    async def test_device_selection_step_form(self, hass):
        """Test device selection step shows form."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._available_devices = {
            "box_gid_1": {"name": "Firewalla Gold", "model": "gold"},
            "box_gid_2": {"name": "Firewalla Purple", "model": "purple"},
        }
        
        result = await flow.async_step_device_selection()
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "device_selection"
        assert CONF_BOX_GID in result["data_schema"].schema
        assert CONF_NAME in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_device_selection_success(self, hass, mock_setup_entry):
        """Test successful device selection and config entry creation."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        flow._available_devices = {
            "box_gid_1": {"name": "Firewalla Gold", "model": "gold"},
        }
        
        with patch.object(flow, "async_set_unique_id"), \
             patch.object(flow, "_abort_if_unique_id_configured"):
            
            result = await flow.async_step_device_selection({
                CONF_BOX_GID: "box_gid_1",
                CONF_NAME: "My Firewalla",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == "My Firewalla"
        assert result["data"][CONF_MSP_URL] == "https://test.firewalla.com"
        assert result["data"][CONF_ACCESS_TOKEN] == "valid_token"
        assert result["data"][CONF_BOX_GID] == "box_gid_1"

    @pytest.mark.asyncio
    async def test_device_selection_empty_name(self, hass):
        """Test device selection with empty name."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._available_devices = {
            "box_gid_1": {"name": "Firewalla Gold", "model": "gold"},
        }
        
        result = await flow.async_step_device_selection({
            CONF_BOX_GID: "box_gid_1",
            CONF_NAME: "",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert CONF_NAME in result["errors"]

    @pytest.mark.asyncio
    async def test_device_selection_invalid_gid(self, hass):
        """Test device selection with invalid box GID."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._available_devices = {
            "box_gid_1": {"name": "Firewalla Gold", "model": "gold"},
        }
        
        result = await flow.async_step_device_selection({
            CONF_BOX_GID: "invalid_gid",
            CONF_NAME: "My Firewalla",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == ERROR_NO_DEVICES

    @pytest.mark.asyncio
    async def test_authenticate_msp_success(self, hass):
        """Test successful MSP authentication."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_client = AsyncMock()
        mock_client.authenticate.return_value = True
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            await flow._authenticate_msp()
            
            mock_client.authenticate.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_msp_invalid_url(self, hass):
        """Test MSP authentication with invalid URL."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "invalid_url"  # No http/https prefix
        flow._access_token = "valid_token"
        
        with pytest.raises(InvalidAuth, match="MSP URL must start with"):
            await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_authenticate_msp_connection_error(self, hass):
        """Test MSP authentication with connection error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ClientConnectorError(
            connection_key=None, os_error=None
        )
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(CannotConnect):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_authenticate_msp_401_error(self, hass):
        """Test MSP authentication with 401 error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "invalid_token"
        
        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ClientResponseError(
            request_info=None, history=None, status=401, message="Unauthorized"
        )
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(InvalidAuth, match="Invalid access token"):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_authenticate_msp_403_error(self, hass):
        """Test MSP authentication with 403 error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ClientResponseError(
            request_info=None, history=None, status=403, message="Forbidden"
        )
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(InvalidAuth, match="Access forbidden"):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_get_available_devices_success(self, hass):
        """Test successful device retrieval."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_boxes_response = {
            "data": [
                {"gid": "box_1", "name": "Firewalla Gold", "model": "gold"},
                {"gid": "box_2", "name": "Firewalla Purple", "model": "purple"},
            ]
        }
        
        mock_client = AsyncMock()
        mock_client.get_boxes.return_value = mock_boxes_response
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            await flow._get_available_devices()
            
            assert len(flow._available_devices) == 2
            assert "box_1" in flow._available_devices
            assert flow._available_devices["box_1"]["name"] == "Firewalla Gold"

    @pytest.mark.asyncio
    async def test_get_available_devices_dict_format(self, hass):
        """Test device retrieval with dict format response."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_boxes_response = {
            "data": {
                "box_1": {"name": "Firewalla Gold", "model": "gold"},
                "box_2": {"name": "Firewalla Purple", "model": "purple"},
            }
        }
        
        mock_client = AsyncMock()
        mock_client.get_boxes.return_value = mock_boxes_response
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            await flow._get_available_devices()
            
            assert len(flow._available_devices) == 2
            assert "box_1" in flow._available_devices
            assert flow._available_devices["box_1"]["gid"] == "box_1"

    @pytest.mark.asyncio
    async def test_get_available_devices_empty_response(self, hass):
        """Test device retrieval with empty response."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_boxes_response = {"data": {}}
        
        mock_client = AsyncMock()
        mock_client.get_boxes.return_value = mock_boxes_response
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            await flow._get_available_devices()
            
            assert len(flow._available_devices) == 0

    @pytest.mark.asyncio
    async def test_get_available_devices_connection_error(self, hass):
        """Test device retrieval with connection error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_client = AsyncMock()
        mock_client.get_boxes.side_effect = aiohttp.ClientConnectorError(
            connection_key=None, os_error=None
        )
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(CannotConnect):
                await flow._get_available_devices()