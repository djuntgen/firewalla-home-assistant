"""Tests for Firewalla integration error handling scenarios."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.firewalla.coordinator import (
    FirewallaMSPClient,
    FirewallaDataUpdateCoordinator,
)
from custom_components.firewalla.config_flow import (
    ConfigFlow,
    CannotConnect,
    InvalidAuth,
)


class TestAPIErrorHandling:
    """Test API error handling scenarios."""

    @pytest.fixture
    def client(self, mock_aiohttp_session):
        """Create a test MSP client."""
        return FirewallaMSPClient(
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.com",
            access_token="test_token_123",
        )

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self, client, mock_aiohttp_session):
        """Test handling of timeout errors with retry logic."""
        # Mock timeout on first call, success on second
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True, "data": {}})

        success_ctx = AsyncMock()
        success_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        success_ctx.__aexit__ = AsyncMock(return_value=False)

        # First call raises timeout, second returns context manager
        mock_aiohttp_session.request = MagicMock(
            side_effect=[asyncio.TimeoutError(), success_ctx]
        )

        result = await client._make_request("GET", "/test/endpoint")

        assert result == {"success": True, "data": {}}
        assert mock_aiohttp_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_connection_error_retry(self, client, mock_aiohttp_session):
        """Test connection error retry logic."""
        # Mock connection error on first two calls, success on third
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True, "data": {}})

        success_ctx = AsyncMock()
        success_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        success_ctx.__aexit__ = AsyncMock(return_value=False)

        conn_err = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
        )

        mock_aiohttp_session.request = MagicMock(
            side_effect=[conn_err, conn_err, success_ctx]
        )

        result = await client._make_request("GET", "/test/endpoint")

        assert result == {"success": True, "data": {}}
        assert mock_aiohttp_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limiting_handling(self, client, mock_aiohttp_session):
        """Test rate limiting (429) error handling."""
        # Mock 429 response then success
        mock_429_response = MagicMock()
        mock_429_response.status = 429

        mock_success_response = MagicMock()
        mock_success_response.status = 200
        mock_success_response.json = AsyncMock(return_value={"success": True, "data": {}})

        ctx_429 = AsyncMock()
        ctx_429.__aenter__ = AsyncMock(return_value=mock_429_response)
        ctx_429.__aexit__ = AsyncMock(return_value=False)

        ctx_success = AsyncMock()
        ctx_success.__aenter__ = AsyncMock(return_value=mock_success_response)
        ctx_success.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp_session.request = MagicMock(
            side_effect=[ctx_429, ctx_success]
        )

        result = await client._make_request("GET", "/test/endpoint")

        assert result == {"success": True, "data": {}}
        assert mock_aiohttp_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, client, mock_aiohttp_session):
        """Test behavior when max retries are exceeded."""
        # Mock timeout on all attempts
        mock_aiohttp_session.request = MagicMock(side_effect=asyncio.TimeoutError())

        with pytest.raises(
            HomeAssistantError, match="MSP API timeout after .* attempts"
        ):
            await client._make_request("GET", "/test/endpoint")

        # Should have tried 3 times (RETRY_ATTEMPTS)
        assert mock_aiohttp_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_404_error_handling(self, client, mock_aiohttp_session):
        """Test 404 error handling."""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp_session.request = MagicMock(return_value=ctx)

        with pytest.raises(HomeAssistantError, match="MSP API endpoint not found"):
            await client._make_request("GET", "/nonexistent/endpoint")

    @pytest.mark.asyncio
    async def test_500_error_handling(self, client, mock_aiohttp_session):
        """Test 500 server error handling."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp_session.request = MagicMock(return_value=ctx)

        with pytest.raises(HomeAssistantError, match="MSP API server error"):
            await client._make_request("GET", "/test/endpoint")

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, client, mock_aiohttp_session):
        """Test handling of invalid JSON responses."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            side_effect=aiohttp.ContentTypeError(
                MagicMock(), (), message="Invalid JSON"
            )
        )
        mock_response.text = AsyncMock(return_value="Invalid JSON response")

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp_session.request = MagicMock(return_value=ctx)

        result = await client._make_request("GET", "/test/endpoint")

        # For status 200 non-JSON responses, returns simple success dict
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_auth_refresh_failure(self, client, mock_aiohttp_session):
        """Test authentication refresh failure."""
        # Mock 401 response that persists after refresh attempt
        mock_401_response = MagicMock()
        mock_401_response.status = 401

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_401_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp_session.request = MagicMock(return_value=ctx)

        with pytest.raises(
            ConfigEntryAuthFailed, match="MSP API authentication expired"
        ):
            await client._make_request("GET", "/test/endpoint")


class TestCoordinatorErrorHandling:
    """Test coordinator error handling scenarios."""

    @pytest.fixture
    def coordinator(self, mock_hass, mock_aiohttp_session):
        """Create a test coordinator."""
        return FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.com",
            access_token="test_token_123",
            box_gid="test_box_gid_456",
        )

    @pytest.mark.asyncio
    async def test_update_data_auth_failure(self, coordinator):
        """Test data update with authentication failure."""
        coordinator.api.authenticate = AsyncMock(return_value=False)
        coordinator.api._authenticated = False

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_data_api_failure(self, coordinator):
        """Test data update with API failure during rule fetch."""
        # Mock successful authentication but failed rules call
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api._authenticated = True
        coordinator.api.get_rules = AsyncMock(
            side_effect=HomeAssistantError("Rules API failed")
        )

        with pytest.raises(UpdateFailed, match="Home Assistant error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_data_empty_response(self, coordinator):
        """Test data update with empty API response."""
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api._authenticated = True
        coordinator.api.get_rules = AsyncMock(return_value=None)

        # Empty/None response should result in empty rules data
        result = await coordinator._async_update_data()
        assert result["rules"] == {}
        assert result["rule_count"]["total"] == 0

    def test_process_rules_data_corruption(self, coordinator):
        """Test rules data processing with corrupted data."""
        # _process_rules_data expects a list or dict with "results" key
        corrupted_data = {
            "results": [
                None,  # Null rule
                "string_instead_of_dict",  # Wrong type
                {"id": "rule3", "type": "internet"},  # Valid but minimal
                {
                    "id": "rule4",
                    "type": "gaming",
                    "target": {"type": "mac", "value": "aa:bb:cc:dd:ee:ff"},
                },  # Valid
            ]
        }

        processed = coordinator._process_rules_data(corrupted_data)

        # Should only process valid rules (dicts)
        assert len(processed) == 2
        assert "rule3" in processed
        assert "rule4" in processed

    @pytest.mark.asyncio
    async def test_pause_rule_empty_id(self, coordinator):
        """Test rule pausing with empty rule ID returns False."""
        result = await coordinator.async_pause_rule("")
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_rule_empty_id(self, coordinator):
        """Test rule resuming with empty rule ID returns False."""
        result = await coordinator.async_resume_rule("")
        assert result is False


class TestConfigFlowErrorHandling:
    """Test config flow error handling scenarios."""

    @pytest.mark.asyncio
    async def test_authenticate_msp_network_timeout(self, hass):
        """Test MSP authentication with network timeout."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.com"
        flow._access_token = "valid_token"

        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ServerTimeoutError()

        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient",
            return_value=mock_client,
        ), patch("custom_components.firewalla.config_flow.async_get_clientsession"):

            with pytest.raises(CannotConnect, match="Network error connecting to MSP API"):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_authenticate_msp_ssl_error(self, hass):
        """Test MSP authentication with SSL error."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.com"
        flow._access_token = "valid_token"

        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = aiohttp.ClientConnectorSSLError(
            MagicMock(), OSError("SSL error")
        )

        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient",
            return_value=mock_client,
        ), patch("custom_components.firewalla.config_flow.async_get_clientsession"):

            with pytest.raises(CannotConnect):
                await flow._authenticate_msp()

    @pytest.mark.asyncio
    async def test_get_boxes_null_response(self, hass):
        """Test box retrieval with null API response."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.com"
        flow._access_token = "valid_token"

        mock_client = AsyncMock()
        mock_client.get_rules.return_value = None

        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient",
            return_value=mock_client,
        ), patch("custom_components.firewalla.config_flow.async_get_clientsession"):

            await flow._get_available_boxes()

            # Should handle gracefully with empty boxes
            assert len(flow._available_boxes) == 0

    @pytest.mark.asyncio
    async def test_get_boxes_successful_response(self, hass):
        """Test box retrieval with successful API response."""
        flow = ConfigFlow()
        flow.hass = hass
        flow._msp_domain = "test.firewalla.com"
        flow._access_token = "valid_token"

        # Mock successful rules response
        mock_client = AsyncMock()
        mock_client.get_rules.return_value = {"results": [], "count": 0}

        with patch(
            "custom_components.firewalla.config_flow.FirewallaMSPClient",
            return_value=mock_client,
        ), patch("custom_components.firewalla.config_flow.async_get_clientsession"):

            await flow._get_available_boxes()

            # Should create a default box entry
            assert len(flow._available_boxes) == 1
            assert "default" in flow._available_boxes


class TestEntityErrorHandling:
    """Test entity error handling scenarios."""

    @pytest.fixture
    def mock_rule_coordinator(self):
        """Create a mock coordinator with rule data for entity tests."""
        coordinator = MagicMock()
        coordinator.data = {
            "rules": {
                "rule-1": {
                    "rid": "rule-1",
                    "id": "rule-1",
                    "type": "internet",
                    "value": "",
                    "target": "",
                    "target_name": "",
                    "disabled": False,
                    "paused": True,
                    "status": "paused",
                    "action": "block",
                    "description": "Block Internet",
                    "priority": 0,
                    "direction": "bidirection",
                    "scope_type": "",
                    "scope_value": "",
                    "dnsOnly": False,
                    "created_at": 0,
                    "modified_at": 0,
                    "ts": 0,
                    "updateTs": 0,
                    "schedule": None,
                    "hit": {},
                    "gid": "",
                    "hit_count": 0,
                    "last_hit": None,
                    "time_quota_minutes": None,
                    "time_used_minutes": None,
                    "schedule_display": None,
                }
            },
            "box_info": {
                "gid": "test_box_gid_456",
                "name": "Test Firewalla",
                "model": "gold",
                "online": True,
            },
            "rule_count": {"total": 1, "active": 0, "paused": 1, "by_type": {"internet": 1}},
            "rule_changes": {"added": [], "removed": [], "modified": []},
        }
        coordinator.last_update_success = True
        coordinator.box_gid = "test_box_gid_456"
        return coordinator

    @pytest.mark.asyncio
    async def test_switch_turn_on_api_failure(self, mock_rule_coordinator):
        """Test switch turn_on (resume) with API failure."""
        from custom_components.firewalla.switch import FirewallaRuleSwitch

        rule_id = "rule-1"
        rule_data = mock_rule_coordinator.data["rules"][rule_id]
        switch = FirewallaRuleSwitch(mock_rule_coordinator, rule_id, rule_data)

        # Mock API failure on resume
        mock_rule_coordinator.async_resume_rule = AsyncMock(return_value=False)

        with pytest.raises(
            HomeAssistantError, match="Failed to resume rule"
        ):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_switch_turn_off_api_failure(self, mock_rule_coordinator):
        """Test switch turn_off (pause) with API failure."""
        from custom_components.firewalla.switch import FirewallaRuleSwitch

        rule_id = "rule-1"
        rule_data = mock_rule_coordinator.data["rules"][rule_id].copy()
        # Set rule as active (not paused) so turn_off actually attempts the pause
        rule_data["paused"] = False
        rule_data["status"] = "active"
        mock_rule_coordinator.data["rules"][rule_id] = rule_data

        switch = FirewallaRuleSwitch(mock_rule_coordinator, rule_id, rule_data)

        # Mock API failure on pause
        mock_rule_coordinator.async_pause_rule = AsyncMock(return_value=False)

        with pytest.raises(
            HomeAssistantError, match="Failed to pause rule"
        ):
            await switch.async_turn_off()

    def test_switch_unavailable_when_rule_missing(self, mock_rule_coordinator):
        """Test switch availability when rule is removed from coordinator data."""
        from custom_components.firewalla.switch import FirewallaRuleSwitch

        rule_id = "rule-1"
        rule_data = mock_rule_coordinator.data["rules"][rule_id]
        switch = FirewallaRuleSwitch(mock_rule_coordinator, rule_id, rule_data)

        # Remove the rule from coordinator data
        del mock_rule_coordinator.data["rules"][rule_id]

        assert switch.available is False

    def test_sensor_no_data_returns_zero(self, mock_rule_coordinator):
        """Test sensor returns 0 when no rule count data is available."""
        from custom_components.firewalla.sensor import FirewallaRulesSensor

        sensor = FirewallaRulesSensor(mock_rule_coordinator)

        # Remove rule_count from data
        del mock_rule_coordinator.data["rule_count"]

        assert sensor.native_value == 0
