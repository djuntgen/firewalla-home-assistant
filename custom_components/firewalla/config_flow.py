"""Config flow for Firewalla integration.

This module handles the configuration flow for setting up the Firewalla integration
with Home Assistant. It provides a two-step process:
1. MSP API authentication with domain and personal access token
2. Box selection from available Firewalla boxes in the MSP account

The integration focuses on rule management - discovering existing Firewalla rules
and creating switch entities for each rule to allow pause/unpause control.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_EXCLUDE_FILTERS,
    CONF_INCLUDE_FILTERS,
    CONF_MSP_URL,
    DEFAULT_MSP_URL_FORMAT,
    DOMAIN,
    ERROR_MESSAGES,
)
from .coordinator import FirewallaMSPClient

_LOGGER = logging.getLogger(__name__)

# MSP URL validation pattern
MSP_URL_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]\.firewalla\.net$')


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._msp_domain: Optional[str] = None
        self._access_token: Optional[str] = None
        self._available_boxes: Dict[str, Any] = {}
        self._user_input: Dict[str, Any] = {}  # Preserve user input on failures

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step for MSP domain and token input with validation."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Preserve user input for data persistence
            self._user_input.update(user_input)
            
            try:
                msp_domain = user_input[CONF_MSP_URL].strip()
                access_token = user_input[CONF_ACCESS_TOKEN].strip()

                # Validate MSP URL format
                if not msp_domain:
                    _LOGGER.debug("Empty MSP domain provided")
                    errors[CONF_MSP_URL] = "invalid_url_format"
                elif not self._validate_msp_url(msp_domain):
                    _LOGGER.debug("Invalid MSP domain format: %s", msp_domain)
                    errors[CONF_MSP_URL] = "invalid_url_format"
                elif not access_token:
                    _LOGGER.debug("Empty access token provided")
                    errors[CONF_ACCESS_TOKEN] = "auth_failed"
                elif len(access_token) < 10:  # Reasonable minimum length for access token
                    _LOGGER.debug("Access token too short: %d characters", len(access_token))
                    errors[CONF_ACCESS_TOKEN] = "auth_failed"
                else:
                    self._msp_domain = msp_domain
                    self._access_token = access_token
                    
                    _LOGGER.debug("Attempting MSP authentication with domain: %s", self._msp_domain)
                    
                    # Authenticate with MSP API and get available boxes
                    await self._authenticate_msp()
                    await self._get_available_boxes()

                    # If we have multiple boxes, proceed to box selection
                    if len(self._available_boxes) > 1:
                        _LOGGER.debug("Found %d boxes, proceeding to box selection", len(self._available_boxes))
                        return await self.async_step_box_selection()
                    elif len(self._available_boxes) == 1:
                        # Only one box, use it directly
                        box_gid = list(self._available_boxes.keys())[0]
                        box_info = self._available_boxes[box_gid]
                        box_name = box_info.get("name", f"Firewalla {box_info.get('model', 'Box')}")
                        
                        _LOGGER.debug("Only one box found, using it directly: %s", box_name)
                        
                        # Test rule access before completing setup
                        await self._test_rule_access()
                        
                        # Check if this box is already configured
                        await self.async_set_unique_id(box_gid)
                        self._abort_if_unique_id_configured()

                        # Create the config entry
                        _LOGGER.info("Successfully configured Firewalla integration for %s", box_name)
                        return self.async_create_entry(
                            title=box_name,
                            data={
                                CONF_MSP_URL: self._msp_domain,
                                CONF_ACCESS_TOKEN: self._access_token,
                                CONF_BOX_GID: box_gid,
                            },
                        )
                    else:
                        _LOGGER.warning("No boxes found in MSP account")
                        errors["base"] = "no_boxes"

            except InvalidAuth as err:
                _LOGGER.error("MSP authentication failed: %s", err)
                errors["base"] = "auth_failed"
            except CannotConnect as err:
                _LOGGER.error("Cannot connect to MSP API: %s", err)
                errors["base"] = "connection_failed"
            except RuleAccessFailed as err:
                _LOGGER.error("Cannot access rules: %s", err)
                errors["base"] = "rule_access_failed"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during MSP authentication: %s", err)
                errors["base"] = "unknown_error"

        # Show the form for MSP domain and access token input
        # Preserve previously entered values if they exist (data persistence)
        msp_domain_default = self._user_input.get(CONF_MSP_URL, DEFAULT_MSP_URL_FORMAT)
        access_token_default = self._user_input.get(CONF_ACCESS_TOKEN, "")
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MSP_URL, default=msp_domain_default): str,
                    vol.Required(CONF_ACCESS_TOKEN, default=access_token_default): str,
                }
            ),
            errors=errors,
        )

    async def async_step_box_selection(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle box selection from MSP account when multiple boxes exist."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                box_gid = user_input[CONF_BOX_GID]

                # Validate selection
                if box_gid not in self._available_boxes:
                    _LOGGER.error("Selected box GID %s not in available boxes", box_gid)
                    errors["base"] = "no_boxes"
                else:
                    box_info = self._available_boxes[box_gid]
                    box_name = box_info.get("name", f"Firewalla {box_info.get('model', 'Box')}")
                    
                    _LOGGER.debug("Creating config entry for box %s (GID: %s)", box_name, box_gid)
                    
                    # Test rule access before completing setup
                    await self._test_rule_access()
                    
                    # Check if this box is already configured
                    await self.async_set_unique_id(box_gid)
                    self._abort_if_unique_id_configured()

                    # Create the config entry
                    _LOGGER.info("Successfully configured Firewalla integration for %s", box_name)
                    return self.async_create_entry(
                        title=box_name,
                        data={
                            CONF_MSP_URL: self._msp_domain,
                            CONF_ACCESS_TOKEN: self._access_token,
                            CONF_BOX_GID: box_gid,
                        },
                    )
            except RuleAccessFailed as err:
                _LOGGER.error("Cannot access rules: %s", err)
                errors["base"] = "rule_access_failed"
            except Exception as err:
                _LOGGER.exception("Error creating config entry: %s", err)
                errors["base"] = "unknown_error"

        # Create box selection options
        box_options = {}
        for gid, box_info in self._available_boxes.items():
            box_name = box_info.get("name", f"Firewalla {box_info.get('model', 'Box')}")
            box_model = box_info.get("model", "Unknown")
            box_options[gid] = f"{box_name} ({box_model})"

        if not box_options:
            # No boxes available, return to user step with error
            errors["base"] = "no_boxes"
            return await self.async_step_user(self._user_input)

        return self.async_show_form(
            step_id="box_selection",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BOX_GID): vol.In(box_options),
                }
            ),
            errors=errors,
        )

    def _validate_msp_url(self, msp_domain: str) -> bool:
        """Validate MSP URL format (mydomain.firewalla.net)."""
        if not msp_domain:
            return False
        
        # Remove any protocol prefix if present
        if msp_domain.startswith(("http://", "https://")):
            msp_domain = msp_domain.split("://", 1)[1]
        
        # Remove any trailing path
        if "/" in msp_domain:
            msp_domain = msp_domain.split("/", 1)[0]
        
        # Check against pattern
        return bool(MSP_URL_PATTERN.match(msp_domain))

    async def _authenticate_msp(self) -> None:
        """Authenticate with Firewalla MSP API using Token authentication."""
        if not self._msp_domain or not self._access_token:
            raise InvalidAuth("MSP domain and access token are required")

        try:
            _LOGGER.debug("Creating MSP client for authentication test")
            session = async_get_clientsession(self.hass)
            client = FirewallaMSPClient(session, self._msp_domain, self._access_token)
            
            _LOGGER.debug("Testing MSP API authentication")
            if not await client.authenticate():
                _LOGGER.error("MSP API authentication failed - invalid credentials")
                raise InvalidAuth("MSP API authentication failed - please check your access token")
                
            _LOGGER.info("MSP API authentication successful for domain: %s", self._msp_domain)
            
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Cannot connect to MSP API at %s: %s", self._msp_domain, err)
            raise CannotConnect(f"Cannot connect to MSP API at {self._msp_domain}: {err}") from err
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

    async def _get_available_boxes(self) -> None:
        """Get available Firewalla boxes from MSP account."""
        if not self._msp_domain or not self._access_token:
            raise InvalidAuth("MSP domain and access token are required")

        try:
            session = async_get_clientsession(self.hass)
            client = FirewallaMSPClient(session, self._msp_domain, self._access_token)
            
            # Get list of boxes - for now we'll use rules endpoint to test access
            # since the official examples don't show a boxes endpoint
            _LOGGER.debug("Testing MSP API access by fetching rules")
            rules_response = await client.get_rules()
            
            if rules_response is not None:
                # If we can access rules, create a dummy box entry
                # In a real implementation, we'd use the actual boxes endpoint
                self._available_boxes = {
                    "default": {
                        "gid": "default",
                        "name": f"Firewalla Box",
                        "model": "Unknown",
                        "online": True,
                    }
                }
                _LOGGER.info("Successfully accessed MSP API rules endpoint")
            else:
                _LOGGER.warning("No response from MSP API rules endpoint")
                self._available_boxes = {}
            
        except aiohttp.ClientError as err:
            _LOGGER.error("Cannot connect to MSP API: %s", err)
            raise CannotConnect(f"Cannot connect to MSP API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting boxes: %s", err)
            raise HomeAssistantError(f"Failed to get boxes: {err}") from err

    async def _test_rule_access(self) -> None:
        """Test rule access permissions using /v2/rules endpoint."""
        if not self._msp_domain or not self._access_token:
            raise RuleAccessFailed("MSP domain and access token are required")

        try:
            session = async_get_clientsession(self.hass)
            client = FirewallaMSPClient(session, self._msp_domain, self._access_token)
            
            _LOGGER.debug("Testing rule access permissions")
            rules_response = await client.get_rules()
            
            if rules_response is not None:
                _LOGGER.info("Rule access test successful")
            else:
                _LOGGER.error("Rule access test failed - no response")
                raise RuleAccessFailed("Cannot access rules - check your MSP permissions")
                
        except aiohttp.ClientResponseError as err:
            if err.status == 403:
                _LOGGER.error("Rule access forbidden: Insufficient permissions (HTTP 403)")
                raise RuleAccessFailed("Access to rules forbidden - check your MSP account permissions") from err
            else:
                _LOGGER.error("Rule access test failed with HTTP %d: %s", err.status, err.message)
                raise RuleAccessFailed(f"Rule access test failed: HTTP {err.status}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error during rule access test: %s", err)
            raise CannotConnect(f"Network error during rule access test: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during rule access test: %s", err)
            raise RuleAccessFailed(f"Rule access test failed due to unexpected error: {err}") from err

    @staticmethod
    @config_entries.HANDLERS.register(DOMAIN)
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Firewalla integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Parse the filter strings into lists
            include_filters = self._parse_filter_string(user_input.get(CONF_INCLUDE_FILTERS, ""))
            exclude_filters = self._parse_filter_string(user_input.get(CONF_EXCLUDE_FILTERS, ""))
            
            options_data = {
                CONF_INCLUDE_FILTERS: include_filters,
                CONF_EXCLUDE_FILTERS: exclude_filters,
            }
            
            return self.async_create_entry(title="", data=options_data)

        # Get current options
        current_options = self.config_entry.options
        include_filters = current_options.get(CONF_INCLUDE_FILTERS, [])
        exclude_filters = current_options.get(CONF_EXCLUDE_FILTERS, [])

        # Convert lists to newline-separated strings for the form
        include_filters_str = "\n".join(include_filters) if include_filters else ""
        exclude_filters_str = "\n".join(exclude_filters) if exclude_filters else ""

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_FILTERS,
                        default=include_filters_str,
                        description={
                            "suggested_value": include_filters_str
                        }
                    ): str,
                    vol.Optional(
                        CONF_EXCLUDE_FILTERS,
                        default=exclude_filters_str,
                        description={
                            "suggested_value": exclude_filters_str
                        }
                    ): str,
                }
            ),
            description_placeholders={
                "include_examples": "status:active\naction:block\ntarget.type:app",
                "exclude_examples": "-status:paused\n-action:allow\n-target.type:category",
            },
        )

    def _parse_filter_string(self, filter_string: str) -> list:
        """Parse a newline-separated filter string into a list."""
        if not filter_string or not filter_string.strip():
            return []
        
        filters = []
        for line in filter_string.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):  # Allow comments with #
                filters.append(line)
        
        return filters


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect to MSP API."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class RuleAccessFailed(HomeAssistantError):
    """Error to indicate we cannot access rules."""