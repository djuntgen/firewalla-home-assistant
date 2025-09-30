"""The Firewalla integration."""
from __future__ import annotations

import logging
from typing import Any, Dict

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DOMAIN,
)
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Supported platforms for this integration
PLATFORMS_TO_SETUP = [Platform.SWITCH, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Firewalla from a config entry."""
    _LOGGER.info("Setting up Firewalla integration for entry %s", entry.entry_id)
    
    try:
        # Extract configuration data with validation
        msp_url = entry.data.get(CONF_MSP_URL)
        access_token = entry.data.get(CONF_ACCESS_TOKEN)
        box_gid = entry.data.get(CONF_BOX_GID)
        
        # Validate required configuration
        if not msp_url or not access_token or not box_gid:
            _LOGGER.error(
                "Missing required configuration data: MSP URL=%s, Token=%s, Box GID=%s",
                bool(msp_url), bool(access_token), bool(box_gid)
            )
            raise ConfigEntryNotReady("Missing required configuration data")
        
        _LOGGER.debug(
            "Initializing Firewalla integration with MSP URL: %s, Box GID: %s",
            msp_url,
            box_gid,
        )
        
        # Get aiohttp session for API communication
        session = async_get_clientsession(hass)
        
        # Initialize the data update coordinator
        coordinator = FirewallaDataUpdateCoordinator(
            hass=hass,
            session=session,
            msp_url=msp_url,
            access_token=access_token,
            box_gid=box_gid,
        )
        
        # Test authentication and initial data fetch
        _LOGGER.debug("Testing MSP API authentication and initial data fetch")
        await coordinator.async_config_entry_first_refresh()
        
        # Store coordinator in hass.data for access by platforms
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator
        
        _LOGGER.info("Successfully initialized Firewalla coordinator")
        
        # Set up platforms asynchronously
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_TO_SETUP)
        
        _LOGGER.info("Successfully set up Firewalla integration platforms")
        
        return True
        
    except ConfigEntryAuthFailed as err:
        _LOGGER.error(
            "Authentication failed during Firewalla setup: %s. "
            "Please check your MSP credentials and try again.",
            err,
        )
        # Re-raise with user-friendly message
        raise ConfigEntryAuthFailed(
            "Authentication failed. Please check your MSP credentials."
        ) from err
        
    except aiohttp.ClientConnectorError as err:
        _LOGGER.error(
            "Cannot connect to Firewalla MSP API at %s: %s. "
            "Please check your network connection and MSP URL.",
            msp_url if 'msp_url' in locals() else 'unknown',
            err,
        )
        raise ConfigEntryNotReady(
            f"Cannot connect to Firewalla MSP API: {err}"
        ) from err
        
    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            _LOGGER.error(
                "MSP API authentication failed with HTTP 401: Invalid access token"
            )
            raise ConfigEntryAuthFailed(
                "Invalid access token. Please check your MSP credentials."
            ) from err
        elif err.status == 403:
            _LOGGER.error(
                "MSP API access forbidden with HTTP 403: Insufficient permissions"
            )
            raise ConfigEntryAuthFailed(
                "Access forbidden. Please check your MSP account permissions."
            ) from err
        elif err.status >= 500:
            _LOGGER.error(
                "MSP API server error %d: %s. Service may be temporarily unavailable.",
                err.status, err.message
            )
            raise ConfigEntryNotReady(
                f"MSP API server error {err.status}. Please try again later."
            ) from err
        else:
            _LOGGER.error(
                "MSP API returned error %d: %s",
                err.status, err.message
            )
            raise ConfigEntryNotReady(
                f"MSP API error {err.status}: {err.message}"
            ) from err
        
    except aiohttp.ClientError as err:
        _LOGGER.error(
            "Network error during Firewalla setup: %s. "
            "Please check your network connection and MSP URL.",
            err,
        )
        raise ConfigEntryNotReady(
            f"Network error connecting to Firewalla MSP API: {err}"
        ) from err
        
    except HomeAssistantError as err:
        _LOGGER.error(
            "Home Assistant error during Firewalla setup: %s",
            err,
        )
        # Re-raise Home Assistant errors as-is
        raise
        
    except Exception as err:
        _LOGGER.exception(
            "Unexpected error during Firewalla setup: %s. "
            "This may indicate a configuration or system issue.",
            err,
        )
        raise ConfigEntryNotReady(
            f"Unexpected error setting up Firewalla integration: {err}"
        ) from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Firewalla config entry."""
    _LOGGER.info("Unloading Firewalla integration for entry %s", entry.entry_id)
    
    try:
        # Unload platforms
        _LOGGER.debug("Unloading Firewalla platforms: %s", PLATFORMS_TO_SETUP)
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, PLATFORMS_TO_SETUP
        )
        
        if unload_ok:
            # Clean up coordinator and stored data
            coordinator_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
            
            if coordinator_data:
                _LOGGER.debug("Cleaning up Firewalla coordinator resources")
                # The coordinator will automatically clean up its resources
                # when it goes out of scope, including the aiohttp session
            else:
                _LOGGER.warning("No coordinator data found for entry %s during unload", entry.entry_id)
                
            # Remove domain data if no more entries
            if DOMAIN in hass.data and not hass.data[DOMAIN]:
                hass.data.pop(DOMAIN, None)
                _LOGGER.debug("Removed Firewalla domain data (no more entries)")
            
            _LOGGER.info("Successfully unloaded Firewalla integration")
        else:
            _LOGGER.error("Failed to unload some Firewalla platforms")
            
        return unload_ok
        
    except KeyError as err:
        _LOGGER.error("Missing data during Firewalla unload: %s", err)
        return False
        
    except Exception as err:
        _LOGGER.exception("Unexpected error unloading Firewalla integration: %s", err)
        return False


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a Firewalla config entry."""
    _LOGGER.info("Reloading Firewalla integration for entry %s", entry.entry_id)
    
    try:
        # Unload the entry first
        _LOGGER.debug("Unloading entry before reload")
        unload_success = await async_unload_entry(hass, entry)
        
        if not unload_success:
            _LOGGER.warning("Unload was not fully successful, proceeding with setup anyway")
        
        # Set up the entry again
        _LOGGER.debug("Setting up entry after unload")
        setup_success = await async_setup_entry(hass, entry)
        
        if setup_success:
            _LOGGER.info("Successfully reloaded Firewalla integration")
        else:
            _LOGGER.error("Failed to set up Firewalla integration during reload")
            raise HomeAssistantError("Failed to set up integration during reload")
        
    except (ConfigEntryAuthFailed, ConfigEntryNotReady) as err:
        _LOGGER.error("Configuration error during Firewalla reload: %s", err)
        # Re-raise config errors as-is
        raise
        
    except Exception as err:
        _LOGGER.exception("Unexpected error reloading Firewalla integration: %s", err)
        raise HomeAssistantError(f"Failed to reload Firewalla integration: {err}") from err


def setup_integration_logging() -> None:
    """Set up integration-wide logging configuration."""
    # This function can be called during integration setup to configure
    # any special logging requirements for the Firewalla integration
    
    # Set appropriate log levels for integration components
    integration_loggers = [
        f"{__name__}",
        f"{__name__.replace('.__init__', '.coordinator')}",
        f"{__name__.replace('.__init__', '.config_flow')}",
        f"{__name__.replace('.__init__', '.switch')}",
        f"{__name__.replace('.__init__', '.sensor')}",
    ]
    
    for logger_name in integration_loggers:
        logger = logging.getLogger(logger_name)
        # Ensure loggers are properly configured
        # The actual log level will be controlled by Home Assistant's logging config
        logger.setLevel(logging.DEBUG)


# Set up logging when module is imported
setup_integration_logging()