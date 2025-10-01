"""Tests for Firewalla rule management config flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.firewalla.config_flow import (
    ConfigFlow,
    CannotConnect,
    InvalidAuth,
    RuleAccessFailed,
)
from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DEFAULT_MSP_URL_FORMAT,
    DOMAIN,
)


@pytest.fixture
def mock_setup_entry():
    """Mock setup entry."""
    with patch(
        "custom_components.firewalla.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_msp_client():
    """Mock MSP client."""
    with patch(
        "custom_components.firewalla.config_flow.FirewallaMSPClient"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client.authenticate = AsyncMock(return_value=True)
        mock_client.get_rules = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp session."""
    with patch(
        "custom_components.firewalla.config_flow.async_get_clientsession"
    ) as mock_session:
        yield mock_session


class TestConfigFlow:
    """Test the Firewalla rule management config flow."""

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
    async def test_user_step_invalid_url_format(self, hass):
        """Test user step with invalid MSP URL format."""
        flow = ConfigFlow()
        flow.hass = hass
        
        result = await flow.async_step_user({
            CONF_MSP_URL: "invalid-url",
            CONF_ACCESS_TOKEN: "test_token_123",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"][CONF_MSP_URL] == "invalid_url_format"

    @pytest.mark.asyncio
    async def test_user_step_empty_token(self, hass):
        """Test user step with empty access token."""
        flow = ConfigFlow()
        flow.hass = hass
        
        result = await flow.async_step_user({
            CONF_MSP_URL: "test.firewalla.net",
            CONF_ACCESS_TOKEN: "",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"][CONF_ACCESS_TOKEN] == "auth_failed"

    @pytest.mark.asyncio
    async def test_user_step_short_token(self, hass):
        """Test user step with too short access token."""
        flow = ConfigFlow()
        flow.hass = hass
        
        result = await flow.async_step_user({
            CONF_MSP_URL: "test.firewalla.net",
            CONF_ACCESS_TOKEN: "short",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"][CONF_ACCESS_TOKEN] == "auth_failed"

    @pytest.mark.asyncio
    async def test_user_step_single_box_success(self, hass, mock_setup_entry, mock_msp_client, mock_aiohttp_session):
        """Test successful user step with single box."""
        flow = ConfigFlow()
        flow.hass = hass
        
        # Mock single box scenario
        flow._available_boxes = {
            "box-123": {
                "gid": "box-123",
                "name": "Firewalla Gold",
                "model": "gold",
            }
        }
        
        with patch.object(flow, '_authenticate_msp', new_callable=AsyncMock), \
             patch.object(flow, '_get_available_boxes', new_callable=AsyncMock), \
             patch.object(flow, '_test_rule_access', new_callable=AsyncMock), \
             patch.object(flow, 'async_set_unique_id'), \
             patch.object(flow, '_abort_if_unique_id_configured'):
            
            result = await flow.async_step_user({
                CONF_MSP_URL: "test.firewalla.net",
                CONF_ACCESS_TOKEN: "test_token_123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == "Firewalla Gold"
        assert result["data"][CONF_MSP_URL] == "test.firewalla.net"
        assert result["data"][CONF_ACCESS_TOKEN] == "test_token_123"
        assert result["data"][CONF_BOX_GID] == "box-123"

    @pytest.mark.asyncio
    async def test_user_step_multiple_boxes(self, hass, mock_msp_client, mock_aiohttp_session):
        """Test user step with multiple boxes leads to box selection."""
        flow = ConfigFlow()
        flow.hass = hass
        
        # Mock multiple boxes scenario
        flow._available_boxes = {
            "box-123": {"gid": "box-123", "name": "Firewalla Gold", "model": "gold"},
            "box-456": {"gid": "box-456", "name": "Firewalla Purple", "model": "purple"},
        }
        
        with patch.object(flow, '_authenticate_msp', new_callable=AsyncMock), \
             patch.object(flow, '_get_available_boxes', new_callable=AsyncMock):
            
            result = await flow.async_step_user({
                CONF_MSP_URL: "test.firewalla.net",
                CONF_ACCESS_TOKEN: "test_token_123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "box_selection"

    @pytest.mark.asyncio
    async def test_user_step_no_boxes(self, hass, mock_msp_client, mock_aiohttp_session):
        """Test user step with no boxes found."""
        flow = ConfigFlow()
        flow.hass = hass
        
        # Mock no boxes scenario
        flow._available_boxes = {}
        
        with patch.object(flow, '_authenticate_msp', new_callable=AsyncMock), \
             patch.object(flow, '_get_available_boxes', new_callable=AsyncMock):
            
            result = await flow.async_step_user({
                CONF_MSP_URL: "test.firewalla.net",
                CONF_ACCESS_TOKEN: "test_token_123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "no_boxes"

    @pytest.mark.asyncio
    async def test_user_step_auth_failed(self, hass, mock_aiohttp_session):
        """Test user step with authentication failure."""
        flow = ConfigFlow()
        flow.hass = hass
        
        with patch.object(flow, '_authenticate_msp', side_effect=InvalidAuth("Auth failed")):
            result = await flow.async_step_user({
                CONF_MSP_URL: "test.firewalla.net",
                CONF_ACCESS_TOKEN: "test_token_123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "auth_failed"

    @pytest.mark.asyncio
    async def test_user_step_connection_failed(self, hass, mock_aiohttp_session):
        """Test user step with connection failure."""
        flow = ConfigFlow()
        flow.hass = hass
        
        with patch.object(flow, '_authenticate_msp', side_effect=CannotConnect("Connection failed")):
            result = await flow.async_step_user({
                CONF_MSP_URL: "test.firewalla.net",
                CONF_ACCESS_TOKEN: "test_token_123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "connection_failed"

    @pytest.mark.asyncio
    async def test_user_step_rule_access_failed(self, hass, mock_aiohttp_session):
        """Test user step with rule access failure."""
        flow = ConfigFlow()
        flow.hass = hass
        
        with patch.object(flow, '_authenticate_msp', new_callable=AsyncMock), \
             patch.object(flow, '_get_available_boxes', new_callable=AsyncMock), \
             patch.object(flow, '_test_rule_access', side_effect=RuleAccessFailed("Rule access failed")):
            
            flow._available_boxes = {
                "box-123": {"gid": "box-123", "name": "Firewalla Gold", "model": "gold"}
            }
            
            result = await flow.async_step_user({
                CONF_MSP_URL: "test.firewalla.net",
                CONF_ACCESS_TOKEN: "test_token_123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "rule_access_failed"

    @pytest.mark.asyncio
    async def test_user_step_data_persistence(self, hass):
        """Test that user input is preserved on validation failures."""
        flow = ConfigFlow()
        flow.hass = hass
        
        # First call with invalid URL
        result = await flow.async_step_user({
            CONF_MSP_URL: "invalid-url",
            CONF_ACCESS_TOKEN: "test_token_123",
        })
        
        # Check that the token is preserved in the form
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        schema_dict = {str(key): key.default() for key in result["data_schema"].schema}
        assert schema_dict[CONF_ACCESS_TOKEN] == "test_token_123"

    @pytest.mark.asyncio
    async def test_box_selection_step_form(self, hass):
        """Test the box selection step shows the form."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._available_boxes = {
            "box-123": {"gid": "box-123", "name": "Firewalla Gold", "model": "gold"},
            "box-456": {"gid": "box-456", "name": "Firewalla Purple", "model": "purple"},
        }
        
        result = await flow.async_step_box_selection()
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "box_selection"
        assert CONF_BOX_GID in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_box_selection_success(self, hass, mock_setup_entry):
        """Test successful box selection."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        flow._available_boxes = {
            "box-123": {"gid": "box-123", "name": "Firewalla Gold", "model": "gold"},
        }
        
        with patch.object(flow, '_test_rule_access', new_callable=AsyncMock), \
             patch.object(flow, 'async_set_unique_id'), \
             patch.object(flow, '_abort_if_unique_id_configured'):
            
            result = await flow.async_step_box_selection({
                CONF_BOX_GID: "box-123",
            })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == "Firewalla Gold"
        assert result["data"][CONF_BOX_GID] == "box-123"

    @pytest.mark.asyncio
    async def test_box_selection_invalid_box(self, hass):
        """Test box selection with invalid box GID."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._available_boxes = {
            "box-123": {"gid": "box-123", "name": "Firewalla Gold", "model": "gold"},
        }
        
        result = await flow.async_step_box_selection({
            CONF_BOX_GID: "box-999",
        })
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "no_boxes"

    def test_validate_msp_url_valid(self):
        """Test MSP URL validation with valid URLs."""
        flow = ConfigFlow()
        
        valid_urls = [
            "test.firewalla.net",
            "my-domain.firewalla.net",
            "company123.firewalla.net",
        ]
        
        for url in valid_urls:
            assert flow._validate_msp_url(url) is True

    def test_validate_msp_url_invalid(self):
        """Test MSP URL validation with invalid URLs."""
        flow = ConfigFlow()
        
        invalid_urls = [
            "",
            "invalid-url",
            "test.example.com",
            "https://test.firewalla.net",
            "test.firewalla.net/path",
            ".firewalla.net",
            "test..firewalla.net",
        ]
        
        for url in invalid_urls:
            assert flow._validate_msp_url(url) is False

    def test_validate_msp_url_with_protocol(self):
        """Test MSP URL validation strips protocol."""
        flow = ConfigFlow()
        
        assert flow._validate_msp_url("https://test.firewalla.net") is True
        assert flow._validate_msp_url("http://test.firewalla.net") is True

    def test_validate_msp_url_with_path(self):
        """Test MSP URL validation strips path."""
        flow = ConfigFlow()
        
        assert flow._validate_msp_url("test.firewalla.net/some/path") is True

    @pytest.mark.asyncio
    async def test_authenticate_msp_success(self, hass, mock_msp_client, mock_aiohttp_session):
        """Test successful MSP authentication."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        
        await flow._authenticate_msp()
        
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_authenticate_msp_connection_error(self, hass, mock_aiohttp_session):
        """Test MSP authentication with connection error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        
        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(side_effect=aiohttp.ClientConnectorError(None, None))
            mock_client_class.return_value = mock_client
            
            with pytest.raises(CannotConnect):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_authenticate_msp_auth_failed(self, hass, mock_aiohttp_session):
        """Test MSP authentication failure."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        
        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client
            
            with pytest.raises(InvalidAuth):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_get_available_boxes_success(self, hass, mock_msp_client, mock_aiohttp_session):
        """Test successful box retrieval."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        
        await flow._get_available_boxes()
        
        # Should create default box entry
        assert "default" in flow._available_boxes

    @pytest.mark.asyncio
    async def test_test_rule_access_success(self, hass, mock_msp_client, mock_aiohttp_session):
        """Test successful rule access test."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        
        await flow._test_rule_access()
        
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_test_rule_access_failed(self, hass, mock_aiohttp_session):
        """Test rule access test failure."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.net"
        flow._access_token = "test_token_123"
        
        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_rules = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with pytest.raises(RuleAccessFailed):
                await flow._test_rule_access()