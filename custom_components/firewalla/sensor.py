"""Sensor platform for Firewalla rule statistics."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla rule statistics sensor entities from a config entry."""
    _LOGGER.debug("Setting up Firewalla rule statistics sensor platform for entry %s", config_entry.entry_id)
    
    try:
        # Get coordinator from hass.data
        coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        # Create the rules summary sensor
        entities = []
        
        try:
            rules_sensor = FirewallaRulesSensor(coordinator)
            entities.append(rules_sensor)
            _LOGGER.debug("Created rules summary sensor")
        except Exception as err:
            _LOGGER.error("Error creating rules summary sensor: %s", err)
        
        if entities:
            async_add_entities(entities, True)
            _LOGGER.info("Successfully added %d Firewalla rule statistics sensor entities", len(entities))
        else:
            _LOGGER.warning("No valid rule statistics sensor entities could be created")
            async_add_entities([], True)
            
    except KeyError as err:
        _LOGGER.error("Missing coordinator data for config entry %s: %s", config_entry.entry_id, err)
        raise HomeAssistantError(f"Coordinator not found for Firewalla integration: {err}") from err
    except Exception as err:
        _LOGGER.exception("Unexpected error setting up Firewalla rule statistics sensor platform: %s", err)
        raise HomeAssistantError(f"Failed to set up Firewalla rule statistics sensor platform: {err}") from err


class FirewallaRulesSensor(CoordinatorEntity, SensorEntity):
    """Sensor entity for Firewalla rules summary and statistics."""

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        """Initialize the rules summary sensor."""
        super().__init__(coordinator)
        
        # Set unique ID as specified in requirements
        self._attr_unique_id = ENTITY_ID_FORMATS["rules_sensor"]
        self._attr_name = "Firewalla Rules Summary"
        
        # Set state class for numeric count
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "rules"
        
        # Set device info
        self._attr_device_info = self._get_device_info()

    def _get_device_info(self) -> Dict[str, Any]:
        """Get device info for the Firewalla box."""
        box_info = {}
        if self.coordinator.data and "box_info" in self.coordinator.data:
            box_info = self.coordinator.data["box_info"]
        
        box_gid = box_info.get("gid", self.coordinator.box_gid)
        box_name = box_info.get("name", f"Firewalla Box {box_gid[:8]}")
        box_model = box_info.get("model", "unknown")
        
        return {
            "identifiers": {(DOMAIN, box_gid)},
            "name": box_name,
            "manufacturer": DEVICE_MANUFACTURER,
            "model": DEVICE_MODEL_MAPPINGS.get(box_model, f"Firewalla {box_model.title()}"),
            "sw_version": box_info.get("version"),
        }

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
                    if hasattr(last_updated, 'isoformat'):
                        attributes["last_updated"] = last_updated.isoformat()
                    else:
                        attributes["last_updated"] = str(last_updated)
                except Exception:
                    attributes["last_updated"] = str(last_updated)
        
        # Add API connectivity status
        attributes["api_status"] = "connected" if self.coordinator.last_update_success else "disconnected"
        
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
        _LOGGER.debug("Rules summary sensor entity being removed from hass: %s", self.name)