"""Tests for Firewalla coordinator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.firewalla.coordinator import (
    FirewallaMSPClient,
    FirewallaDataUpdateCoordinator,
)
from custom_components.firewalla.const import API_ENDPOINTS


class TestFirewallaMSPClient:
    """Test the Firewalla MSP API client."""

    @pytest.fixture
    def client(self, mock_aiohttp_session):
        """Create a test MSP client."""
        return FirewallaMSPClient(
            session=mock_aiohttp_session,
            msp_url="https://test.firewalla.com",
            access_token="test_token_123",
        )

    @pytest.mark.asyncio
    async def test_authenticate_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful authentication."""
        # Mock successful boxes response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["boxes"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.authenticate()
        
        assert result is True
        assert client.is_authenticated is True
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self, client, mock_aiohttp_session):
        """Test authentication with invalid credentials."""
        # Mock 401 response
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.authenticate()
        
        assert result is False
        assert client.is_authenticated is False

    @pytest.mark.asyncio
    async def test_authenticate_connection_error(self, client, mock_aiohttp_session):
        """Test authentication with connection error."""
        # Mock connection error
        mock_aiohttp_session.request.side_effect = aiohttp.ClientConnectorError(
            connection_key=None, os_error=None
        )

        result = await client.authenticate()
        
        assert result is False
        assert client.is_authenticated is False

    @pytest.mark.asyncio
    async def test_make_request_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful API request."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["boxes"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client._make_request("GET", "/test/endpoint")
        
        assert result == mock_api_responses["boxes"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_retry_on_timeout(self, client, mock_aiohttp_session):
        """Test request retry on timeout."""
        # Mock timeout then success
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"success": True}
        
        mock_aiohttp_session.request.side_effect = [
            aiohttp.ServerTimeoutError(),
            mock_response.__aenter__(),
        ]

        result = await client._make_request("GET", "/test/endpoint")
        
        assert result == {"success": True}
        assert mock_aiohttp_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_auth_refresh(self, client, mock_aiohttp_session, mock_api_responses):
        """Test automatic authentication refresh on 401."""
        # Mock 401 then success after refresh
        mock_401_response = AsyncMock()
        mock_401_response.status = 401
        
        mock_success_response = AsyncMock()
        mock_success_response.status = 200
        mock_success_response.json.return_value = mock_api_responses["boxes"]
        
        mock_aiohttp_session.request.return_value.__aenter__.side_effect = [
            mock_401_response,  # First call gets 401
            mock_success_response,  # Auth refresh call
            mock_success_response,  # Retry call succeeds
        ]

        result = await client._make_request("GET", "/test/endpoint")
        
        assert result == mock_api_responses["boxes"]
        assert mock_aiohttp_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_get_boxes(self, client, mock_aiohttp_session, mock_api_responses):
        """Test get_boxes method."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["boxes"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.get_boxes()
        
        assert result == mock_api_responses["boxes"]
        # Verify correct endpoint was called
        call_args = mock_aiohttp_session.request.call_args
        assert API_ENDPOINTS["boxes"] in call_args[0][1]

    @pytest.mark.asyncio
    async def test_get_devices(self, client, mock_aiohttp_session, mock_api_responses):
        """Test get_devices method."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["devices"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.get_devices("test_box_gid")
        
        assert result == mock_api_responses["devices"]
        # Verify correct endpoint was called with box GID
        call_args = mock_aiohttp_session.request.call_args
        assert "test_box_gid" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_create_rule(self, client, mock_aiohttp_session, mock_api_responses):
        """Test create_rule method."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["create_rule"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        rule_data = {
            "type": "internet",
            "target": "mac:aa:bb:cc:dd:ee:ff",
            "action": "block",
            "description": "Test rule",
        }

        result = await client.create_rule("test_box_gid", rule_data)
        
        assert result == mock_api_responses["create_rule"]
        # Verify POST method was used
        call_args = mock_aiohttp_session.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == rule_data


class TestFirewallaDataUpdateCoordinator:
    """Test the Firewalla data update coordinator."""

    @pytest.fixture
    def coordinator(self, mock_hass, mock_aiohttp_session):
        """Create a test coordinator."""
        return FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=mock_aiohttp_session,
            msp_url="https://test.firewalla.com",
            access_token="test_token_123",
            box_gid="test_box_gid_456",
        )

    @pytest.mark.asyncio
    async def test_update_data_success(self, coordinator, mock_api_responses):
        """Test successful data update."""
        # Mock API client methods
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.get_box_info = AsyncMock(return_value=mock_api_responses["box_info"])
        coordinator.api.get_devices = AsyncMock(return_value=mock_api_responses["devices"])
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])
        coordinator.api.is_authenticated = True

        result = await coordinator._async_update_data()
        
        assert "box_info" in result
        assert "devices" in result
        assert "rules" in result
        assert result["box_info"] == mock_api_responses["box_info"]["data"]

    @pytest.mark.asyncio
    async def test_update_data_auth_failure(self, coordinator):
        """Test data update with authentication failure."""
        # Mock authentication failure
        coordinator.api.authenticate = AsyncMock(return_value=False)
        coordinator.api.is_authenticated = False

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_data_api_error(self, coordinator):
        """Test data update with API error."""
        # Mock API error
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.get_box_info = AsyncMock(side_effect=HomeAssistantError("API Error"))
        coordinator.api.is_authenticated = True

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_process_devices_data(self, coordinator, mock_devices_data):
        """Test device data processing."""
        processed = coordinator._process_devices_data(mock_devices_data)
        
        assert len(processed) == 2
        assert "aa:bb:cc:dd:ee:ff" in processed
        assert processed["aa:bb:cc:dd:ee:ff"]["name"] == "Test Device 1"
        assert processed["aa:bb:cc:dd:ee:ff"]["online"] is True

    @pytest.mark.asyncio
    async def test_process_devices_data_invalid(self, coordinator):
        """Test device data processing with invalid data."""
        invalid_data = {
            "device1": "invalid_string",  # Should be dict
            "device2": {"mac": "aa:bb:cc:dd:ee:ff", "name": "Valid Device"},
        }
        
        processed = coordinator._process_devices_data(invalid_data)
        
        # Should only process valid device
        assert len(processed) == 1
        assert "device2" in processed

    @pytest.mark.asyncio
    async def test_process_rules_data(self, coordinator, mock_rules_data):
        """Test rules data processing."""
        processed = coordinator._process_rules_data(mock_rules_data)
        
        assert len(processed) == 2
        assert "rule_123" in processed
        assert processed["rule_123"]["type"] == "internet"
        assert processed["rule_123"]["paused"] is False

    @pytest.mark.asyncio
    async def test_create_rule_success(self, coordinator, mock_api_responses):
        """Test successful rule creation."""
        coordinator.api.create_rule = AsyncMock(return_value=mock_api_responses["create_rule"])
        coordinator.async_request_refresh = AsyncMock()

        rule_data = {
            "type": "internet",
            "target": "aa:bb:cc:dd:ee:ff",  # Will be prefixed with "mac:"
            "action": "block",
            "description": "Test rule",
        }

        result = await coordinator.async_create_rule(rule_data)
        
        assert result == mock_api_responses["create_rule"]["data"]
        # Verify MAC prefix was added
        coordinator.api.create_rule.assert_called_once()
        call_args = coordinator.api.create_rule.call_args[0][1]
        assert call_args["target"] == "mac:aa:bb:cc:dd:ee:ff"

    @pytest.mark.asyncio
    async def test_create_rule_missing_fields(self, coordinator):
        """Test rule creation with missing required fields."""
        rule_data = {
            "type": "internet",
            # Missing target and action
        }

        with pytest.raises(ValueError, match="Missing required field"):
            await coordinator.async_create_rule(rule_data)

    @pytest.mark.asyncio
    async def test_pause_rule_success(self, coordinator, mock_api_responses):
        """Test successful rule pausing."""
        coordinator.api.pause_rule = AsyncMock(return_value=mock_api_responses["pause_rule"])
        coordinator.async_request_refresh = AsyncMock()

        result = await coordinator.async_pause_rule("rule_123")
        
        assert result == mock_api_responses["pause_rule"]
        coordinator.api.pause_rule.assert_called_once_with("test_box_gid_456", "rule_123")

    @pytest.mark.asyncio
    async def test_pause_rule_empty_id(self, coordinator):
        """Test rule pausing with empty rule ID."""
        with pytest.raises(ValueError, match="Rule ID cannot be empty"):
            await coordinator.async_pause_rule("")

    @pytest.mark.asyncio
    async def test_unpause_rule_success(self, coordinator, mock_api_responses):
        """Test successful rule unpausing."""
        coordinator.api.unpause_rule = AsyncMock(return_value=mock_api_responses["unpause_rule"])
        coordinator.async_request_refresh = AsyncMock()

        result = await coordinator.async_unpause_rule("rule_123")
        
        assert result == mock_api_responses["unpause_rule"]
        coordinator.api.unpause_rule.assert_called_once_with("test_box_gid_456", "rule_123")

    @pytest.mark.asyncio
    async def test_get_box_devices_cached(self, coordinator, mock_coordinator_data):
        """Test getting devices from cached data."""
        coordinator.data = mock_coordinator_data
        
        devices = await coordinator.async_get_box_devices()
        
        assert devices == mock_coordinator_data["devices"]

    @pytest.mark.asyncio
    async def test_get_box_devices_api_call(self, coordinator, mock_api_responses):
        """Test getting devices via API call when no cached data."""
        coordinator.data = None
        coordinator.api.get_devices = AsyncMock(return_value=mock_api_responses["devices"])
        
        devices = await coordinator.async_get_box_devices()
        
        coordinator.api.get_devices.assert_called_once_with("test_box_gid_456")

    @pytest.mark.asyncio
    async def test_get_rules_with_query(self, coordinator, mock_api_responses):
        """Test getting rules with query parameter."""
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])
        
        rules = await coordinator.async_get_rules("status:active")
        
        coordinator.api.get_rules.assert_called_once_with("test_box_gid_456", "status:active")