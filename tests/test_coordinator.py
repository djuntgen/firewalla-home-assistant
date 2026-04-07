"""Tests for Firewalla rule management coordinator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.firewalla.coordinator import (
    FirewallaMSPClient,
    FirewallaDataUpdateCoordinator,
    _format_schedule,
)
from custom_components.firewalla.const import (
    API_ENDPOINTS,
    DEFAULT_BASE_POLL_INTERVAL,
    DEFAULT_DEVICES_INTERVAL,
    DEFAULT_FULL_RULES_INTERVAL,
    DEFAULT_USERS_CACHE_TTL,
    UPDATE_INTERVAL,
)


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
                "status": "active",
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
                "status": "paused",
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
        "resume_success": {"success": True},
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
    async def test_authenticate_success(
        self, client, mock_aiohttp_session, mock_api_responses
    ):
        """Test successful authentication."""
        # Mock successful rules response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["rules"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

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
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await client.authenticate()

        assert result is False
        assert client.is_authenticated is False

    @pytest.mark.asyncio
    async def test_authenticate_connection_error(self, client, mock_aiohttp_session):
        """Test authentication with connection error."""
        # Mock connection error
        mock_aiohttp_session.request.side_effect = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
        )

        result = await client.authenticate()

        assert result is False
        assert client.is_authenticated is False

    @pytest.mark.asyncio
    async def test_get_rules_success(
        self, client, mock_aiohttp_session, mock_api_responses
    ):
        """Test successful rules retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["rules"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await client.get_rules()

        assert result == mock_api_responses["rules"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rules_with_query(
        self, client, mock_aiohttp_session, mock_api_responses
    ):
        """Test rules retrieval with query parameter."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["rules"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await client.get_rules("status:active")

        assert result == mock_api_responses["rules"]
        # Verify query parameter was included in URL (url is a positional arg)
        call_args = mock_aiohttp_session.request.call_args
        url_arg = call_args[0][1]  # second positional arg
        assert "query=status:active" in url_arg

    @pytest.mark.asyncio
    async def test_pause_rule_success(
        self, client, mock_aiohttp_session, mock_api_responses
    ):
        """Test successful rule pausing."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["pause_success"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await client.pause_rule("rule-123")

        assert result == mock_api_responses["pause_success"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_rule_success(
        self, client, mock_aiohttp_session, mock_api_responses
    ):
        """Test successful rule resuming."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_api_responses["resume_success"]
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await client.resume_rule("rule-123")

        assert result == mock_api_responses["resume_success"]
        mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rule_status_success(
        self, client, mock_aiohttp_session, mock_api_responses
    ):
        """Test successful individual rule status retrieval."""
        rule_data = mock_api_responses["rules"][0]
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = rule_data
        mock_aiohttp_session.request.return_value.__aenter__.return_value = (
            mock_response
        )

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

        with patch("asyncio.sleep", new_callable=AsyncMock):
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

        with patch("asyncio.sleep", new_callable=AsyncMock):
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
        coordinator.api.get_devices = AsyncMock(return_value=[])
        coordinator.api.get_users = AsyncMock(return_value=[])
        coordinator.api._authenticated = True

        result = await coordinator._async_update_data()

        assert "rules" in result
        assert "rule_count" in result
        assert "box_info" in result
        assert "groups" in result
        assert len(result["rules"]) == 2
        assert result["rule_count"]["total"] == 2
        assert result["rule_count"]["active"] == 1
        assert result["rule_count"]["paused"] == 1

    @pytest.mark.asyncio
    async def test_async_update_data_authentication_required(
        self, coordinator, mock_api_responses
    ):
        """Test data update when authentication is required."""
        # Mock not authenticated initially
        coordinator.api._authenticated = False
        coordinator.api.authenticate = AsyncMock(return_value=True)
        coordinator.api.get_rules = AsyncMock(return_value=mock_api_responses["rules"])
        coordinator.api.get_devices = AsyncMock(return_value=[])
        coordinator.api.get_users = AsyncMock(return_value=[])

        result = await coordinator._async_update_data()

        # Should call authenticate first
        coordinator.api.authenticate.assert_called_once()
        assert "rules" in result

    @pytest.mark.asyncio
    async def test_async_update_data_authentication_failed(self, coordinator):
        """Test data update when authentication fails."""
        coordinator.api._authenticated = False
        coordinator.api.authenticate = AsyncMock(return_value=False)

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_api_error(self, coordinator):
        """Test data update with API error."""
        coordinator.api._authenticated = True
        coordinator.api.get_rules = AsyncMock(
            side_effect=HomeAssistantError("API Error")
        )

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
        """Test successful rule pausing (no refresh — optimistic updates handle UI)."""
        coordinator.api.pause_rule = AsyncMock(return_value={"success": True})

        result = await coordinator.async_pause_rule("rule-123")

        assert result is True
        coordinator.api.pause_rule.assert_called_once_with("rule-123")

    @pytest.mark.asyncio
    async def test_async_pause_rule_failure(self, coordinator):
        """Test rule pausing failure."""
        coordinator.api.pause_rule = AsyncMock(return_value=None)

        result = await coordinator.async_pause_rule("rule-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_async_resume_rule_success(self, coordinator):
        """Test successful rule resuming (no refresh — optimistic updates handle UI)."""
        coordinator.api.resume_rule = AsyncMock(return_value={"success": True})

        result = await coordinator.async_resume_rule("rule-123")

        assert result is True
        coordinator.api.resume_rule.assert_called_once_with("rule-123")

    @pytest.mark.asyncio
    async def test_async_get_rules_cached(self, coordinator):
        """Test getting rules from cached data."""
        coordinator.data = {"rules": {"rule-123": {"rid": "rule-123"}}}

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

    def test_process_rules_data_enriched_fields(self, coordinator):
        """Test that processed rules include hit_count, last_hit, time quota/used, and schedule_display."""
        rules_list = [
            {
                "id": "rule-enriched",
                "type": "internet",
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "disabled": False,
                "paused": False,
                "action": "block",
                "description": "Enriched rule",
                "hit": {"count": 42, "lastHitTs": 1700000000},
                "timeUsage": {"quota": 120, "used": 45},
                "schedule": {"cronTime": "0 22 * * 1,2,3,4,5", "duration": 3600},
            }
        ]

        result = coordinator._process_rules_data(rules_list)

        rule = result["rule-enriched"]
        assert rule["hit_count"] == 42
        assert rule["last_hit"] == 1700000000
        assert rule["time_quota_minutes"] == 120
        assert rule["time_used_minutes"] == 45
        assert rule["schedule_display"] is not None
        assert "22:00" in rule["schedule_display"]

    def test_process_rules_data_enriched_fields_defaults(self, coordinator):
        """Test enriched fields default values when source data is missing."""
        rules_list = [
            {
                "id": "rule-minimal",
                "type": "internet",
                "disabled": False,
                "paused": False,
                "action": "block",
            }
        ]

        result = coordinator._process_rules_data(rules_list)

        rule = result["rule-minimal"]
        assert rule["hit_count"] == 0
        assert rule["last_hit"] is None
        assert rule["time_quota_minutes"] is None
        assert rule["time_used_minutes"] is None
        assert rule["schedule_display"] is None


class TestFormatSchedule:
    """Test the _format_schedule helper function."""

    def test_none_schedule(self):
        """Test with None input."""
        assert _format_schedule(None) is None

    def test_empty_schedule(self):
        """Test with empty dict input."""
        assert _format_schedule({}) is None

    def test_no_cron_time(self):
        """Test with schedule missing cronTime."""
        assert _format_schedule({"duration": 3600}) is None

    def test_empty_cron_time(self):
        """Test with empty cronTime string."""
        assert _format_schedule({"cronTime": ""}) is None

    def test_daily_midnight(self):
        """Test daily at midnight cron pattern: 0 0 * * *."""
        result = _format_schedule({"cronTime": "0 0 * * *"})
        assert result == "daily at 00:00"

    def test_weekdays_at_2200(self):
        """Test weekdays at 22:00 cron pattern: 0 22 * * 1,2,3,4,5."""
        result = _format_schedule({"cronTime": "0 22 * * 1,2,3,4,5", "duration": 3600})
        assert "weekdays" in result
        assert "22:00" in result
        assert "1h" in result

    def test_specific_days(self):
        """Test specific days cron pattern: 0 0 * * 1,2,3,4."""
        result = _format_schedule({"cronTime": "0 0 * * 1,2,3,4"})
        assert "Mon" in result
        assert "Tue" in result
        assert "Wed" in result
        assert "Thu" in result
        assert "00:00" in result

    def test_weekends(self):
        """Test weekends cron pattern: 0 9 * * 0,6."""
        result = _format_schedule({"cronTime": "0 9 * * 0,6"})
        assert "weekends" in result
        assert "09:00" in result

    def test_all_seven_days_is_daily(self):
        """Test all seven days shows as daily: 0 8 * * 0,1,2,3,4,5,6."""
        result = _format_schedule({"cronTime": "0 8 * * 0,1,2,3,4,5,6"})
        assert "daily" in result
        assert "08:00" in result

    def test_duration_hours_and_minutes(self):
        """Test duration formatting with hours and minutes."""
        result = _format_schedule({"cronTime": "0 10 * * *", "duration": 5400})
        assert "1h 30m" in result

    def test_duration_minutes_only(self):
        """Test duration formatting with minutes only."""
        result = _format_schedule({"cronTime": "0 10 * * *", "duration": 1800})
        assert "30m" in result

    def test_duration_all_day(self):
        """Test duration formatting for all day (>= 24h)."""
        result = _format_schedule({"cronTime": "0 0 * * *", "duration": 86400})
        assert "all day" in result

    def test_no_duration(self):
        """Test schedule without duration."""
        result = _format_schedule({"cronTime": "0 15 * * *"})
        assert result == "daily at 15:00"
        assert "for" not in result

    def test_short_cron_returns_raw(self):
        """Test that a cron string with fewer than 5 parts returns raw."""
        result = _format_schedule({"cronTime": "0 0 *"})
        assert result == "0 0 *"


class TestFirewallaMSPClientDevicesUsers:
    """Tests for devices and users API methods."""

    @pytest.mark.asyncio
    async def test_get_devices(self, mock_aiohttp_session):
        client = FirewallaMSPClient(mock_aiohttp_session, "test.firewalla.net", "test_token")
        mock_devices = [
            {"id": "AA:BB:CC:DD:EE:FF", "name": "Test Phone", "online": True, "group": {"id": "28", "name": "Alice"}}
        ]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_devices)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp_session.request = MagicMock(return_value=mock_response)
        result = await client.get_devices()
        assert result == mock_devices

    @pytest.mark.asyncio
    async def test_get_users(self, mock_aiohttp_session):
        client = FirewallaMSPClient(mock_aiohttp_session, "test.firewalla.net", "test_token")
        mock_users = [
            {"id": "box:29", "name": "Alice", "affiliatedTag": "28", "devices": ["AA:BB:CC:DD:EE:FF"]}
        ]
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_users)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp_session.request = MagicMock(return_value=mock_response)
        result = await client.get_users()
        assert result == mock_users


class TestGroupProcessing:
    """Tests for group and user data processing."""

    def test_build_groups_from_devices(self):
        from custom_components.firewalla.coordinator import _build_groups

        devices = [
            {"id": "AA:BB:CC:DD:EE:01", "name": "Phone", "online": True, "deviceType": "phone",
             "group": {"id": "28", "name": "Alice"}},
            {"id": "AA:BB:CC:DD:EE:02", "name": "Tablet", "online": False, "deviceType": "tablet",
             "group": {"id": "28", "name": "Alice"}},
            {"id": "AA:BB:CC:DD:EE:03", "name": "Camera", "online": True, "deviceType": "camera",
             "group": {"id": "25", "name": "Cameras"}},
            {"id": "AA:BB:CC:DD:EE:04", "name": "Laptop", "online": True, "deviceType": "desktop"},
        ]
        users = [
            {"id": "box:29", "name": "Alice", "affiliatedTag": "28",
             "devices": ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"],
             "download": 1000, "upload": 500},
        ]
        rules = {
            "rule1": {"id": "rule1", "action": "block", "type": "internet", "scope_type": "group", "scope_value": "28", "paused": False},
            "rule2": {"id": "rule2", "action": "block", "type": "category", "scope_type": "group", "scope_value": "28", "paused": False},
        }

        groups = _build_groups(devices, users, rules)

        assert "28" in groups
        assert groups["28"]["name"] == "Alice"
        assert groups["28"]["is_user_group"] is True
        assert groups["28"]["user_id"] == "box:29"
        assert groups["28"]["device_count"] == 2
        assert groups["28"]["internet_block_rule_id"] == "rule1"
        assert groups["28"]["internet_blocked"] is True
        assert groups["28"]["download"] == 1000

        assert "25" in groups
        assert groups["25"]["name"] == "Cameras"
        assert groups["25"]["is_user_group"] is False
        assert groups["25"]["internet_block_rule_id"] is None

    def test_build_groups_resolves_uuid_names(self):
        from custom_components.firewalla.coordinator import _build_groups

        devices = [
            {"id": "AA:BB:CC:DD:EE:01", "name": "Bob Tablet", "online": True, "deviceType": "tablet",
             "group": {"id": "32", "name": "BFB913AE-49E7-4465-961D-6FB1496147DF"}},
        ]
        users = [
            {"id": "box:33", "name": "Bob", "affiliatedTag": "32", "devices": ["AA:BB:CC:DD:EE:01"],
             "download": 0, "upload": 0},
        ]

        groups = _build_groups(devices, users, {})
        assert groups["32"]["name"] == "Bob"

    def test_build_groups_internet_paused(self):
        from custom_components.firewalla.coordinator import _build_groups

        devices = [
            {"id": "AA:BB:CC:DD:EE:01", "name": "Phone", "online": True, "deviceType": "phone",
             "group": {"id": "28", "name": "Alice"}},
        ]
        rules = {
            "rule1": {"id": "rule1", "action": "block", "type": "internet", "scope_type": "group", "scope_value": "28", "paused": True},
        }

        groups = _build_groups(devices, [], rules)
        assert groups["28"]["internet_blocked"] is False

    def test_build_groups_no_devices(self):
        from custom_components.firewalla.coordinator import _build_groups

        groups = _build_groups([], [], {})
        assert groups == {}


class TestGroupRulesAndTimeLimits:
    def test_build_groups_tracks_all_rules(self):
        from custom_components.firewalla.coordinator import _build_groups
        devices = [{"id": "AA:BB", "name": "Phone", "online": True, "deviceType": "phone", "group": {"id": "28", "name": "Alice"}}]
        rules = {
            "r1": {"id": "r1", "action": "block", "type": "internet", "value": "", "scope_type": "group", "scope_value": "28", "paused": False, "status": "active", "hit_count": 100},
            "r2": {"id": "r2", "action": "block", "type": "category", "value": "porn", "scope_type": "group", "scope_value": "28", "paused": False, "status": "active", "hit_count": 50},
            "r3": {"id": "r3", "action": "block", "type": "app", "value": "tiktok", "scope_type": "group", "scope_value": "28", "paused": True, "status": "paused", "hit_count": 200},
            "r4": {"id": "r4", "action": "block", "type": "category", "value": "vpn", "scope_type": "group", "scope_value": "28", "paused": False, "status": "active", "hit_count": 0},
        }
        groups = _build_groups(devices, [], rules)
        g = groups["28"]
        assert g["internet_block_rule_id"] == "r1"
        assert len(g["group_rules"]) == 4
        assert g["group_rules"]["r2"]["type"] == "category"
        assert g["group_rules"]["r2"]["value"] == "porn"
        assert g["group_rules"]["r2"]["paused"] is False
        assert g["group_rules"]["r3"]["value"] == "tiktok"
        assert g["group_rules"]["r3"]["paused"] is True
        assert g["group_rules"]["r3"]["hit_count"] == 200

    def test_build_time_limits(self):
        from custom_components.firewalla.coordinator import _build_time_limits
        users = [{"id": "box:33", "name": "Bob", "affiliatedTag": "32", "devices": [], "download": 0, "upload": 0}]
        rules = {
            "r1": {"id": "r1", "action": "timelimit", "type": "app", "value": "roblox",
                   "scope_type": "user", "scope_value": "33", "paused": False,
                   "time_quota_minutes": 60, "time_used_minutes": 61,
                   "schedule_display": "daily at 00:00 all day", "hit_count": 8789},
            "r2": {"id": "r2", "action": "timelimit", "type": "app", "value": "youtube",
                   "scope_type": "user", "scope_value": "33", "paused": False,
                   "time_quota_minutes": 60, "time_used_minutes": 62,
                   "schedule_display": "Sun-Thu at 00:00 all day", "hit_count": 29328},
        }
        tl = _build_time_limits(users, rules)
        assert "33" in tl
        assert tl["33"]["user_name"] == "Bob"
        assert len(tl["33"]["limits"]) == 2
        r = tl["33"]["limits"]["r1"]
        assert r["app"] == "roblox"
        assert r["quota"] == 60
        assert r["used"] == 61
        assert r["remaining"] == 0
        assert r["reached"] is True

    def test_build_time_limits_not_reached(self):
        from custom_components.firewalla.coordinator import _build_time_limits
        users = [{"id": "box:33", "name": "Bob", "affiliatedTag": "32", "devices": [], "download": 0, "upload": 0}]
        rules = {
            "r1": {"id": "r1", "action": "timelimit", "type": "app", "value": "facebook",
                   "scope_type": "user", "scope_value": "33", "paused": False,
                   "time_quota_minutes": 60, "time_used_minutes": 2,
                   "schedule_display": "daily", "hit_count": 0},
        }
        tl = _build_time_limits(users, rules)
        fb = tl["33"]["limits"]["r1"]
        assert fb["remaining"] == 58
        assert fb["reached"] is False

    def test_build_time_limits_empty(self):
        from custom_components.firewalla.coordinator import _build_time_limits
        assert _build_time_limits([], {}) == {}

    def test_build_time_limits_ignores_non_timelimit(self):
        from custom_components.firewalla.coordinator import _build_time_limits
        users = [{"id": "box:33", "name": "Bob", "affiliatedTag": "32", "devices": [], "download": 0, "upload": 0}]
        rules = {
            "r1": {"id": "r1", "action": "block", "type": "internet", "value": "",
                   "scope_type": "user", "scope_value": "33", "paused": False,
                   "time_quota_minutes": None, "time_used_minutes": None,
                   "schedule_display": None, "hit_count": 0},
        }
        assert _build_time_limits(users, rules) == {}

    def test_build_groups_activity_detection(self):
        from custom_components.firewalla.coordinator import _build_groups
        devices = [
            {"id": "AA:BB", "name": "Phone", "online": True, "deviceType": "phone",
             "totalDownload": 10000, "group": {"id": "28", "name": "Alice"}},
        ]
        # First poll — no previous data, should not be active
        groups = _build_groups(devices, [], {}, previous_downloads=None)
        assert groups["28"]["active"] is False  # No delta on first poll
        assert groups["28"]["total_download"] == 10000

        # Second poll — download increased by 20000 bytes (above 10KB threshold)
        devices[0]["totalDownload"] = 30000
        last_active = {}
        groups2 = _build_groups(devices, [], {}, previous_downloads={"28": 10000}, last_active_times=last_active)
        assert groups2["28"]["active"] is True
        assert groups2["28"]["download_delta"] == 20000
        assert "28" in last_active  # timestamp was recorded

    def test_build_groups_activity_below_threshold(self):
        from custom_components.firewalla.coordinator import _build_groups
        devices = [
            {"id": "AA:BB", "name": "Phone", "online": True, "deviceType": "phone",
             "totalDownload": 15000, "group": {"id": "28", "name": "Alice"}},
        ]
        groups = _build_groups(devices, [], {}, previous_downloads={"28": 10000})
        assert groups["28"]["active"] is False  # 5000 bytes < 10240 threshold


class TestSplitPolling:
    """Tests for split-polling: timelimit-only on most polls, full rules at interval."""

    @pytest.fixture
    def mock_hass(self):
        return MagicMock()

    @pytest.fixture
    def coordinator(self, mock_hass, mock_aiohttp_session):
        return FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.net",
            access_token="test_token_123",
            box_gid="box-123",
            base_poll_interval=45,
            full_rules_interval=300,  # every ~7 polls (300/45)
            devices_interval=600,  # every ~13 polls (600/45)
            users_cache_ttl=1800,
        )

    def test_configurable_intervals_stored(self, coordinator):
        """Test that configurable intervals are stored correctly."""
        assert coordinator._base_poll_interval == 45
        assert coordinator._full_rules_interval == 300
        assert coordinator._devices_interval == 600
        assert coordinator._users_cache_ttl == 1800
        assert coordinator._full_rules_every == 6  # 300 // 45
        assert coordinator._devices_every == 13  # 600 // 45

    def test_minimum_interval_clamping(self, mock_hass, mock_aiohttp_session):
        """Test that intervals are clamped to sensible minimums."""
        coord = FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.net",
            access_token="test_token_123",
            box_gid="box-123",
            base_poll_interval=10,  # below minimum of 30
            full_rules_interval=10,  # below base_poll_interval
            devices_interval=5,
            users_cache_ttl=10,
        )
        assert coord._base_poll_interval == 30  # clamped to 30
        assert coord._full_rules_interval == 30  # clamped to base
        assert coord._devices_interval == 30  # clamped to base
        assert coord._users_cache_ttl == 60  # minimum 60s

    @pytest.mark.asyncio
    async def test_first_poll_fetches_full_rules(self, coordinator):
        """Poll 1 should fetch full rules (not timelimit-only)."""
        coordinator.api._authenticated = True
        full_rules = [
            {"id": "r1", "action": "block", "type": "internet", "disabled": False, "paused": False},
            {"id": "r2", "action": "timelimit", "type": "app", "disabled": False, "paused": False},
        ]
        coordinator.api.get_rules = AsyncMock(return_value=full_rules)
        coordinator.api.get_devices = AsyncMock(return_value=[])
        coordinator.api.get_users = AsyncMock(return_value=[])

        result = await coordinator._async_update_data()

        # get_rules called once with no query (full fetch)
        coordinator.api.get_rules.assert_called_once_with()
        assert len(result["rules"]) == 2

    @pytest.mark.asyncio
    async def test_second_poll_fetches_timelimit_only(self, coordinator):
        """Poll 2 should fetch timelimit-only since full_rules_every=6."""
        coordinator.api._authenticated = True
        full_rules = [
            {"id": "r1", "action": "block", "type": "internet", "disabled": False, "paused": False},
            {"id": "r2", "action": "timelimit", "type": "app", "disabled": False, "paused": False},
        ]
        tl_rules = [
            {"id": "r2", "action": "timelimit", "type": "app", "disabled": False, "paused": False,
             "timeUsage": {"quota": 60, "used": 30}},
        ]
        coordinator.api.get_devices = AsyncMock(return_value=[])
        coordinator.api.get_users = AsyncMock(return_value=[])

        # First poll — full rules
        coordinator.api.get_rules = AsyncMock(return_value=full_rules)
        await coordinator._async_update_data()

        # Second poll — timelimit-only
        coordinator.api.get_rules = AsyncMock(return_value=tl_rules)
        result = await coordinator._async_update_data()

        # Should call with timelimit query
        coordinator.api.get_rules.assert_called_once_with("action:timelimit")
        # Both rules should be in result (r1 from cache, r2 updated)
        assert len(result["rules"]) == 2
        assert "r1" in result["rules"]
        assert "r2" in result["rules"]

    @pytest.mark.asyncio
    async def test_seventh_poll_fetches_full_rules_again(self, coordinator):
        """Poll 7 should trigger a full rules refresh (poll_count % 6 == 1)."""
        coordinator.api._authenticated = True
        rules = [{"id": "r1", "action": "block", "type": "internet", "disabled": False, "paused": False}]
        coordinator.api.get_rules = AsyncMock(return_value=rules)
        coordinator.api.get_devices = AsyncMock(return_value=[])
        coordinator.api.get_users = AsyncMock(return_value=[])

        # Simulate 6 polls (first is full, next 5 are timelimit)
        for _ in range(6):
            await coordinator._async_update_data()

        # 7th poll
        coordinator.api.get_rules = AsyncMock(return_value=rules)
        await coordinator._async_update_data()

        # Should have done a full fetch (no query arg)
        coordinator.api.get_rules.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_devices_polled_at_configured_interval(self, coordinator):
        """Devices should be fetched every 13 polls (devices_interval=600, base=45)."""
        coordinator.api._authenticated = True
        rules = [{"id": "r1", "action": "block", "type": "internet", "disabled": False, "paused": False}]
        mock_devices = [{"id": "AA:BB", "name": "Phone", "online": True}]
        coordinator.api.get_rules = AsyncMock(return_value=rules)
        coordinator.api.get_devices = AsyncMock(return_value=mock_devices)
        coordinator.api.get_users = AsyncMock(return_value=[{"id": "box:1", "name": "Test"}])

        # Poll 1 — devices fetched (first poll, poll_count=1, 1%13=1)
        await coordinator._async_update_data()
        assert coordinator.api.get_devices.call_count == 1

        # Polls 2-13 — devices NOT fetched (cache exists, poll_count%13 != 1)
        for _ in range(12):
            await coordinator._async_update_data()
        assert coordinator.api.get_devices.call_count == 1

        # Poll 14 — devices fetched (poll_count=14, 14%13=1)
        await coordinator._async_update_data()
        assert coordinator.api.get_devices.call_count == 2

    def test_default_interval_values(self, mock_hass, mock_aiohttp_session):
        """Test that defaults are used when no explicit intervals are provided."""
        coord = FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=mock_aiohttp_session,
            msp_domain="test.firewalla.net",
            access_token="test_token_123",
            box_gid="box-123",
        )
        assert coord._base_poll_interval == DEFAULT_BASE_POLL_INTERVAL
        assert coord._full_rules_interval == DEFAULT_FULL_RULES_INTERVAL
        assert coord._devices_interval == DEFAULT_DEVICES_INTERVAL
        assert coord._users_cache_ttl == DEFAULT_USERS_CACHE_TTL
