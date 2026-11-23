"""Repair config entries that setup saved with a placeholder box gid (#24).

Before v1.2.1 the config flow saved the gid ``"default"`` instead of the real
gid from /v2/boxes. That gid is part of the box entities' unique_ids and of the
box device's identifier, so it is repaired in the registries, in place.

This runs from ``async_setup_entry`` rather than ``async_migrate_entry``:
raising ConfigEntryNotReady from a migration (to retry when the API is down)
is only supported on recent Home Assistant releases, and this integration
supports older ones.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_BOX_GID,
    CONF_BOX_MODEL,
    CONF_BOX_NAME,
    CONF_PENDING_BOX_GID,
    DOMAIN,
    ENTITY_ID_FORMATS,
    LEGACY_BOX_GID,
    LEGACY_BOX_TITLE,
)
from .coordinator import FirewallaMSPClient, box_display_name, boxes_by_gid

_LOGGER = logging.getLogger(__name__)

_LEGACY_REFRESH_UID = f"firewalla_{LEGACY_BOX_GID}_refresh"
_LEGACY_BOX_UID_PREFIX = f"firewalla_box_{LEGACY_BOX_GID}_"


def _repaired_unique_id(unique_id: str, box_gid: str) -> str | None:
    """The unique_id an entity of the placeholder box has on the real box.

    None for unique_ids that don't contain the box gid (rules, groups, devices,
    time limits and the rules summary).
    """
    if unique_id == _LEGACY_REFRESH_UID:
        return f"firewalla_{box_gid}_refresh"
    if unique_id.startswith(_LEGACY_BOX_UID_PREFIX):
        return f"firewalla_box_{box_gid}_{unique_id[len(_LEGACY_BOX_UID_PREFIX):]}"
    return None


# The box entities' unique_ids are firewalla_box_<gid>_<key>, by domain.
_BOX_ENTITY_KEYS = {
    "binary_sensor": ("online",),
    "sensor": (
        "public_ip",
        "total_devices",
        "online_devices",
        "alarms",
        "firmware",
        "blocked_flows",
    ),
}


def _root_device_id(ent_reg: er.EntityRegistry, entry: ConfigEntry) -> str | None:
    """The entry's box device: the one its rules summary sensor is on."""
    entity_id = ent_reg.async_get_entity_id(
        "sensor", DOMAIN, ENTITY_ID_FORMATS["rules_sensor"]
    )
    entity = ent_reg.async_get(entity_id) if entity_id else None
    if entity is None or entity.config_entry_id != entry.entry_id:
        return None
    return entity.device_id


def _box_entity_gid(entity: er.RegistryEntry, root_device_id: str | None) -> str | None:
    """The gid in a box entity's unique_id; None for any other entity."""
    unique_id = entity.unique_id
    for key in _BOX_ENTITY_KEYS.get(entity.domain, ()):
        prefix, suffix = "firewalla_box_", f"_{key}"
        if unique_id.startswith(prefix) and unique_id.endswith(suffix):
            return unique_id[len(prefix) : -len(suffix)] or None
    # Only the refresh button on the box device: other *_refresh are not it.
    if (
        entity.domain == "button"
        and root_device_id is not None
        and entity.device_id == root_device_id
        and unique_id.startswith("firewalla_")
        and unique_id.endswith("_refresh")
    ):
        return unique_id[len("firewalla_") : -len("_refresh")] or None
    return None


def partially_repaired(
    ent_reg: er.EntityRegistry, dev_reg: dr.DeviceRegistry, entry: ConfigEntry
) -> bool:
    """Whether an interrupted repair left this entry's records on a real gid.

    A placeholder entry never creates them otherwise: its box entities and box
    device all carry the placeholder gid. Only records known to belong to the
    box count, so records a later release adds can't make an untouched entry
    look half-repaired. Moved records are found with or without a saved
    target, so a missing target can't lead to loading on the placeholder.
    """
    pinned = entry.data.get(CONF_PENDING_BOX_GID)
    root_device_id = _root_device_id(ent_reg, entry)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        gid = _box_entity_gid(entity, root_device_id)
        if gid is not None and gid != LEGACY_BOX_GID:
            return True
        if (
            pinned
            and entity.domain == "button"
            and entity.unique_id == f"firewalla_{pinned}_refresh"
        ):
            return True
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        gids = {ident for domain, ident in device.identifiers if domain == DOMAIN}
        if pinned and pinned in gids:
            return True
        if device.id == root_device_id and gids and LEGACY_BOX_GID not in gids:
            return True
    return False


async def async_repair_legacy_box_identity(
    hass: HomeAssistant, entry: ConfigEntry, client: FirewallaMSPClient
) -> None:
    """Move an entry saved with the placeholder gid onto its real box.

    The box is the one chosen in Reconfigure, else the account's only box,
    which must then be the one the entry was set up for. A multi-box account
    without a choice is left alone. Entity and device records are updated
    rather than recreated, so entity_ids, device ids, user customizations and
    child-device links survive.

    Until the first registry record moves, anything unexpected changes
    nothing: the entry keeps running on the placeholder (rules, groups and
    devices work; the box status entities stay unavailable), and the repair is
    tried again at the next setup. The target box is saved in the entry before
    the first move, so an interrupted repair is finished on that same box at
    the next setup, without needing /v2/boxes. Until it can be finished, setup
    is retried: the platforms never load on a half-moved entry.
    """
    if entry.data.get(CONF_BOX_GID) != LEGACY_BOX_GID:
        return

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    pinned = entry.data.get(CONF_PENDING_BOX_GID)
    resuming = partially_repaired(ent_reg, dev_reg, entry)

    if resuming:
        if not pinned:
            # Not loaded on the placeholder (that would duplicate the moved
            # entities) and not guessed; Reconfigure explains what to do.
            raise ConfigEntryNotReady(
                "An interrupted box identity repair (#24) moved records but its "
                "target box was not saved. Open Reconfigure on this entry for "
                "what to do"
            )
        box_gid = pinned
        record = {
            "name": entry.data.get(CONF_BOX_NAME),
            "model": entry.data.get(CONF_BOX_MODEL),
        }
    else:
        try:
            boxes = boxes_by_gid(await client.get_boxes())
        except Exception as err:  # noqa: BLE001 — never block setup over this
            _LOGGER.warning(
                "Could not list Firewalla boxes to repair this entry's box "
                "identity (#24); box status stays unavailable until it is retried "
                "at the next start: %s",
                err,
            )
            return
        if pinned:
            if pinned not in boxes:
                _LOGGER.warning(
                    "The Firewalla box chosen in Reconfigure is not in this "
                    "account's /v2/boxes; nothing was changed. Choose it again in "
                    "Reconfigure"
                )
                return
            box_gid = pinned
        elif len(boxes) == 1:
            box_gid = next(iter(boxes))
        else:
            _LOGGER.warning(
                "This Firewalla entry was set up before v1.2.1 without its box's "
                "id (#24), and the account has %d boxes. Rules, groups and devices "
                "keep working; to load the box status entities, choose the box in "
                "Settings > Devices & services > Firewalla > Reconfigure",
                len(boxes),
            )
            return
        record = boxes[box_gid]

    collisions: list[str] = []
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == box_gid:
            collisions.append(f"config entry {other.entry_id} already has the box")

    entity_moves: dict[str, str] = {}
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        new_unique_id = _repaired_unique_id(entity.unique_id, box_gid)
        if new_unique_id is None:
            continue
        existing = ent_reg.async_get_entity_id(entity.domain, DOMAIN, new_unique_id)
        if existing is not None:
            collisions.append(f"{existing} already has unique_id {new_unique_id}")
        entity_moves[entity.entity_id] = new_unique_id

    # Only a device this entry alone owns may be moved, or (after an
    # interrupted repair) already sit on the real gid.
    only_this_entry = {entry.entry_id}
    legacy_device = dev_reg.async_get_device(identifiers={(DOMAIN, LEGACY_BOX_GID)})
    real_device = dev_reg.async_get_device(identifiers={(DOMAIN, box_gid)})
    if legacy_device is not None and legacy_device.config_entries != only_this_entry:
        collisions.append(f"device {legacy_device.id} is shared with another entry")
    if real_device is not None and (
        legacy_device is not None or real_device.config_entries != only_this_entry
    ):
        collisions.append(f"device {real_device.id} already has the box")

    if collisions:
        message = (
            "Not repairing this Firewalla entry's box identity (#24): "
            + "; ".join(collisions)
        )
        if resuming:
            # Records already moved: loading on the placeholder would duplicate.
            raise ConfigEntryNotReady(message)
        _LOGGER.warning(
            "%s. Nothing was changed; box status stays unavailable", message
        )
        return

    box_name = box_display_name(record)
    box_model = record.get("model")
    metadata: dict[str, Any] = {CONF_BOX_NAME: box_name}
    if isinstance(box_model, str) and box_model:
        metadata[CONF_BOX_MODEL] = box_model
    data: dict[str, Any] = {**entry.data, **metadata, CONF_BOX_GID: box_gid}
    data.pop(CONF_PENDING_BOX_GID, None)

    try:
        if not resuming:
            # Pin the target before the first move, so a retry finishes it.
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, **metadata, CONF_PENDING_BOX_GID: box_gid},
            )
        for entity_id, new_unique_id in entity_moves.items():
            ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)
        if legacy_device is not None:
            dev_reg.async_update_device(
                legacy_device.id,
                new_identifiers=(legacy_device.identifiers - {(DOMAIN, LEGACY_BOX_GID)})
                | {(DOMAIN, box_gid)},
            )
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            unique_id=box_gid,
            # Keep a title the user chose; replace only the placeholder's.
            title=box_name if entry.title == LEGACY_BOX_TITLE else entry.title,
        )
    except Exception as err:
        # Part of the repair may be done. Setting up the platforms now would
        # recreate the moved entities under the placeholder gid, so retry the
        # whole setup instead: the retry finishes the pinned target.
        raise ConfigEntryNotReady(
            f"Interrupted while repairing the box identity (#24): {err}"
        ) from err
    _LOGGER.info(
        "Repaired this Firewalla entry's box identity (#24): %d entities and "
        "the box device now use the real box id",
        len(entity_moves),
    )
