"""Binary sensor platform for Firewalla group activity and device online status."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MANUFACTURER, DOMAIN
from .coordinator import FirewallaDataUpdateCoordinator
from .sensor import box_device_info

_LOGGER = logging.getLogger(__name__)


def _device_unique_id(mac: str) -> str:
    return f"firewalla_device_{mac.replace(':', '_')}"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla binary sensors: group activity + per-device online status."""
    coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    async_add_entities([FirewallaBoxOnlineSensor(coordinator)])

    known_group_ids: set[str] = set()
    known_device_groups: dict[str, str] = {}  # device MAC -> group ID

    @callback
    def _async_update_binary_sensors():
        if not coordinator.data or "groups" not in coordinator.data:
            return

        # --- Activity sensors (one per group: user groups and device groups) ---
        current_ids = set(coordinator.data["groups"])

        new_ids = current_ids - known_group_ids
        if new_ids:
            async_add_entities(
                [FirewallaUserActivitySensor(coordinator, gid) for gid in new_ids]
            )
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

        # --- Per-device online sensors (devices in any group) ---
        current_device_groups: dict[str, str] = {}
        for gid, gdata in coordinator.data["groups"].items():
            for device in gdata.get("devices", []):
                mac = device.get("mac", "")
                if mac:
                    current_device_groups[mac] = gid

        removed_macs = known_device_groups.keys() - current_device_groups.keys()
        if removed_macs:
            ent_reg = er.async_get(hass)
            for mac in removed_macs:
                entity_id = ent_reg.async_get_entity_id(
                    "binary_sensor", DOMAIN, _device_unique_id(mac)
                )
                if entity_id:
                    ent_reg.async_remove(entity_id)
                del known_device_groups[mac]

        # A device that moved to another group keeps its entity (and any user
        # customisation); the sensor finds its data by MAC, and here its registry
        # entry is moved to the new group's HA device. If that HA device doesn't
        # exist yet (a group first seen in this poll), retry on the next poll.
        moved_macs = {
            mac
            for mac, gid in known_device_groups.items()
            if mac in current_device_groups and current_device_groups[mac] != gid
        }
        if moved_macs:
            ent_reg = er.async_get(hass)
            dev_reg = dr.async_get(hass)
            for mac in moved_macs:
                new_gid = current_device_groups[mac]
                group_device = dev_reg.async_get_device(
                    identifiers={(DOMAIN, f"group_{new_gid}")}
                )
                entity_id = ent_reg.async_get_entity_id(
                    "binary_sensor", DOMAIN, _device_unique_id(mac)
                )
                if group_device is None or entity_id is None:
                    continue
                ent_reg.async_update_entity(entity_id, device_id=group_device.id)
                known_device_groups[mac] = new_gid

        new_macs = current_device_groups.keys() - known_device_groups.keys()
        if new_macs:
            async_add_entities(
                [
                    FirewallaDeviceOnlineSensor(
                        coordinator, current_device_groups[mac], mac
                    )
                    for mac in new_macs
                ]
            )
            for mac in new_macs:
                known_device_groups[mac] = current_device_groups[mac]

    _async_update_binary_sensors()
    config_entry.async_on_unload(
        coordinator.async_add_listener(_async_update_binary_sensors)
    )


class FirewallaUserActivitySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor detecting active internet usage for a Firewalla group.

    Used for user groups and device groups. The unique ID keeps its original
    ``firewalla_user_`` prefix so existing entities, and a device group that later
    gets a user, keep the same ID.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: FirewallaDataUpdateCoordinator, group_id: str
    ) -> None:
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
        """ON when data is actively flowing for this group's devices."""
        group = self._get_group_data()
        if not group:
            return False
        return group.get("active", False)

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
        devices = group.get("devices", [])
        online = [d for d in devices if d.get("online")]
        return {
            "group_id": self._group_id,
            "online_devices": len(online),
            "total_devices": len(devices),
            "active_devices": [d["name"] for d in devices if d.get("online")],
            "download_delta_bytes": group.get("download_delta", 0),
        }


class FirewallaDeviceOnlineSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor showing online/offline status for a specific device."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: FirewallaDataUpdateCoordinator, group_id: str, mac: str
    ) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._mac = mac
        device = self._get_device_data()
        device_name = device["name"] if device else mac
        group = coordinator.data["groups"].get(group_id, {}) if coordinator.data else {}
        group_name = group.get("name", group_id)
        self._attr_unique_id = _device_unique_id(mac)
        self._attr_name = device_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_id}")},
            name=group_name,
            manufacturer=DEVICE_MANUFACTURER,
            model="Group",
            via_device=(DOMAIN, coordinator.box_gid),
        )

    def _get_device_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data or "groups" not in self.coordinator.data:
            return None
        # Search every group: the device may have moved since this entity was made.
        for group in self.coordinator.data["groups"].values():
            for device in group.get("devices", []):
                if device.get("mac") == self._mac:
                    return device
        return None

    @property
    def is_on(self) -> bool:
        device = self._get_device_data()
        if not device:
            return False
        return device.get("online", False)

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success and self._get_device_data() is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self._get_device_data()
        if not device:
            return {"mac": self._mac}
        return {
            "mac": self._mac,
            "ip": device.get("ip", ""),
            "mac_vendor": device.get("mac_vendor", ""),
            "network": device.get("network", ""),
            "last_seen": device.get("last_seen"),
            "ip_reserved": device.get("ip_reserved", False),
            "download_24h_mb": round(device.get("total_download", 0) / (1024**2), 1),
            "upload_24h_mb": round(device.get("total_upload", 0) / (1024**2), 1),
        }


class FirewallaBoxOnlineSensor(CoordinatorEntity, BinarySensorEntity):
    """Whether the configured Firewalla box is online, as reported by the MSP."""

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"firewalla_box_{coordinator.box_gid}_online"
        self._attr_device_info = box_device_info(coordinator)

    def _box_stats(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("box_stats")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._box_stats() is not None

    @property
    def is_on(self) -> bool | None:
        stats = self._box_stats()
        return stats["online"] if stats is not None else None
