"""Switch platform for Firewalla rule control."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_MANUFACTURER,
    DEVICE_MODEL_MAPPINGS,
    DOMAIN,
    RULE_ACTIONS,
    RULE_ATTRIBUTES,
    RULE_TYPES,
)
from .coordinator import FirewallaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Action prefixes for entity name generation.
_ACTION_PREFIXES: dict[str, str] = {
    "block": "Block",
    "allow": "Allow",
    "timelimit": "Limit",
}


def _generate_clean_entity_id(entity_name: str, rule_id: str) -> str:
    """Generate a clean, deterministic entity ID fragment from a rule name."""
    clean_id = entity_name.lower()

    # Remove common prefixes to keep IDs shorter.
    for prefix in ("block ", "allow ", "limit ", "firewalla ", "rule "):
        if clean_id.startswith(prefix):
            clean_id = clean_id[len(prefix) :]
            break

    clean_id = re.sub(r"[^a-z0-9]+", "_", clean_id).strip("_")

    if len(clean_id) > 40:
        clean_id = clean_id[:40].rstrip("_")

    if len(clean_id) < 3:
        rule_id_short = rule_id.split("-")[0] if "-" in rule_id else rule_id[:8]
        clean_id = f"rule_{rule_id_short}"

    return clean_id


def _make_unique_id(coordinator: FirewallaDataUpdateCoordinator, rule_id: str) -> str:
    """Build the unique_id for a rule switch entity.

    Uses the rule's current data from the coordinator when available so that the
    generated id is consistent with what the entity class produces in __init__.
    """
    rule_data = None
    if coordinator.data and "rules" in coordinator.data:
        rule_data = coordinator.data["rules"].get(rule_id)

    if rule_data and isinstance(rule_data, dict):
        entity_name = _generate_entity_name(rule_data)
    else:
        entity_name = f"rule_{rule_id}"

    return f"firewalla_rule_{_generate_clean_entity_id(entity_name, rule_id)}"


def _generate_entity_name(rule_data: dict[str, Any]) -> str:
    """Generate a descriptive entity name based on rule information."""
    description = rule_data.get("description", "").strip()
    if description:
        return description

    rule_type = rule_data.get("type", "unknown")
    rule_value = rule_data.get("value", "")
    action = rule_data.get("action", "block")
    action_prefix = _ACTION_PREFIXES.get(action, action.title())
    rule_type_display = RULE_TYPES.get(rule_type, rule_type.title())

    if rule_type == "app":
        app_name = rule_value.title() if rule_value else "App"
        return f"{action_prefix} {app_name}"
    elif rule_type == "category":
        category_name = rule_value.title() if rule_value else "Category"
        return f"{action_prefix} {category_name} Category"
    elif rule_type == "domain":
        domain_name = rule_value if rule_value else "Domain"
        return f"{action_prefix} {domain_name}"
    elif rule_type == "ip":
        ip_address = rule_value if rule_value else "IP"
        return f"{action_prefix} {ip_address}"
    elif rule_type == "internet":
        return f"{action_prefix} Internet Access"
    elif rule_type == "intranet":
        if rule_value:
            return f"Intranet Access - {rule_value[:8]}"
        return "Intranet Access"
    else:
        if rule_value:
            return f"{rule_type_display} - {rule_value}"
        return f"{rule_type_display} Rule"


def _format_timestamp(value: int | float) -> str | None:
    """Format a numeric timestamp to ISO-8601, handling seconds and milliseconds."""
    if not value:
        return None
    try:
        if value > 1e10:
            value = value / 1000
        return datetime.fromtimestamp(value).isoformat()
    except (ValueError, OSError):
        return str(value)


def _format_schedule(schedule: dict | list | None) -> str | None:
    """Return a human-readable schedule string, or None."""
    if not schedule:
        return None
    if isinstance(schedule, dict):
        days = schedule.get("days", [])
        time_start = schedule.get("startTime", schedule.get("start", ""))
        time_end = schedule.get("endTime", schedule.get("end", ""))
        if days or time_start or time_end:
            day_str = ", ".join(str(d) for d in days) if days else "every day"
            return f"{day_str} {time_start}-{time_end}".strip()
        return str(schedule)
    if isinstance(schedule, list):
        parts = []
        for entry in schedule:
            if isinstance(entry, dict):
                parts.append(_format_schedule(entry) or str(entry))
            else:
                parts.append(str(entry))
        return "; ".join(parts) if parts else None
    return str(schedule)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Firewalla rule control switch entities from a config entry."""
    coordinator: FirewallaDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    known_rule_ids: set[str] = set()
    known_group_ids: set[str] = set()
    known_group_rule_keys: set[tuple[str, str]] = set()

    @callback
    def _async_update_entities() -> None:
        """Synchronise switch entities with the current set of rules."""
        if not coordinator.data or "rules" not in coordinator.data:
            return

        current_ids = set(coordinator.data["rules"].keys())

        # --- add entities for newly discovered rules ---
        new_ids = current_ids - known_rule_ids
        if new_ids:
            new_entities: list[FirewallaRuleSwitch] = []
            for rid in new_ids:
                rule_data = coordinator.data["rules"][rid]
                if isinstance(rule_data, dict):
                    new_entities.append(
                        FirewallaRuleSwitch(coordinator, rid, rule_data)
                    )
            if new_entities:
                async_add_entities(new_entities)
            known_rule_ids.update(new_ids)

        # --- remove entities for deleted rules ---
        removed_ids = known_rule_ids - current_ids
        if removed_ids:
            ent_reg = er.async_get(hass)
            for rid in removed_ids:
                entity_id = ent_reg.async_get_entity_id(
                    "switch", DOMAIN, _make_unique_id(coordinator, rid)
                )
                if entity_id:
                    ent_reg.async_remove(entity_id)
            known_rule_ids.difference_update(removed_ids)

        # --- Group internet switches ---
        current_groups = set()
        if coordinator.data and "groups" in coordinator.data:
            for gid, gdata in coordinator.data["groups"].items():
                if gdata.get("internet_block_rule_id"):
                    current_groups.add(gid)

        new_groups = current_groups - known_group_ids
        if new_groups:
            group_entities = [FirewallaGroupInternetSwitch(coordinator, gid) for gid in new_groups]
            async_add_entities(group_entities)
            known_group_ids.update(new_groups)

        removed_groups = known_group_ids - current_groups
        if removed_groups:
            ent_reg = er.async_get(hass)
            for gid in removed_groups:
                entity_id = ent_reg.async_get_entity_id("switch", DOMAIN, f"firewalla_group_{gid}_internet")
                if entity_id:
                    ent_reg.async_remove(entity_id)
            known_group_ids.difference_update(removed_groups)

        # --- Group rule switches (category/app blocks, excluding internet) ---
        current_group_rule_keys: set[tuple[str, str]] = set()
        if coordinator.data and "groups" in coordinator.data:
            for gid, gdata in coordinator.data["groups"].items():
                internet_rule_id = gdata.get("internet_block_rule_id")
                for rid in gdata.get("group_rules", {}):
                    if rid != internet_rule_id:  # Skip internet — has its own switch
                        current_group_rule_keys.add((gid, rid))

        new_group_rules = current_group_rule_keys - known_group_rule_keys
        if new_group_rules:
            new_entities = [FirewallaGroupRuleSwitch(coordinator, gid, rid) for gid, rid in new_group_rules]
            async_add_entities(new_entities)
            known_group_rule_keys.update(new_group_rules)

        removed_group_rules = known_group_rule_keys - current_group_rule_keys
        if removed_group_rules:
            ent_reg = er.async_get(hass)
            for gid, rid in removed_group_rules:
                entity_id = ent_reg.async_get_entity_id("switch", DOMAIN, f"firewalla_group_{gid}_rule_{rid}")
                if entity_id:
                    ent_reg.async_remove(entity_id)
            known_group_rule_keys.difference_update(removed_group_rules)

    # Perform the initial sync, then listen for coordinator updates.
    _async_update_entities()
    config_entry.async_on_unload(
        coordinator.async_add_listener(_async_update_entities)
    )


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class FirewallaRuleSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for controlling individual Firewalla rules (pause/resume)."""

    _attr_has_entity_name = True

    _unrecorded_attributes = frozenset(
        {
            "rule_id",
            "action",
            "priority",
            "description",
            "created_at",
            "modified_at",
            "rule_type_display",
            "target",
            "target_name",
            "schedule",
            "schedule_display",
            "scope_type",
            "scope_value",
            "direction",
            "dnsOnly",
        }
    )

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        rule_id: str,
        rule_data: dict[str, Any],
    ) -> None:
        """Initialize the rule switch."""
        super().__init__(coordinator)
        self._rule_id = rule_id
        self._rule_data = rule_data.copy()

        entity_name = _generate_entity_name(rule_data)
        clean_entity_id = _generate_clean_entity_id(entity_name, rule_id)
        self._attr_unique_id = f"firewalla_rule_{clean_entity_id}"
        self._attr_name = entity_name
        self._attr_device_info = self._build_device_info()

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    def _build_device_info(self) -> DeviceInfo:
        """Build device info for the Firewalla box."""
        box_info: dict[str, Any] = {}
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

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool:
        """Return True if the rule is active (not paused)."""
        current = self._get_current_rule_data()
        if current:
            return not current.get("paused", False)
        return False

    @property
    def available(self) -> bool:
        """Return True if coordinator is healthy and the rule still exists."""
        return (
            self.coordinator.last_update_success
            and self._get_current_rule_data() is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes with rich rule metadata."""
        current = self._get_current_rule_data()
        if not current:
            return {"rule_id": self._rule_id, "status": "Rule not found"}

        attrs: dict[str, Any] = {"rule_id": self._rule_id}

        # Standard rule attributes from RULE_ATTRIBUTES list.
        for key in RULE_ATTRIBUTES:
            if key in current:
                value = current[key]
                if key in ("created_at", "modified_at") and isinstance(
                    value, (int, float)
                ):
                    formatted = _format_timestamp(value)
                    if formatted is not None:
                        attrs[key] = formatted
                else:
                    attrs[key] = value

        # Human-readable rule type.
        rule_type = current.get("type", "unknown")
        attrs["rule_type_display"] = RULE_TYPES.get(rule_type, rule_type.title())

        # Rule status.
        attrs["rule_status"] = (
            "active" if not current.get("paused", False) else "paused"
        )
        attrs["rule_disabled"] = current.get("disabled", False)

        # Enriched attributes from coordinator.
        hit_info = current.get("hit", {})
        if isinstance(hit_info, dict):
            attrs["hit_count"] = hit_info.get("count", current.get("hit_count", 0))
            last_hit_ts = hit_info.get("ts", current.get("last_hit"))
            if last_hit_ts and isinstance(last_hit_ts, (int, float)):
                formatted = _format_timestamp(last_hit_ts)
                if formatted is not None:
                    attrs["last_hit"] = formatted
        else:
            attrs["hit_count"] = current.get("hit_count", 0)

        # Time quota / usage (only if present).
        time_quota = current.get("time_quota_minutes")
        if time_quota is not None:
            attrs["time_quota_minutes"] = time_quota

        time_used = current.get("time_used_minutes")
        if time_used is not None:
            attrs["time_used_minutes"] = time_used

        # Schedule display.
        schedule_raw = current.get("schedule")
        schedule_display = current.get("schedule_display") or _format_schedule(
            schedule_raw
        )
        if schedule_display:
            attrs["schedule_display"] = schedule_display

        # Scope.
        scope_type = current.get("scope_type")
        if scope_type:
            attrs["scope_type"] = scope_type
        scope_value = current.get("scope_value")
        if scope_value:
            attrs["scope_value"] = scope_value

        # Direction.
        direction = current.get("direction")
        if direction:
            attrs["direction"] = direction

        # DNS-only flag.
        dns_only = current.get("dnsOnly")
        if dns_only is not None:
            attrs["dnsOnly"] = dns_only

        return attrs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_current_rule_data(self) -> dict[str, Any] | None:
        """Get current rule data from the coordinator."""
        if not self.coordinator.data or "rules" not in self.coordinator.data:
            return None
        return self.coordinator.data["rules"].get(self._rule_id)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the rule (resume it to make it active)."""
        current = self._get_current_rule_data()
        if not current:
            raise HomeAssistantError(f"Rule {self._rule_id} not found")

        if not current.get("paused", False):
            return

        success = await self.coordinator.async_resume_rule(self._rule_id)
        if not success:
            raise HomeAssistantError(f"Failed to resume rule {self._rule_id}")

        # Optimistic local update.
        rule = self.coordinator.data["rules"].get(self._rule_id)
        if rule:
            rule["paused"] = False
            rule["status"] = "active"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the rule (pause it while preserving configuration)."""
        current = self._get_current_rule_data()
        if not current:
            raise HomeAssistantError(f"Rule {self._rule_id} not found")

        if current.get("paused", False):
            return

        success = await self.coordinator.async_pause_rule(self._rule_id)
        if not success:
            raise HomeAssistantError(f"Failed to pause rule {self._rule_id}")

        # Optimistic local update.
        rule = self.coordinator.data["rules"].get(self._rule_id)
        if rule:
            rule["paused"] = True
            rule["status"] = "paused"
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug(
            "Rule switch entity added to hass: %s (%s)",
            self._rule_id,
            self._attr_name,
        )

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        _LOGGER.debug(
            "Rule switch entity being removed from hass: %s (%s)",
            self._rule_id,
            self._attr_name,
        )


# ---------------------------------------------------------------------------
# Group Internet Access Switch
# ---------------------------------------------------------------------------


class FirewallaGroupInternetSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to control internet access for a Firewalla group.

    ON = internet is allowed (block rule is paused).
    OFF = internet is blocked (block rule is active).
    """

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({
        "group_id", "is_user_group", "user_id", "device_count",
        "rule_count", "internet_block_rule_id",
    })

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        group = self._get_group_data()
        group_name = group["name"] if group else group_id
        self._attr_unique_id = f"firewalla_group_{group_id}_internet"
        self._attr_name = f"{group_name} Internet Access"
        self._attr_icon = "mdi:web"
        self._attr_device_info = self._build_device_info()

    def _get_group_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data or "groups" not in self.coordinator.data:
            return None
        return self.coordinator.data["groups"].get(self._group_id)

    def _build_device_info(self) -> DeviceInfo:
        group = self._get_group_data()
        group_name = group["name"] if group else self._group_id
        return DeviceInfo(
            identifiers={(DOMAIN, f"group_{self._group_id}")},
            name=f"Firewalla Group: {group_name}",
            manufacturer=DEVICE_MANUFACTURER,
            model="Group",
            via_device=(DOMAIN, self.coordinator.box_gid),
        )

    @property
    def is_on(self) -> bool:
        group = self._get_group_data()
        if not group:
            return False
        return not group.get("internet_blocked", False)

    @property
    def available(self) -> bool:
        group = self._get_group_data()
        return (
            self.coordinator.last_update_success
            and group is not None
            and group.get("internet_block_rule_id") is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        group = self._get_group_data()
        if not group:
            return {"group_id": self._group_id}
        return {
            "group_id": self._group_id,
            "group_name": group["name"],
            "is_user_group": group.get("is_user_group", False),
            "user_id": group.get("user_id"),
            "device_count": group.get("device_count", 0),
            "rule_count": group.get("rule_count", 0),
            "internet_block_rule_id": group.get("internet_block_rule_id"),
            "download": group.get("download", 0),
            "upload": group.get("upload", 0),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        group = self._get_group_data()
        if not group:
            raise HomeAssistantError(f"Group {self._group_id} not found")
        rule_id = group.get("internet_block_rule_id")
        if not rule_id:
            raise HomeAssistantError(f"No internet block rule for group {self._group_id}")
        success = await self.coordinator.async_pause_rule(rule_id)
        if not success:
            raise HomeAssistantError(f"Failed to allow internet for group {group['name']}")
        group["internet_blocked"] = False
        rule = self.coordinator.data.get("rules", {}).get(rule_id)
        if rule:
            rule["paused"] = True
            rule["status"] = "paused"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        group = self._get_group_data()
        if not group:
            raise HomeAssistantError(f"Group {self._group_id} not found")
        rule_id = group.get("internet_block_rule_id")
        if not rule_id:
            raise HomeAssistantError(f"No internet block rule for group {self._group_id}")
        success = await self.coordinator.async_resume_rule(rule_id)
        if not success:
            raise HomeAssistantError(f"Failed to block internet for group {group['name']}")
        group["internet_blocked"] = True
        rule = self.coordinator.data.get("rules", {}).get(rule_id)
        if rule:
            rule["paused"] = False
            rule["status"] = "active"
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Group Rule Switch (category/app blocks)
# ---------------------------------------------------------------------------


class FirewallaGroupRuleSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for a group-scoped block rule (category/app). ON=block active, OFF=block paused."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"group_id", "rule_id", "rule_type", "target_value", "hit_count"})

    def __init__(self, coordinator: FirewallaDataUpdateCoordinator, group_id: str, rule_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._rule_id = rule_id
        group = self._get_group_data()
        rule_info = self._get_rule_info()
        group_name = group["name"] if group else group_id
        target = (rule_info["value"] if rule_info else "unknown").title()
        self._attr_unique_id = f"firewalla_group_{group_id}_rule_{rule_id}"
        self._attr_name = f"{group_name} {target} Block"
        self._attr_icon = "mdi:shield-lock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_id}")},
            name=f"Firewalla Group: {group_name}",
            manufacturer=DEVICE_MANUFACTURER,
            model="Group",
            via_device=(DOMAIN, coordinator.box_gid),
        )

    def _get_group_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data or "groups" not in self.coordinator.data:
            return None
        return self.coordinator.data["groups"].get(self._group_id)

    def _get_rule_info(self) -> dict[str, Any] | None:
        group = self._get_group_data()
        if not group:
            return None
        return group.get("group_rules", {}).get(self._rule_id)

    @property
    def is_on(self) -> bool:
        rule_info = self._get_rule_info()
        if not rule_info:
            return False
        return not rule_info.get("paused", False)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_rule_info() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rule_info = self._get_rule_info()
        if not rule_info:
            return {"group_id": self._group_id, "rule_id": self._rule_id}
        return {
            "group_id": self._group_id,
            "rule_id": self._rule_id,
            "rule_type": rule_info.get("type", ""),
            "target_value": rule_info.get("value", ""),
            "action": rule_info.get("action", ""),
            "hit_count": rule_info.get("hit_count", 0),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate the block rule (resume it)."""
        rule_info = self._get_rule_info()
        if not rule_info:
            raise HomeAssistantError(f"Rule {self._rule_id} not found")
        success = await self.coordinator.async_resume_rule(self._rule_id)
        if not success:
            raise HomeAssistantError(f"Failed to resume rule {self._rule_id}")
        rule_info["paused"] = False
        rule_info["status"] = "active"
        rule = self.coordinator.data.get("rules", {}).get(self._rule_id)
        if rule:
            rule["paused"] = False
            rule["status"] = "active"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate the block rule (pause it)."""
        rule_info = self._get_rule_info()
        if not rule_info:
            raise HomeAssistantError(f"Rule {self._rule_id} not found")
        success = await self.coordinator.async_pause_rule(self._rule_id)
        if not success:
            raise HomeAssistantError(f"Failed to pause rule {self._rule_id}")
        rule_info["paused"] = True
        rule_info["status"] = "paused"
        rule = self.coordinator.data.get("rules", {}).get(self._rule_id)
        if rule:
            rule["paused"] = True
            rule["status"] = "paused"
        self.async_write_ha_state()
