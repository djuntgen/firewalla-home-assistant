"""Data update coordinator for Firewalla integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_ENDPOINTS,
    API_TIMEOUT,
    DOMAIN,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class FirewallaMSPClient:
    """Client for Firewalla MSP API communication."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        msp_url: str,
        access_token: str,
    ) -> None:
        """Initialize the MSP API client."""
        self._session = session
        self._msp_url = msp_url.rstrip("/")
        self._access_token = access_token
        self._authenticated = False
        self._auth_lock = asyncio.Lock()

    async def authenticate(self) -> bool:
        """Authenticate with the MSP API and validate the token."""
        try:
            _LOGGER.debug("Attempting MSP API authentication")
            # Test authentication by fetching boxes list
            response = await self._make_request("GET", API_ENDPOINTS["boxes"], retry_auth=False)
            if response and "data" in response:
                self._authenticated = True
                _LOGGER.info("MSP API authentication successful")
                return True
            else:
                _LOGGER.error("MSP API authentication failed: Invalid response format - %s", response)
                return False
        except ConfigEntryAuthFailed as err:
            _LOGGER.error("MSP API authentication failed: Invalid credentials - %s", err)
            return False
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("MSP API authentication failed: Cannot connect to server - %s", err)
            return False
        except aiohttp.ClientResponseError as err:
            _LOGGER.error("MSP API authentication failed: HTTP %d - %s", err.status, err.message)
            return False
        except Exception as err:
            _LOGGER.exception("MSP API authentication failed with unexpected error: %s", err)
            return False

    async def _refresh_authentication(self) -> bool:
        """Refresh authentication by re-validating the current token."""
        try:
            _LOGGER.debug("Attempting MSP API token refresh")
            # Reset authentication state
            self._authenticated = False
            
            # Test the current token by making a simple API call
            response = await self._make_request("GET", API_ENDPOINTS["boxes"], retry_auth=False)
            if response and "data" in response:
                self._authenticated = True
                _LOGGER.info("MSP API token refresh successful")
                return True
            else:
                _LOGGER.error("MSP API token refresh failed: Invalid response format - %s", response)
                return False
        except ConfigEntryAuthFailed as err:
            _LOGGER.error("MSP API token refresh failed: Authentication error - %s", err)
            return False
        except aiohttp.ClientError as err:
            _LOGGER.error("MSP API token refresh failed: Network error - %s", err)
            return False
        except Exception as err:
            _LOGGER.exception("MSP API token refresh failed with unexpected error: %s", err)
            return False

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the MSP API with retry logic."""
        url = f"{self._msp_url}{endpoint}"
        headers = {
            "Authorization": f"Token {self._access_token}",
            "Content-Type": "application/json",
        }

        for attempt in range(RETRY_ATTEMPTS):
            try:
                timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
                
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=data,
                    timeout=timeout,
                    **kwargs,
                ) as response:
                    _LOGGER.debug(
                        "MSP API request: %s %s (attempt %d/%d) - Status: %d",
                        method,
                        url,
                        attempt + 1,
                        RETRY_ATTEMPTS,
                        response.status,
                    )

                    # Handle authentication errors
                    if response.status == 401:
                        if retry_auth:
                            _LOGGER.warning("MSP API authentication expired (HTTP 401), attempting refresh")
                            async with self._auth_lock:
                                if await self._refresh_authentication():
                                    # Update headers with refreshed token and retry
                                    headers["Authorization"] = f"Token {self._access_token}"
                                    _LOGGER.debug("Token refreshed, retrying request")
                                    continue
                                else:
                                    _LOGGER.error("MSP API authentication refresh failed")
                                    raise ConfigEntryAuthFailed("MSP API authentication refresh failed")
                        else:
                            _LOGGER.error("MSP API authentication failed (HTTP 401)")
                            raise ConfigEntryAuthFailed("MSP API authentication failed")
                    
                    # Handle rate limiting
                    if response.status == 429:
                        wait_time = RETRY_BACKOFF_FACTOR ** attempt
                        _LOGGER.warning(
                            "MSP API rate limited (HTTP 429), waiting %d seconds before retry (attempt %d/%d)",
                            wait_time, attempt + 1, RETRY_ATTEMPTS
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Handle other HTTP errors
                    if response.status >= 400:
                        error_text = await response.text()
                        _LOGGER.error(
                            "MSP API returned HTTP %d for %s %s: %s",
                            response.status, method, url, error_text
                        )
                        
                        if response.status == 403:
                            raise ConfigEntryAuthFailed(f"MSP API access forbidden (HTTP 403): {error_text}")
                        elif response.status == 404:
                            raise HomeAssistantError(f"MSP API endpoint not found (HTTP 404): {url}")
                        elif response.status >= 500:
                            raise HomeAssistantError(f"MSP API server error (HTTP {response.status}): {error_text}")
                        else:
                            raise HomeAssistantError(f"MSP API error (HTTP {response.status}): {error_text}")

                    # Success - parse response
                    try:
                        result = await response.json()
                        _LOGGER.debug("MSP API response received: %d bytes", len(str(result)))
                        return result
                    except aiohttp.ContentTypeError as err:
                        # Handle non-JSON responses
                        text = await response.text()
                        _LOGGER.debug("MSP API non-JSON response: %s", text[:200])
                        if response.status == 200:
                            return {"success": True, "data": text}
                        else:
                            _LOGGER.error("MSP API returned non-JSON error response: %s", text)
                            raise HomeAssistantError(f"MSP API returned invalid response format: {err}")

            except asyncio.TimeoutError as err:
                _LOGGER.warning(
                    "MSP API timeout on attempt %d/%d for %s %s: %s",
                    attempt + 1,
                    RETRY_ATTEMPTS,
                    method,
                    url,
                    err,
                )
                if attempt == RETRY_ATTEMPTS - 1:
                    _LOGGER.error("MSP API timeout after %d attempts for %s %s", RETRY_ATTEMPTS, method, url)
                    raise HomeAssistantError(f"MSP API timeout after {RETRY_ATTEMPTS} attempts")
                
                # Exponential backoff
                wait_time = RETRY_BACKOFF_FACTOR ** attempt
                _LOGGER.debug("Waiting %d seconds before retry due to timeout", wait_time)
                await asyncio.sleep(wait_time)

            except aiohttp.ClientConnectorError as err:
                _LOGGER.warning(
                    "MSP API connection error on attempt %d/%d for %s %s: %s",
                    attempt + 1,
                    RETRY_ATTEMPTS,
                    method,
                    url,
                    err,
                )
                if attempt == RETRY_ATTEMPTS - 1:
                    _LOGGER.error("MSP API connection failed after %d attempts: %s", RETRY_ATTEMPTS, err)
                    raise HomeAssistantError(f"Cannot connect to MSP API: {err}")
                
                # Exponential backoff
                wait_time = RETRY_BACKOFF_FACTOR ** attempt
                _LOGGER.debug("Waiting %d seconds before retry due to connection error", wait_time)
                await asyncio.sleep(wait_time)

            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    "MSP API client error on attempt %d/%d for %s %s: %s",
                    attempt + 1,
                    RETRY_ATTEMPTS,
                    method,
                    url,
                    err,
                )
                if attempt == RETRY_ATTEMPTS - 1:
                    _LOGGER.error("MSP API client error after %d attempts: %s", RETRY_ATTEMPTS, err)
                    raise HomeAssistantError(f"MSP API client error: {err}")
                
                # Exponential backoff
                wait_time = RETRY_BACKOFF_FACTOR ** attempt
                _LOGGER.debug("Waiting %d seconds before retry due to client error", wait_time)
                await asyncio.sleep(wait_time)

            except (ConfigEntryAuthFailed, HomeAssistantError):
                # Don't retry authentication failures or other Home Assistant errors
                raise

            except Exception as err:
                _LOGGER.error(
                    "Unexpected MSP API error on attempt %d/%d for %s %s: %s",
                    attempt + 1,
                    RETRY_ATTEMPTS,
                    method,
                    url,
                    err,
                )
                if attempt == RETRY_ATTEMPTS - 1:
                    _LOGGER.exception("Unexpected MSP API error after %d attempts", RETRY_ATTEMPTS)
                    raise HomeAssistantError(f"Unexpected MSP API error: {err}")
                
                # Exponential backoff
                wait_time = RETRY_BACKOFF_FACTOR ** attempt
                _LOGGER.debug("Waiting %d seconds before retry due to unexpected error", wait_time)
                await asyncio.sleep(wait_time)

        _LOGGER.error("MSP API request failed after all %d retry attempts for %s %s", RETRY_ATTEMPTS, method, url)
        raise HomeAssistantError(f"MSP API request failed after {RETRY_ATTEMPTS} attempts")

    async def get_boxes(self) -> Dict[str, Any]:
        """Get list of available Firewalla boxes."""
        return await self._make_request("GET", API_ENDPOINTS["boxes"])

    async def get_box_info(self, box_gid: str) -> Dict[str, Any]:
        """Get information about a specific Firewalla box."""
        endpoint = API_ENDPOINTS["box_info"].format(gid=box_gid)
        return await self._make_request("GET", endpoint)

    async def get_devices(self, box_gid: str) -> Dict[str, Any]:
        """Get devices connected to a Firewalla box."""
        endpoint = API_ENDPOINTS["devices"].format(gid=box_gid)
        return await self._make_request("GET", endpoint)

    async def get_rules(self, box_gid: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Get rules for a Firewalla box with optional query parameters."""
        endpoint = API_ENDPOINTS["rules"].format(gid=box_gid)
        if query:
            endpoint += f"?query={query}"
        return await self._make_request("GET", endpoint)

    async def create_rule(self, box_gid: str, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new rule for a Firewalla box."""
        endpoint = API_ENDPOINTS["create_rule"].format(gid=box_gid)
        return await self._make_request("POST", endpoint, data=rule_data)

    async def pause_rule(self, box_gid: str, rule_id: str) -> Dict[str, Any]:
        """Pause a rule for a Firewalla box."""
        endpoint = API_ENDPOINTS["pause_rule"].format(gid=box_gid, rid=rule_id)
        return await self._make_request("POST", endpoint)

    async def unpause_rule(self, box_gid: str, rule_id: str) -> Dict[str, Any]:
        """Unpause a rule for a Firewalla box."""
        endpoint = API_ENDPOINTS["unpause_rule"].format(gid=box_gid, rid=rule_id)
        return await self._make_request("POST", endpoint)

    @property
    def is_authenticated(self) -> bool:
        """Return whether the client is authenticated."""
        return self._authenticated


class FirewallaDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Firewalla MSP API."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        msp_url: str,
        access_token: str,
        box_gid: str,
    ) -> None:
        """Initialize the coordinator."""
        self.api = FirewallaMSPClient(session, msp_url, access_token)
        self.box_gid = box_gid
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from MSP API with automatic token refresh."""
        _LOGGER.debug("Starting MSP API data update for box %s", self.box_gid)
        
        try:
            # Ensure we're authenticated
            if not self.api.is_authenticated:
                _LOGGER.debug("API not authenticated, attempting initial authentication")
                if not await self.api.authenticate():
                    _LOGGER.error("MSP API authentication failed during data update")
                    raise ConfigEntryAuthFailed("MSP API authentication failed")

            # Fetch all required data concurrently for better performance
            _LOGGER.debug("Fetching data from MSP API endpoints concurrently")
            try:
                box_info_task = self.api.get_box_info(self.box_gid)
                devices_task = self.api.get_devices(self.box_gid)
                rules_task = self.api.get_rules(self.box_gid)
                
                box_info, devices, rules = await asyncio.gather(
                    box_info_task, devices_task, rules_task, return_exceptions=True
                )
                
                # Check for exceptions in the results
                if isinstance(box_info, Exception):
                    _LOGGER.error("Failed to fetch box info: %s", box_info)
                    raise box_info
                if isinstance(devices, Exception):
                    _LOGGER.error("Failed to fetch devices: %s", devices)
                    raise devices
                if isinstance(rules, Exception):
                    _LOGGER.error("Failed to fetch rules: %s", rules)
                    raise rules
                
                # Validate API responses
                if not isinstance(box_info, dict) or "data" not in box_info:
                    _LOGGER.error("Invalid box info response format: %s", box_info)
                    raise UpdateFailed("Invalid box info response from MSP API")
                
                if not isinstance(devices, dict) or "data" not in devices:
                    _LOGGER.error("Invalid devices response format: %s", devices)
                    raise UpdateFailed("Invalid devices response from MSP API")
                
                if not isinstance(rules, dict) or "data" not in rules:
                    _LOGGER.error("Invalid rules response format: %s", rules)
                    raise UpdateFailed("Invalid rules response from MSP API")
                
                # Process and structure the data
                box_data = box_info.get("data", {})
                devices_data = self._process_devices_data(devices.get("data", {}))
                rules_data = self._process_rules_data(rules.get("data", {}))
                
                processed_data = {
                    "box_info": box_data,
                    "devices": devices_data,
                    "rules": rules_data,
                    "last_updated": self.last_update_success,
                }
                
                _LOGGER.debug(
                    "Successfully updated data from MSP API: %d devices, %d rules",
                    len(devices_data),
                    len(rules_data)
                )
                return processed_data

            except ConfigEntryAuthFailed:
                # Authentication failed during data fetch
                _LOGGER.error("Authentication failed during data update")
                raise

        except ConfigEntryAuthFailed:
            # Re-raise authentication errors without wrapping
            raise
        except UpdateFailed:
            # Re-raise UpdateFailed errors without wrapping
            raise
        except HomeAssistantError as err:
            _LOGGER.error("Home Assistant error during data update: %s", err)
            raise UpdateFailed(f"Home Assistant error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during MSP API data update: %s", err)
            raise UpdateFailed(f"Unexpected error communicating with MSP API: {err}") from err

    def _process_devices_data(self, devices_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and normalize devices data from the API."""
        if not isinstance(devices_data, dict):
            _LOGGER.warning("Invalid devices data format received from API: %s", type(devices_data))
            return {}
        
        processed_devices = {}
        invalid_devices = 0
        
        for device_id, device_info in devices_data.items():
            try:
                if not isinstance(device_info, dict):
                    _LOGGER.debug("Skipping invalid device data for %s: %s", device_id, type(device_info))
                    invalid_devices += 1
                    continue
                
                # Ensure required fields exist with defaults
                processed_device = {
                    "mac": device_info.get("mac", device_id),
                    "name": device_info.get("name", f"Device {device_id}"),
                    "ip": device_info.get("ip", ""),
                    "online": bool(device_info.get("online", False)),
                    "lastActiveTimestamp": device_info.get("lastActiveTimestamp", 0),
                    "deviceClass": device_info.get("deviceClass", "unknown"),
                }
                
                # Include all original fields, but validate critical ones
                for key, value in device_info.items():
                    if key not in processed_device:
                        processed_device[key] = value
                
                processed_devices[device_id] = processed_device
                
            except Exception as err:
                _LOGGER.warning("Error processing device %s: %s", device_id, err)
                invalid_devices += 1
                continue
        
        if invalid_devices > 0:
            _LOGGER.warning("Skipped %d invalid device entries", invalid_devices)
        
        _LOGGER.debug("Processed %d valid devices", len(processed_devices))
        return processed_devices

    def _process_rules_data(self, rules_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and normalize rules data from the API."""
        if not isinstance(rules_data, dict):
            _LOGGER.warning("Invalid rules data format received from API: %s", type(rules_data))
            return {}
        
        processed_rules = {}
        invalid_rules = 0
        
        for rule_id, rule_info in rules_data.items():
            try:
                if not isinstance(rule_info, dict):
                    _LOGGER.debug("Skipping invalid rule data for %s: %s", rule_id, type(rule_info))
                    invalid_rules += 1
                    continue
                
                # Ensure required fields exist with defaults
                processed_rule = {
                    "rid": rule_info.get("rid", rule_id),
                    "type": rule_info.get("type", "unknown"),
                    "target": rule_info.get("target", ""),
                    "disabled": bool(rule_info.get("disabled", False)),
                    "paused": bool(rule_info.get("paused", False)),
                    "action": rule_info.get("action", "block"),
                    "description": rule_info.get("description", ""),
                }
                
                # Include all original fields
                for key, value in rule_info.items():
                    if key not in processed_rule:
                        processed_rule[key] = value
                
                processed_rules[rule_id] = processed_rule
                
            except Exception as err:
                _LOGGER.warning("Error processing rule %s: %s", rule_id, err)
                invalid_rules += 1
                continue
        
        if invalid_rules > 0:
            _LOGGER.warning("Skipped %d invalid rule entries", invalid_rules)
        
        _LOGGER.debug("Processed %d valid rules", len(processed_rules))
        return processed_rules

    async def async_get_box_devices(self) -> Dict[str, Any]:
        """Get managed devices for the specific Firewalla box.
        
        Returns a dictionary of devices with MAC addresses as keys.
        Each device contains: mac, name, ip, online, lastActiveTimestamp, deviceClass.
        """
        try:
            # First try to get from cached data
            if self.data and "devices" in self.data:
                return self.data["devices"]
            
            # If no cached data, fetch directly from API
            _LOGGER.debug("Fetching devices directly from API for box %s", self.box_gid)
            response = await self.api.get_devices(self.box_gid)
            
            if response and "data" in response:
                devices_data = self._process_devices_data(response["data"])
                _LOGGER.debug("Retrieved %d devices from API", len(devices_data))
                return devices_data
            else:
                _LOGGER.warning("No device data received from API")
                return {}
                
        except Exception as err:
            _LOGGER.error("Failed to get box devices: %s", err)
            return {}

    async def async_get_rules(self, query: Optional[str] = None) -> Dict[str, Any]:
        """Get current rules and their status with optional filtering.
        
        Args:
            query: Optional query string for filtering rules (e.g., "status:active", "action:block")
            
        Returns a dictionary of rules with rule IDs as keys.
        Each rule contains: rid, type, target, disabled, paused, action, description.
        """
        try:
            # If no query specified and we have cached data, return it
            if not query and self.data and "rules" in self.data:
                return self.data["rules"]
            
            # Fetch from API with optional query
            _LOGGER.debug("Fetching rules from API for box %s with query: %s", self.box_gid, query)
            response = await self.api.get_rules(self.box_gid, query)
            
            if response and "data" in response:
                # Handle both direct data and paginated results
                rules_data = response["data"]
                if isinstance(rules_data, dict) and "results" in rules_data:
                    # Paginated response format
                    rules_list = rules_data["results"]
                    rules_dict = {rule.get("id", rule.get("rid", str(i))): rule for i, rule in enumerate(rules_list)}
                elif isinstance(rules_data, list):
                    # Direct list format
                    rules_dict = {rule.get("id", rule.get("rid", str(i))): rule for i, rule in enumerate(rules_data)}
                else:
                    # Direct dictionary format
                    rules_dict = rules_data
                
                processed_rules = self._process_rules_data(rules_dict)
                _LOGGER.debug("Retrieved %d rules from API", len(processed_rules))
                return processed_rules
            else:
                _LOGGER.warning("No rules data received from API")
                return {}
                
        except Exception as err:
            _LOGGER.error("Failed to get rules: %s", err)
            return {}

    async def async_create_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new rule for device blocking or gaming pause.
        
        Args:
            rule_data: Rule configuration containing:
                - type: Rule type ("internet" for blocking, "gaming" for gaming pause)
                - target: Target device MAC address (format: "mac:aa:bb:cc:dd:ee:ff")
                - action: Rule action ("block" or "allow")
                - description: Human-readable description
                - Additional rule-specific parameters
                
        Returns the created rule data from the API response.
        """
        try:
            _LOGGER.debug("Creating rule for box %s: %s", self.box_gid, rule_data)
            
            # Validate required fields
            required_fields = ["type", "target", "action"]
            for field in required_fields:
                if field not in rule_data:
                    raise ValueError(f"Missing required field '{field}' in rule data")
            
            # Ensure target is in correct format for MAC addresses
            if rule_data["target"] and not rule_data["target"].startswith("mac:"):
                if ":" in rule_data["target"] and len(rule_data["target"]) == 17:
                    # Looks like a MAC address, add the mac: prefix
                    rule_data["target"] = f"mac:{rule_data['target']}"
            
            result = await self.api.create_rule(self.box_gid, rule_data)
            
            if result and "data" in result:
                _LOGGER.info("Successfully created rule: %s", result["data"].get("id", "unknown"))
                # Trigger a data refresh to get the updated rules
                await self.async_request_refresh()
                return result["data"]
            else:
                _LOGGER.error("Invalid response when creating rule: %s", result)
                raise HomeAssistantError("Failed to create rule: Invalid API response")
                
        except Exception as err:
            _LOGGER.error("Failed to create rule: %s", err)
            raise

    async def async_pause_rule(self, rule_id: str) -> Dict[str, Any]:
        """Pause a rule to temporarily disable it while preserving for future use.
        
        Args:
            rule_id: The unique identifier of the rule to pause
            
        Returns the API response confirming the rule was paused.
        """
        try:
            _LOGGER.debug("Pausing rule %s for box %s", rule_id, self.box_gid)
            
            if not rule_id:
                raise ValueError("Rule ID cannot be empty")
            
            result = await self.api.pause_rule(self.box_gid, rule_id)
            
            if result:
                _LOGGER.info("Successfully paused rule: %s", rule_id)
                # Trigger a data refresh to get the updated rule status
                await self.async_request_refresh()
                return result
            else:
                _LOGGER.error("Invalid response when pausing rule %s: %s", rule_id, result)
                raise HomeAssistantError(f"Failed to pause rule {rule_id}: Invalid API response")
                
        except Exception as err:
            _LOGGER.error("Failed to pause rule %s: %s", rule_id, err)
            raise

    async def async_unpause_rule(self, rule_id: str) -> Dict[str, Any]:
        """Unpause a rule to re-enable it.
        
        Args:
            rule_id: The unique identifier of the rule to unpause
            
        Returns the API response confirming the rule was unpaused.
        """
        try:
            _LOGGER.debug("Unpausing rule %s for box %s", rule_id, self.box_gid)
            
            if not rule_id:
                raise ValueError("Rule ID cannot be empty")
            
            result = await self.api.unpause_rule(self.box_gid, rule_id)
            
            if result:
                _LOGGER.info("Successfully unpaused rule: %s", rule_id)
                # Trigger a data refresh to get the updated rule status
                await self.async_request_refresh()
                return result
            else:
                _LOGGER.error("Invalid response when unpausing rule %s: %s", rule_id, result)
                raise HomeAssistantError(f"Failed to unpause rule {rule_id}: Invalid API response")
                
        except Exception as err:
            _LOGGER.error("Failed to unpause rule %s: %s", rule_id, err)
            raise

    @property
    def box_info(self) -> Dict[str, Any]:
        """Get box information from cached data."""
        if self.data and "box_info" in self.data:
            return self.data["box_info"]
        return {}

    @property
    def devices(self) -> Dict[str, Any]:
        """Get devices from cached data."""
        if self.data and "devices" in self.data:
            return self.data["devices"]
        return {}

    @property
    def rules(self) -> Dict[str, Any]:
        """Get rules from cached data."""
        if self.data and "rules" in self.data:
            return self.data["rules"]
        return {}

    async def async_create_device_block_rule(self, device_mac: str, device_name: str = None) -> Dict[str, Any]:
        """Create an internet blocking rule for a specific device.
        
        Args:
            device_mac: MAC address of the device to block
            device_name: Optional friendly name for the rule description
            
        Returns the created rule data.
        """
        rule_data = {
            "type": "internet",
            "target": f"mac:{device_mac}" if not device_mac.startswith("mac:") else device_mac,
            "action": "block",
            "description": f"Block internet access for {device_name or device_mac}",
            "enabled": True
        }
        
        return await self.async_create_rule(rule_data)

    async def async_create_gaming_pause_rule(self, device_mac: str, device_name: str = None) -> Dict[str, Any]:
        """Create a gaming pause rule for a specific device.
        
        Args:
            device_mac: MAC address of the device to pause gaming
            device_name: Optional friendly name for the rule description
            
        Returns the created rule data.
        """
        rule_data = {
            "type": "gaming",
            "target": f"mac:{device_mac}" if not device_mac.startswith("mac:") else device_mac,
            "action": "block",
            "description": f"Gaming pause for {device_name or device_mac}",
            "enabled": True
        }
        
        return await self.async_create_rule(rule_data)

    async def async_get_device_rules(self, device_mac: str, rule_type: str = None) -> Dict[str, Any]:
        """Get all rules for a specific device, optionally filtered by type.
        
        Args:
            device_mac: MAC address of the device
            rule_type: Optional rule type filter ("internet", "gaming", etc.)
            
        Returns dictionary of rules for the device.
        """
        try:
            # Format MAC address consistently
            target_mac = f"mac:{device_mac}" if not device_mac.startswith("mac:") else device_mac
            
            # Get all rules and filter for this device
            all_rules = await self.async_get_rules()
            device_rules = {}
            
            for rule_id, rule_data in all_rules.items():
                if rule_data.get("target") == target_mac:
                    if not rule_type or rule_data.get("type") == rule_type:
                        device_rules[rule_id] = rule_data
            
            _LOGGER.debug("Found %d rules for device %s (type: %s)", len(device_rules), device_mac, rule_type)
            return device_rules
            
        except Exception as err:
            _LOGGER.error("Failed to get device rules for %s: %s", device_mac, err)
            return {}

    @property
    def devices(self) -> Dict[str, Any]:
        """Get devices data from coordinator."""
        if self.data and "devices" in self.data:
            return self.data["devices"]
        return {}

    @property
    def box_info(self) -> Dict[str, Any]:
        """Get box information from coordinator."""
        if self.data and "box_info" in self.data:
            return self.data["box_info"]
        return {}

    @property
    def rules(self) -> Dict[str, Any]:
        """Get rules data from coordinator."""
        if self.data and "rules" in self.data:
            return self.data["rules"]
        return {}

    def get_device_by_mac(self, mac_address: str) -> Optional[Dict[str, Any]]:
        """Get device information by MAC address from cached data.
        
        Args:
            mac_address: MAC address of the device
            
        Returns device data or None if not found.
        """
        devices = self.devices
        return devices.get(mac_address)

    def get_device_friendly_name(self, device_mac: str, device_data: Dict[str, Any] = None) -> str:
        """Get a friendly name for a device, handling disambiguation for multiple devices.
        
        Args:
            device_mac: MAC address of the device
            device_data: Optional device data (will fetch if not provided)
            
        Returns a friendly, disambiguated device name.
        """
        if device_data is None:
            device_data = self.get_device_by_mac(device_mac)
            if not device_data:
                return f"Device {device_mac}"
        
        # Get the base name from device data
        base_name = device_data.get("name", "")
        hostname = device_data.get("hostname", "")
        
        # Prefer hostname over name if available and different
        if hostname and hostname != base_name:
            friendly_name = self._sanitize_device_name(hostname)
        elif base_name:
            friendly_name = self._sanitize_device_name(base_name)
        else:
            # Fallback to device class or MAC
            device_class = device_data.get("deviceClass", "")
            if device_class and device_class != "unknown":
                friendly_name = f"{self._format_model_name(device_class)}"
            else:
                friendly_name = f"Device {device_mac}"
        
        # Check for name conflicts with other devices
        all_devices = self.devices
        conflicting_devices = []
        
        for other_mac, other_data in all_devices.items():
            if other_mac != device_mac:
                other_name = other_data.get("name", "")
                other_hostname = other_data.get("hostname", "")
                
                # Check if names would conflict
                if (other_hostname and other_hostname == friendly_name) or \
                   (other_name and other_name == friendly_name):
                    conflicting_devices.append(other_mac)
        
        # If there are conflicts, add disambiguation
        if conflicting_devices:
            # Add IP address for disambiguation if available
            device_ip = device_data.get("ip", "")
            if device_ip:
                friendly_name = f"{friendly_name} ({device_ip})"
            else:
                # Fallback to last 4 characters of MAC address
                mac_suffix = device_mac.replace(":", "")[-4:].upper()
                friendly_name = f"{friendly_name} ({mac_suffix})"
        
        return friendly_name

    def get_device_info_dict(self, device_mac: str, device_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get comprehensive device info dictionary for Home Assistant device registry.
        
        Args:
            device_mac: MAC address of the device
            device_data: Optional device data (will fetch if not provided)
            
        Returns device info dictionary with all required fields.
        """
        if device_data is None:
            device_data = self.get_device_by_mac(device_mac)
            if not device_data:
                return {}
        
        # Get friendly name with disambiguation
        friendly_name = self.get_device_friendly_name(device_mac, device_data)
        
        # Get box information for firmware version
        box_data = self.box_info
        
        # Determine device model based on device class
        device_class = device_data.get("deviceClass", "unknown")
        model = self._format_model_name(device_class)
        
        # Build device info dictionary
        device_info = {
            "identifiers": {(DOMAIN, device_mac)},
            "name": friendly_name,
            "manufacturer": "Firewalla",
            "model": model,
        }
        
        # Add firmware version from box info if available
        firmware_version = box_data.get("version") or box_data.get("firmwareVersion")
        if firmware_version:
            device_info["sw_version"] = firmware_version
        
        # Add connection via Firewalla box
        if hasattr(self, 'box_gid') and self.box_gid:
            device_info["via_device"] = (DOMAIN, self.box_gid)
        
        # Add additional identifiers if available
        device_ip = device_data.get("ip")
        if device_ip:
            device_info["connections"] = {("ip", device_ip)}
        
        return device_info

    def get_all_device_info_dicts(self) -> Dict[str, Dict[str, Any]]:
        """Get device info dictionaries for all devices.
        
        Returns a dictionary mapping MAC addresses to device info dictionaries.
        """
        device_info_dicts = {}
        devices = self.devices
        
        for device_mac, device_data in devices.items():
            device_info_dicts[device_mac] = self.get_device_info_dict(device_mac, device_data)
        
        return device_info_dicts

    def has_device_info_changed(self, device_mac: str, previous_device_data: Dict[str, Any]) -> bool:
        """Check if device information has changed since the last update.
        
        Args:
            device_mac: MAC address of the device
            previous_device_data: Previous device data to compare against
            
        Returns True if device info has changed, False otherwise.
        """
        current_device_data = self.get_device_by_mac(device_mac)
        if not current_device_data:
            return previous_device_data is not None
        
        # Check key fields that affect device info
        key_fields = ["name", "hostname", "deviceClass", "ip"]
        
        for field in key_fields:
            if current_device_data.get(field) != previous_device_data.get(field):
                return True
        
        # Check if box info has changed (affects firmware version)
        box_data = self.box_info
        if box_data.get("version") != getattr(self, '_last_box_version', None):
            self._last_box_version = box_data.get("version")
            return True
        
        return False

    def _sanitize_device_name(self, name: str) -> str:
        """Sanitize device name for use in Home Assistant.
        
        Args:
            name: Raw device name
            
        Returns sanitized name suitable for Home Assistant entities.
        """
        if not name or not isinstance(name, str):
            return "Unknown Device"
        
        # Remove or replace problematic characters
        import re
        
        # Replace common problematic characters
        sanitized = name.strip()
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', sanitized)  # Replace filesystem-unsafe chars
        sanitized = re.sub(r'\s+', ' ', sanitized)  # Normalize whitespace
        sanitized = sanitized.strip('_. ')  # Remove leading/trailing punctuation
        
        # Ensure name is not empty after sanitization
        if not sanitized:
            return "Unknown Device"
        
        # Limit length to reasonable size
        if len(sanitized) > 50:
            sanitized = sanitized[:47] + "..."
        
        return sanitized

    def _format_model_name(self, device_class: str) -> str:
        """Format device class into a readable model name.
        
        Args:
            device_class: Raw device class from API
            
        Returns formatted model name.
        """
        if not device_class or device_class == "unknown":
            return "Network Device"
        
        # Handle common device classes
        class_mappings = {
            "gaming_console": "Gaming Console",
            "smart_tv": "Smart TV",
            "mobile_phone": "Mobile Phone",
            "laptop": "Laptop",
            "desktop": "Desktop Computer",
            "tablet": "Tablet",
            "smart_speaker": "Smart Speaker",
            "iot_device": "IoT Device",
            "router": "Router",
            "access_point": "Access Point",
        }
        
        # Check for direct mapping
        if device_class.lower() in class_mappings:
            return class_mappings[device_class.lower()]
        
        # Format by replacing underscores and capitalizing
        formatted = device_class.replace("_", " ").replace("-", " ")
        formatted = " ".join(word.capitalize() for word in formatted.split())
        
        return formatted