"""Binary sensor platform for Firewalla user activity detection."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MANUFACTURER, DOMAIN
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla user activity binary sensors."""
    coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    known_group_ids: set[str] = set()

    @callback
    def _async_update_activity_sensors():
        if not coordinator.data or "groups" not in coordinator.data:
            return
        # Only create activity sensors for user groups (kids/people, not device groups like "Cameras")
        current_ids = {
            gid for gid, gdata in coordinator.data["groups"].items()
            if gdata.get("is_user_group")
        }

        new_ids = current_ids - known_group_ids
        if new_ids:
            async_add_entities([
                FirewallaUserActivitySensor(coordinator, gid)
                for gid in new_ids
            ])
            known_group_ids.update(new_ids)

        removed_ids = known_group_ids - current_ids
        if removed_ids:
            ent_reg = er.async_get(hass)
            for gid in removed_ids:
                entity_id = ent_reg.async_get_entity_id(
                    "binary_sensor", DOMAIN, f"firewalla_user_{gid}_active"
                )
                if entity_id:
                    ent_reg.async_remove(entity_id)
            known_group_ids.difference_update(removed_ids)

    _async_update_activity_sensors()
    config_entry.async_on_unload(
        coordinator.async_add_listener(_async_update_activity_sensors)
    )


class FirewallaUserActivitySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor detecting active internet usage for a Firewalla user group."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        group = self._get_group_data()
        group_name = group["name"] if group else group_id
        self._attr_unique_id = f"firewalla_user_{group_id}_active"
        self._attr_name = "Active"
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
    def is_on(self) -> bool:
        """ON when data is actively flowing for this user's devices."""
        group = self._get_group_data()
        if not group:
            return False
        return group.get("active", False)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_group_data() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        group = self._get_group_data()
        if not group:
            return {"group_id": self._group_id}
        devices = group.get("devices", [])
        online = [d for d in devices if d.get("online")]
        return {
            "group_id": self._group_id,
            "online_devices": len(online),
            "total_devices": len(devices),
            "active_devices": [d["name"] for d in devices if d.get("online")],
            "download_delta_bytes": group.get("download_delta", 0),
        }
