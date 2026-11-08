"""Sensor platform for Firewalla rule statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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


def box_device_info(coordinator: FirewallaDataUpdateCoordinator) -> DeviceInfo:
    """Device info for the configured Firewalla box (shared by its entities)."""
    box_info = {}
    if coordinator.data and "box_info" in coordinator.data:
        box_info = coordinator.data["box_info"]

    box_gid = box_info.get("gid", coordinator.box_gid)
    box_name = box_info.get("name", f"Firewalla Box {box_gid[:8]}")
    box_model = box_info.get("model", "unknown")

    return DeviceInfo(
        identifiers={(DOMAIN, box_gid)},
        name=box_name,
        manufacturer=DEVICE_MANUFACTURER,
        model=DEVICE_MODEL_MAPPINGS.get(box_model, f"Firewalla {box_model.title()}"),
        sw_version=box_info.get("version"),
    )


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

        entities.extend(
            FirewallaBoxStatSensor(coordinator, description)
            for description in BOX_STAT_SENSORS
        )
        entities.append(FirewallaFirmwareSensor(coordinator))

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
        blocked_flows_added = False

        @callback
        def _async_update_dynamic_sensors():
            nonlocal blocked_flows_added
            # --- Blocked flows today: the trends endpoint is account-wide, so it
            # is the configured box's number only when the account has one box.
            box_stats = (coordinator.data or {}).get("box_stats")
            if (
                not blocked_flows_added
                and box_stats is not None
                and box_stats.get("box_count") == 1
            ):
                async_add_entities([FirewallaBlockedFlowsSensor(coordinator)])
                blocked_flows_added = True

            # --- Time limit sensors ---
            current_tl_keys: set[tuple[str, str]] = set()
            if coordinator.data and "time_limits" in coordinator.data:
                for uid, udata in coordinator.data["time_limits"].items():
                    for rid in udata.get("limits", {}):
                        current_tl_keys.add((uid, rid))

            new_tl = current_tl_keys - known_time_limit_keys
            if new_tl:
                new_sensors = [
                    FirewallaTimeLimitSensor(coordinator, uid, rid)
                    for uid, rid in new_tl
                ]
                async_add_entities(new_sensors)
                known_time_limit_keys.update(new_tl)

            removed_tl = known_time_limit_keys - current_tl_keys
            if removed_tl:
                ent_reg = er.async_get(hass)
                for uid, rid in removed_tl:
                    entity_id = ent_reg.async_get_entity_id(
                        "sensor", DOMAIN, f"firewalla_timelimit_{uid}_{rid}"
                    )
                    if entity_id:
                        ent_reg.async_remove(entity_id)
                known_time_limit_keys.difference_update(removed_tl)

            # --- Bandwidth sensors (per group: user groups and device groups) ---
            current_bw_gids: set[str] = set()
            if coordinator.data and "groups" in coordinator.data:
                current_bw_gids = set(coordinator.data["groups"])

            new_bw = current_bw_gids - known_bandwidth_gids
            if new_bw:
                bw_sensors = []
                for gid in new_bw:
                    bw_sensors.append(
                        FirewallaBandwidthSensor(coordinator, gid, "download")
                    )
                    bw_sensors.append(
                        FirewallaBandwidthSensor(coordinator, gid, "upload")
                    )
                async_add_entities(bw_sensors)
                known_bandwidth_gids.update(new_bw)

            removed_bw = known_bandwidth_gids - current_bw_gids
            if removed_bw:
                ent_reg = er.async_get(hass)
                for gid in removed_bw:
                    for direction in ("download", "upload"):
                        entity_id = ent_reg.async_get_entity_id(
                            "sensor", DOMAIN, f"firewalla_group_{gid}_{direction}"
                        )
                        if entity_id:
                            ent_reg.async_remove(entity_id)
                known_bandwidth_gids.difference_update(removed_bw)

        _async_update_dynamic_sensors()
        config_entry.async_on_unload(
            coordinator.async_add_listener(_async_update_dynamic_sensors)
        )

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
    _unrecorded_attributes = frozenset(
        {
            "box_name",
            "box_model",
            "rules_by_type",
        }
    )

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
        return box_device_info(self.coordinator)

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
    _unrecorded_attributes = frozenset(
        {"user_scope_id", "rule_id", "user_id", "schedule"}
    )

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        user_scope_id: str,
        rule_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._user_scope_id = user_scope_id
        self._rule_id = rule_id
        user_data = self._get_user_data()
        limit_data = self._get_limit_data()
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
                name=group_data["name"],
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
        return (
            self.coordinator.last_update_success and self._get_limit_data() is not None
        )

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
            "usage_percent": (
                min(100, round(limit.get("used", 0) / limit["quota"] * 100))
                if limit.get("quota")
                else 0
            ),
            "reached": limit.get("reached", False),
            "paused": limit.get("paused", False),
            "schedule": limit.get("schedule_display"),
            "hit_count": limit.get("hit_count", 0),
        }


class FirewallaBandwidthSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing 24h bandwidth usage per group (user or device group).

    The value is the sum of the group's devices' ``totalDownload`` /
    ``totalUpload``, which the MSP API defines as bytes for the last 24 hours.
    """

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
        return round(bytes_val / (1024**3), 2)  # bytes to GB

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success and self._get_group_data() is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        group = self._get_group_data()
        if not group:
            return {"group_id": self._group_id}
        bytes_val = group.get(f"total_{self._direction}", 0)
        return {
            "group_id": self._group_id,
            "bytes": bytes_val,
            "mb": round(bytes_val / (1024**2), 1),
        }


# ---------------------------------------------------------------------------
# Box status and statistics (#13)
# ---------------------------------------------------------------------------


def _box_stats(coordinator: FirewallaDataUpdateCoordinator) -> dict[str, Any] | None:
    if not coordinator.data:
        return None
    return coordinator.data.get("box_stats")


@dataclass(frozen=True)
class BoxStatDescription:
    """One sensor read from the coordinator's ``box_stats``."""

    key: str
    name: str
    icon: str
    value: Callable[[dict[str, Any]], Any]
    unit: str | None = None
    state_class: SensorStateClass | None = None
    entity_category: EntityCategory | None = None


BOX_STAT_SENSORS: tuple[BoxStatDescription, ...] = (
    BoxStatDescription(
        key="public_ip",
        name="Public IP",
        icon="mdi:ip-network",
        value=lambda stats: stats.get("public_ip"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BoxStatDescription(
        key="total_devices",
        name="Total devices",
        icon="mdi:devices",
        value=lambda stats: stats.get("device_count"),
        unit="devices",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BoxStatDescription(
        key="online_devices",
        name="Online devices",
        icon="mdi:lan-connect",
        value=lambda stats: stats.get("online_devices"),
        unit="devices",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BoxStatDescription(
        key="alarms",
        name="Alarms",
        icon="mdi:alarm-light",
        value=lambda stats: stats.get("alarm_count"),
        unit="alarms",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


class FirewallaBoxStatSensor(CoordinatorEntity, SensorEntity):
    """A status/statistics sensor on the Firewalla box's HA device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        description: BoxStatDescription,
    ) -> None:
        super().__init__(coordinator)
        self._description = description
        self._attr_unique_id = f"firewalla_box_{coordinator.box_gid}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.unit
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category
        self._attr_device_info = box_device_info(coordinator)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and (
            _box_stats(self.coordinator) is not None
        )

    @property
    def native_value(self) -> Any:
        stats = _box_stats(self.coordinator)
        return self._description.value(stats) if stats is not None else None


class FirewallaFirmwareSensor(FirewallaBoxStatSensor):
    """Firmware version; also keeps the box HA device's ``sw_version`` current."""

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            BoxStatDescription(
                key="firmware",
                name="Firmware version",
                icon="mdi:chip",
                value=lambda stats: stats.get("version"),
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        version = self.native_value
        if version and self.registry_entry and self.registry_entry.device_id:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get(self.registry_entry.device_id)
            if device and device.sw_version != version:
                dev_reg.async_update_device(device.id, sw_version=version)
        super()._handle_coordinator_update()


class FirewallaBlockedFlowsSensor(CoordinatorEntity, SensorEntity):
    """Blocked flows in the box's current local day (latest daily trend point).

    Firewalla's ``ts`` is the start of that day in the box's own timezone; it is
    passed through as-is, not reinterpreted in Home Assistant's timezone.
    """

    _attr_has_entity_name = True
    _attr_name = "Blocked flows today"
    _attr_icon = "mdi:shield-off"
    _attr_native_unit_of_measurement = "flows"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"firewalla_box_{coordinator.box_gid}_blocked_flows"
        self._attr_device_info = box_device_info(coordinator)

    def _point(self) -> dict[str, Any] | None:
        stats = _box_stats(self.coordinator)
        if stats is None or stats.get("box_count") != 1:
            return None
        return stats.get("blocked_flows")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._point() is not None

    @property
    def native_value(self) -> Any:
        point = self._point()
        return point.get("value") if point else None

    @property
    def last_reset(self) -> datetime | None:
        point = self._point()
        if not point:
            return None
        return datetime.fromtimestamp(point["ts"], tz=timezone.utc)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        point = self._point()
        return {"day_start_ts": point["ts"]} if point else {}
