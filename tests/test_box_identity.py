"""Real box identity (#24): discovery in the config flow, the in-place repair of
entries saved with the placeholder gid, and Reconfigure.

The MSP API is mocked only at the HTTP layer; config flow, client, coordinator,
platforms and the HA registries all run for real.
"""

import logging
from unittest.mock import patch

import pytest
from aioresponses import CallbackResult
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_BOX_MODEL,
    CONF_BOX_NAME,
    CONF_MSP_URL,
    CONF_PENDING_BOX_GID,
    DOMAIN,
    LEGACY_BOX_GID,
    LEGACY_BOX_TITLE,
)
from tests.test_issue_24_regression import (  # noqa: F401 — fixtures
    BASE,
    BOX,
    BOX_RECORD,
    DOMAIN_NAME,
    TOKEN,
    _box_entity_id,
    api,
    auto_enable_custom_integrations,
    session,
)

OTHER = "9d41b2c0-other-box-gid"
OTHER_RECORD = {**BOX_RECORD, "gid": OTHER, "name": "Cabin", "model": "purple"}
# Unique_id suffixes of the box entities a v1.2.0 install has (blocked_flows is
# only created once the box count is known to be 1, so a legacy entry never had it).
LEGACY_BOX_KEYS = (
    "online",
    "public_ip",
    "firmware",
    "total_devices",
    "online_devices",
    "alarms",
)


# ---------------------------------------------------------------------------
# Helpers for the discovery and upgrade tests
# ---------------------------------------------------------------------------


class BoxesEndpoint:
    """/v2/boxes whose answer a test can change between setups."""

    def __init__(self, api, payload, status=200):
        self.payload = payload
        self.status = status
        api.get(f"{BASE}/boxes", callback=self, repeat=True)

    def __call__(self, url, **kwargs):
        if self.status != 200:
            return CallbackResult(status=self.status, body="unavailable")
        return CallbackResult(status=200, payload=self.payload)


@pytest.fixture
def no_setup():
    """Config-flow-only tests: don't set up the entry the flow creates."""
    with patch("custom_components.firewalla.async_setup_entry", return_value=True):
        yield


def _add_entry(hass, gid, title, unique_id=None, msp=DOMAIN_NAME, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=gid if unique_id is None else unique_id,
        data={CONF_MSP_URL: msp, CONF_ACCESS_TOKEN: TOKEN, CONF_BOX_GID: gid, **data},
    )
    entry.add_to_hass(hass)
    return entry


def _legacy_entry(hass, **kwargs):
    """A config entry exactly as v1.2.0 setup saved it."""
    return _add_entry(hass, LEGACY_BOX_GID, LEGACY_BOX_TITLE, **kwargs)


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _unload(hass, entry):
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def _install_v120(hass, api):
    """A loaded legacy entry with the registry records a v1.2.0 install has.

    /v2/boxes is down for this first setup, so the repair can't run and the
    platforms register their entities under the placeholder gid, as v1.2.0 did.
    """
    boxes = BoxesEndpoint(api, [BOX_RECORD], status=500)
    entry = _legacy_entry(hass)
    await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == LEGACY_BOX_GID  # nothing changed
    return entry, boxes


def _uid_to_entity_id(hass):
    return {
        e.unique_id: e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.platform == DOMAIN
    }


def _snapshot(hass, *entries):
    """Everything the repair could change, for before/after comparisons."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    return (
        [(dict(e.data), e.unique_id, e.title) for e in entries],
        sorted(
            (e.entity_id, e.unique_id, e.device_id, e.name, e.config_entry_id)
            for e in ent_reg.entities.values()
        ),
        sorted(
            (
                d.id,
                tuple(sorted(d.identifiers)),
                d.name,
                d.name_by_user,
                d.via_device_id,
                tuple(sorted(d.config_entries)),
            )
            for d in dev_reg.devices.values()
        ),
    )


# ---------------------------------------------------------------------------
# New setup: discovery from /v2/boxes
# ---------------------------------------------------------------------------


async def _submit_credentials(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MSP_URL: DOMAIN_NAME, CONF_ACCESS_TOKEN: TOKEN}
    )


async def test_new_setup_saves_real_box_metadata(hass, api):
    BoxesEndpoint(api, [BOX_RECORD])
    result = await _submit_credentials(hass)
    await hass.async_block_till_done()

    entry = result["result"]
    assert entry.title == "Home"
    assert entry.data[CONF_BOX_NAME] == "Home"
    assert entry.data[CONF_BOX_MODEL] == "gold_pro"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, BOX)})
    assert device.name == "Home"
    assert device.model == "Firewalla Gold Pro"
    assert device.sw_version == "1.982"
    # New installs name box entities after the real box.
    assert _box_entity_id(hass, "online") == "binary_sensor.home_online"
    await _unload(hass, entry)


@pytest.mark.parametrize(
    "payload",
    [[], {"results": [BOX_RECORD]}, [None, "box", {"gid": ""}, {"name": "no gid"}]],
    ids=["empty", "not-a-list", "no-usable-records"],
)
async def test_new_setup_without_usable_boxes(hass, api, no_setup, payload):
    BoxesEndpoint(api, payload)
    result = await _submit_credentials(hass)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "no_boxes"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_new_setup_skips_malformed_and_repeated_records(hass, api, no_setup):
    BoxesEndpoint(
        api,
        [
            None,
            {"gid": ""},
            {"name": "no gid"},
            BOX_RECORD,
            {**BOX_RECORD, "name": "Dup"},
        ],
    )
    result = await _submit_credentials(hass)
    assert result["type"] == "create_entry"
    assert result["data"][CONF_BOX_GID] == BOX
    assert result["title"] == "Home"


@pytest.mark.parametrize(
    ("status", "error"),
    [(500, "connection_failed"), (401, "auth_failed"), (403, "auth_failed")],
)
async def test_new_setup_boxes_api_failure(hass, api, no_setup, status, error):
    BoxesEndpoint(api, [BOX_RECORD], status=status)
    result = await _submit_credentials(hass)
    assert result["type"] == "form"
    assert result["errors"] == {"base": error}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_new_setup_multiple_boxes_asks(hass, api, no_setup):
    BoxesEndpoint(api, [BOX_RECORD, OTHER_RECORD])
    result = await _submit_credentials(hass)
    assert result["type"] == "form"
    assert result["step_id"] == "box_selection"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOX_GID: OTHER}
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Cabin"
    assert result["data"][CONF_BOX_GID] == OTHER
    assert result["result"].unique_id == OTHER


async def test_new_setup_same_box_twice_aborts(hass, api, no_setup):
    BoxesEndpoint(api, [BOX_RECORD])
    _add_entry(hass, BOX, "Home")
    result = await _submit_credentials(hass)
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_new_setup_aborts_while_legacy_entry_for_account_exists(
    hass, api, no_setup
):
    """The legacy entry may be this box; setup repairs it, so don't duplicate."""
    BoxesEndpoint(api, [BOX_RECORD])
    _legacy_entry(hass, msp=f"https://{DOMAIN_NAME}/")
    result = await _submit_credentials(hass)
    assert result["type"] == "abort"
    # Its own reason, not already_configured: on a multi-box account the user
    # is adding another box and must choose the legacy entry's box first.
    assert result["reason"] == "legacy_entry_needs_box"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_new_setup_ignores_legacy_entry_of_another_account(hass, api, no_setup):
    BoxesEndpoint(api, [BOX_RECORD])
    _legacy_entry(hass, msp="elsewhere.firewalla.net")
    result = await _submit_credentials(hass)
    assert result["type"] == "create_entry"
    assert result["data"][CONF_BOX_GID] == BOX


# ---------------------------------------------------------------------------
# Upgrade: legacy entries are repaired in place
# ---------------------------------------------------------------------------


async def test_upgrade_repairs_in_place_and_keeps_customizations(hass, api):
    entry, boxes = await _install_v120(hass, api)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    before = _uid_to_entity_id(hass)
    legacy_uids = {"firewalla_default_refresh"} | {
        f"firewalla_box_default_{k}" for k in LEGACY_BOX_KEYS
    }
    assert legacy_uids <= set(before)
    online_id = before["firewalla_box_default_online"]
    assert online_id == "binary_sensor.firewalla_box_default_online"
    assert hass.states.get(online_id).state == "unavailable"  # the bug

    # What a user may have done to the v1.2.0 records.
    box_device = dev_reg.async_get_device(identifiers={(DOMAIN, LEGACY_BOX_GID)})
    assert box_device.name == "Firewalla Box default"
    dev_reg.async_update_device(box_device.id, name_by_user="Router")
    ent_reg.async_update_entity(online_id, name="WAN up")
    ent_reg.async_update_entity(
        before["firewalla_box_default_public_ip"], new_entity_id="sensor.my_public_ip"
    )
    group_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "group_7")},
        name="Kids",
        via_device=(DOMAIN, LEGACY_BOX_GID),
    )
    assert group_device.via_device_id == box_device.id
    before = _uid_to_entity_id(hass)  # with the user's entity_id change
    entity_count = len(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
    await _unload(hass, entry)

    boxes.status = 200
    await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    assert entry.data[CONF_BOX_NAME] == "Home"
    assert entry.unique_id == BOX
    assert entry.title == "Home"

    after = _uid_to_entity_id(hass)
    # Same entity_ids (and so history), now under the real gid.
    assert after["firewalla_box_" + BOX + "_online"] == online_id
    assert after[f"firewalla_box_{BOX}_public_ip"] == "sensor.my_public_ip"
    assert after[f"firewalla_{BOX}_refresh"] == before["firewalla_default_refresh"]
    for key in LEGACY_BOX_KEYS:
        assert (
            after[f"firewalla_box_{BOX}_{key}"]
            == before[f"firewalla_box_default_{key}"]
        )
    assert not legacy_uids & set(after)
    # Unrelated entities are untouched; only blocked_flows is new.
    assert after["firewalla_rules_summary"] == before["firewalla_rules_summary"]
    assert set(after) - {f"firewalla_box_{BOX}_{k}" for k in LEGACY_BOX_KEYS} - {
        f"firewalla_{BOX}_refresh"
    } == (set(before) - legacy_uids) | {f"firewalla_box_{BOX}_blocked_flows"}
    assert (
        len(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
        == entity_count + 1
    )

    # Same device record: id, user name and the group's link survive.
    assert dev_reg.async_get_device(identifiers={(DOMAIN, LEGACY_BOX_GID)}) is None
    repaired = dev_reg.async_get_device(identifiers={(DOMAIN, BOX)})
    assert repaired.id == box_device.id
    assert repaired.name_by_user == "Router"
    assert repaired.name == "Home"
    assert repaired.model == "Firewalla Gold Pro"
    assert dev_reg.async_get(group_device.id).via_device_id == box_device.id
    assert ent_reg.async_get(online_id).name == "WAN up"
    assert ent_reg.async_get(online_id).device_id == box_device.id

    # And the box statistics load.
    assert hass.states.get(online_id).state == "on"
    assert hass.states.get("sensor.my_public_ip").state == "203.0.113.7"

    # Idempotent: further setups change nothing.
    snapshot = _snapshot(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _snapshot(hass, entry) == snapshot
    await _unload(hass, entry)


def _collide_entry(hass):
    _add_entry(hass, BOX, "Home")


def _collide_entity(hass):
    er.async_get(hass).async_get_or_create(
        "binary_sensor", DOMAIN, f"firewalla_box_{BOX}_online"
    )


def _collide_device(hass):
    other = MockConfigEntry(domain="other_integration")
    other.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={(DOMAIN, BOX)}
    )


def _share_legacy_device(hass):
    """Another entry also owns the placeholder box device (found in review)."""
    other = MockConfigEntry(domain="other_integration")
    other.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={(DOMAIN, LEGACY_BOX_GID)}
    )


@pytest.mark.parametrize(
    "collide",
    [_collide_entry, _collide_entity, _collide_device, _share_legacy_device],
    ids=["entry", "entity", "device", "shared-legacy-device"],
)
async def test_upgrade_collision_changes_nothing(hass, api, caplog, collide):
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    collide(hass)
    before = _snapshot(hass, entry)

    boxes.status = 200
    with caplog.at_level(logging.WARNING):
        await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED  # rules still load
    assert _snapshot(hass, entry) == before
    assert "Not repairing this Firewalla entry's box identity" in caplog.text
    online = _uid_to_entity_id(hass)["firewalla_box_default_online"]
    assert hass.states.get(online).state == "unavailable"
    await _unload(hass, entry)


@pytest.mark.parametrize(
    "payload", [[], [BOX_RECORD, OTHER_RECORD]], ids=["no-boxes", "two-boxes"]
)
async def test_upgrade_without_single_box_changes_nothing(hass, api, caplog, payload):
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    before = _snapshot(hass, entry)

    boxes.payload, boxes.status = payload, 200
    with caplog.at_level(logging.WARNING):
        await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert _snapshot(hass, entry) == before
    assert f"the account has {len(payload)} boxes" in caplog.text
    await _unload(hass, entry)


async def test_upgrade_never_adopts_a_foreign_device(hass, api):
    """No placeholder device to move, but another owner's device has the real
    gid: the entry must not attach itself to it (found in review)."""
    entry = _legacy_entry(hass)
    foreign = MockConfigEntry(domain="other_integration")
    foreign.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    target = dev_reg.async_get_or_create(
        config_entry_id=foreign.entry_id, identifiers={(DOMAIN, BOX)}, name="Foreign"
    )
    BoxesEndpoint(api, [BOX_RECORD])

    await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == LEGACY_BOX_GID
    assert dev_reg.async_get(target.id).config_entries == {foreign.entry_id}
    await _unload(hass, entry)


async def test_upgrade_interrupted_then_retried(hass, api):
    """A repair stopped part-way retries setup and never duplicates entities."""
    entry, boxes = await _install_v120(hass, api)
    before = _uid_to_entity_id(hass)
    await _unload(hass, entry)
    boxes.status = 200

    real_update = hass.config_entries.async_update_entry

    def fail_on_repair(entry_, **kwargs):
        if kwargs.get("unique_id") == BOX:
            raise RuntimeError("interrupted")
        return real_update(entry_, **kwargs)

    with patch.object(hass.config_entries, "async_update_entry", fail_on_repair):
        await _setup(hass, entry)
    # Entities and device moved, entry not: setup must retry, not load.
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert entry.data[CONF_BOX_GID] == LEGACY_BOX_GID
    assert "firewalla_box_default_online" not in _uid_to_entity_id(hass)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    after = _uid_to_entity_id(hass)
    assert (
        after[f"firewalla_box_{BOX}_online"] == before["firewalla_box_default_online"]
    )
    assert not any("_default_" in uid for uid in after)
    assert len(after) == len(set(after.values()))  # no duplicate records
    assert hass.states.get(before["firewalla_box_default_online"]).state == "on"
    await _unload(hass, entry)


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ([BOX_RECORD], 500),  # found in review: 8 registry entities became 15
        ([], 200),
        ([OTHER_RECORD], 200),  # the account's one box changed
        ([BOX_RECORD, OTHER_RECORD], 200),  # no longer a one-box account
    ],
    ids=["boxes-api-down", "no-boxes", "changed-box", "two-boxes"],
)
async def test_upgrade_interrupted_retry_finishes_pinned_box(
    hass, api, payload, status
):
    """Once a repair has moved records, a retry finishes that same box, whatever
    /v2/boxes says now; it never loads the placeholder platforms, which would
    duplicate the moved entities."""
    entry, boxes = await _install_v120(hass, api)
    before = _uid_to_entity_id(hass)
    await _unload(hass, entry)
    boxes.status = 200

    real_update = hass.config_entries.async_update_entry

    def fail_on_repair(entry_, **kwargs):
        if kwargs.get("unique_id") == BOX:
            raise RuntimeError("interrupted")
        return real_update(entry_, **kwargs)

    with patch.object(hass.config_entries, "async_update_entry", fail_on_repair):
        await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert entry.data[CONF_PENDING_BOX_GID] == BOX  # pinned before any move

    boxes.payload, boxes.status = payload, status
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    assert entry.unique_id == BOX
    assert entry.data[CONF_BOX_NAME] == "Home"
    assert CONF_PENDING_BOX_GID not in entry.data
    after = _uid_to_entity_id(hass)
    assert not any("_default_" in uid for uid in after)
    assert not any(OTHER in uid for uid in after)
    for key in LEGACY_BOX_KEYS:
        assert (
            after[f"firewalla_box_{BOX}_{key}"]
            == before[f"firewalla_box_default_{key}"]
        )
    assert len(after) <= len(before) + 1  # at most + blocked_flows; no duplicates
    assert len(set(after.values())) == len(after)
    await _unload(hass, entry)


@pytest.mark.parametrize(
    ("payload", "status"),
    [([BOX_RECORD], 500), ([BOX_RECORD, OTHER_RECORD], 200)],
    ids=["boxes-api-down", "two-boxes"],
)
async def test_upgrade_interrupted_mid_entity_moves(hass, api, payload, status):
    """Interrupted at the third entity move (found in QA): the retry finishes
    the rest on the pinned box and nothing is duplicated."""
    entry, boxes = await _install_v120(hass, api)
    before = _uid_to_entity_id(hass)
    await _unload(hass, entry)
    boxes.status = 200

    ent_reg = er.async_get(hass)
    real_update_entity = ent_reg.async_update_entity
    moves = 0

    def fail_third_move(entity_id, **kwargs):
        nonlocal moves
        if "new_unique_id" in kwargs:
            moves += 1
            if moves == 3:
                raise RuntimeError("interrupted")
        return real_update_entity(entity_id, **kwargs)

    with patch.object(ent_reg, "async_update_entity", fail_third_move):
        await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert moves == 3

    boxes.payload, boxes.status = payload, status
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    after = _uid_to_entity_id(hass)
    assert not any("_default_" in uid for uid in after)
    for key in LEGACY_BOX_KEYS:
        assert (
            after[f"firewalla_box_{BOX}_{key}"]
            == before[f"firewalla_box_default_{key}"]
        )
    assert len(set(after.values())) == len(after) <= len(before) + 1
    await _unload(hass, entry)


async def test_upgrade_interrupted_retry_waits_on_collision(hass, api):
    """A collision that appears after records moved: retry, never load."""
    entry, boxes = await _install_v120(hass, api)
    count = len(_uid_to_entity_id(hass))
    await _unload(hass, entry)
    boxes.status = 200

    real_update = hass.config_entries.async_update_entry

    def fail_on_repair(entry_, **kwargs):
        if kwargs.get("unique_id") == BOX:
            raise RuntimeError("interrupted")
        return real_update(entry_, **kwargs)

    with patch.object(hass.config_entries, "async_update_entry", fail_on_repair):
        await _setup(hass, entry)
    _collide_entry(hass)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert entry.data[CONF_BOX_GID] == LEGACY_BOX_GID
    assert len(_uid_to_entity_id(hass)) == count
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Reconfigure
# ---------------------------------------------------------------------------


async def _reconfigure(hass, entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["step_id"] == "reconfigure"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MSP_URL: DOMAIN_NAME, CONF_ACCESS_TOKEN: TOKEN}
    )


async def test_multibox_legacy_entry_box_chosen_in_reconfigure(hass, api):
    """Option 1 (approved): a multi-box legacy entry waits for an explicit choice."""
    entry, boxes = await _install_v120(hass, api)
    before = _uid_to_entity_id(hass)
    device_id = (
        dr.async_get(hass).async_get_device(identifiers={(DOMAIN, LEGACY_BOX_GID)}).id
    )
    boxes.payload, boxes.status = [BOX_RECORD, OTHER_RECORD], 200

    result = await _reconfigure(hass, entry)
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure_box"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOX_GID: OTHER}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()  # the reload runs the repair

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == OTHER
    assert entry.unique_id == OTHER
    assert entry.title == "Cabin"
    assert CONF_PENDING_BOX_GID not in entry.data
    after = _uid_to_entity_id(hass)
    for key in LEGACY_BOX_KEYS:
        assert (
            after[f"firewalla_box_{OTHER}_{key}"]
            == before[f"firewalla_box_default_{key}"]
        )
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, OTHER)})
    assert device.id == device_id
    assert hass.states.get(before["firewalla_box_default_online"]).state == "on"
    await _unload(hass, entry)


async def test_multibox_reconfigure_refuses_box_with_own_entry(hass, api):
    entry, boxes = await _install_v120(hass, api)
    _add_entry(hass, BOX, "Home")
    boxes.payload, boxes.status = [BOX_RECORD, OTHER_RECORD], 200

    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOX_GID: BOX}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "box_already_configured"}
    assert entry.data[CONF_BOX_GID] == LEGACY_BOX_GID
    assert CONF_PENDING_BOX_GID not in entry.data
    await _unload(hass, entry)


async def test_reconfigure_keeps_real_box(hass, api):
    BoxesEndpoint(api, [BOX_RECORD])
    entry = _add_entry(hass, BOX, "Home", **{CONF_BOX_NAME: "Home"})
    await _setup(hass, entry)

    result = await _reconfigure(hass, entry)
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_BOX_GID] == BOX
    assert entry.data[CONF_BOX_NAME] == "Home"
    await _unload(hass, entry)


async def test_reconfigure_rejects_account_without_the_box(hass, api, no_setup):
    BoxesEndpoint(api, [OTHER_RECORD])
    entry = _add_entry(hass, BOX, "Home")

    result = await _reconfigure(hass, entry)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "box_not_found"}
    assert entry.data[CONF_BOX_GID] == BOX


async def test_reconfigure_keeps_pinned_box_of_unfinished_repair(hass, api):
    """Reconfigure can't switch boxes under a half-done repair; setup finishes it."""
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    boxes.status = 200
    real_update = hass.config_entries.async_update_entry

    def fail_on_repair(entry_, **kwargs):
        if kwargs.get("unique_id") == BOX:
            raise RuntimeError("interrupted")
        return real_update(entry_, **kwargs)

    with patch.object(hass.config_entries, "async_update_entry", fail_on_repair):
        await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY

    boxes.payload = [BOX_RECORD, OTHER_RECORD]
    result = await _reconfigure(hass, entry)
    assert result["type"] == "abort"  # no box choice offered
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    assert not any(OTHER in uid for uid in _uid_to_entity_id(hass))
    await _unload(hass, entry)


async def test_reconfigure_unfinished_repair_needs_the_pinned_box(hass, api):
    """Credentials for an account without the pinned box are refused and not
    saved (found in review of ccb122c)."""
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    boxes.status = 200
    real_update = hass.config_entries.async_update_entry

    def fail_on_repair(entry_, **kwargs):
        if kwargs.get("unique_id") == BOX:
            raise RuntimeError("interrupted")
        return real_update(entry_, **kwargs)

    with patch.object(hass.config_entries, "async_update_entry", fail_on_repair):
        await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    data_before = dict(entry.data)

    boxes.payload = [OTHER_RECORD]
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MSP_URL: DOMAIN_NAME, CONF_ACCESS_TOKEN: "another-token-0123456789"},
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "box_not_found"}
    assert dict(entry.data) == data_before
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_reconfigure_box_choice_rechecks_repair_on_submit(hass, api):
    """A repair that starts while the box form is open keeps its pinned box
    (race found in architect review of e36a5bc)."""
    entry, boxes = await _install_v120(hass, api)
    online = _uid_to_entity_id(hass)["firewalla_box_default_online"]
    # Unloaded, so the simulated repair below doesn't trigger a reload.
    await _unload(hass, entry)
    boxes.payload, boxes.status = [BOX_RECORD, OTHER_RECORD], 200
    result = await _reconfigure(hass, entry)
    assert result["step_id"] == "reconfigure_box"

    # Meanwhile a setup retry pins BOX and moves a record.
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PENDING_BOX_GID: BOX}
    )
    er.async_get(hass).async_update_entity(
        online, new_unique_id=f"firewalla_box_{BOX}_online"
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOX_GID: OTHER}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "box_identity_changed"
    assert entry.data[CONF_PENDING_BOX_GID] == BOX
    assert entry.data[CONF_ACCESS_TOKEN] == TOKEN


# ---------------------------------------------------------------------------
# Second review (pre-PR): positive detection of an interrupted repair, a
# missing target, and the abort while a legacy entry exists
# ---------------------------------------------------------------------------


def _add_unrelated_records(hass, entry):
    """Records a later release might add to an entry: not box evidence."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    wan = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "wan_1")}, name="WAN 1"
    )
    ent_reg.async_get_or_create(
        "button", DOMAIN, "firewalla_wan_1_refresh", config_entry=entry
    )
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, "firewalla_box_wan_1_latency", config_entry=entry
    )
    # Shaped like a box sensor but on another device (dev-review of 58653a3).
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "firewalla_box_wan_1_online_devices",
        config_entry=entry,
        device_id=wan.id,
    )


async def test_upgrade_ignores_unrelated_records_one_box(hass, api):
    """An extra device or *_refresh button must not look like a half-done
    repair: that would keep every legacy entry from loading (second review)."""
    entry, boxes = await _install_v120(hass, api)
    online = _uid_to_entity_id(hass)["firewalla_box_default_online"]
    await _unload(hass, entry)
    _add_unrelated_records(hass, entry)

    boxes.status = 200
    await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    assert _uid_to_entity_id(hass)[f"firewalla_box_{BOX}_online"] == online
    assert hass.states.get(online).state == "on"
    assert "firewalla_wan_1_refresh" in _uid_to_entity_id(hass)
    await _unload(hass, entry)


async def test_upgrade_ignores_unrelated_records_two_boxes(hass, api, caplog):
    """Multi-box legacy entry with unrelated records: loads untouched, and
    Reconfigure offers the box choice."""
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    _add_unrelated_records(hass, entry)
    before = _snapshot(hass, entry)

    boxes.payload, boxes.status = [BOX_RECORD, OTHER_RECORD], 200
    with caplog.at_level(logging.WARNING):
        await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert _snapshot(hass, entry) == before
    assert "the account has 2 boxes" in caplog.text
    result = await _reconfigure(hass, entry)
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure_box"
    await _unload(hass, entry)


def _fail_on_entry_repair(hass):
    real_update = hass.config_entries.async_update_entry

    def fail(entry_, **kwargs):
        if kwargs.get("unique_id") == BOX:
            raise RuntimeError("interrupted")
        return real_update(entry_, **kwargs)

    return patch.object(hass.config_entries, "async_update_entry", fail)


def _fail_on_entity_move(hass, number):
    ent_reg = er.async_get(hass)
    real_update_entity = ent_reg.async_update_entity
    moves = 0

    def fail(entity_id, **kwargs):
        nonlocal moves
        if "new_unique_id" in kwargs:
            moves += 1
            if moves == number:
                raise RuntimeError("interrupted")
        return real_update_entity(entity_id, **kwargs)

    return patch.object(ent_reg, "async_update_entity", fail)


def _fail_on_device_move(hass):
    dev_reg = dr.async_get(hass)
    real_update_device = dev_reg.async_update_device

    def fail(device_id, **kwargs):
        if "new_identifiers" in kwargs:
            raise RuntimeError("interrupted")
        return real_update_device(device_id, **kwargs)

    return patch.object(dev_reg, "async_update_device", fail)


def _make_v110_registry(hass, without_refresh=False):
    """v1.1.0 had no box entities: only the refresh button and the box device
    carry the gid, so the button can be the only record a repair moved, and
    without it (removed by the user) the device is."""
    ent_reg = er.async_get(hass)
    keys = [f"firewalla_box_default_{key}" for key in LEGACY_BOX_KEYS]
    if without_refresh:
        keys.append("firewalla_default_refresh")
    for unique_id in keys:
        ent_reg.async_remove(_uid_to_entity_id(hass)[unique_id])


@pytest.mark.parametrize(
    ("interrupt", "v110"),
    [
        (lambda hass: _fail_on_entity_move(hass, 2), False),  # first record moved
        (lambda hass: _fail_on_entity_move(hass, 4), False),
        (_fail_on_device_move, False),  # every entity moved, the device not
        (_fail_on_entry_repair, False),  # entities and device moved, the entry not
        (_fail_on_device_move, "v1.1.0"),  # only the refresh button moved
        (_fail_on_entry_repair, "no-refresh"),  # only the box device moved
        (lambda hass: _fail_on_entity_move(hass, 4), "no-summary"),
    ],
    ids=[
        "after-first-move",
        "mid-entity-moves",
        "before-device-move",
        "before-entry",
        "v1.1.0-before-device-move",
        "v1.1.0-no-refresh-before-entry",
        "no-rules-summary-mid-entity-moves",
    ],
)
async def test_interrupted_repair_without_saved_target(hass, api, interrupt, v110):
    """Moved records but no saved target (e.g. config entries restored from an
    older backup than the registries): setup keeps retrying rather than
    duplicating entities, nothing is changed, and Reconfigure says why at once
    instead of asking for credentials (second review)."""
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    if v110 == "no-summary":
        # The box device can't be found: exact box entity forms still count.
        er.async_get(hass).async_remove(
            _uid_to_entity_id(hass)["firewalla_rules_summary"]
        )
    elif v110:
        _make_v110_registry(hass, without_refresh=v110 == "no-refresh")
    count = len(_uid_to_entity_id(hass))
    boxes.status = 200
    with interrupt(hass):
        await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    await _unload(hass, entry)
    hass.config_entries.async_update_entry(
        entry,
        data={k: v for k, v in entry.data.items() if k != CONF_PENDING_BOX_GID},
    )
    before = _snapshot(hass, entry)
    assert entry.data[CONF_ACCESS_TOKEN] == TOKEN

    await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert _snapshot(hass, entry) == before
    assert len(_uid_to_entity_id(hass)) == count

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "repair_target_missing"
    # Strings carry no URLs (hassfest); the issues link is a placeholder.
    assert result["description_placeholders"]["issues_url"].endswith("/issues")
    assert _snapshot(hass, entry) == before
    await _unload(hass, entry)


async def test_pinned_refresh_uid_on_another_domain_is_not_evidence(hass, api):
    """Only the refresh *button* on the pinned gid shows a repair started; a
    sensor with that unique_id must not make setup skip /v2/boxes and finish
    a repair that never started (lead review of b4d2556)."""
    entry, boxes = await _install_v120(hass, api)  # /v2/boxes stays down
    await _unload(hass, entry)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PENDING_BOX_GID: BOX}  # chosen, not moved
    )
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"firewalla_{BOX}_refresh", config_entry=entry
    )
    before = _snapshot(hass, entry)

    await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == LEGACY_BOX_GID
    assert _snapshot(hass, entry) == before
    await _unload(hass, entry)


async def test_pinned_refresh_button_alone_resumes_without_box_device(hass, api):
    """v1.1.0 entry without its rules summary sensor (so the box device can't be
    found), interrupted after only the refresh button moved: the pinned button
    still marks the repair as started, so a retry with /v2/boxes down finishes
    it instead of creating a second refresh button."""
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    _make_v110_registry(hass)
    ent_reg = er.async_get(hass)
    ent_reg.async_remove(_uid_to_entity_id(hass)["firewalla_rules_summary"])
    refresh = _uid_to_entity_id(hass)["firewalla_default_refresh"]
    boxes.status = 200
    with _fail_on_device_move(hass):
        await _setup(hass, entry)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert entry.data[CONF_PENDING_BOX_GID] == BOX

    boxes.status = 500
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    uids = _uid_to_entity_id(hass)
    assert uids[f"firewalla_{BOX}_refresh"] == refresh
    assert "firewalla_default_refresh" not in uids
    await _unload(hass, entry)


async def test_unrelated_refresh_button_without_box_device(hass, api):
    """When the box device can't be found (no rules summary sensor), a
    *_refresh button is not evidence of a repair: it can't be tied to the box."""
    entry, boxes = await _install_v120(hass, api)
    await _unload(hass, entry)
    ent_reg = er.async_get(hass)
    ent_reg.async_remove(_uid_to_entity_id(hass)["firewalla_rules_summary"])
    ent_reg.async_get_or_create(
        "button", DOMAIN, "firewalla_wan_1_refresh", config_entry=entry
    )

    boxes.status = 200
    await _setup(hass, entry)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_BOX_GID] == BOX
    await _unload(hass, entry)
