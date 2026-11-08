"""Device groups (no matching user) get the same entities as user groups (#11).

These drive each platform's coordinator listener, with groups built by the real
``_build_groups`` and HA's real entity/device registries.
"""

from unittest.mock import MagicMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla import binary_sensor, sensor
from custom_components.firewalla.const import DOMAIN
from custom_components.firewalla.coordinator import (
    FirewallaDataUpdateCoordinator,
    _build_groups,
)

USERS = [{"id": "box:29", "name": "Alice", "affiliatedTag": "28"}]


def _device(mac, gid, gname, online=True, down=0, up=0):
    return {
        "id": mac,
        "name": f"Device {mac}",
        "online": online,
        "totalDownload": down,
        "totalUpload": up,
        "group": {"id": gid, "name": gname},
    }


def _devices(cameras_group="25"):
    return [
        _device("AA:AA:AA:AA:AA:01", "28", "Alice"),  # user group
        _device("BB:BB:BB:BB:BB:01", cameras_group, "Cameras", down=3 * 1024**3),
        _device(
            "BB:BB:BB:BB:BB:02", "25", "Cameras", online=False, down=1024**3, up=1024**3
        ),
    ]


class _Platform:
    """Runs one platform's async_setup_entry and replays coordinator polls."""

    def __init__(self, hass, module, devices):
        self.hass = hass
        self.module = module
        self.entry = MockConfigEntry(domain=DOMAIN, data={})
        self.entry.add_to_hass(hass)
        self.coordinator = MagicMock(spec=FirewallaDataUpdateCoordinator)
        self.coordinator.box_gid = "box-gid"
        self.coordinator.last_update_success = True
        self.coordinator.data = {"groups": _build_groups(devices, USERS, {})}
        self.listeners = []
        self.coordinator.async_add_listener.side_effect = (
            lambda cb: self.listeners.append(cb) or (lambda: None)
        )
        self.added = []
        hass.data.setdefault(DOMAIN, {})[self.entry.entry_id] = self.coordinator

    async def setup(self):
        await self.module.async_setup_entry(
            self.hass, self.entry, lambda ents: self.added.extend(ents)
        )

    def poll(self, devices):
        self.coordinator.data = {"groups": _build_groups(devices, USERS, {})}
        for cb in self.listeners:
            cb()

    def unique_ids(self):
        return {e.unique_id for e in self.added}


async def test_binary_sensors_for_user_and_device_groups(hass):
    platform = _Platform(hass, binary_sensor, _devices())
    await platform.setup()

    # User group: the same unique IDs as before this change.
    # Device group "25" (no matching user): the same patterns.
    assert platform.unique_ids() == {
        "firewalla_user_28_active",
        "firewalla_device_AA_AA_AA_AA_AA_01",
        "firewalla_user_25_active",
        "firewalla_device_BB_BB_BB_BB_BB_01",
        "firewalla_device_BB_BB_BB_BB_BB_02",
        "firewalla_box_box-gid_online",  # box status (#13), not per group
    }
    by_id = {e.unique_id: e for e in platform.added}
    assert by_id["firewalla_device_BB_BB_BB_BB_BB_01"].is_on is True
    assert by_id["firewalla_device_BB_BB_BB_BB_BB_02"].is_on is False
    assert by_id["firewalla_device_BB_BB_BB_BB_BB_01"].device_info["identifiers"] == {
        (DOMAIN, "group_25")
    }
    assert by_id["firewalla_user_25_active"].extra_state_attributes[
        "total_devices"
    ] == 2

    # A second poll with the same data adds nothing.
    platform.poll(_devices())
    assert len(platform.added) == 6


async def test_bandwidth_sensors_for_user_and_device_groups(hass):
    platform = _Platform(hass, sensor, _devices())
    await platform.setup()

    bw = {
        e.unique_id: e
        for e in platform.added
        if isinstance(e, sensor.FirewallaBandwidthSensor)
    }
    assert set(bw) == {
        "firewalla_group_28_download",
        "firewalla_group_28_upload",
        "firewalla_group_25_download",
        "firewalla_group_25_upload",
    }
    # Device group value: sum of its devices' 24h totalDownload/totalUpload.
    assert bw["firewalla_group_25_download"].native_value == 4.0
    assert bw["firewalla_group_25_upload"].native_value == 1.0


async def test_group_that_disappears_is_removed(hass):
    platform = _Platform(hass, binary_sensor, _devices())
    await platform.setup()
    ent_reg = er.async_get(hass)
    for e in platform.added:
        ent_reg.async_get_or_create(
            "binary_sensor", DOMAIN, e.unique_id, config_entry=platform.entry
        )

    platform.poll([d for d in _devices() if d["group"]["id"] != "25"])

    remaining = {
        e.unique_id for e in ent_reg.entities.values() if e.platform == DOMAIN
    }
    assert remaining == {
        "firewalla_user_28_active",
        "firewalla_device_AA_AA_AA_AA_AA_01",
        "firewalla_box_box-gid_online",
    }


@pytest.fixture
def registries(hass):
    return er.async_get(hass), dr.async_get(hass)


def _group_device(dev_reg, entry, gid):
    return dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"group_{gid}")}
    )


async def test_device_moving_between_groups_keeps_its_entity(hass, registries):
    ent_reg, dev_reg = registries
    platform = _Platform(hass, binary_sensor, _devices())
    await platform.setup()
    cameras = _group_device(dev_reg, platform.entry, "25")
    alice = _group_device(dev_reg, platform.entry, "28")
    entry = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "firewalla_device_BB_BB_BB_BB_BB_01",
        config_entry=platform.entry,
        device_id=cameras.id,
    )
    sensor_entity = next(
        e for e in platform.added if e.unique_id == entry.unique_id
    )
    added_before = len(platform.added)

    # BB:..:01 moves from the device group to Alice's user group.
    platform.poll(_devices(cameras_group="28"))

    moved = ent_reg.async_get(entry.entity_id)
    assert moved is not None  # same entity_id, not removed and re-created
    assert moved.device_id == alice.id
    assert len(platform.added) == added_before
    assert sensor_entity.available is True
    assert sensor_entity.is_on is True


async def test_device_moving_to_group_without_ha_device_yet_retries(hass, registries):
    ent_reg, dev_reg = registries
    platform = _Platform(hass, binary_sensor, _devices())
    await platform.setup()
    cameras = _group_device(dev_reg, platform.entry, "25")
    entry = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "firewalla_device_BB_BB_BB_BB_BB_01",
        config_entry=platform.entry,
        device_id=cameras.id,
    )

    # Moves to a group seen for the first time; its HA device doesn't exist yet.
    platform.poll(_devices(cameras_group="40"))
    assert ent_reg.async_get(entry.entity_id).device_id == cameras.id
    assert "firewalla_user_40_active" in platform.unique_ids()

    new_group = _group_device(dev_reg, platform.entry, "40")
    platform.poll(_devices(cameras_group="40"))
    assert ent_reg.async_get(entry.entity_id).device_id == new_group.id
