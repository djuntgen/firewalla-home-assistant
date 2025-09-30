"""Tests for Firewalla integration error handling scenarios."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.firewalla.coordinator import FirewallaMSPClient, FirewallaDataUpdateCoordinator
from custom_components.firewalla.config_flow import ConfigFlow, CannotConnect, InvalidAuth


class TestAPIErrorHandling:
    """Test API error handling scenarios."""

    @pytest.fixture
    def client(self, mock_aiohttp_session):
        """Create a test MSP client."""
        return FirewallaMSPClient(
            session=mock_aiohttp_session,
            msp_url="https://test.firewalla.com",
            access_token="test_token_123",
        )

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self, client, mock_aiohttp_session):
        """Test handling of timeout errors with retry logic."""
        # Mock timeout on first call, success on second
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"success": True, "data": {}}
        
        mock_aiohttp_session.request.side_effect = [
            aiohttp.ServerTimeoutError(),
            mock_response.__aenter__(),
        ]

        result = await client._make_request("GET", "/test/endpoint")
        
        assert result == {"success": True, "data": {}}
        assert mock_aiohttp_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_connection_error_retry(self, client, mock_aiohttp_session):
        """Test connection error retry logic."""
        # Mock connection error on first two calls, success on third
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"success": True, "data": {}}
        
        mock_aiohttp_session.request.side_effect = [
            aiohttp.ClientConnectorError(connection_key=None, os_error=None),
            aiohttp.ClientConnectorError(connection_key=None, os_error=None),
            mock_response.__aenter__(),
        ]

        result = await client._make_request("GET", "/test/endpoint")
        
        assert result == {"success": True, "data": {}}
        assert mock_aiohttp_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limiting_handling(self, client, mock_aiohttp_session):
        """Test rate limiting (429) error handling."""
        # Mock 429 response then success
        mock_429_response = AsyncMock()
        mock_429_response.status = 429
        
        mock_success_response = AsyncMock()
        mock_success_response.status = 200
        mock_success_response.json.return_value = {"success": True, "data": {}}
        
        mock_aiohttp_session.request.return_value.__aenter__.side_effect = [
            mock_429_response,
            mock_success_response,
        ]

        result = await client._make_request("GET", "/test/endpoint")
        
        assert result == {"success": True, "data": {}}
        assert mock_aiohttp_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, client, mock_aiohttp_session):
        """Test behavior when max retries are exceeded."""
        # Mock timeout on all attempts
        mock_aiohttp_session.request.side_effect = aiohttp.ServerTimeoutError()

        with pytest.raises(HomeAssistantError, match="MSP API timeout after .* attempts"):
            await client._make_request("GET", "/test/endpoint")
        
        # Should have tried 3 times (RETRY_ATTEMPTS)
        assert mock_aiohttp_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_404_error_handling(self, client, mock_aiohttp_session):
        """Test 404 error handling."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text.return_value = "Not Found"
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        with pytest.raises(HomeAssistantError, match="MSP API endpoint not found"):
            await client._make_request("GET", "/nonexistent/endpoint")

    @pytest.mark.asyncio
    async def test_500_error_handling(self, client, mock_aiohttp_session):
        """Test 500 server error handling."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal Server Error"
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        with pytest.raises(HomeAssistantError, match="MSP API server error"):
            await client._make_request("GET", "/test/endpoint")

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, client, mock_aiohttp_session):
        """Test handling of invalid JSON responses."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.side_effect = aiohttp.ContentTypeError(
            request_info=None, history=None, message="Invalid JSON"
        )
        mock_response.text.return_value = "Invalid JSON response"
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client._make_request("GET", "/test/endpoint")
        
        # Should return text response wrapped in success format
        assert result == {"success": True, "data": "Invalid JSON response"}

    @pytest.mark.asyncio
    async def test_auth_refresh_failure(self, client, mock_aiohttp_session):
        """Test authentication refresh failure."""
        # Mock 401 response that persists after refresh attempt
        mock_401_response = AsyncMock()
        mock_401_response.status = 401
        
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_401_response

        with pytest.raises(ConfigEntryAuthFailed, match="MSP API authentication refresh failed"):
            await client._make_request("GET", "/test/endpoint")


class TestCoordinatorErrorHandling:
    """Test coordinator error handling scenarios."""

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
    async def test_update_data_auth_failure(self, coordinator):
        """Test data update with authentication failure."""
        coordinator.api.authenticate = AsyncMock(return_value=False)
        coordinator.api.is_authenticated = False

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_data_partial_failure(self, coordinator, mock_api_responses):
        """Test data update with partial API failures."""
        # Mock successful authentication and box info, but failed devices call
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.is_authenticated = True
        coordinator.api.get_box_info = AsyncMock(return_value=mock_api_responses["box_info"])
        coordinator.api.get_devices = AsyncMock(side_effect=HomeAssistantError("Devices API failed"))
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])

        with pytest.raises(UpdateFailed, match="Home Assistant error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_data_invalid_response_format(self, coordinator):
        """Test data update with invalid API response format."""
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.is_authenticated = True
        coordinator.api.get_box_info = AsyncMock(return_value={"invalid": "format"})  # Missing "data" key
        coordinator.api.get_devices = AsyncMock(return_value={"data": {}})
        coordinator.api.get_rules = AsyncMock(return_value={"data": {}})

        with pytest.raises(UpdateFailed, match="Invalid box info response"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_process_devices_data_corruption(self, coordinator):
        """Test device data processing with corrupted data."""
        corrupted_data = {
            "device1": None,  # Null device
            "device2": "string_instead_of_dict",  # Wrong type
            "device3": {"mac": "aa:bb:cc:dd:ee:ff"},  # Valid but minimal
            "device4": {"mac": "11:22:33:44:55:66", "name": "Valid Device"},  # Valid
        }
        
        processed = coordinator._process_devices_data(corrupted_data)
        
        # Should only process valid devices
        assert len(processed) == 2
        assert "device3" in processed
        assert "device4" in processed

    @pytest.mark.asyncio
    async def test_process_rules_data_corruption(self, coordinator):
        """Test rules data processing with corrupted data."""
        corrupted_data = {
            "rule1": None,  # Null rule
            "rule2": [],  # Wrong type (list instead of dict)
            "rule3": {"rid": "rule3", "type": "internet"},  # Valid but minimal
            "rule4": {"rid": "rule4", "type": "gaming", "target": "mac:aa:bb:cc:dd:ee:ff"},  # Valid
        }
        
        processed = coordinator._process_rules_data(corrupted_data)
        
        # Should only process valid rules
        assert len(processed) == 2
        assert "rule3" in processed
        assert "rule4" in processed

    @pytest.mark.asyncio
    async def test_create_rule_validation_error(self, coordinator):
        """Test rule creation with validation errors."""
        # Missing required fields
        invalid_rule_data = {
            "type": "internet",
            # Missing "target" and "action"
        }

        with pytest.raises(ValueError, match="Missing required field"):
            await coordinator.async_create_rule(invalid_rule_data)

    @pytest.mark.asyncio
    async def test_pause_rule_empty_id(self, coordinator):
        """Test rule pausing with empty rule ID."""
        with pytest.raises(ValueError, match="Rule ID cannot be empty"):
            await coordinator.async_pause_rule("")

    @pytest.mark.asyncio
    async def test_unpause_rule_empty_id(self, coordinator):
        """Test rule unpausing with empty rule ID."""
        with pytest.raises(ValueError, match="Rule ID cannot be empty"):
            await coordinator.async_unpause_rule("")


class TestConfigFlowErrorHandling:
    """Test config flow error handling scenarios."""

    @pytest.mark.asyncio
    async def test_authenticate_msp_network_timeout(self, hass):
        """Test MSP authentication with network timeout."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ServerTimeoutError()
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(CannotConnect, match="Network error"):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_authenticate_msp_ssl_error(self, hass):
        """Test MSP authentication with SSL error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ClientSSLError()
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(CannotConnect):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_get_devices_malformed_response(self, hass):
        """Test device retrieval with malformed API response."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        # Mock malformed response (missing "data" key)
        mock_boxes_response = {"success": True}  # Missing "data"
        
        mock_client = AsyncMock()
        mock_client.get_boxes.return_value = mock_boxes_response
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            with pytest.raises(CannotConnect, match="Invalid response from MSP API"):
                await flow._get_available_devices()

    @pytest.mark.asyncio
    async def test_get_devices_empty_data(self, hass):
        """Test device retrieval with empty data."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_url = "https://test.firewalla.com"
        flow._access_token = "valid_token"
        
        # Mock empty response
        mock_boxes_response = {"data": None}
        
        mock_client = AsyncMock()
        mock_client.get_boxes.return_value = mock_boxes_response
        
        with patch("custom_components.firewalla.config_flow.FirewallaMSPClient", return_value=mock_client), \
             patch("custom_components.firewalla.config_flow.async_get_clientsession"):
            
            await flow._get_available_devices()
            
            # Should handle gracefully with empty devices
            assert len(flow._available_devices) == 0


class TestEntityErrorHandling:
    """Test entity error handling scenarios."""

    @pytest.mark.asyncio
    async def test_switch_turn_on_api_failure(self, mock_coordinator, mock_devices_data):
        """Test switch turn_on with API failure."""
        from custom_components.firewalla.switch import FirewallaBlockSwitch
        
        device_mac = "aa:bb:cc:dd:ee:ff"
        device_info = mock_devices_data[device_mac]
        switch = FirewallaBlockSwitch(mock_coordinator, device_mac, device_info)
        
        # Mock API failure
        mock_coordinator.async_create_device_block_rule = AsyncMock(
            side_effect=HomeAssistantError("API Error")
        )
        
        with patch.object(switch, "is_on", False), \
             patch.object(switch, "_find_paused_block_rule", return_value=None):
            
            with pytest.raises(HomeAssistantError, match="Failed to enable internet blocking"):
                await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_sensor_unavailable_device(self, mock_coordinator, mock_devices_data):
        """Test sensor behavior with unavailable device."""
        from custom_components.firewalla.sensor import FirewallaDeviceStatusSensor
        
        device_mac = "aa:bb:cc:dd:ee:ff"
        device_data = mock_devices_data[device_mac]
        sensor = FirewallaDeviceStatusSensor(mock_coordinator, device_mac, device_data)
        
        # Mock device not found
        mock_coordinator.get_device_by_mac.return_value = None
        mock_coordinator.last_update_success = True
        
        assert sensor.available is False
        assert sensor.native_value == "unknown"
        assert sensor.extra_state_attributes == {}

    def test_sensor_invalid_timestamp(self, mock_coordinator, mock_devices_data):
        """Test sensor handling of invalid timestamp data."""
        from custom_components.firewalla.sensor import FirewallaDeviceStatusSensor
        
        device_mac = "aa:bb:cc:dd:ee:ff"
        device_data = mock_devices_data[device_mac].copy()
        device_data["lastActiveTimestamp"] = "invalid_timestamp"
        
        sensor = FirewallaDeviceStatusSensor(mock_coordinator, device_mac, device_data)
        mock_coordinator.get_device_by_mac.return_value = device_data
        
        attributes = sensor.extra_state_attributes
        
        # Should handle invalid timestamp gracefully
        assert "last_seen" in attributes
        assert attributes["last_seen"] == "invalid_timestamp"