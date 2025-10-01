"""Tests for Firewalla rule management coordinator."""
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


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp session."""
    session = MagicMock()
    session.request = MagicMock()
    return session


@pytest.fixture
def mock_api_responses():
    """Create mock API responses."""
    return {
        "rules": [
            {
                "id": "rule-123",
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
            },
            {
                "id": "rule-456",
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
            },
        ],
        "rules_paginated": {
            "results": [
                {
                    "id": "rule-123",
                    "type": "internet",
                    "target": "mac:aa:bb:cc:dd:ee:ff",
                    "disabled": False,
                    "paused": False,
                    "action": "block",
                    "description": "Test rule",
                }
            ]
        },
        "pause_success": {"success": True},
        "unpause_success": {"success": True},
    }


class TestFirewallaMSPClient:
    """Test the Firewalla MSP API client for rule management."""

    @pytest.fixture
    def client(self, mock_aiohttp_session):
        """Create a test MSP client."""
        return FirewallaMSPClient(
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.net",
            access_token="test_token_123",
        )

    @pytest.mark.asyncio
    async def test_authenticate_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful authentication."""
        # Mock successful rules response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["rules"]
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
    async def test_get_rules_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful rules retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["rules"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.get_rules()
        
        assert result == mock_api_responses["rules"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rules_with_query(self, client, mock_aiohttp_session, mock_api_responses):
        """Test rules retrieval with query parameter."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["rules"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.get_rules("status:active")
        
        assert result == mock_api_responses["rules"]
        # Verify query parameter was included in URL
        call_args = mock_aiohttp_session.request.call_args
        assert "query=status:active" in call_args[1]["url"] or "query=status:active" in str(call_args)

    @pytest.mark.asyncio
    async def test_pause_rule_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful rule pausing."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["pause_success"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.pause_rule("rule-123")
        
        assert result == mock_api_responses["pause_success"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_unpause_rule_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful rule unpausing."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["unpause_success"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.unpause_rule("rule-123")
        
        assert result == mock_api_responses["unpause_success"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rule_status_success(self, client, mock_aiohttp_session, mock_api_responses):
        """Test successful individual rule status retrieval."""
        rule_data = mock_api_responses["rules"][0]
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = rule_data
        mock_aiohttp_session.request.return_value.__aenter__.return_value = mock_response

        result = await client.get_rule_status("rule-123")
        
        assert result == rule_data
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_rate_limit_retry(self, client, mock_aiohttp_session):
        """Test rate limit handling with retry."""
        # First call returns 429, second call succeeds
        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        
        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json.return_value = {"success": True}
        
        mock_aiohttp_session.request.return_value.__aenter__.side_effect = [
            mock_response_429,
            mock_response_200,
        ]

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await client.get_rules()
        
        assert result == {"success": True}
        assert mock_aiohttp_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_timeout_retry(self, client, mock_aiohttp_session):
        """Test timeout handling with retry."""
        # First call times out, second call succeeds
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"success": True}
        
        mock_aiohttp_session.request.return_value.__aenter__.side_effect = [
            aiohttp.ServerTimeoutError(),
            mock_response,
        ]

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await client.get_rules()
        
        assert result == {"success": True}
        assert mock_aiohttp_session.request.call_count == 2


class TestFirewallaDataUpdateCoordinator:
    """Test the Firewalla data update coordinator for rule management."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def coordinator(self, mock_hass, mock_aiohttp_session):
        """Create a test coordinator."""
        return FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.net",
            access_token="test_token_123",
            box_gid="box-123",
        )

    @pytest.mark.asyncio
    async def test_async_update_data_success(self, coordinator, mock_api_responses):
        """Test successful data update."""
        # Mock the API client methods
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])
        coordinator.api.is_authenticated = True

        result = await coordinator._async_update_data()
        
        assert "rules" in result
        assert "rule_count" in result
        assert "box_info" in result
        assert len(result["rules"]) == 2
        assert result["rule_count"]["total"] == 2
        assert result["rule_count"]["active"] == 1
        assert result["rule_count"]["paused"] == 1

    @pytest.mark.asyncio
    async def test_async_update_data_authentication_required(self, coordinator, mock_api_responses):
        """Test data update when authentication is required."""
        # Mock not authenticated initially
        coordinator.api.is_authenticated = False
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])

        result = await coordinator._async_update_data()
        
        # Should call authenticate first
        coordinator.api.authenticate.assert_called_once()
        assert "rules" in result

    @pytest.mark.asyncio
    async def test_async_update_data_authentication_failed(self, coordinator):
        """Test data update when authentication fails."""
        coordinator.api.is_authenticated = False
        coordinator.api.authenticate = AsyncMock(return_value=False)

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_api_error(self, coordinator):
        """Test data update with API error."""
        coordinator.api.is_authenticated = True
        coordinator.api.get_rules = AsyncMock(side_effect=HomeAssistantError("API Error"))

        with pytest.raises(UpdateFailed, match="API Error"):
            await coordinator._async_update_data()

    def test_process_rules_data_list_format(self, coordinator, mock_api_responses):
        """Test processing rules data in list format."""
        rules_list = mock_api_responses["rules"]
        
        result = coordinator._process_rules_data(rules_list)
        
        assert len(result) == 2
        assert "rule-123" in result
        assert "rule-456" in result
        assert result["rule-123"]["rid"] == "rule-123"
        assert result["rule-123"]["type"] == "internet"

    def test_process_rules_data_paginated_format(self, coordinator, mock_api_responses):
        """Test processing rules data in paginated format."""
        paginated_data = mock_api_responses["rules_paginated"]
        
        result = coordinator._process_rules_data(paginated_data)
        
        assert len(result) == 1
        assert "rule-123" in result

    def test_process_rules_data_empty(self, coordinator):
        """Test processing empty rules data."""
        result = coordinator._process_rules_data([])
        
        assert result == {}

    def test_process_rules_data_invalid(self, coordinator):
        """Test processing invalid rules data."""
        result = coordinator._process_rules_data("invalid")
        
        assert result == {}

    def test_detect_rule_changes_added(self, coordinator):
        """Test rule change detection for added rules."""
        coordinator._previous_rules = {"rule-123": {"rid": "rule-123"}}
        current_rules = {
            "rule-123": {"rid": "rule-123"},
            "rule-456": {"rid": "rule-456"},
        }
        
        changes = coordinator._detect_rule_changes(current_rules)
        
        assert changes["added"] == ["rule-456"]
        assert changes["removed"] == []
        assert changes["modified"] == []

    def test_detect_rule_changes_removed(self, coordinator):
        """Test rule change detection for removed rules."""
        coordinator._previous_rules = {
            "rule-123": {"rid": "rule-123"},
            "rule-456": {"rid": "rule-456"},
        }
        current_rules = {"rule-123": {"rid": "rule-123"}}
        
        changes = coordinator._detect_rule_changes(current_rules)
        
        assert changes["added"] == []
        assert changes["removed"] == ["rule-456"]
        assert changes["modified"] == []

    def test_detect_rule_changes_modified(self, coordinator):
        """Test rule change detection for modified rules."""
        coordinator._previous_rules = {
            "rule-123": {"rid": "rule-123", "paused": False, "modified_at": 1000}
        }
        current_rules = {
            "rule-123": {"rid": "rule-123", "paused": True, "modified_at": 2000}
        }
        
        changes = coordinator._detect_rule_changes(current_rules)
        
        assert changes["added"] == []
        assert changes["removed"] == []
        assert changes["modified"] == ["rule-123"]

    def test_calculate_rule_statistics(self, coordinator):
        """Test rule statistics calculation."""
        rules_data = {
            "rule-123": {"paused": False, "type": "internet"},
            "rule-456": {"paused": True, "type": "category"},
            "rule-789": {"paused": False, "type": "internet"},
        }
        
        stats = coordinator._calculate_rule_statistics(rules_data)
        
        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["paused"] == 1
        assert stats["by_type"]["internet"] == 2
        assert stats["by_type"]["category"] == 1

    @pytest.mark.asyncio
    async def test_async_pause_rule_success(self, coordinator):
        """Test successful rule pausing."""
        coordinator.api.pause_rule = AsyncMock(return_value={"success": True})
        coordinator.async_request_refresh = AsyncMock()

        result = await coordinator.async_pause_rule("rule-123")
        
        assert result is True
        coordinator.api.pause_rule.assert_called_once_with("rule-123")
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_pause_rule_failure(self, coordinator):
        """Test rule pausing failure."""
        coordinator.api.pause_rule = AsyncMock(return_value=None)

        result = await coordinator.async_pause_rule("rule-123")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_async_unpause_rule_success(self, coordinator):
        """Test successful rule unpausing."""
        coordinator.api.unpause_rule = AsyncMock(return_value={"success": True})
        coordinator.async_request_refresh = AsyncMock()

        result = await coordinator.async_unpause_rule("rule-123")
        
        assert result is True
        coordinator.api.unpause_rule.assert_called_once_with("rule-123")
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_get_rules_cached(self, coordinator):
        """Test getting rules from cached data."""
        coordinator.data = {
            "rules": {"rule-123": {"rid": "rule-123"}}
        }

        result = await coordinator.async_get_rules()
        
        assert result == {"rule-123": {"rid": "rule-123"}}

    @pytest.mark.asyncio
    async def test_async_get_rules_from_api(self, coordinator, mock_api_responses):
        """Test getting rules directly from API."""
        coordinator.data = None
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])

        result = await coordinator.async_get_rules("status:active")
        
        coordinator.api.get_rules.assert_called_once_with("status:active")
        assert len(result) == 2