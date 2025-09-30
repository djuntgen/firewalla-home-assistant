"""Config flow for Firewalla integration.

This module handles the configuration flow for setting up the Firewalla integration
with Home Assistant. It provides a two-step process:
1. MSP API authentication with URL and personal access token
2. Device selection from available Firewalla devices in the MSP account
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DEFAULT_MSP_URL,
    DOMAIN,
)
from .coordinator import FirewallaMSPClient

_LOGGER = logging.getLogger(__name__)

# Error codes for user-friendly messages
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_NO_DEVICES = "no_devices"
ERROR_UNKNOWN = "unknown"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._msp_url: Optional[str] = None
        self._access_token: Optional[str] = None
        self._available_devices: Dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step for MSP token input and validation."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                self._msp_url = user_input[CONF_MSP_URL].rstrip("/")
                self._access_token = user_input[CONF_ACCESS_TOKEN].strip()

                # Basic validation
                if not self._access_token:
                    _LOGGER.debug("Empty access token provided")
                    errors["base"] = ERROR_INVALID_AUTH
                elif len(self._access_token) < 10:  # Reasonable minimum length for access token
                    _LOGGER.debug("Access token too short: %d characters", len(self._access_token))
                    errors["base"] = ERROR_INVALID_AUTH
                elif not self._msp_url:
                    _LOGGER.debug("Empty MSP URL provided")
                    errors["base"] = ERROR_CANNOT_CONNECT
                else:
                    _LOGGER.debug("Attempting MSP authentication with URL: %s", self._msp_url)
                    
                    # Authenticate with MSP API and get available devices
                    await self._authenticate_msp()
                    await self._get_available_devices()

                    # If we have devices, proceed to device selection
                    if self._available_devices:
                        _LOGGER.debug("Found %d devices, proceeding to device selection", len(self._available_devices))
                        return await self.async_step_device_selection()
                    else:
                        _LOGGER.warning("No devices found in MSP account")
                        errors["base"] = ERROR_NO_DEVICES

            except InvalidAuth as err:
                _LOGGER.error("MSP authentication failed: %s", err)
                errors["base"] = ERROR_INVALID_AUTH
            except CannotConnect as err:
                _LOGGER.error("Cannot connect to MSP API: %s", err)
                errors["base"] = ERROR_CANNOT_CONNECT
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during MSP authentication: %s", err)
                errors["base"] = ERROR_UNKNOWN

        # Show the form for MSP URL and access token input
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MSP_URL, default=DEFAULT_MSP_URL): str,
                    vol.Required(CONF_ACCESS_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device_selection(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle device selection from MSP account."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                box_gid = user_input[CONF_BOX_GID]
                device_name = user_input[CONF_NAME].strip()

                # Validate inputs
                if not device_name:
                    _LOGGER.debug("Empty device name provided")
                    errors[CONF_NAME] = "Integration name cannot be empty"
                elif box_gid not in self._available_devices:
                    _LOGGER.error("Selected box GID %s not in available devices", box_gid)
                    errors["base"] = ERROR_NO_DEVICES
                else:
                    _LOGGER.debug("Creating config entry for device %s (GID: %s)", device_name, box_gid)
                    
                    # Check if this device is already configured
                    await self.async_set_unique_id(box_gid)
                    self._abort_if_unique_id_configured()

                    # Create the config entry
                    _LOGGER.info("Successfully configured Firewalla integration for %s", device_name)
                    return self.async_create_entry(
                        title=device_name,
                        data={
                            CONF_MSP_URL: self._msp_url,
                            CONF_ACCESS_TOKEN: self._access_token,
                            CONF_BOX_GID: box_gid,
                            CONF_NAME: device_name,
                        },
                    )
            except Exception as err:
                _LOGGER.exception("Error creating config entry: %s", err)
                errors["base"] = ERROR_UNKNOWN

        # Create device selection options
        device_options = {}
        default_name = None
        for gid, device_info in self._available_devices.items():
            device_name = device_info.get("name", f"Firewalla {device_info.get('model', 'Device')}")
            device_options[gid] = device_name
            # Use the first device name as default
            if default_name is None:
                default_name = device_name

        if not device_options:
            # No devices available, return to user step with error
            errors["base"] = ERROR_NO_DEVICES
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MSP_URL, default=self._msp_url or DEFAULT_MSP_URL): str,
                        vol.Required(CONF_ACCESS_TOKEN, default=self._access_token or ""): str,
                    }
                ),
                errors=errors,
            )

        return self.async_show_form(
            step_id="device_selection",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BOX_GID): vol.In(device_options),
                    vol.Required(CONF_NAME, default=default_name): str,
                }
            ),
            errors=errors,
        )

    async def _authenticate_msp(self) -> None:
        """Authenticate with Firewalla MSP API."""
        if not self._msp_url or not self._access_token:
            raise InvalidAuth("MSP URL and access token are required")

        # Basic URL validation
        if not self._msp_url.startswith(("http://", "https://")):
            raise InvalidAuth("MSP URL must start with http:// or https://")

        try:
            _LOGGER.debug("Creating MSP client for authentication test")
            session = async_get_clientsession(self.hass)
            client = FirewallaMSPClient(session, self._msp_url, self._access_token)
            
            _LOGGER.debug("Testing MSP API authentication")
            if not await client.authenticate():
                _LOGGER.error("MSP API authentication failed - invalid credentials")
                raise InvalidAuth("MSP API authentication failed - please check your access token")
                
            _LOGGER.info("MSP API authentication successful for URL: %s", self._msp_url)
            
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Cannot connect to MSP API at %s: %s", self._msp_url, err)
            raise CannotConnect(f"Cannot connect to MSP API at {self._msp_url}: {err}") from err
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.error("MSP API authentication failed: Invalid access token (HTTP 401)")
                raise InvalidAuth("Invalid access token") from err
            elif err.status == 403:
                _LOGGER.error("MSP API access forbidden: Insufficient permissions (HTTP 403)")
                raise InvalidAuth("Access forbidden - check your MSP account permissions") from err
            elif err.status >= 500:
                _LOGGER.error("MSP API server error %d: %s", err.status, err.message)
                raise CannotConnect(f"MSP API server error {err.status} - service may be temporarily unavailable") from err
            else:
                _LOGGER.error("MSP API returned error %d: %s", err.status, err.message)
                raise CannotConnect(f"MSP API error {err.status}: {err.message}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error connecting to MSP API: %s", err)
            raise CannotConnect(f"Network error connecting to MSP API: {err}") from err
        except InvalidAuth:
            # Re-raise InvalidAuth exceptions
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error during MSP authentication: %s", err)
            raise InvalidAuth(f"Authentication failed due to unexpected error: {err}") from err

    async def _get_available_devices(self) -> None:
        """Get available Firewalla devices from MSP account."""
        if not self._msp_url or not self._access_token:
            raise InvalidAuth("MSP URL and access token are required")

        try:
            session = async_get_clientsession(self.hass)
            client = FirewallaMSPClient(session, self._msp_url, self._access_token)
            
            # Get list of boxes
            _LOGGER.debug("Fetching Firewalla devices from MSP API")
            boxes_response = await client.get_boxes()
            
            if not boxes_response or not isinstance(boxes_response, dict):
                _LOGGER.error("Invalid response from MSP API: %s", boxes_response)
                raise CannotConnect("Invalid response from MSP API")
                
            boxes_data = boxes_response.get("data", {})
            
            if not boxes_data:
                _LOGGER.warning("No Firewalla devices found in MSP account")
                self._available_devices = {}
                return

            # Process boxes data - handle both list and dict formats
            if isinstance(boxes_data, list):
                for box in boxes_data:
                    if isinstance(box, dict) and "gid" in box:
                        self._available_devices[box["gid"]] = box
                        _LOGGER.debug("Found device: %s (%s)", box.get("name", "Unknown"), box["gid"])
            elif isinstance(boxes_data, dict):
                # If boxes_data is a dict, it might be keyed by gid
                for gid, box_info in boxes_data.items():
                    if isinstance(box_info, dict):
                        # Ensure gid is in the box_info
                        box_info["gid"] = gid
                        self._available_devices[gid] = box_info
                        _LOGGER.debug("Found device: %s (%s)", box_info.get("name", "Unknown"), gid)

            _LOGGER.info("Found %d Firewalla devices in MSP account", len(self._available_devices))
            
            if not self._available_devices:
                _LOGGER.warning("No valid Firewalla devices found in MSP response")
            
        except aiohttp.ClientError as err:
            _LOGGER.error("Cannot connect to MSP API: %s", err)
            raise CannotConnect(f"Cannot connect to MSP API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting devices: %s", err)
            raise HomeAssistantError(f"Failed to get devices: {err}") from err


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect to MSP API."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""