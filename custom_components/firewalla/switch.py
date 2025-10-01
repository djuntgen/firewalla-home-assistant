"""Switch platform for Firewalla rule control."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
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
    RULE_ATTRIBUTES,
    RULE_TYPES,
)
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla rule control switch entities from a config entry."""
    _LOGGER.debug("Setting up Firewalla rule control switch platform for entry %s", config_entry.entry_id)
    
    try:
        # Get coordinator from hass.data
        coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        # Create switch entities for each discovered rule
        entities = []
        
        # Get rules from coordinator
        if coordinator.data and "rules" in coordinator.data:
            rules = coordinator.data["rules"]
            _LOGGER.debug("Found %d rules for switch creation", len(rules))
            
            for rule_id, rule_data in rules.items():
                try:
                    # Validate rule data
                    if not isinstance(rule_data, dict):
                        _LOGGER.warning("Invalid rule data for %s: %s", rule_id, type(rule_data))
                        continue
                    
                    # Create rule control switch
                    rule_switch = FirewallaRuleSwitch(coordinator, rule_id, rule_data)
                    entities.append(rule_switch)
                    _LOGGER.debug(
                        "Created rule switch for rule %s (%s)", 
                        rule_id, 
                        rule_data.get("description", "No description")
                    )
                        
                except Exception as err:
                    _LOGGER.error("Error creating switch entity for rule %s: %s", rule_id, err)
                    continue
        else:
            _LOGGER.warning("No rules found in coordinator data for switch creation")
        
        if entities:
            async_add_entities(entities, True)
            _LOGGER.info("Successfully added %d Firewalla rule control switch entities", len(entities))
        else:
            _LOGGER.warning("No valid rule switch entities could be created")
            async_add_entities([], True)
            
    except KeyError as err:
        _LOGGER.error("Missing coordinator data for config entry %s: %s", config_entry.entry_id, err)
        raise HomeAssistantError(f"Coordinator not found for Firewalla integration: {err}") from err
    except Exception as err:
        _LOGGER.exception("Unexpected error setting up Firewalla rule control switch platform: %s", err)
        raise HomeAssistantError(f"Failed to set up Firewalla rule control switch platform: {err}") from err


class FirewallaRuleSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for controlling individual Firewalla rules (pause/unpause)."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        rule_id: str,
        rule_data: Dict[str, Any],
    ) -> None:
        """Initialize the rule switch."""
        super().__init__(coordinator)
        self._rule_id = rule_id
        self._rule_data = rule_data.copy()
        
        # Generate a clean entity ID based on rule name
        entity_name = self._generate_entity_name(rule_data)
        clean_entity_id = self._generate_clean_entity_id(entity_name, rule_id)
        self._attr_unique_id = f"firewalla_rule_{clean_entity_id}"
        
        # Set entity name based on rule information
        self._attr_name = self._generate_entity_name(rule_data)
        
        # Set device info
        self._attr_device_info = self._get_device_info()

    def _generate_clean_entity_id(self, entity_name: str, rule_id: str) -> str:
        """Generate a clean entity ID from the rule name."""
        import re
        
        # Start with the entity name
        clean_id = entity_name.lower()
        
        # Remove common prefixes to make IDs shorter
        prefixes_to_remove = ["block ", "allow ", "firewalla ", "rule "]
        for prefix in prefixes_to_remove:
            if clean_id.startswith(prefix):
                clean_id = clean_id[len(prefix):]
                break
        
        # Replace spaces and special characters with underscores
        clean_id = re.sub(r'[^a-z0-9]+', '_', clean_id)
        
        # Remove leading/trailing underscores
        clean_id = clean_id.strip('_')
        
        # Limit length to keep entity IDs reasonable
        if len(clean_id) > 40:
            clean_id = clean_id[:40].rstrip('_')
        
        # If the cleaned ID is empty or too short, use first part of rule ID
        if len(clean_id) < 3:
            rule_id_short = rule_id.split('-')[0] if '-' in rule_id else rule_id[:8]
            clean_id = f"rule_{rule_id_short}"
        
        return clean_id

    def _generate_entity_name(self, rule_data: Dict[str, Any]) -> str:
        """Generate a descriptive entity name based on rule information."""
        # Try to use rule description first
        description = rule_data.get("description", "").strip()
        if description:
            return description
        
        # Get rule type and value from actual API structure
        rule_type = rule_data.get("type", "unknown")
        rule_value = rule_data.get("value", "")
        
        # Create descriptive name based on rule type
        rule_type_display = RULE_TYPES.get(rule_type, rule_type.title())
        
        if rule_type == "app":
            # App blocking rule
            app_name = rule_value.title() if rule_value else "App"
            return f"Block {app_name}"
        elif rule_type == "category":
            # Category blocking rule
            category_name = rule_value.title() if rule_value else "Category"
            return f"Block {category_name} Category"
        elif rule_type == "domain":
            # Domain blocking rule
            domain_name = rule_value if rule_value else "Domain"
            return f"Block {domain_name}"
        elif rule_type == "ip":
            # IP blocking rule
            ip_address = rule_value if rule_value else "IP"
            return f"Block {ip_address}"
        elif rule_type == "internet":
            # Internet blocking rule
            return "Block Internet Access"
        elif rule_type == "intranet":
            # Intranet rule
            if rule_value:
                return f"Intranet Access - {rule_value[:8]}"
            else:
                return "Intranet Access"
        else:
            # Generic rule
            if rule_value:
                return f"{rule_type_display} - {rule_value}"
            else:
                return f"{rule_type_display} Rule"

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
    def name(self) -> str:
        """Return the name of the entity, refreshed from current rule data."""
        # Get current rule data to ensure fresh name
        current_rule_data = self._get_current_rule_data()
        if current_rule_data:
            return self._generate_entity_name(current_rule_data)
        else:
            # Fallback to stored name if rule not found
            return self._attr_name

    @property
    def is_on(self) -> bool:
        """Return True if the rule is active (not paused), False if paused."""
        current_rule_data = self._get_current_rule_data()
        if current_rule_data:
            # ON = rule is active (not paused), OFF = rule is paused
            return not current_rule_data.get("paused", False)
        
        # If rule not found, assume it's been deleted (OFF state)
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Entity is available if coordinator has data and rule exists
        return (
            self.coordinator.last_update_success
            and self._get_current_rule_data() is not None
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes with rich rule metadata."""
        current_rule_data = self._get_current_rule_data()
        if not current_rule_data:
            return {"rule_id": self._rule_id, "status": "Rule not found"}
        
        attributes = {"rule_id": self._rule_id}
        
        # Add all rule attributes
        for attr_key in RULE_ATTRIBUTES:
            if attr_key in current_rule_data:
                value = current_rule_data[attr_key]
                
                # Format timestamps for better readability
                if attr_key in ["created_at", "modified_at"] and isinstance(value, (int, float)):
                    try:
                        from datetime import datetime
                        # Handle both seconds and milliseconds timestamps
                        if value > 1e10:  # Likely milliseconds
                            value = value / 1000
                        dt = datetime.fromtimestamp(value)
                        attributes[attr_key] = dt.isoformat()
                    except (ValueError, OSError):
                        attributes[attr_key] = str(value)
                else:
                    attributes[attr_key] = value
        
        # Add human-readable rule type
        rule_type = current_rule_data.get("type", "unknown")
        attributes["rule_type_display"] = RULE_TYPES.get(rule_type, rule_type.title())
        
        # Add rule status information
        attributes["rule_status"] = "active" if not current_rule_data.get("paused", False) else "paused"
        attributes["rule_disabled"] = current_rule_data.get("disabled", False)
        
        return attributes

    def _get_current_rule_data(self) -> Optional[Dict[str, Any]]:
        """Get current rule data from coordinator."""
        if not self.coordinator.data or "rules" not in self.coordinator.data:
            return None
        
        return self.coordinator.data["rules"].get(self._rule_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the rule (unpause it to make it active)."""
        _LOGGER.debug("Turning on (unpausing) rule %s", self._rule_id)
        
        try:
            current_rule_data = self._get_current_rule_data()
            if not current_rule_data:
                _LOGGER.error("Cannot turn on rule %s: rule not found", self._rule_id)
                raise HomeAssistantError(f"Rule {self._rule_id} not found")
            
            # Check if rule is already active
            if not current_rule_data.get("paused", False):
                _LOGGER.debug("Rule %s is already active", self._rule_id)
                return
            
            # Unpause the rule
            _LOGGER.info("Unpausing rule %s", self._rule_id)
            success = await self.coordinator.async_unpause_rule(self._rule_id)
            
            if success:
                _LOGGER.debug("Successfully unpaused rule %s", self._rule_id)
            else:
                _LOGGER.error("Failed to unpause rule %s", self._rule_id)
                raise HomeAssistantError(f"Failed to unpause rule {self._rule_id}")
            
        except HomeAssistantError:
            # Re-raise Home Assistant errors as-is
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error turning on rule %s: %s", self._rule_id, err)
            raise HomeAssistantError(f"Failed to turn on rule: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the rule (pause it while preserving configuration)."""
        _LOGGER.debug("Turning off (pausing) rule %s", self._rule_id)
        
        try:
            current_rule_data = self._get_current_rule_data()
            if not current_rule_data:
                _LOGGER.error("Cannot turn off rule %s: rule not found", self._rule_id)
                raise HomeAssistantError(f"Rule {self._rule_id} not found")
            
            # Check if rule is already paused
            if current_rule_data.get("paused", False):
                _LOGGER.debug("Rule %s is already paused", self._rule_id)
                return
            
            # Pause the rule (preserves configuration for future use)
            _LOGGER.info("Pausing rule %s", self._rule_id)
            success = await self.coordinator.async_pause_rule(self._rule_id)
            
            if success:
                _LOGGER.debug("Successfully paused rule %s", self._rule_id)
            else:
                _LOGGER.error("Failed to pause rule %s", self._rule_id)
                raise HomeAssistantError(f"Failed to pause rule {self._rule_id}")
            
        except HomeAssistantError:
            # Re-raise Home Assistant errors as-is
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error turning off rule %s: %s", self._rule_id, err)
            raise HomeAssistantError(f"Failed to turn off rule: {err}") from err

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("Rule switch entity added to hass: %s (%s)", self._rule_id, self.name)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        _LOGGER.debug("Rule switch entity being removed from hass: %s (%s)", self._rule_id, self.name)