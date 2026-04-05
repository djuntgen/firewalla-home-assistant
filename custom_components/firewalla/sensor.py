"""Sensor platform for Firewalla rule statistics."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_MANUFACTURER,
    DEVICE_MODEL_MAPPINGS,
    DOMAIN,
    ENTITY_ID_FORMATS,
    SENSOR_ATTRIBUTES,
)
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla rule statistics sensor entities from a config entry."""
    _LOGGER.debug(
        "Setting up Firewalla rule statistics sensor platform for entry %s",
        config_entry.entry_id,
    )

    try:
        # Get coordinator from hass.data
        coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][
            config_entry.entry_id
        ]

        # Create the rules summary sensor
        entities = []

        try:
            rules_sensor = FirewallaRulesSensor(coordinator)
            entities.append(rules_sensor)
            _LOGGER.debug("Created rules summary sensor")
        except Exception as err:
            _LOGGER.error("Error creating rules summary sensor: %s", err)

        if entities:
            async_add_entities(entities)
            _LOGGER.info(
                "Successfully added %d Firewalla rule statistics sensor entities",
                len(entities),
            )
        else:
            _LOGGER.warning("No valid rule statistics sensor entities could be created")
            async_add_entities([])

        known_time_limit_keys: set[tuple[str, str]] = set()
        known_bandwidth_gids: set[str] = set()

        @callback
        def _async_update_dynamic_sensors():
            # --- Time limit sensors ---
            current_tl_keys: set[tuple[str, str]] = set()
            if coordinator.data and "time_limits" in coordinator.data:
                for uid, udata in coordinator.data["time_limits"].items():
                    for rid in udata.get("limits", {}):
                        current_tl_keys.add((uid, rid))

            new_tl = current_tl_keys - known_time_limit_keys
            if new_tl:
                new_sensors = [FirewallaTimeLimitSensor(coordinator, uid, rid) for uid, rid in new_tl]
                async_add_entities(new_sensors)
                known_time_limit_keys.update(new_tl)

            removed_tl = known_time_limit_keys - current_tl_keys
            if removed_tl:
                ent_reg = er.async_get(hass)
                for uid, rid in removed_tl:
                    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"firewalla_timelimit_{uid}_{rid}")
                    if entity_id:
                        ent_reg.async_remove(entity_id)
                known_time_limit_keys.difference_update(removed_tl)

            # --- Bandwidth sensors (per user group) ---
            current_bw_gids: set[str] = set()
            if coordinator.data and "groups" in coordinator.data:
                for gid, gdata in coordinator.data["groups"].items():
                    if gdata.get("is_user_group"):
                        current_bw_gids.add(gid)

            new_bw = current_bw_gids - known_bandwidth_gids
            if new_bw:
                bw_sensors = []
                for gid in new_bw:
                    bw_sensors.append(FirewallaBandwidthSensor(coordinator, gid, "download"))
                    bw_sensors.append(FirewallaBandwidthSensor(coordinator, gid, "upload"))
                async_add_entities(bw_sensors)
                known_bandwidth_gids.update(new_bw)

            removed_bw = known_bandwidth_gids - current_bw_gids
            if removed_bw:
                ent_reg = er.async_get(hass)
                for gid in removed_bw:
                    for direction in ("download", "upload"):
                        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"firewalla_group_{gid}_{direction}")
                        if entity_id:
                            ent_reg.async_remove(entity_id)
                known_bandwidth_gids.difference_update(removed_bw)

        _async_update_dynamic_sensors()
        config_entry.async_on_unload(coordinator.async_add_listener(_async_update_dynamic_sensors))

    except KeyError as err:
        _LOGGER.error(
            "Missing coordinator data for config entry %s: %s",
            config_entry.entry_id,
            err,
        )
        raise HomeAssistantError(
            f"Coordinator not found for Firewalla integration: {err}"
        ) from err
    except Exception as err:
        _LOGGER.exception(
            "Unexpected error setting up Firewalla rule statistics sensor platform: %s",
            err,
        )
        raise HomeAssistantError(
            f"Failed to set up Firewalla rule statistics sensor platform: {err}"
        ) from err


class FirewallaRulesSensor(CoordinatorEntity, SensorEntity):
    """Sensor entity for Firewalla rules summary and statistics."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({
        "box_name", "box_model", "rules_by_type",
    })

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        """Initialize the rules summary sensor."""
        super().__init__(coordinator)

        # Set unique ID as specified in requirements
        self._attr_unique_id = ENTITY_ID_FORMATS["rules_sensor"]
        self._attr_name = "Firewalla Rules Summary"

        # Set state class for numeric count
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "rules"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Set device info
        self._attr_device_info = self._get_device_info()

    def _get_device_info(self) -> DeviceInfo:
        """Get device info for the Firewalla box."""
        box_info = {}
        if self.coordinator.data and "box_info" in self.coordinator.data:
            box_info = self.coordinator.data["box_info"]

        box_gid = box_info.get("gid", self.coordinator.box_gid)
        box_name = box_info.get("name", f"Firewalla Box {box_gid[:8]}")
        box_model = box_info.get("model", "unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, box_gid)},
            name=box_name,
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL_MAPPINGS.get(
                box_model, f"Firewalla {box_model.title()}"
            ),
            sw_version=box_info.get("version"),
        )

    @property
    def native_value(self) -> int:
        """Return the total count of discovered rules."""
        try:
            if not self.coordinator.data or "rule_count" not in self.coordinator.data:
                _LOGGER.debug("No rule count data available")
                return 0

            rule_count = self.coordinator.data["rule_count"]
            total_rules = rule_count.get("total", 0)

            _LOGGER.debug("Total rules count: %d", total_rules)
            return total_rules

        except Exception as err:
            _LOGGER.error("Error getting total rules count: %s", err)
            return 0

    @property
    def available(self) -> bool:
        """Return True if the coordinator has successful data."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return comprehensive rule statistics and integration health information."""
        if not self.coordinator.data:
            return {"status": "No data available"}

        attributes = {}

        # Add rule count statistics
        if "rule_count" in self.coordinator.data:
            rule_count = self.coordinator.data["rule_count"]

            for attr_key in SENSOR_ATTRIBUTES:
                if attr_key in rule_count:
                    attributes[attr_key] = rule_count[attr_key]

        # Add last updated timestamp
        if "last_updated" in self.coordinator.data:
            last_updated = self.coordinator.data["last_updated"]
            if last_updated:
                try:
                    if hasattr(last_updated, "isoformat"):
                        attributes["last_updated"] = last_updated.isoformat()
                    else:
                        attributes["last_updated"] = str(last_updated)
                except Exception:
                    attributes["last_updated"] = str(last_updated)

        # Add API connectivity status
        attributes["api_status"] = (
            "connected" if self.coordinator.last_update_success else "disconnected"
        )

        # Add rule change information if available
        if "rule_changes" in self.coordinator.data:
            rule_changes = self.coordinator.data["rule_changes"]
            if any(rule_changes.values()):
                attributes["recent_changes"] = {
                    "added": len(rule_changes.get("added", [])),
                    "removed": len(rule_changes.get("removed", [])),
                    "modified": len(rule_changes.get("modified", [])),
                }

        # Add box information
        if "box_info" in self.coordinator.data:
            box_info = self.coordinator.data["box_info"]
            attributes["box_name"] = box_info.get("name", "Unknown")
            attributes["box_model"] = box_info.get("model", "Unknown")
            attributes["box_online"] = box_info.get("online", False)

        return attributes

    @property
    def icon(self) -> str:
        """Return the icon for this sensor based on rule statistics."""
        try:
            if not self.coordinator.data or "rule_count" not in self.coordinator.data:
                return "mdi:shield-outline"

            rule_count = self.coordinator.data["rule_count"]
            total_rules = rule_count.get("total", 0)
            active_rules = rule_count.get("active", 0)

            if total_rules == 0:
                return "mdi:shield-outline"
            elif active_rules == 0:
                return "mdi:shield-off"
            elif active_rules < total_rules / 2:
                return "mdi:shield-check"
            else:
                return "mdi:shield"

        except Exception:
            return "mdi:shield-outline"

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("Rules summary sensor entity added to hass: %s", self.name)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        _LOGGER.debug(
            "Rules summary sensor entity being removed from hass: %s", self.name
        )


class FirewallaTimeLimitSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing app time usage for a user's time limit rule."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "min"
    _unrecorded_attributes = frozenset({"user_scope_id", "rule_id", "user_id", "schedule"})

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator, user_scope_id: str, rule_id: str) -> None:
        super().__init__(coordinator)
        self._user_scope_id = user_scope_id
        self._rule_id = rule_id
        user_data = self._get_user_data()
        limit_data = self._get_limit_data()
        user_name = user_data["user_name"] if user_data else f"User {user_scope_id}"
        app_name = (limit_data["app"] if limit_data else "unknown").title()
        self._attr_unique_id = f"firewalla_timelimit_{user_scope_id}_{rule_id}"
        self._attr_name = app_name
        # Attach to the user's affiliated group device
        affiliated_group = user_data.get("affiliated_group", "") if user_data else ""
        group_data = None
        if affiliated_group and coordinator.data and "groups" in coordinator.data:
            group_data = coordinator.data["groups"].get(affiliated_group)
        if group_data:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"group_{affiliated_group}")},
                name=group_data['name'],
                manufacturer=DEVICE_MANUFACTURER,
                model="Group",
                via_device=(DOMAIN, coordinator.box_gid),
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, coordinator.box_gid)},
                name=f"Firewalla Box {coordinator.box_gid[:8]}",
                manufacturer=DEVICE_MANUFACTURER,
            )

    def _get_user_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data or "time_limits" not in self.coordinator.data:
            return None
        return self.coordinator.data["time_limits"].get(self._user_scope_id)

    def _get_limit_data(self) -> dict[str, Any] | None:
        user_data = self._get_user_data()
        if not user_data:
            return None
        return user_data.get("limits", {}).get(self._rule_id)

    @property
    def native_value(self) -> int:
        limit = self._get_limit_data()
        if not limit:
            return 0
        return limit.get("remaining", 0)

    @property
    def icon(self) -> str:
        limit = self._get_limit_data()
        if limit and limit.get("reached"):
            return "mdi:timer-alert"
        return "mdi:timer-outline"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_limit_data() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        limit = self._get_limit_data()
        user_data = self._get_user_data()
        if not limit:
            return {"user_scope_id": self._user_scope_id, "rule_id": self._rule_id}
        return {
            "user_scope_id": self._user_scope_id,
            "rule_id": self._rule_id,
            "user_name": user_data["user_name"] if user_data else "",
            "app": limit.get("app", ""),
            "quota_minutes": limit.get("quota", 0),
            "used_minutes": limit.get("used", 0),
            "remaining_minutes": limit.get("remaining", 0),
            "usage_percent": min(100, round(limit.get("used", 0) / limit["quota"] * 100)) if limit.get("quota") else 0,
            "reached": limit.get("reached", False),
            "paused": limit.get("paused", False),
            "schedule": limit.get("schedule_display"),
            "hit_count": limit.get("hit_count", 0),
        }


class FirewallaBandwidthSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing 24h bandwidth usage per user group."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "GB"
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: FirewallaDataUpdateCoordinator, group_id: str, direction: str
    ) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._direction = direction  # "download" or "upload"
        group = self._get_group_data()
        group_name = group["name"] if group else group_id
        self._attr_unique_id = f"firewalla_group_{group_id}_{direction}"
        self._attr_name = direction.title()
        self._attr_icon = "mdi:download" if direction == "download" else "mdi:upload"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_id}")},
            name=group_name,
            manufacturer=DEVICE_MANUFACTURER,
            model="Group",
            via_device=(DOMAIN, coordinator.box_gid),
        )

    def _get_group_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data or "groups" not in self.coordinator.data:
            return None
        return self.coordinator.data["groups"].get(self._group_id)

    @property
    def native_value(self) -> float:
        group = self._get_group_data()
        if not group:
            return 0
        bytes_val = group.get(f"total_{self._direction}", 0)
        return round(bytes_val / (1024 ** 3), 2)  # bytes to GB

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_group_data() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        group = self._get_group_data()
        if not group:
            return {"group_id": self._group_id}
        bytes_val = group.get(f"total_{self._direction}", 0)
        return {
            "group_id": self._group_id,
            "bytes": bytes_val,
            "mb": round(bytes_val / (1024 ** 2), 1),
        }
