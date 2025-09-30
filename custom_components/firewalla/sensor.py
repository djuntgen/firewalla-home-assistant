"""Sensor platform for Firewalla integration."""
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
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla sensor entities from a config entry."""
    _LOGGER.debug("Setting up Firewalla sensor platform for entry %s", config_entry.entry_id)
    
    try:
        # Get coordinator from hass.data
        coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        # Create device status sensors for each device
        entities = []
        
        # Get devices from coordinator data
        devices = coordinator.devices
        _LOGGER.debug("Creating device status sensors for %d devices", len(devices))
        
        for mac_address, device_data in devices.items():
            try:
                # Validate device data
                if not isinstance(device_data, dict):
                    _LOGGER.warning("Invalid device data for %s: %s", mac_address, type(device_data))
                    continue
                
                sensor = FirewallaDeviceStatusSensor(
                    coordinator=coordinator,
                    mac_address=mac_address,
                    device_data=device_data,
                )
                entities.append(sensor)
                _LOGGER.debug("Created device status sensor for %s (%s)", mac_address, device_data.get("name", "Unknown"))
                
            except Exception as err:
                _LOGGER.error("Error creating device sensor for %s: %s", mac_address, err)
                continue
        
        # Add the rules count sensor
        try:
            rules_sensor = FirewallaRulesSensor(coordinator)
            entities.append(rules_sensor)
            _LOGGER.debug("Created rules count sensor")
        except Exception as err:
            _LOGGER.error("Error creating rules sensor: %s", err)
        
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Successfully added %d Firewalla sensors (%d device sensors + rules sensor)", len(entities), len(devices))
        else:
            _LOGGER.warning("No valid sensor entities could be created")
            async_add_entities([])
            
    except KeyError as err:
        _LOGGER.error("Missing coordinator data for config entry %s: %s", config_entry.entry_id, err)
        raise HomeAssistantError(f"Coordinator not found for Firewalla integration: {err}") from err
    except Exception as err:
        _LOGGER.exception("Unexpected error setting up Firewalla sensor platform: %s", err)
        raise HomeAssistantError(f"Failed to set up Firewalla sensor platform: {err}") from err


class FirewallaDeviceStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor entity for Firewalla device status."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        mac_address: str,
        device_data: Dict[str, Any],
    ) -> None:
        """Initialize the device status sensor."""
        super().__init__(coordinator)
        
        self._mac_address = mac_address
        self._device_data = device_data
        
        # Get friendly name with disambiguation
        friendly_name = coordinator.get_device_friendly_name(mac_address, device_data)
        
        # Create unique ID using MAC address
        self._attr_unique_id = f"firewalla_{mac_address.replace(':', '')}_status"
        self._attr_name = f"{friendly_name} Status"

    @property
    def name(self) -> str:
        """Return the name of the entity, refreshed from current device data."""
        # Get current device data and friendly name
        current_device_data = self.coordinator.get_device_by_mac(self._mac_address)
        if current_device_data:
            friendly_name = self.coordinator.get_device_friendly_name(self._mac_address, current_device_data)
            return f"{friendly_name} Status"
        else:
            # Fallback to stored name if device not found
            return self._attr_name
        
        # Set device class for connectivity
        self._attr_device_class = SensorDeviceClass.ENUM
        
        # Set available options for the sensor
        self._attr_options = ["online", "offline", "unknown"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this sensor, refreshed from current coordinator data."""
        # Get current device data to ensure fresh information
        current_device_data = self.coordinator.get_device_by_mac(self._mac_address)
        if current_device_data:
            device_info_dict = self.coordinator.get_device_info_dict(self._mac_address, current_device_data)
        else:
            # Fallback to stored device data if device not found
            device_info_dict = self.coordinator.get_device_info_dict(self._mac_address, self._device_data)
        
        # Convert to DeviceInfo object
        return DeviceInfo(**device_info_dict)

    @property
    def native_value(self) -> str:
        """Return the current status of the device."""
        try:
            # Get current device data from coordinator
            current_device = self.coordinator.get_device_by_mac(self._mac_address)
            
            if current_device is None:
                _LOGGER.debug("Device %s not found in coordinator data", self._mac_address)
                return "unknown"
            
            # Return online/offline based on device status
            online_status = current_device.get("online", False)
            status = "online" if online_status else "offline"
            _LOGGER.debug("Device %s status: %s", self._mac_address, status)
            return status
            
        except Exception as err:
            _LOGGER.error("Error getting device status for %s: %s", self._mac_address, err)
            return "unknown"

    @property
    def available(self) -> bool:
        """Return True if the device data is accessible."""
        # Check if coordinator has data and our device exists
        if not self.coordinator.last_update_success:
            return False
        
        # Check if our device still exists in the coordinator data
        current_device = self.coordinator.get_device_by_mac(self._mac_address)
        return current_device is not None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes for the device."""
        try:
            current_device = self.coordinator.get_device_by_mac(self._mac_address)
            
            if current_device is None:
                _LOGGER.debug("Device %s not found for attributes", self._mac_address)
                return {}
            
            # Get friendly name with disambiguation
            friendly_name = self.coordinator.get_device_friendly_name(self._mac_address, current_device)
            
            attributes = {
                "mac_address": self._mac_address,
                "device_name": current_device.get("name", "Unknown"),
                "device_friendly_name": friendly_name,
                "device_hostname": current_device.get("hostname", ""),
                "ip_address": current_device.get("ip", ""),
                "device_class": current_device.get("deviceClass", "unknown"),
            }
            
            # Add last seen timestamp if available
            last_active = current_device.get("lastActiveTimestamp")
            if last_active:
                try:
                    # Convert timestamp to readable format
                    if isinstance(last_active, (int, float)):
                        # Handle both seconds and milliseconds timestamps
                        if last_active > 1e10:  # Likely milliseconds
                            last_active = last_active / 1000
                        
                        last_seen_dt = datetime.fromtimestamp(last_active)
                        attributes["last_seen"] = last_seen_dt.isoformat()
                    else:
                        attributes["last_seen"] = str(last_active)
                except (ValueError, OSError) as err:
                    _LOGGER.debug("Could not parse last active timestamp %s for device %s: %s", last_active, self._mac_address, err)
                    attributes["last_seen"] = str(last_active)
            
            # Add Firewalla box information
            box_info = self.coordinator.box_info
            if box_info:
                attributes.update({
                    "firewalla_box_name": box_info.get("name", ""),
                    "firewalla_box_model": box_info.get("model", ""),
                    "firewalla_firmware_version": box_info.get("version", ""),
                })
            
            # Add any additional device attributes from the API
            try:
                for key, value in current_device.items():
                    if key not in ["mac", "name", "ip", "online", "lastActiveTimestamp", "deviceClass", "hostname"]:
                        # Add with firewalla_ prefix to avoid conflicts
                        attributes[f"firewalla_{key}"] = value
            except Exception as err:
                _LOGGER.debug("Error processing additional device attributes for %s: %s", self._mac_address, err)
            
            return attributes
            
        except Exception as err:
            _LOGGER.error("Error getting device attributes for %s: %s", self._mac_address, err)
            return {"error": "Failed to get device attributes"}

    @property
    def icon(self) -> str:
        """Return the icon for this sensor."""
        current_device = self.coordinator.get_device_by_mac(self._mac_address)
        
        if current_device is None:
            return "mdi:help-network"
        
        # Choose icon based on device status
        if current_device.get("online", False):
            return "mdi:check-network"
        else:
            return "mdi:close-network"


class FirewallaRulesSensor(CoordinatorEntity, SensorEntity):
    """Sensor entity for Firewalla active rules count."""

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator) -> None:
        """Initialize the rules count sensor."""
        super().__init__(coordinator)
        
        # Set unique ID as specified in requirements
        self._attr_unique_id = "firewalla_rules_active"
        self._attr_name = "Firewalla Active Rules"
        
        # Set state class for numeric count
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "rules"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this sensor."""
        box_data = self.coordinator.box_info
        
        # Get box name and model information
        box_name = box_data.get("name", "Firewalla Box")
        box_model = box_data.get("model", "Unknown")
        
        # Format model name nicely
        if box_model and box_model != "Unknown":
            formatted_model = box_model.replace("_", " ").title()
        else:
            formatted_model = "Firewalla Device"
        
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.box_gid)},
            name=box_name,
            manufacturer="Firewalla",
            model=formatted_model,
            sw_version=box_data.get("version") or box_data.get("firmwareVersion"),
        )

    @property
    def native_value(self) -> int:
        """Return the count of active rules."""
        try:
            rules = self.coordinator.rules
            
            if not rules:
                _LOGGER.debug("No rules data available")
                return 0
            
            # Count active rules (not disabled and not paused)
            active_count = 0
            invalid_rules = 0
            
            for rule_id, rule_data in rules.items():
                try:
                    if not isinstance(rule_data, dict):
                        _LOGGER.debug("Invalid rule data for %s: %s", rule_id, type(rule_data))
                        invalid_rules += 1
                        continue
                    
                    disabled = bool(rule_data.get("disabled", False))
                    paused = bool(rule_data.get("paused", False))
                    
                    # Rule is active if it's not disabled and not paused
                    if not disabled and not paused:
                        active_count += 1
                        
                except Exception as err:
                    _LOGGER.debug("Error processing rule %s: %s", rule_id, err)
                    invalid_rules += 1
                    continue
            
            if invalid_rules > 0:
                _LOGGER.debug("Skipped %d invalid rules when counting active rules", invalid_rules)
            
            _LOGGER.debug("Active rules count: %d (total rules: %d)", active_count, len(rules))
            return active_count
            
        except Exception as err:
            _LOGGER.error("Error counting active rules: %s", err)
            return 0

    @property
    def available(self) -> bool:
        """Return True if the coordinator has successful data."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes for the rules sensor."""
        rules = self.coordinator.rules
        
        if not rules:
            return {
                "total_rules": 0,
                "active_rules": 0,
                "paused_rules": 0,
                "disabled_rules": 0,
                "last_updated": None,
            }
        
        # Count different rule states
        total_rules = len(rules)
        active_rules = 0
        paused_rules = 0
        disabled_rules = 0
        
        for rule_data in rules.values():
            if isinstance(rule_data, dict):
                disabled = rule_data.get("disabled", False)
                paused = rule_data.get("paused", False)
                
                if disabled:
                    disabled_rules += 1
                elif paused:
                    paused_rules += 1
                else:
                    active_rules += 1
        
        attributes = {
            "total_rules": total_rules,
            "active_rules": active_rules,
            "paused_rules": paused_rules,
            "disabled_rules": disabled_rules,
        }
        
        # Add last updated timestamp
        if hasattr(self.coordinator, 'last_update_success_time') and self.coordinator.last_update_success_time:
            attributes["last_updated"] = self.coordinator.last_update_success_time.isoformat()
        elif self.coordinator.data and "last_updated" in self.coordinator.data:
            attributes["last_updated"] = self.coordinator.data["last_updated"]
        else:
            attributes["last_updated"] = None
        
        return attributes

    @property
    def icon(self) -> str:
        """Return the icon for this sensor."""
        active_count = self.native_value
        
        if active_count == 0:
            return "mdi:shield-outline"
        elif active_count < 5:
            return "mdi:shield-check"
        else:
            return "mdi:shield-alert"