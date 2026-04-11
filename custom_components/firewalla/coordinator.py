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
    DEFAULT_BASE_POLL_INTERVAL,
    DEFAULT_DEVICES_INTERVAL,
    DEFAULT_FULL_RULES_INTERVAL,
    DEFAULT_USERS_CACHE_TTL,
    DOMAIN,
    MSP_API_V2_BASE,
    RETRY_ATTEMPTS,
    RETRY_DELAYS,
)

_LOGGER = logging.getLogger(__name__)


def _format_schedule(schedule: dict | None) -> str | None:
    """Convert cron schedule to human-readable text."""
    if not schedule:
        return None

    cron = schedule.get("cronTime", "")
    duration = schedule.get("duration", 0)

    if not cron:
        return None

    # Parse cron: minute hour dom month dow
    parts = cron.split()
    if len(parts) < 5:
        return cron  # Return raw if unparseable

    minute, hour, dom, month, dow = parts[:5]

    # Format time
    try:
        time_str = (
            f"{int(hour):02d}:{int(minute):02d}"
            if hour != "*" and minute != "*"
            else "every hour"
        )
    except ValueError:
        time_str = f"{hour}:{minute}"

    # Format days
    day_map = {
        "0": "Sun",
        "1": "Mon",
        "2": "Tue",
        "3": "Wed",
        "4": "Thu",
        "5": "Fri",
        "6": "Sat",
        "7": "Sun",
    }
    if dow == "*":
        day_str = "daily"
    else:
        days = [day_map.get(d.strip(), d.strip()) for d in dow.split(",")]
        if len(days) == 7:
            day_str = "daily"
        elif len(days) == 5 and all(
            d in ["Mon", "Tue", "Wed", "Thu", "Fri"] for d in days
        ):
            day_str = "weekdays"
        elif len(days) == 2 and all(d in ["Sat", "Sun"] for d in days):
            day_str = "weekends"
        else:
            day_str = ", ".join(days)

    # Format duration
    if duration > 0:
        hours = duration // 3600
        mins = (duration % 3600) // 60
        if hours >= 24:
            dur_str = "all day"
        elif hours > 0 and mins > 0:
            dur_str = f"for {hours}h {mins}m"
        elif hours > 0:
            dur_str = f"for {hours}h"
        else:
            dur_str = f"for {mins}m"
        return f"{day_str} at {time_str} {dur_str}"

    return f"{day_str} at {time_str}"


def _build_groups(
    devices: list,
    users: list,
    rules: dict[str, Any],
    previous_downloads: dict[str, int] | None = None,
    last_active_times: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build groups dict from device and user data, cross-referenced with rules."""
    user_by_tag: dict[str, dict] = {}
    for user in users:
        tag = user.get("affiliatedTag")
        if tag:
            user_by_tag[tag] = user

    groups: dict[str, dict[str, Any]] = {}
    for device in devices:
        group_info = device.get("group")
        if not group_info or not isinstance(group_info, dict):
            continue
        gid = str(group_info.get("id", ""))
        if not gid:
            continue

        if gid not in groups:
            raw_name = group_info.get("name", gid)
            user_data = user_by_tag.get(gid)
            resolved_name = user_data["name"] if user_data else raw_name

            groups[gid] = {
                "name": resolved_name,
                "is_user_group": user_data is not None,
                "user_id": user_data["id"] if user_data else None,
                "device_count": 0,
                "devices": [],
                "internet_block_rule_id": None,
                "internet_blocked": False,
                "rule_count": 0,
                "group_rules": {},
                "download": user_data.get("download", 0) if user_data else 0,
                "upload": user_data.get("upload", 0) if user_data else 0,
            }

        network_info = device.get("network", {})
        groups[gid]["device_count"] += 1
        groups[gid]["devices"].append(
            {
                "name": device.get("name", "Unknown"),
                "mac": device.get("id", ""),
                "online": device.get("online", False),
                "type": device.get("deviceType", ""),
                "ip": device.get("ip", ""),
                "total_download": device.get("totalDownload", 0),
                "total_upload": device.get("totalUpload", 0),
                "mac_vendor": device.get("macVendor", ""),
                "last_seen": device.get("lastSeen"),
                "ip_reserved": device.get("ipReserved", False),
                "network": (
                    network_info.get("name", "")
                    if isinstance(network_info, dict)
                    else ""
                ),
            }
        )

    # Compute download totals and activity per group.
    # Activity uses a 5-minute cooldown: once data flow is detected, the user
    # stays "active" until 5 minutes pass with no significant traffic.
    # This prevents flapping from background keep-alive packets.
    import time

    ACTIVITY_THRESHOLD = 10240  # 10KB per poll — filters background noise
    ACTIVITY_COOLDOWN = 300  # 5 minutes of silence before marking inactive

    now = time.time()
    if previous_downloads is None:
        previous_downloads = {}
    if last_active_times is None:
        last_active_times = {}

    for gid, group in groups.items():
        total_dl = sum(d.get("total_download", 0) for d in group["devices"])
        total_ul = sum(d.get("total_upload", 0) for d in group["devices"])
        prev_dl = previous_downloads.get(gid, total_dl)
        delta = total_dl - prev_dl
        group["total_download"] = total_dl
        group["total_upload"] = total_ul
        group["download_delta"] = delta

        # If meaningful traffic detected, update last-active timestamp
        if delta > ACTIVITY_THRESHOLD:
            last_active_times[gid] = now

        # Active if last meaningful traffic was within the cooldown window
        last_active = last_active_times.get(gid, 0)
        group["active"] = (now - last_active) < ACTIVITY_COOLDOWN

    # Build user scope → group ID lookup for user-scoped rules (App Controls)
    user_scope_to_group: dict[str, str] = {}
    for user in users:
        uid = user.get("id", "")
        tag = user.get("affiliatedTag")
        parts = uid.rsplit(":", 1)
        if len(parts) == 2 and tag and tag in groups:
            user_scope_to_group[parts[1]] = tag

    for rule_id, rule in rules.items():
        scope_type = rule.get("scope_type", "")
        scope_value = str(rule.get("scope_value", ""))

        # Resolve group ID: group-scoped rules map directly,
        # user-scoped rules (App Controls) map via user→group lookup
        if scope_type == "group" and scope_value in groups:
            gid = scope_value
        elif scope_type == "user" and scope_value in user_scope_to_group:
            gid = user_scope_to_group[scope_value]
        else:
            continue

        groups[gid]["rule_count"] += 1

        groups[gid]["group_rules"][rule_id] = {
            "type": rule.get("type", ""),
            "value": rule.get("value", ""),
            "action": rule.get("action", ""),
            "paused": rule.get("paused", False),
            "status": rule.get("status", "active"),
            "hit_count": rule.get("hit_count", 0),
        }

        if rule.get("type") == "internet" and rule.get("action") == "block":
            groups[gid]["internet_block_rule_id"] = rule_id
            groups[gid]["internet_blocked"] = not rule.get("paused", False)

    return groups


def _build_time_limits(
    users: list,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Build per-user time limit data from timelimit and time-capped block rules.

    Firewalla represents time limits in two ways:
    - action=timelimit, scope=user — app-specific limits (e.g., YouTube 60 min/day)
    - action=block, target=internet, scope=group, with timeUsage — Internet time limits
    Both are surfaced as time limit sensors.
    """
    user_by_scope: dict[str, dict] = {}
    user_by_group: dict[str, dict] = {}
    for user in users:
        uid = user.get("id", "")
        parts = uid.rsplit(":", 1)
        if len(parts) == 2:
            user_by_scope[parts[1]] = user
        tag = user.get("affiliatedTag")
        if tag:
            user_by_group[tag] = user

    time_limits: dict[str, Any] = {}

    def _ensure_user_entry(scope_value: str, user_data: dict) -> None:
        if scope_value not in time_limits:
            time_limits[scope_value] = {
                "user_name": user_data.get("name", f"User {scope_value}"),
                "user_id": user_data.get("id", ""),
                "affiliated_group": user_data.get("affiliatedTag", ""),
                "limits": {},
            }

    for rule_id, rule in rules.items():
        quota = rule.get("time_quota_minutes") or 0
        used = rule.get("time_used_minutes") or 0
        action = rule.get("action", "")
        scope_type = rule.get("scope_type", "")
        scope_value = str(rule.get("scope_value", ""))

        if action == "timelimit" and scope_type == "user" and scope_value:
            # App-specific time limits (e.g., YouTube 60 min/day)
            user_data = user_by_scope.get(scope_value, {})
            _ensure_user_entry(scope_value, user_data)
        elif quota > 0 and scope_type == "group" and scope_value:
            # Internet/block rules with time usage (e.g., Internet 2 hr/day)
            user_data = user_by_group.get(scope_value, {})
            if not user_data:
                continue  # skip non-user groups (e.g., "Cameras")
            # Map group scope to user scope for consistency
            uid = user_data.get("id", "")
            parts = uid.rsplit(":", 1)
            scope_value = parts[1] if len(parts) == 2 else scope_value
            _ensure_user_entry(scope_value, user_data)
        else:
            continue

        remaining = max(0, quota - used)
        app_name = rule.get("value", "") or rule.get("type", "unknown")

        time_limits[scope_value]["limits"][rule_id] = {
            "app": app_name,
            "quota": quota,
            "used": used,
            "remaining": remaining,
            "reached": used >= quota if quota > 0 else False,
            "paused": rule.get("paused", False),
            "schedule_display": rule.get("schedule_display"),
            "hit_count": rule.get("hit_count", 0),
        }

    return time_limits


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
            response = await self._make_request(
                "GET", API_ENDPOINTS["rules"], retry_auth=False
            )
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
            _LOGGER.exception(
                "MSP API authentication failed with unexpected error: %s", err
            )
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
                            raise ConfigEntryAuthFailed(
                                "MSP API authentication expired"
                            )
                        else:
                            _LOGGER.error("MSP API authentication failed (HTTP 401)")
                            raise ConfigEntryAuthFailed("MSP API authentication failed")

                    # Handle rate limiting
                    if response.status == 429:
                        if attempt < RETRY_ATTEMPTS - 1:
                            wait_time = RETRY_DELAYS[
                                min(attempt, len(RETRY_DELAYS) - 1)
                            ]
                            _LOGGER.warning(
                                "MSP API rate limited (HTTP 429), waiting %d seconds before retry",
                                wait_time,
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
                            response.status,
                            method,
                            url,
                            error_text,
                        )

                        if response.status == 403:
                            raise ConfigEntryAuthFailed(
                                f"MSP API access forbidden: {error_text}"
                            )
                        elif response.status == 404:
                            raise HomeAssistantError(
                                f"MSP API endpoint not found: {url}"
                            )
                        elif response.status >= 500:
                            raise HomeAssistantError(
                                f"MSP API server error (HTTP {response.status}): {error_text}"
                            )
                        else:
                            raise HomeAssistantError(
                                f"MSP API error (HTTP {response.status}): {error_text}"
                            )

                    # Success - parse response
                    try:
                        result = await response.json()
                        _LOGGER.debug("MSP API response received successfully")
                        return result
                    except aiohttp.ContentTypeError:
                        # Handle non-JSON responses (e.g., for pause/resume operations)
                        if response.status == 200:
                            return {"success": True}
                        else:
                            text = await response.text()
                            _LOGGER.error(
                                "MSP API returned non-JSON error response: %s", text
                            )
                            raise HomeAssistantError(
                                "MSP API returned invalid response format"
                            )

            except asyncio.TimeoutError:
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    _LOGGER.warning(
                        "MSP API timeout on attempt %d/%d, waiting %d seconds before retry",
                        attempt + 1,
                        RETRY_ATTEMPTS,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    _LOGGER.error("MSP API timeout after %d attempts", RETRY_ATTEMPTS)
                    raise HomeAssistantError(
                        f"MSP API timeout after {RETRY_ATTEMPTS} attempts"
                    )

            except aiohttp.ClientConnectorError as err:
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    _LOGGER.warning(
                        "MSP API connection error on attempt %d/%d: %s, waiting %d seconds before retry",
                        attempt + 1,
                        RETRY_ATTEMPTS,
                        err,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    _LOGGER.error(
                        "MSP API connection failed after %d attempts: %s",
                        RETRY_ATTEMPTS,
                        err,
                    )
                    raise HomeAssistantError(f"Cannot connect to MSP API: {err}")

            except (ConfigEntryAuthFailed, HomeAssistantError):
                # Don't retry authentication failures or other Home Assistant errors
                raise

            except Exception as err:
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    _LOGGER.warning(
                        "Unexpected MSP API error on attempt %d/%d: %s, waiting %d seconds before retry",
                        attempt + 1,
                        RETRY_ATTEMPTS,
                        err,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    _LOGGER.exception(
                        "Unexpected MSP API error after %d attempts", RETRY_ATTEMPTS
                    )
                    raise HomeAssistantError(f"Unexpected MSP API error: {err}")

        raise HomeAssistantError(
            f"MSP API request failed after {RETRY_ATTEMPTS} attempts"
        )

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

    async def resume_rule(self, rule_id: str) -> Dict[str, Any]:
        """Resume a paused rule via MSP API."""
        endpoint = API_ENDPOINTS["rule_resume"].format(rule_id=rule_id)
        return await self._make_request("POST", endpoint)

    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get individual rule status for verification."""
        endpoint = API_ENDPOINTS["rule_detail"].format(rule_id=rule_id)
        return await self._make_request("GET", endpoint)

    async def get_devices(self) -> list:
        """Get all devices from MSP API."""
        return await self._make_request("GET", API_ENDPOINTS["devices"])

    async def get_users(self) -> list:
        """Get all users from MSP API."""
        return await self._make_request("GET", API_ENDPOINTS["users"])

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
        config_entry=None,
        include_filters: Optional[list] = None,
        exclude_filters: Optional[list] = None,
        base_poll_interval: int = DEFAULT_BASE_POLL_INTERVAL,
        full_rules_interval: int = DEFAULT_FULL_RULES_INTERVAL,
        devices_interval: int = DEFAULT_DEVICES_INTERVAL,
        users_cache_ttl: int = DEFAULT_USERS_CACHE_TTL,
    ) -> None:
        """Initialize the coordinator."""
        self.api = FirewallaMSPClient(session, msp_domain, access_token)
        self.box_gid = box_gid
        self._previous_rules = {}
        self._previous_group_downloads: dict[str, int] = {}
        self._last_active_times: dict[str, float] = {}
        self.include_filters = include_filters or []
        self.exclude_filters = exclude_filters or []

        # Configurable polling intervals
        self._base_poll_interval: int = max(30, base_poll_interval)
        self._full_rules_interval: int = max(
            self._base_poll_interval, full_rules_interval
        )
        self._devices_interval: int = max(self._base_poll_interval, devices_interval)
        self._users_cache_ttl: float = float(max(60, users_cache_ttl))

        # Derive poll-cycle counts from intervals
        # e.g. full_rules_interval=180, base=60 → full rules every 3 polls
        self._full_rules_every: int = max(
            1, self._full_rules_interval // self._base_poll_interval
        )
        self._devices_every: int = max(
            1, self._devices_interval // self._base_poll_interval
        )

        # Caching state
        self._cached_users: list = []
        self._users_last_fetched: float = 0
        self._cached_devices: list = []
        self._cached_full_rules: dict[str, Any] = {}
        self._poll_count: int = 0

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._base_poll_interval),
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch rule data from MSP API with automatic rule change detection."""
        _LOGGER.debug("Starting MSP API data update for box %s", self.box_gid)

        try:
            # Ensure we're authenticated
            if not self.api.is_authenticated:
                _LOGGER.debug(
                    "API not authenticated, attempting initial authentication"
                )
                if not await self.api.authenticate():
                    _LOGGER.error("MSP API authentication failed during data update")
                    raise ConfigEntryAuthFailed("MSP API authentication failed")

            self._poll_count += 1
            import time as _time

            now = _time.time()

            # --- Split-polling for rules ---
            # Full rules: fetched at configurable interval (default every 6 polls = 3 min)
            # Timelimit-only: fetched every poll (30s) and merged into cached full rules
            is_full_rules_poll = (
                self._poll_count % self._full_rules_every == 1
                or not self._cached_full_rules
            )

            if is_full_rules_poll:
                _LOGGER.debug("Full rules refresh (poll %d)", self._poll_count)
                rules_response = await self._fetch_filtered_rules()
                rules_data = self._process_rules_data(rules_response)
                self._cached_full_rules = rules_data
            else:
                # Lightweight poll: only timelimit rules (~5.5KB vs ~55KB)
                _LOGGER.debug("Timelimit-only refresh (poll %d)", self._poll_count)
                tl_response = await self.api.get_rules("action:timelimit")
                tl_data = self._process_rules_data(tl_response)
                # Merge updated timelimit data into cached full rules
                rules_data = dict(self._cached_full_rules)
                rules_data.update(tl_data)

            # Detect rule changes
            rule_changes = self._detect_rule_changes(rules_data)

            # Calculate rule statistics
            rule_stats = self._calculate_rule_statistics(rules_data)

            # Fetch devices at configurable interval (default every 2 polls = 60s)
            if self._poll_count % self._devices_every == 1 or not self._cached_devices:
                devices_response = await self.api.get_devices()
                self._cached_devices = (
                    devices_response if isinstance(devices_response, list) else []
                )
            devices_list = self._cached_devices

            # Cache users for configurable TTL (default 10 min)
            if (
                now - self._users_last_fetched
            ) > self._users_cache_ttl or not self._cached_users:
                users_response = await self.api.get_users()
                self._cached_users = (
                    users_response if isinstance(users_response, list) else []
                )
                self._users_last_fetched = now
            users_list = self._cached_users

            groups_data = _build_groups(
                devices_list,
                users_list,
                rules_data,
                self._previous_group_downloads,
                self._last_active_times,
            )

            # Update tracking state for next poll
            self._previous_group_downloads = {
                gid: gdata["total_download"] for gid, gdata in groups_data.items()
            }
            # _last_active_times is mutated in-place by _build_groups

            time_limits_data = _build_time_limits(users_list, rules_data)

            processed_data = {
                "rules": rules_data,
                "rule_count": rule_stats,
                "rule_changes": rule_changes,
                "last_updated": self.last_update_success,
                "box_info": {
                    "gid": self.box_gid,
                    "name": f"Firewalla Box {self.box_gid[:8]}",
                    "online": True,  # Assume online if we can fetch data
                },
                "groups": groups_data,
                "time_limits": time_limits_data,
            }

            # Update previous rules for next comparison
            self._previous_rules = rules_data.copy()

            _LOGGER.debug(
                "Successfully updated rule data from MSP API: %d rules (%d active, %d paused)",
                rule_stats["total"],
                rule_stats["active"],
                rule_stats["paused"],
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
            raise UpdateFailed(
                f"Unexpected error communicating with MSP API: {err}"
            ) from err

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
                    _LOGGER.debug(
                        "Fetching rules with include filter: %s", filter_query
                    )
                    filtered_response = await self.api.get_rules(filter_query)

                    if (
                        isinstance(filtered_response, dict)
                        and "results" in filtered_response
                    ):
                        # Merge results, avoiding duplicates by rule ID
                        existing_ids = {rule["id"] for rule in all_rules["results"]}
                        for rule in filtered_response["results"]:
                            if rule["id"] not in existing_ids:
                                all_rules["results"].append(rule)
                                existing_ids.add(rule["id"])

                except Exception as err:
                    _LOGGER.warning(
                        "Failed to apply include filter '%s': %s", filter_query, err
                    )
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
                    clean_query = filter_query.lstrip("-")
                    _LOGGER.debug(
                        "Fetching rules to exclude with filter: %s", clean_query
                    )

                    exclude_response = await self.api.get_rules(clean_query)

                    if (
                        isinstance(exclude_response, dict)
                        and "results" in exclude_response
                    ):
                        for rule in exclude_response["results"]:
                            rules_to_exclude.add(rule["id"])

                except Exception as err:
                    _LOGGER.warning(
                        "Failed to apply exclude filter '%s': %s", filter_query, err
                    )
                    continue

            # Remove excluded rules
            if rules_to_exclude:
                original_count = len(all_rules["results"])
                all_rules["results"] = [
                    rule
                    for rule in all_rules["results"]
                    if rule["id"] not in rules_to_exclude
                ]
                excluded_count = original_count - len(all_rules["results"])
                _LOGGER.debug(
                    "Excluded %d rules based on exclude filters", excluded_count
                )

        # Update count
        all_rules["count"] = len(all_rules["results"])

        _LOGGER.debug(
            "Rule filtering complete: %d rules after applying %d include and %d exclude filters",
            all_rules["count"],
            len(self.include_filters),
            len(self.exclude_filters),
        )

        return all_rules

    def _process_rules_data(
        self, rules_response: Dict[str, Any] | list
    ) -> Dict[str, Any]:
        """Process and normalize rules data from the MSP API."""
        if not rules_response:
            _LOGGER.warning("No rules data received from API")
            return {}

        # Handle different response formats
        rules_list = []
        if isinstance(rules_response, list):
            rules_list = rules_response
            _LOGGER.debug(
                "Rules response is direct array with %d items", len(rules_list)
            )
        elif isinstance(rules_response, dict):
            if "results" in rules_response:
                rules_list = rules_response["results"]
                _LOGGER.debug(
                    "Rules response has 'results' key with %d items", len(rules_list)
                )
            else:
                rules_list = list(rules_response.values()) if rules_response else []
                _LOGGER.debug(
                    "Rules response is dict, converted to list with %d items",
                    len(rules_list),
                )
        else:
            _LOGGER.error(
                "Invalid rules response format: expected dict or list, got %s",
                type(rules_response),
            )
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
                rule_id = rule_info.get(
                    "id", rule_info.get("rid", f"rule_{len(processed_rules)}")
                )

                # Extract target information from real API structure
                target_info = rule_info.get("target", {})
                target_type = (
                    target_info.get("type", "unknown")
                    if isinstance(target_info, dict)
                    else rule_info.get("type", "unknown")
                )
                target_value = (
                    target_info.get("value", "")
                    if isinstance(target_info, dict)
                    else rule_info.get("value", "")
                )

                # Extract scope information
                scope_info = rule_info.get("scope", {})
                scope_type = (
                    scope_info.get("type", "") if isinstance(scope_info, dict) else ""
                )
                scope_value = (
                    scope_info.get("value", "") if isinstance(scope_info, dict) else ""
                )

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
                    "description": rule_info.get(
                        "description", rule_info.get("notes", "")
                    ),
                    "priority": rule_info.get("priority", 0),
                    "direction": rule_info.get("direction", "bidirection"),
                    # Scope information
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    # DNS-only flag from target
                    "dnsOnly": (
                        target_info.get("dnsOnly", False)
                        if isinstance(target_info, dict)
                        else False
                    ),
                    # Timestamps (real API uses ts/updateTs)
                    "created_at": rule_info.get("ts", rule_info.get("createdAt", 0)),
                    "modified_at": rule_info.get(
                        "updateTs", rule_info.get("modifiedAt", 0)
                    ),
                    "ts": rule_info.get("ts", 0),
                    "updateTs": rule_info.get("updateTs", 0),
                    "resumeTs": rule_info.get("resumeTs"),
                    # Additional fields
                    "schedule": rule_info.get("schedule"),
                    "hit": rule_info.get("hit", {}),
                    "gid": rule_info.get("gid", ""),
                }

                # Extract hit data
                hit_info = rule_info.get("hit", {})
                processed_rule["hit_count"] = (
                    hit_info.get("count", 0) if isinstance(hit_info, dict) else 0
                )
                processed_rule["last_hit"] = (
                    hit_info.get("lastHitTs") if isinstance(hit_info, dict) else None
                )

                # Extract time usage (for timelimit rules)
                time_usage = rule_info.get("timeUsage", {})
                if isinstance(time_usage, dict) and time_usage:
                    processed_rule["time_quota_minutes"] = time_usage.get("quota")
                    processed_rule["time_used_minutes"] = time_usage.get("used")
                else:
                    processed_rule["time_quota_minutes"] = None
                    processed_rule["time_used_minutes"] = None

                # Format schedule for display
                processed_rule["schedule_display"] = _format_schedule(
                    rule_info.get("schedule")
                )

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

    def _describe_rule(self, rule: Dict[str, Any]) -> str:
        """Build a human-readable description of a rule for logging."""
        action = rule.get("action", "block")
        target_type = rule.get("type", "unknown")
        target_value = rule.get("target_name") or rule.get("value") or rule.get("target", "")
        scope_type = rule.get("scope_type", "")
        scope_value = rule.get("scope_value", "")

        # Resolve scope to a friendly name
        scope_desc = ""
        if scope_type in ("group", "user") and scope_value:
            groups = self.data.get("groups", {}) if self.data else {}
            # Match by group ID key, user_id, or name
            if scope_value in groups:
                scope_desc = groups[scope_value].get("name", scope_value)
            else:
                for gdata in groups.values():
                    if gdata.get("user_id") == scope_value:
                        scope_desc = gdata["name"]
                        break
            if not scope_desc:
                scope_desc = scope_value

        parts = [action.title(), target_type.title()]
        if target_value:
            parts.append(f'"{target_value.title()}"')
        if scope_desc:
            parts.append(f"for {scope_desc}")
        elif scope_type:
            parts.append(f"({scope_type})")

        return " ".join(parts)

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

                if (
                    current_rule.get("paused") != previous_rule.get("paused")
                    or current_rule.get("disabled") != previous_rule.get("disabled")
                    or current_rule.get("modified_at")
                    != previous_rule.get("modified_at")
                ):
                    changes["modified"].append(rule_id)

        # Log detailed change information
        for rule_id in changes["added"]:
            rule = current_rules.get(rule_id, {})
            _LOGGER.info("Rule added: %s [%s]", self._describe_rule(rule), rule_id)

        for rule_id in changes["removed"]:
            rule = self._previous_rules.get(rule_id, {})
            _LOGGER.info("Rule removed: %s [%s]", self._describe_rule(rule), rule_id)

        for rule_id in changes["modified"]:
            current_rule = current_rules.get(rule_id, {})
            previous_rule = self._previous_rules.get(rule_id, {})
            desc = self._describe_rule(current_rule)

            # Describe what changed
            detail_parts = []
            if current_rule.get("paused") != previous_rule.get("paused"):
                if current_rule.get("paused"):
                    detail_parts.append("paused")
                else:
                    detail_parts.append("resumed")
            if current_rule.get("disabled") != previous_rule.get("disabled"):
                if current_rule.get("disabled"):
                    detail_parts.append("disabled")
                else:
                    detail_parts.append("enabled")

            detail = ", ".join(detail_parts) if detail_parts else "modified"
            _LOGGER.info("Rule %s: %s [%s]", detail, desc, rule_id)

        if any(changes.values()):
            _LOGGER.debug(
                "Rule changes summary: %d added, %d removed, %d modified",
                len(changes["added"]),
                len(changes["removed"]),
                len(changes["modified"]),
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
                # No refresh needed — switch entities do optimistic updates,
                # and the next regular 30s poll confirms the state.
                return True
            else:
                _LOGGER.error("Failed to pause rule %s: Invalid API response", rule_id)
                return False

        except Exception as err:
            _LOGGER.error("Failed to pause rule %s: %s", rule_id, err)
            return False

    async def async_resume_rule(self, rule_id: str) -> bool:
        """Resume a paused rule to re-enable it."""
        try:
            _LOGGER.debug("Resuming rule %s", rule_id)

            if not rule_id:
                raise ValueError("Rule ID cannot be empty")

            result = await self.api.resume_rule(rule_id)

            if result:
                _LOGGER.info("Successfully resumed rule: %s", rule_id)
                # No refresh needed — switch entities do optimistic updates,
                # and the next regular 30s poll confirms the state.
                return True
            else:
                _LOGGER.error("Failed to resume rule %s: Invalid API response", rule_id)
                return False

        except Exception as err:
            _LOGGER.error("Failed to resume rule %s: %s", rule_id, err)
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
