"""Button platform for Firewalla manual refresh."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    """Set up Firewalla refresh button."""
    coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    async_add_entities([FirewallaRefreshButton(coordinator)])


class FirewallaRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger a manual data refresh from the Firewalla API."""

    _attr_has_entity_name = True
    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"firewalla_{coordinator.box_gid}_refresh"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link to the main Firewalla box device."""
        box_info = (
            self.coordinator.data.get("box_info", {}) if self.coordinator.data else {}
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.box_gid)},
            name=box_info.get("name", f"Firewalla Box {self.coordinator.box_gid[:8]}"),
            manufacturer=DEVICE_MANUFACTURER,
        )

    async def async_press(self) -> None:
        """Handle the button press — trigger a full coordinator refresh."""
        _LOGGER.debug("Manual refresh triggered")
        # Force a full rules refresh on the next poll by resetting the cache
        self.coordinator._cached_full_rules = {}
        await self.coordinator.async_request_refresh()
