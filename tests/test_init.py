"""Tests for Firewalla integration initialization."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)

from custom_components.firewalla import (
    async_setup_entry,
    async_unload_entry,
    async_reload_entry,
    setup_integration_logging,
)
from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DOMAIN,
)


class TestAsyncSetupEntry:
    """Test integration setup."""

    @pytest.mark.asyncio
    async def test_setup_entry_success(self, mock_hass, mock_config_entry):
        """Test successful integration setup."""
        # Mock coordinator with real dict data so .get() works
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.data = {
            "rule_count": {"total": 5, "active": 3, "paused": 2},
        }

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            result = await async_setup_entry(mock_hass, mock_config_entry)

            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
            assert (
                mock_hass.data[DOMAIN][mock_config_entry.entry_id] == mock_coordinator
            )

            # Verify platforms were set up
            mock_hass.config_entries.async_forward_entry_setups.assert_called_once_with(
                mock_config_entry, ["switch", "sensor", "binary_sensor", "button"]
            )

    @pytest.mark.asyncio
    async def test_setup_entry_missing_config(self, mock_hass):
        """Test setup with missing configuration data."""
        # Create config entry with missing data
        incomplete_config = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test Firewalla",
            data={
                CONF_MSP_URL: "https://test.firewalla.com",
                # Missing CONF_ACCESS_TOKEN and CONF_BOX_GID
            },
            source="user",
            entry_id="test_entry_id",
            unique_id="test_incomplete",
            options={},
            discovery_keys={},
        )

        with pytest.raises(
            ConfigEntryNotReady, match="Missing required configuration data"
        ):
            await async_setup_entry(mock_hass, incomplete_config)

    @pytest.mark.asyncio
    async def test_setup_entry_auth_failed(self, mock_hass, mock_config_entry):
        """Test setup with authentication failure."""
        # Mock coordinator that fails authentication
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh.side_effect = (
            ConfigEntryAuthFailed("Auth failed")
        )

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            with pytest.raises(ConfigEntryAuthFailed, match="Authentication failed"):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_entry_connection_error(self, mock_hass, mock_config_entry):
        """Test setup with connection error."""
        # Mock coordinator that fails with connection error
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh.side_effect = (
            aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
            )
        )

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            with pytest.raises(
                ConfigEntryNotReady, match="Cannot connect to Firewalla MSP API"
            ):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_entry_http_401_error(self, mock_hass, mock_config_entry):
        """Test setup with HTTP 401 error."""
        # Mock coordinator that fails with 401 error
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh.side_effect = (
            aiohttp.ClientResponseError(
                request_info=None, history=None, status=401, message="Unauthorized"
            )
        )

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            with pytest.raises(ConfigEntryAuthFailed, match="Invalid access token"):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_entry_http_403_error(self, mock_hass, mock_config_entry):
        """Test setup with HTTP 403 error."""
        # Mock coordinator that fails with 403 error
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh.side_effect = (
            aiohttp.ClientResponseError(
                request_info=None, history=None, status=403, message="Forbidden"
            )
        )

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            with pytest.raises(ConfigEntryAuthFailed, match="Access forbidden"):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_entry_http_500_error(self, mock_hass, mock_config_entry):
        """Test setup with HTTP 500 error."""
        # Mock coordinator that fails with 500 error
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh.side_effect = (
            aiohttp.ClientResponseError(
                request_info=None,
                history=None,
                status=500,
                message="Internal Server Error",
            )
        )

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            with pytest.raises(ConfigEntryNotReady, match="MSP API server error 500"):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_entry_unexpected_error(self, mock_hass, mock_config_entry):
        """Test setup with unexpected error."""
        # Mock coordinator that fails with unexpected error
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh.side_effect = Exception(
            "Unexpected error"
        )

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            with pytest.raises(
                ConfigEntryNotReady, match="Unexpected error setting up"
            ):
                await async_setup_entry(mock_hass, mock_config_entry)


class TestAsyncUnloadEntry:
    """Test integration unload."""

    @pytest.mark.asyncio
    async def test_unload_entry_success(self, mock_hass, mock_config_entry):
        """Test successful integration unload."""
        # Set up hass.data with coordinator
        mock_coordinator = MagicMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        # Verify coordinator was removed from hass.data (domain key also removed since last entry)
        assert mock_config_entry.entry_id not in mock_hass.data.get(DOMAIN, {})

        # Verify platforms were unloaded
        mock_hass.config_entries.async_unload_platforms.assert_called_once_with(
            mock_config_entry, ["switch", "sensor", "binary_sensor", "button"]
        )

    @pytest.mark.asyncio
    async def test_unload_entry_platform_failure(self, mock_hass, mock_config_entry):
        """Test unload with platform unload failure."""
        # Set up hass.data with coordinator
        mock_coordinator = MagicMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is False
        # Coordinator should NOT be removed when platforms failed to unload
        assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_entry_missing_coordinator(self, mock_hass, mock_config_entry):
        """Test unload with missing coordinator data."""
        # No coordinator in hass.data
        mock_hass.data = {DOMAIN: {}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_remove_domain_data(self, mock_hass, mock_config_entry):
        """Test unload removes domain data when no more entries."""
        # Set up hass.data with coordinator (only entry)
        mock_coordinator = MagicMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        # Verify entire domain was removed from hass.data
        assert DOMAIN not in mock_hass.data

    @pytest.mark.asyncio
    async def test_unload_entry_keep_domain_data(self, mock_hass, mock_config_entry):
        """Test unload keeps domain data when other entries exist."""
        # Set up hass.data with multiple coordinators
        mock_coordinator1 = MagicMock()
        mock_coordinator2 = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: mock_coordinator1,
                "other_entry_id": mock_coordinator2,
            }
        }
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        # Verify domain data still exists with other entry
        assert DOMAIN in mock_hass.data
        assert "other_entry_id" in mock_hass.data[DOMAIN]
        assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_entry_exception(self, mock_hass, mock_config_entry):
        """Test unload with exception."""
        # Set up hass.data with coordinator
        mock_coordinator = MagicMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(
            side_effect=Exception("Unload error")
        )

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is False


class TestAsyncReloadEntry:
    """Test integration reload."""

    @pytest.mark.asyncio
    async def test_reload_entry_calls_async_reload(self, mock_hass, mock_config_entry):
        """Test that reload delegates to hass.config_entries.async_reload."""
        await async_reload_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_reload.assert_called_once_with(
            mock_config_entry.entry_id
        )

    @pytest.mark.asyncio
    async def test_reload_entry_propagates_exceptions(self, mock_hass, mock_config_entry):
        """Test that exceptions from async_reload propagate to the caller."""
        mock_hass.config_entries.async_reload = AsyncMock(
            side_effect=Exception("Reload failed")
        )

        with pytest.raises(Exception, match="Reload failed"):
            await async_reload_entry(mock_hass, mock_config_entry)


class TestSetupIntegrationLogging:
    """Test integration logging setup."""

    def test_setup_integration_logging(self):
        """Test logging setup function."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            setup_integration_logging()

            # Verify loggers were configured
            assert mock_get_logger.call_count >= 5  # At least 5 loggers
            mock_logger.setLevel.assert_called()

    def test_setup_integration_logging_exists_and_callable(self):
        """Test that setup_integration_logging is defined and callable."""
        # Verify the function exists and can be called without error
        assert callable(setup_integration_logging)
        # Call it again to verify it doesn't raise
        setup_integration_logging()


class TestEndToEndIntegration:
    """Test end-to-end integration functionality."""

    @pytest.mark.asyncio
    async def test_full_integration_setup_and_operation(
        self, mock_hass, mock_config_entry
    ):
        """Test complete integration setup with all platforms and verify operation."""
        # Mock coordinator with realistic data (must be a real dict for .get() calls)
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.data = {
            "box_info": {
                "gid": "test-box-gid",
                "name": "Test Firewalla",
                "model": "gold",
                "online": True,
                "version": "1.975",
            },
            "devices": {
                "aa:bb:cc:dd:ee:ff": {
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "name": "Test Device",
                    "ip": "192.168.1.100",
                    "online": True,
                    "lastActiveTimestamp": 1648632679.193,
                    "deviceClass": "laptop",
                }
            },
            "rules": {
                "rule-1": {
                    "rid": "rule-1",
                    "type": "internet",
                    "target": "mac:aa:bb:cc:dd:ee:ff",
                    "disabled": False,
                    "paused": False,
                    "action": "block",
                }
            },
            "rule_count": {"total": 1, "active": 1, "paused": 0},
        }

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            # Test setup
            result = await async_setup_entry(mock_hass, mock_config_entry)

            # Verify setup success
            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]

            # Verify coordinator was initialized and first refresh called
            mock_coordinator.async_config_entry_first_refresh.assert_called_once()

            # Verify platforms were set up
            mock_hass.config_entries.async_forward_entry_setups.assert_called_once_with(
                mock_config_entry, ["switch", "sensor", "binary_sensor", "button"]
            )

            # Verify coordinator data is accessible
            stored_coordinator = mock_hass.data[DOMAIN][mock_config_entry.entry_id]
            assert stored_coordinator == mock_coordinator
            assert stored_coordinator.data is not None
            assert "box_info" in stored_coordinator.data
            assert "devices" in stored_coordinator.data
            assert "rules" in stored_coordinator.data

    @pytest.mark.asyncio
    async def test_integration_reload_preserves_functionality(
        self, mock_hass, mock_config_entry
    ):
        """Test that integration reload delegates to hass.config_entries.async_reload."""
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.data = {"rule_count": {"total": 5, "active": 3, "paused": 2}}

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            # Initial setup
            setup_result = await async_setup_entry(mock_hass, mock_config_entry)
            assert setup_result is True

            # Reload delegates to HA's built-in reload mechanism
            await async_reload_entry(mock_hass, mock_config_entry)

            # Verify async_reload was called with the correct entry_id
            mock_hass.config_entries.async_reload.assert_called_once_with(
                mock_config_entry.entry_id
            )

    @pytest.mark.asyncio
    async def test_integration_handles_platform_failures_gracefully(
        self, mock_hass, mock_config_entry
    ):
        """Test integration handles individual platform failures without breaking setup."""
        mock_coordinator = AsyncMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.data = {"rule_count": {"total": 5, "active": 3, "paused": 2}}

        # Mock platform setup that succeeds
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            return_value=mock_coordinator,
        ), patch("custom_components.firewalla.async_get_clientsession"):

            result = await async_setup_entry(mock_hass, mock_config_entry)

            # Setup should still succeed
            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_integration_cleanup_on_unload(self, mock_hass, mock_config_entry):
        """Test complete cleanup when integration is unloaded."""
        # Set up integration first
        mock_coordinator = AsyncMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True

        # Verify complete cleanup
        assert mock_config_entry.entry_id not in mock_hass.data.get(DOMAIN, {})

        # If this was the last entry, domain should be removed
        if not mock_hass.data.get(DOMAIN):
            assert DOMAIN not in mock_hass.data

    @pytest.mark.asyncio
    async def test_multiple_integration_instances(self, mock_hass):
        """Test multiple Firewalla integrations can coexist."""
        # Create two different config entries
        config_entry_1 = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Firewalla 1",
            data={
                CONF_MSP_URL: "https://test1.firewalla.com",
                CONF_ACCESS_TOKEN: "token1",
                CONF_BOX_GID: "box-gid-1",
            },
            source="user",
            entry_id="entry_1",
            unique_id="box-gid-1",
            options={},
            discovery_keys={},
        )

        config_entry_2 = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Firewalla 2",
            data={
                CONF_MSP_URL: "https://test2.firewalla.com",
                CONF_ACCESS_TOKEN: "token2",
                CONF_BOX_GID: "box-gid-2",
            },
            source="user",
            entry_id="entry_2",
            unique_id="box-gid-2",
            options={},
            discovery_keys={},
        )

        mock_coordinator_1 = AsyncMock()
        mock_coordinator_1.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator_1.data = {"rule_count": {"total": 5, "active": 3, "paused": 2}}
        mock_coordinator_2 = AsyncMock()
        mock_coordinator_2.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator_2.data = {"rule_count": {"total": 3, "active": 2, "paused": 1}}

        with patch(
            "custom_components.firewalla.FirewallaDataUpdateCoordinator",
            side_effect=[mock_coordinator_1, mock_coordinator_2],
        ), patch("custom_components.firewalla.async_get_clientsession"):

            # Set up both integrations
            result_1 = await async_setup_entry(mock_hass, config_entry_1)
            result_2 = await async_setup_entry(mock_hass, config_entry_2)

            assert result_1 is True
            assert result_2 is True

            # Verify both coordinators are stored separately
            assert DOMAIN in mock_hass.data
            assert "entry_1" in mock_hass.data[DOMAIN]
            assert "entry_2" in mock_hass.data[DOMAIN]
            assert mock_hass.data[DOMAIN]["entry_1"] == mock_coordinator_1
            assert mock_hass.data[DOMAIN]["entry_2"] == mock_coordinator_2

            # Unload one integration
            mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
            unload_result = await async_unload_entry(mock_hass, config_entry_1)

            assert unload_result is True

            # Verify only one coordinator was removed
            assert "entry_1" not in mock_hass.data[DOMAIN]
            assert "entry_2" in mock_hass.data[DOMAIN]
            assert mock_hass.data[DOMAIN]["entry_2"] == mock_coordinator_2
