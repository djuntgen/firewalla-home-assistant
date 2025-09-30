"""Switch platform for Firewalla integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RULE_TYPES, RULE_ACTIONS, GAMING_DEVICE_CLASSES
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _is_gaming_capable_device(device_info: Dict[str, Any]) -> bool:
    """Check if a device is gaming-capable based on device class or name."""
    device_class = device_info.get("deviceClass", "").lower()
    device_name = device_info.get("name", "").lower()
    
    # Check if device class matches known gaming device classes
    for gaming_class in GAMING_DEVICE_CLASSES:
        if gaming_class.lower() in device_class:
            return True
    
    # Check device name for gaming-related keywords
    gaming_keywords = [
        "xbox", "playstation", "ps4", "ps5", "nintendo", "switch", 
        "steam", "gaming", "console", "deck"
    ]
    
    for keyword in gaming_keywords:
        if keyword in device_name:
            return True
    
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla switch entities from a config entry."""
    _LOGGER.debug("Setting up Firewalla switch platform for entry %s", config_entry.entry_id)
    
    try:
        # Get coordinator from hass.data
        coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        # Create switch entities for each device
        entities = []
        
        # Get devices from coordinator
        devices = coordinator.devices
        _LOGGER.debug("Found %d devices for switch creation", len(devices))
        
        if not devices:
            _LOGGER.warning("No devices found in coordinator data for switch creation")
            # Still call async_add_entities with empty list to complete setup
            async_add_entities([], True)
            return
        
        for device_mac, device_info in devices.items():
            try:
                # Validate device data
                if not isinstance(device_info, dict):
                    _LOGGER.warning("Invalid device info for %s: %s", device_mac, type(device_info))
                    continue
                
                # Create internet blocking switch for each device
                block_switch = FirewallaBlockSwitch(coordinator, device_mac, device_info)
                entities.append(block_switch)
                _LOGGER.debug("Created block switch for device %s (%s)", device_info.get("name", device_mac), device_mac)
                
                # Create gaming pause switch for gaming-capable devices
                if _is_gaming_capable_device(device_info):
                    gaming_switch = FirewallaGamingSwitch(coordinator, device_mac, device_info)
                    entities.append(gaming_switch)
                    _LOGGER.debug("Created gaming switch for device %s (%s)", device_info.get("name", device_mac), device_mac)
                    
            except Exception as err:
                _LOGGER.error("Error creating switch entities for device %s: %s", device_mac, err)
                continue
        
        if entities:
            async_add_entities(entities, True)
            _LOGGER.info("Successfully added %d Firewalla switch entities", len(entities))
        else:
            _LOGGER.warning("No valid switch entities could be created")
            async_add_entities([], True)
            
    except KeyError as err:
        _LOGGER.error("Missing coordinator data for config entry %s: %s", config_entry.entry_id, err)
        raise HomeAssistantError(f"Coordinator not found for Firewalla integration: {err}") from err
    except Exception as err:
        _LOGGER.exception("Unexpected error setting up Firewalla switch platform: %s", err)
        raise HomeAssistantError(f"Failed to set up Firewalla switch platform: {err}") from err


class FirewallaBlockSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for controlling internet blocking rules for Firewalla devices."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        device_mac: str,
        device_info: Dict[str, Any],
    ) -> None:
        """Initialize the block switch."""
        super().__init__(coordinator)
        self._device_mac = device_mac
        self._device_info = device_info
        self._active_rule_id: Optional[str] = None
        
        # Get friendly name with disambiguation
        friendly_name = coordinator.get_device_friendly_name(device_mac, device_info)
        
        # Set unique ID and entity name
        self._attr_unique_id = f"firewalla_{device_mac.replace(':', '')}_block"
        self._attr_name = f"{friendly_name} Block"

    @property
    def name(self) -> str:
        """Return the name of the entity, refreshed from current device data."""
        # Get current device data and friendly name
        current_device_data = self.coordinator.get_device_by_mac(self._device_mac)
        if current_device_data:
            friendly_name = self.coordinator.get_device_friendly_name(self._device_mac, current_device_data)
            return f"{friendly_name} Block"
        else:
            # Fallback to stored name if device not found
            return self._attr_name
        
        # Set device info using coordinator method
        self._attr_device_info = coordinator.get_device_info_dict(device_mac, device_info)

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information, refreshed from current coordinator data."""
        # Get current device data to ensure fresh information
        current_device_data = self.coordinator.get_device_by_mac(self._device_mac)
        if current_device_data:
            return self.coordinator.get_device_info_dict(self._device_mac, current_device_data)
        else:
            # Fallback to stored device info if device not found
            return self._attr_device_info

    @property
    def is_on(self) -> bool:
        """Return True if the internet blocking rule is active."""
        # Check if there's an active internet blocking rule for this device
        rules = self.coordinator.rules
        for rule_id, rule_data in rules.items():
            if (
                rule_data.get("type") == RULE_TYPES["INTERNET_BLOCK"]
                and rule_data.get("target") == f"mac:{self._device_mac}"
                and rule_data.get("action") == RULE_ACTIONS["BLOCK"]
                and not rule_data.get("paused", False)
                and not rule_data.get("disabled", False)
            ):
                self._active_rule_id = rule_id
                return True
        
        self._active_rule_id = None
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Entity is available if coordinator has data and device exists
        return (
            self.coordinator.last_update_success
            and self._device_mac in self.coordinator.devices
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        # Get current device info to ensure fresh data
        device_info = self.coordinator.get_device_by_mac(self._device_mac) or {}
        
        # Get friendly name with disambiguation
        friendly_name = self.coordinator.get_device_friendly_name(self._device_mac, device_info)
        
        attributes = {
            "device_mac": self._device_mac,
            "device_name": device_info.get("name", "Unknown"),
            "device_friendly_name": friendly_name,
            "device_hostname": device_info.get("hostname", ""),
            "device_ip": device_info.get("ip", ""),
            "device_online": device_info.get("online", False),
            "device_class": device_info.get("deviceClass", "unknown"),
        }
        
        # Add last seen information if available
        last_active = device_info.get("lastActiveTimestamp")
        if last_active:
            try:
                from datetime import datetime
                # Handle both seconds and milliseconds timestamps
                if isinstance(last_active, (int, float)):
                    if last_active > 1e10:  # Likely milliseconds
                        last_active = last_active / 1000
                    last_seen_dt = datetime.fromtimestamp(last_active)
                    attributes["last_seen"] = last_seen_dt.isoformat()
            except (ValueError, OSError):
                attributes["last_seen"] = str(last_active)
        
        # Add Firewalla box information
        box_info = self.coordinator.box_info
        if box_info:
            attributes.update({
                "firewalla_box_name": box_info.get("name", ""),
                "firewalla_box_model": box_info.get("model", ""),
                "firewalla_firmware_version": box_info.get("version", ""),
            })
        
        # Add active rule information if available
        if self._active_rule_id:
            rule_data = self.coordinator.rules.get(self._active_rule_id, {})
            attributes.update({
                "active_rule_id": self._active_rule_id,
                "rule_description": rule_data.get("description", ""),
                "rule_created": rule_data.get("created", ""),
            })
        
        return attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the internet blocking rule for this device."""
        _LOGGER.debug("Turning on internet block for device %s (%s)", self._device_mac, self._device_info.get("name", "Unknown"))
        
        try:
            # Check if there's already an active rule
            if self.is_on:
                _LOGGER.debug("Internet block already active for device %s", self._device_mac)
                return
            
            # Check if there's a paused rule we can unpause
            paused_rule_id = await self._find_paused_block_rule()
            if paused_rule_id:
                _LOGGER.info("Unpausing existing internet block rule %s for device %s", paused_rule_id, self._device_mac)
                await self.coordinator.async_unpause_rule(paused_rule_id)
            else:
                # Create a new blocking rule
                device_name = self._device_info.get("name", self._device_mac)
                _LOGGER.info("Creating new internet block rule for device %s (%s)", self._device_mac, device_name)
                await self.coordinator.async_create_device_block_rule(
                    self._device_mac, device_name
                )
            
            # Request coordinator update to refresh entity state
            await self.coordinator.async_request_refresh()
            _LOGGER.debug("Successfully enabled internet blocking for device %s", self._device_mac)
            
        except HomeAssistantError:
            # Re-raise Home Assistant errors as-is
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error turning on internet block for device %s: %s", self._device_mac, err)
            raise HomeAssistantError(f"Failed to enable internet blocking: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the internet blocking rule for this device (pause it to preserve for future use)."""
        _LOGGER.debug("Turning off internet block for device %s (%s)", self._device_mac, self._device_info.get("name", "Unknown"))
        
        try:
            # Find the active rule to pause
            active_rule_id = await self._find_active_block_rule()
            if not active_rule_id:
                _LOGGER.debug("No active internet block rule found for device %s", self._device_mac)
                return
            
            # Pause the rule instead of deleting it to preserve for future use
            _LOGGER.info("Pausing internet block rule %s for device %s", active_rule_id, self._device_mac)
            await self.coordinator.async_pause_rule(active_rule_id)
            
            # Request coordinator update to refresh entity state
            await self.coordinator.async_request_refresh()
            _LOGGER.debug("Successfully disabled internet blocking for device %s", self._device_mac)
            
        except HomeAssistantError:
            # Re-raise Home Assistant errors as-is
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error turning off internet block for device %s: %s", self._device_mac, err)
            raise HomeAssistantError(f"Failed to disable internet blocking: {err}") from err

    async def _find_active_block_rule(self) -> Optional[str]:
        """Find the active internet blocking rule for this device."""
        try:
            device_rules = await self.coordinator.async_get_device_rules(
                self._device_mac, RULE_TYPES["INTERNET_BLOCK"]
            )
            
            for rule_id, rule_data in device_rules.items():
                if (
                    rule_data.get("action") == RULE_ACTIONS["BLOCK"]
                    and not rule_data.get("paused", False)
                    and not rule_data.get("disabled", False)
                ):
                    return rule_id
            
            return None
            
        except Exception as err:
            _LOGGER.error("Failed to find active block rule for device %s: %s", self._device_mac, err)
            return None

    async def _find_paused_block_rule(self) -> Optional[str]:
        """Find a paused internet blocking rule for this device that can be unpaused."""
        try:
            device_rules = await self.coordinator.async_get_device_rules(
                self._device_mac, RULE_TYPES["INTERNET_BLOCK"]
            )
            
            for rule_id, rule_data in device_rules.items():
                if (
                    rule_data.get("action") == RULE_ACTIONS["BLOCK"]
                    and rule_data.get("paused", False)
                    and not rule_data.get("disabled", False)
                ):
                    return rule_id
            
            return None
            
        except Exception as err:
            _LOGGER.error("Failed to find paused block rule for device %s: %s", self._device_mac, err)
            return None


class FirewallaGamingSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for controlling gaming pause rules for Firewalla devices."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        device_mac: str,
        device_info: Dict[str, Any],
    ) -> None:
        """Initialize the gaming switch."""
        super().__init__(coordinator)
        self._device_mac = device_mac
        self._device_info = device_info
        self._active_rule_id: Optional[str] = None
        
        # Get friendly name with disambiguation
        friendly_name = coordinator.get_device_friendly_name(device_mac, device_info)
        
        # Set unique ID and entity name
        self._attr_unique_id = f"firewalla_{device_mac.replace(':', '')}_gaming"
        self._attr_name = f"{friendly_name} Gaming Pause"

    @property
    def name(self) -> str:
        """Return the name of the entity, refreshed from current device data."""
        # Get current device data and friendly name
        current_device_data = self.coordinator.get_device_by_mac(self._device_mac)
        if current_device_data:
            friendly_name = self.coordinator.get_device_friendly_name(self._device_mac, current_device_data)
            return f"{friendly_name} Gaming Pause"
        else:
            # Fallback to stored name if device not found
            return self._attr_name
        
        # Set device info using coordinator method
        self._attr_device_info = coordinator.get_device_info_dict(device_mac, device_info)

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information, refreshed from current coordinator data."""
        # Get current device data to ensure fresh information
        current_device_data = self.coordinator.get_device_by_mac(self._device_mac)
        if current_device_data:
            return self.coordinator.get_device_info_dict(self._device_mac, current_device_data)
        else:
            # Fallback to stored device info if device not found
            return self._attr_device_info

    @property
    def is_on(self) -> bool:
        """Return True if the gaming pause rule is active."""
        # Check if there's an active gaming pause rule for this device
        rules = self.coordinator.rules
        for rule_id, rule_data in rules.items():
            if (
                rule_data.get("type") == RULE_TYPES["GAMING_PAUSE"]
                and rule_data.get("target") == f"mac:{self._device_mac}"
                and rule_data.get("action") == RULE_ACTIONS["BLOCK"]
                and not rule_data.get("paused", False)
                and not rule_data.get("disabled", False)
            ):
                self._active_rule_id = rule_id
                return True
        
        self._active_rule_id = None
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Entity is available if coordinator has data and device exists and is gaming-capable
        return (
            self.coordinator.last_update_success
            and self._device_mac in self.coordinator.devices
            and _is_gaming_capable_device(self._device_info)
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        # Get current device info to ensure fresh data
        device_info = self.coordinator.get_device_by_mac(self._device_mac) or {}
        
        # Get friendly name with disambiguation
        friendly_name = self.coordinator.get_device_friendly_name(self._device_mac, device_info)
        
        attributes = {
            "device_mac": self._device_mac,
            "device_name": device_info.get("name", "Unknown"),
            "device_friendly_name": friendly_name,
            "device_hostname": device_info.get("hostname", ""),
            "device_ip": device_info.get("ip", ""),
            "device_online": device_info.get("online", False),
            "device_class": device_info.get("deviceClass", "unknown"),
            "gaming_capable": True,
        }
        
        # Add last seen information if available
        last_active = device_info.get("lastActiveTimestamp")
        if last_active:
            try:
                from datetime import datetime
                # Handle both seconds and milliseconds timestamps
                if isinstance(last_active, (int, float)):
                    if last_active > 1e10:  # Likely milliseconds
                        last_active = last_active / 1000
                    last_seen_dt = datetime.fromtimestamp(last_active)
                    attributes["last_seen"] = last_seen_dt.isoformat()
            except (ValueError, OSError):
                attributes["last_seen"] = str(last_active)
        
        # Add Firewalla box information
        box_info = self.coordinator.box_info
        if box_info:
            attributes.update({
                "firewalla_box_name": box_info.get("name", ""),
                "firewalla_box_model": box_info.get("model", ""),
                "firewalla_firmware_version": box_info.get("version", ""),
            })
        
        # Add active rule information if available
        if self._active_rule_id:
            rule_data = self.coordinator.rules.get(self._active_rule_id, {})
            attributes.update({
                "active_rule_id": self._active_rule_id,
                "rule_description": rule_data.get("description", ""),
                "rule_created": rule_data.get("created", ""),
            })
        
        return attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the gaming pause rule for this device."""
        _LOGGER.debug("Turning on gaming pause for device %s (%s)", self._device_mac, self._device_info.get("name", "Unknown"))
        
        try:
            # Check if there's already an active rule
            if self.is_on:
                _LOGGER.debug("Gaming pause already active for device %s", self._device_mac)
                return
            
            # Check if there's a paused rule we can unpause
            paused_rule_id = await self._find_paused_gaming_rule()
            if paused_rule_id:
                _LOGGER.info("Unpausing existing gaming pause rule %s for device %s", paused_rule_id, self._device_mac)
                await self.coordinator.async_unpause_rule(paused_rule_id)
            else:
                # Create a new gaming pause rule
                device_name = self._device_info.get("name", self._device_mac)
                _LOGGER.info("Creating new gaming pause rule for device %s (%s)", self._device_mac, device_name)
                await self.coordinator.async_create_gaming_pause_rule(
                    self._device_mac, device_name
                )
            
            # Request coordinator update to refresh entity state
            await self.coordinator.async_request_refresh()
            _LOGGER.debug("Successfully enabled gaming pause for device %s", self._device_mac)
            
        except HomeAssistantError:
            # Re-raise Home Assistant errors as-is
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error turning on gaming pause for device %s: %s", self._device_mac, err)
            raise HomeAssistantError(f"Failed to enable gaming pause: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the gaming pause rule for this device (pause it to preserve for future use)."""
        _LOGGER.debug("Turning off gaming pause for device %s (%s)", self._device_mac, self._device_info.get("name", "Unknown"))
        
        try:
            # Find the active rule to pause
            active_rule_id = await self._find_active_gaming_rule()
            if not active_rule_id:
                _LOGGER.debug("No active gaming pause rule found for device %s", self._device_mac)
                return
            
            # Pause the rule instead of deleting it to preserve for future use
            _LOGGER.info("Pausing gaming pause rule %s for device %s", active_rule_id, self._device_mac)
            await self.coordinator.async_pause_rule(active_rule_id)
            
            # Request coordinator update to refresh entity state
            await self.coordinator.async_request_refresh()
            _LOGGER.debug("Successfully disabled gaming pause for device %s", self._device_mac)
            
        except HomeAssistantError:
            # Re-raise Home Assistant errors as-is
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error turning off gaming pause for device %s: %s", self._device_mac, err)
            raise HomeAssistantError(f"Failed to disable gaming pause: {err}") from err

    async def _find_active_gaming_rule(self) -> Optional[str]:
        """Find the active gaming pause rule for this device."""
        try:
            device_rules = await self.coordinator.async_get_device_rules(
                self._device_mac, RULE_TYPES["GAMING_PAUSE"]
            )
            
            for rule_id, rule_data in device_rules.items():
                if (
                    rule_data.get("action") == RULE_ACTIONS["BLOCK"]
                    and not rule_data.get("paused", False)
                    and not rule_data.get("disabled", False)
                ):
                    return rule_id
            
            return None
            
        except Exception as err:
            _LOGGER.error("Failed to find active gaming rule for device %s: %s", self._device_mac, err)
            return None

    async def _find_paused_gaming_rule(self) -> Optional[str]:
        """Find a paused gaming pause rule for this device that can be unpaused."""
        try:
            device_rules = await self.coordinator.async_get_device_rules(
                self._device_mac, RULE_TYPES["GAMING_PAUSE"]
            )
            
            for rule_id, rule_data in device_rules.items():
                if (
                    rule_data.get("action") == RULE_ACTIONS["BLOCK"]
                    and rule_data.get("paused", False)
                    and not rule_data.get("disabled", False)
                ):
                    return rule_id
            
            return None
            
        except Exception as err:
            _LOGGER.error("Failed to find paused gaming rule for device %s: %s", self._device_mac, err)
            return None