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
    AUTH_HEADER_FORMAT,
    CONTENT_TYPE,
    DOMAIN,
    MSP_API_V2_BASE,
    RETRY_ATTEMPTS,
    RETRY_DELAYS,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class FirewallaMSPClient:
    """Client for Firewalla MSP API communication focused on rule management."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        msp_domain: str,
        access_token: str,
    ) -> None:
        """Initialize the MSP API client."""
        self._session = session
        self._access_token = access_token
        
        # Parse MSP domain to handle both formats: 
        # - mydomain.firewalla.net
        # - https://mydomain.firewalla.net
        parsed_domain = msp_domain.rstrip("/")
        if parsed_domain.startswith(("http://", "https://")):
            # Extract domain from full URL
            parsed_domain = parsed_domain.split("://", 1)[1]
        
        self._msp_domain = parsed_domain
        self._base_url = MSP_API_V2_BASE.format(domain=self._msp_domain)
        self._authenticated = False
        self._auth_lock = asyncio.Lock()

    async def authenticate(self) -> bool:
        """Authenticate with the MSP API and validate the token."""
        try:
            _LOGGER.debug("Attempting MSP API authentication")
            # Test authentication by fetching rules list
            response = await self._make_request("GET", API_ENDPOINTS["rules"], retry_auth=False)
            if response is not None:
                self._authenticated = True
                _LOGGER.info("MSP API authentication successful")
                return True
            else:
                _LOGGER.error("MSP API authentication failed: Invalid response")
                return False
        except ConfigEntryAuthFailed as err:
            _LOGGER.error("MSP API authentication failed: %s", err)
            return False
        except Exception as err:
            _LOGGER.exception("MSP API authentication failed with unexpected error: %s", err)
            return False

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any] | list | None:
        """Make an authenticated request to the MSP API with retry logic."""
        url = f"{self._base_url}{endpoint}"
        headers = {
            "Authorization": AUTH_HEADER_FORMAT.format(token=self._access_token),
            "Content-Type": CONTENT_TYPE,
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
                            _LOGGER.warning("MSP API authentication expired (HTTP 401)")
                            raise ConfigEntryAuthFailed("MSP API authentication expired")
                        else:
                            _LOGGER.error("MSP API authentication failed (HTTP 401)")
                            raise ConfigEntryAuthFailed("MSP API authentication failed")
                    
                    # Handle rate limiting
                    if response.status == 429:
                        if attempt < RETRY_ATTEMPTS - 1:
                            wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                            _LOGGER.warning(
                                "MSP API rate limited (HTTP 429), waiting %d seconds before retry",
                                wait_time
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise HomeAssistantError("MSP API rate limit exceeded")
                    
                    # Handle other HTTP errors
                    if response.status >= 400:
                        error_text = await response.text()
                        _LOGGER.error(
                            "MSP API returned HTTP %d for %s %s: %s",
                            response.status, method, url, error_text
                        )
                        
                        if response.status == 403:
                            raise ConfigEntryAuthFailed(f"MSP API access forbidden: {error_text}")
                        elif response.status == 404:
                            raise HomeAssistantError(f"MSP API endpoint not found: {url}")
                        elif response.status >= 500:
                            raise HomeAssistantError(f"MSP API server error (HTTP {response.status}): {error_text}")
                        else:
                            raise HomeAssistantError(f"MSP API error (HTTP {response.status}): {error_text}")

                    # Success - parse response
                    try:
                        result = await response.json()
                        _LOGGER.debug("MSP API response received successfully")
                        return result
                    except aiohttp.ContentTypeError:
                        # Handle non-JSON responses (e.g., for pause/unpause operations)
                        if response.status == 200:
                            return {"success": True}
                        else:
                            text = await response.text()
                            _LOGGER.error("MSP API returned non-JSON error response: %s", text)
                            raise HomeAssistantError(f"MSP API returned invalid response format")

            except asyncio.TimeoutError:
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    _LOGGER.warning(
                        "MSP API timeout on attempt %d/%d, waiting %d seconds before retry",
                        attempt + 1, RETRY_ATTEMPTS, wait_time
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    _LOGGER.error("MSP API timeout after %d attempts", RETRY_ATTEMPTS)
                    raise HomeAssistantError(f"MSP API timeout after {RETRY_ATTEMPTS} attempts")

            except aiohttp.ClientConnectorError as err:
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    _LOGGER.warning(
                        "MSP API connection error on attempt %d/%d: %s, waiting %d seconds before retry",
                        attempt + 1, RETRY_ATTEMPTS, err, wait_time
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    _LOGGER.error("MSP API connection failed after %d attempts: %s", RETRY_ATTEMPTS, err)
                    raise HomeAssistantError(f"Cannot connect to MSP API: {err}")

            except (ConfigEntryAuthFailed, HomeAssistantError):
                # Don't retry authentication failures or other Home Assistant errors
                raise

            except Exception as err:
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    _LOGGER.warning(
                        "Unexpected MSP API error on attempt %d/%d: %s, waiting %d seconds before retry",
                        attempt + 1, RETRY_ATTEMPTS, err, wait_time
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    _LOGGER.exception("Unexpected MSP API error after %d attempts", RETRY_ATTEMPTS)
                    raise HomeAssistantError(f"Unexpected MSP API error: {err}")

        raise HomeAssistantError(f"MSP API request failed after {RETRY_ATTEMPTS} attempts")

    async def get_rules(self, query: Optional[str] = None) -> Dict[str, Any] | list:
        """Get rules from MSP API with optional query parameters."""
        endpoint = API_ENDPOINTS["rules"]
        if query:
            endpoint += f"?query={query}"
        return await self._make_request("GET", endpoint)

    async def pause_rule(self, rule_id: str) -> Dict[str, Any]:
        """Pause a rule via MSP API."""
        endpoint = API_ENDPOINTS["rule_pause"].format(rule_id=rule_id)
        return await self._make_request("POST", endpoint)

    async def unpause_rule(self, rule_id: str) -> Dict[str, Any]:
        """Unpause a rule via MSP API."""
        endpoint = API_ENDPOINTS["rule_unpause"].format(rule_id=rule_id)
        return await self._make_request("POST", endpoint)

    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get individual rule status for verification."""
        endpoint = API_ENDPOINTS["rule_detail"].format(rule_id=rule_id)
        return await self._make_request("GET", endpoint)

    @property
    def is_authenticated(self) -> bool:
        """Return whether the client is authenticated."""
        return self._authenticated


class FirewallaDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching rule data from the Firewalla MSP API."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        msp_domain: str,
        access_token: str,
        box_gid: str,
        include_filters: Optional[list] = None,
        exclude_filters: Optional[list] = None,
    ) -> None:
        """Initialize the coordinator."""
        self.api = FirewallaMSPClient(session, msp_domain, access_token)
        self.box_gid = box_gid
        self._previous_rules = {}
        self.include_filters = include_filters or []
        self.exclude_filters = exclude_filters or []
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch rule data from MSP API with automatic rule change detection."""
        _LOGGER.debug("Starting MSP API data update for box %s", self.box_gid)
        
        try:
            # Ensure we're authenticated
            if not self.api.is_authenticated:
                _LOGGER.debug("API not authenticated, attempting initial authentication")
                if not await self.api.authenticate():
                    _LOGGER.error("MSP API authentication failed during data update")
                    raise ConfigEntryAuthFailed("MSP API authentication failed")

            # Fetch rules with filters applied
            _LOGGER.debug("Fetching rules from MSP API with filters")
            rules_response = await self._fetch_filtered_rules()
            
            # Process rules data
            rules_data = self._process_rules_data(rules_response)
            
            # Detect rule changes
            rule_changes = self._detect_rule_changes(rules_data)
            
            # Calculate rule statistics
            rule_stats = self._calculate_rule_statistics(rules_data)
            
            processed_data = {
                "rules": rules_data,
                "rule_count": rule_stats,
                "rule_changes": rule_changes,
                "last_updated": self.last_update_success,
                "box_info": {
                    "gid": self.box_gid,
                    "name": f"Firewalla Box {self.box_gid[:8]}",
                    "online": True,  # Assume online if we can fetch data
                }
            }
            
            # Update previous rules for next comparison
            self._previous_rules = rules_data.copy()
            
            _LOGGER.debug(
                "Successfully updated rule data from MSP API: %d rules (%d active, %d paused)",
                rule_stats["total"],
                rule_stats["active"], 
                rule_stats["paused"]
            )
            return processed_data

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

    async def _fetch_filtered_rules(self) -> Dict[str, Any]:
        """Fetch rules with include/exclude filters applied."""
        all_rules = {"results": [], "count": 0}
        
        # If no filters are specified, fetch all rules
        if not self.include_filters and not self.exclude_filters:
            _LOGGER.debug("No filters specified, fetching all rules")
            return await self.api.get_rules()
        
        # Apply include filters
        if self.include_filters:
            _LOGGER.debug("Applying %d include filters", len(self.include_filters))
            for filter_query in self.include_filters:
                try:
                    _LOGGER.debug("Fetching rules with include filter: %s", filter_query)
                    filtered_response = await self.api.get_rules(filter_query)
                    
                    if isinstance(filtered_response, dict) and "results" in filtered_response:
                        # Merge results, avoiding duplicates by rule ID
                        existing_ids = {rule["id"] for rule in all_rules["results"]}
                        for rule in filtered_response["results"]:
                            if rule["id"] not in existing_ids:
                                all_rules["results"].append(rule)
                                existing_ids.add(rule["id"])
                    
                except Exception as err:
                    _LOGGER.warning("Failed to apply include filter '%s': %s", filter_query, err)
                    continue
        else:
            # No include filters, start with all rules
            _LOGGER.debug("No include filters, starting with all rules")
            all_rules = await self.api.get_rules()
        
        # Apply exclude filters
        if self.exclude_filters:
            _LOGGER.debug("Applying %d exclude filters", len(self.exclude_filters))
            rules_to_exclude = set()
            
            for filter_query in self.exclude_filters:
                try:
                    # Remove the '-' prefix if present (it's handled by the query logic)
                    clean_query = filter_query.lstrip('-')
                    _LOGGER.debug("Fetching rules to exclude with filter: %s", clean_query)
                    
                    exclude_response = await self.api.get_rules(clean_query)
                    
                    if isinstance(exclude_response, dict) and "results" in exclude_response:
                        for rule in exclude_response["results"]:
                            rules_to_exclude.add(rule["id"])
                    
                except Exception as err:
                    _LOGGER.warning("Failed to apply exclude filter '%s': %s", filter_query, err)
                    continue
            
            # Remove excluded rules
            if rules_to_exclude:
                original_count = len(all_rules["results"])
                all_rules["results"] = [
                    rule for rule in all_rules["results"] 
                    if rule["id"] not in rules_to_exclude
                ]
                excluded_count = original_count - len(all_rules["results"])
                _LOGGER.debug("Excluded %d rules based on exclude filters", excluded_count)
        
        # Update count
        all_rules["count"] = len(all_rules["results"])
        
        _LOGGER.debug(
            "Rule filtering complete: %d rules after applying %d include and %d exclude filters",
            all_rules["count"],
            len(self.include_filters),
            len(self.exclude_filters)
        )
        
        return all_rules

    def _process_rules_data(self, rules_response: Dict[str, Any] | list) -> Dict[str, Any]:
        """Process and normalize rules data from the MSP API."""
        if not rules_response:
            _LOGGER.warning("No rules data received from API")
            return {}
        
        # Handle different response formats
        rules_list = []
        if isinstance(rules_response, list):
            rules_list = rules_response
            _LOGGER.debug("Rules response is direct array with %d items", len(rules_list))
        elif isinstance(rules_response, dict):
            if "results" in rules_response:
                rules_list = rules_response["results"]
                _LOGGER.debug("Rules response has 'results' key with %d items", len(rules_list))
            else:
                rules_list = list(rules_response.values()) if rules_response else []
                _LOGGER.debug("Rules response is dict, converted to list with %d items", len(rules_list))
        else:
            _LOGGER.error("Invalid rules response format: expected dict or list, got %s", type(rules_response))
            return {}
        
        processed_rules = {}
        invalid_rules = 0
        
        for rule_info in rules_list:
            try:
                if not isinstance(rule_info, dict):
                    _LOGGER.debug("Skipping invalid rule data: %s", type(rule_info))
                    invalid_rules += 1
                    continue
                
                # Use rule ID as the key
                rule_id = rule_info.get("id", rule_info.get("rid", f"rule_{len(processed_rules)}"))
                
                # Extract target information from real API structure
                target_info = rule_info.get("target", {})
                target_type = target_info.get("type", "unknown") if isinstance(target_info, dict) else rule_info.get("type", "unknown")
                target_value = target_info.get("value", "") if isinstance(target_info, dict) else rule_info.get("value", "")
                
                # Extract scope information
                scope_info = rule_info.get("scope", {})
                scope_type = scope_info.get("type", "") if isinstance(scope_info, dict) else ""
                scope_value = scope_info.get("value", "") if isinstance(scope_info, dict) else ""
                
                # Determine if rule is paused based on status field
                status = rule_info.get("status", "active")
                is_paused = status == "paused"
                is_disabled = rule_info.get("disabled", False)
                
                # Process rule data based on real MSP API structure
                processed_rule = {
                    # Core identifiers
                    "rid": rule_id,
                    "id": rule_id,
                    # Rule definition (real API structure)
                    "type": target_type,
                    "value": target_value,
                    "target": target_value,  # Map value to target for compatibility
                    "target_name": rule_info.get("target_name", ""),
                    # Rule state
                    "disabled": bool(is_disabled),
                    "paused": bool(is_paused),
                    "status": status,
                    "action": rule_info.get("action", "block"),
                    # Rule metadata
                    "description": rule_info.get("description", rule_info.get("notes", "")),
                    "priority": rule_info.get("priority", 0),
                    "direction": rule_info.get("direction", "bidirection"),
                    # Scope information
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    # DNS-only flag from target
                    "dnsOnly": target_info.get("dnsOnly", False) if isinstance(target_info, dict) else False,
                    # Timestamps (real API uses ts/updateTs)
                    "created_at": rule_info.get("ts", rule_info.get("createdAt", 0)),
                    "modified_at": rule_info.get("updateTs", rule_info.get("modifiedAt", 0)),
                    "ts": rule_info.get("ts", 0),
                    "updateTs": rule_info.get("updateTs", 0),
                    # Additional fields
                    "schedule": rule_info.get("schedule"),
                    "hit": rule_info.get("hit", {}),
                    "gid": rule_info.get("gid", ""),
                }
                
                # Include all original fields
                for key, value in rule_info.items():
                    if key not in processed_rule:
                        processed_rule[key] = value
                
                processed_rules[rule_id] = processed_rule
                
            except Exception as err:
                _LOGGER.warning("Error processing rule: %s", err)
                invalid_rules += 1
                continue
        
        if invalid_rules > 0:
            _LOGGER.warning("Skipped %d invalid rule entries", invalid_rules)
        
        _LOGGER.debug("Processed %d valid rules", len(processed_rules))
        return processed_rules

    def _detect_rule_changes(self, current_rules: Dict[str, Any]) -> Dict[str, Any]:
        """Compare current rules with previous rules to detect changes."""
        changes = {
            "added": [],
            "removed": [],
            "modified": [],
        }
        
        # Find added rules
        for rule_id in current_rules:
            if rule_id not in self._previous_rules:
                changes["added"].append(rule_id)
        
        # Find removed rules
        for rule_id in self._previous_rules:
            if rule_id not in current_rules:
                changes["removed"].append(rule_id)
        
        # Find modified rules
        for rule_id in current_rules:
            if rule_id in self._previous_rules:
                current_rule = current_rules[rule_id]
                previous_rule = self._previous_rules[rule_id]
                
                # Check if rule state or metadata changed
                if (current_rule.get("paused") != previous_rule.get("paused") or
                    current_rule.get("disabled") != previous_rule.get("disabled") or
                    current_rule.get("modified_at") != previous_rule.get("modified_at")):
                    changes["modified"].append(rule_id)
        
        if any(changes.values()):
            _LOGGER.debug(
                "Rule changes detected: %d added, %d removed, %d modified",
                len(changes["added"]),
                len(changes["removed"]),
                len(changes["modified"])
            )
        
        return changes

    def _calculate_rule_statistics(self, rules_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate rule statistics for the sensor entity."""
        stats = {
            "total": len(rules_data),
            "active": 0,
            "paused": 0,
            "by_type": {},
        }
        
        for rule in rules_data.values():
            # Count active vs paused
            if rule.get("paused", False):
                stats["paused"] += 1
            else:
                stats["active"] += 1
            
            # Count by type
            rule_type = rule.get("type", "unknown")
            stats["by_type"][rule_type] = stats["by_type"].get(rule_type, 0) + 1
        
        return stats

    async def async_get_rules(self, query: Optional[str] = None) -> Dict[str, Any]:
        """Get current rules with optional filtering."""
        try:
            # If no query specified and we have cached data, return it
            if not query and self.data and "rules" in self.data:
                return self.data["rules"]
            
            # Fetch from API with optional query
            _LOGGER.debug("Fetching rules from API with query: %s", query)
            response = await self.api.get_rules(query)
            
            if response:
                processed_rules = self._process_rules_data(response)
                _LOGGER.debug("Retrieved %d rules from API", len(processed_rules))
                return processed_rules
            
            _LOGGER.warning("No rules data received from API")
            return {}
                
        except Exception as err:
            _LOGGER.error("Failed to get rules: %s", err)
            return {}

    async def async_pause_rule(self, rule_id: str) -> bool:
        """Pause a rule to temporarily disable it while preserving configuration."""
        try:
            _LOGGER.debug("Pausing rule %s", rule_id)
            
            if not rule_id:
                raise ValueError("Rule ID cannot be empty")
            
            result = await self.api.pause_rule(rule_id)
            
            if result:
                _LOGGER.info("Successfully paused rule: %s", rule_id)
                # Trigger a data refresh to get the updated rule status
                await self.async_request_refresh()
                return True
            else:
                _LOGGER.error("Failed to pause rule %s: Invalid API response", rule_id)
                return False
                
        except Exception as err:
            _LOGGER.error("Failed to pause rule %s: %s", rule_id, err)
            return False

    async def async_unpause_rule(self, rule_id: str) -> bool:
        """Unpause a rule to re-enable it."""
        try:
            _LOGGER.debug("Unpausing rule %s", rule_id)
            
            if not rule_id:
                raise ValueError("Rule ID cannot be empty")
            
            result = await self.api.unpause_rule(rule_id)
            
            if result:
                _LOGGER.info("Successfully unpaused rule: %s", rule_id)
                # Trigger a data refresh to get the updated rule status
                await self.async_request_refresh()
                return True
            else:
                _LOGGER.error("Failed to unpause rule %s: Invalid API response", rule_id)
                return False
                
        except Exception as err:
            _LOGGER.error("Failed to unpause rule %s: %s", rule_id, err)
            return False

    async def async_get_rule_status(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Get individual rule status for verification."""
        try:
            _LOGGER.debug("Getting status for rule %s", rule_id)
            
            if not rule_id:
                raise ValueError("Rule ID cannot be empty")
            
            result = await self.api.get_rule_status(rule_id)
            
            if result:
                _LOGGER.debug("Retrieved status for rule %s", rule_id)
                return result
            else:
                _LOGGER.warning("No status data received for rule %s", rule_id)
                return None
                
        except Exception as err:
            _LOGGER.error("Failed to get rule status for %s: %s", rule_id, err)
            return None