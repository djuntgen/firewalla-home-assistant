"""Box status and statistics entities (#13), with the MSP API mocked by aioresponses."""

import asyncio
import logging
import re
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla import binary_sensor, sensor
from custom_components.firewalla.const import DOMAIN, FLOW_TRENDS_INTERVAL
from custom_components.firewalla.coordinator import FirewallaDataUpdateCoordinator

BOX = "box-gid-1"
BASE = "https://box.firewalla.invalid/v2"
RULES_URL = re.compile(r"^https://box\.firewalla\.invalid/v2/rules(\?.*)?$")

BOX_RECORD = {
    "gid": BOX,
    "name": "Home",
    "model": "gold_pro",
    "online": True,
    "version": "1.982",
    "publicIP": "203.0.113.7",
    "deviceCount": 181,
    "ruleCount": 103,
    "alarmCount": 470,
}
OTHER_BOX = {**BOX_RECORD, "gid": "box-gid-2", "online": False, "alarmCount": 3}
DEVICES = [
    {"id": "AA:00:00:00:00:01", "gid": BOX, "online": True},
    {"id": "AA:00:00:00:00:02", "gid": BOX, "online": True},
    {"id": "AA:00:00:00:00:03", "gid": BOX, "online": False},
    {"id": "BB:00:00:00:00:01", "gid": "box-gid-2", "online": True},  # other box
]
# Unordered on purpose; the latest ts is the box's current local day.
TRENDS = [
    {"ts": 1793505600, "value": 1200},
    {"ts": 1793595600, "value": 345},
    {"ts": 1793419200, "value": 980},
]


@pytest.fixture
async def session():
    # ThreadedResolver: the default aiodns resolver leaves a pycares thread behind,
    # which the HA test harness's thread check rejects. aioresponses answers
    # every request, so nothing is resolved or connected either way.
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as s:
        yield s


@pytest.fixture
def api():
    with aioresponses() as m:
        m.get(RULES_URL, payload={"results": [], "count": 0}, repeat=True)
        m.get(f"{BASE}/devices", payload=DEVICES, repeat=True)
        m.get(f"{BASE}/users", payload=[], repeat=True)
        yield m


def _coordinator(session, **options):
    coord = FirewallaDataUpdateCoordinator(
        hass=MagicMock(),
        session=session,
        msp_domain="box.firewalla.invalid",
        access_token="test-token",
        box_gid=BOX,
        **options,
    )
    coord.api._authenticated = True
    return coord


async def _poll(coord, at=1_000_000.0):
    with patch("time.time", return_value=at):
        coord.data = await coord._async_update_data()
    coord.last_update_success = True
    return coord.data


def _requests(api, path):
    return sum(
        len(calls)
        for (method, url), calls in api.requests.items()
        if method == "GET" and str(url).startswith(f"{BASE}{path}")
    )


def _entities(coord):
    by_key = {
        d.key: sensor.FirewallaBoxStatSensor(coord, d) for d in sensor.BOX_STAT_SENSORS
    }
    by_key["firmware"] = sensor.FirewallaFirmwareSensor(coord)
    by_key["blocked_flows"] = sensor.FirewallaBlockedFlowsSensor(coord)
    by_key["online"] = binary_sensor.FirewallaBoxOnlineSensor(coord)
    return by_key


async def test_each_entity_state(session, api):
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    data = await _poll(coord)

    e = _entities(coord)
    assert e["online"].is_on is True
    assert e["public_ip"].native_value == "203.0.113.7"
    assert e["firmware"].native_value == "1.982"
    assert e["total_devices"].native_value == 181
    assert e["online_devices"].native_value == 2  # this box's online devices only
    assert e["alarms"].native_value == 470
    assert e["blocked_flows"].native_value == 345
    assert e["blocked_flows"].extra_state_attributes == {"day_start_ts": 1793595600}
    assert e["blocked_flows"].last_reset.timestamp() == 1793595600
    assert all(entity.available for entity in e.values())

    assert e["public_ip"].entity_category == "diagnostic"
    assert e["firmware"].entity_category == "diagnostic"
    assert e["online"].device_class == "connectivity"
    # Attached to the box's HA device, with firmware as its sw_version.
    assert e["alarms"].device_info["identifiers"] == {(DOMAIN, BOX)}
    assert data["box_info"]["version"] == "1.982"
    assert sensor.box_device_info(coord)["sw_version"] == "1.982"


async def test_box_offline(session, api):
    api.get(f"{BASE}/boxes", payload=[{**BOX_RECORD, "online": False}], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    await _poll(coord)
    online = binary_sensor.FirewallaBoxOnlineSensor(coord)
    assert online.available is True
    assert online.is_on is False


async def test_api_calls_at_default_options(session, api):
    """Boxes only on device-list refresh polls; trends at most every 15 min."""
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS)
    api.get(f"{BASE}/trends/flows", payload=[{"ts": 1793595600, "value": 400}])
    coord = _coordinator(session)  # defaults: base 45 s, devices 600 s
    t0 = 1_000_000.0
    polls = 27  # 0 .. 1170 s

    box_polls, device_polls, trend_polls, values = [], [], [], []
    for n in range(polls):
        before = {p: _requests(api, p) for p in ("/boxes", "/devices", "/trends")}
        data = await _poll(coord, t0 + n * 45)
        after = {p: _requests(api, p) for p in before}
        if after["/boxes"] > before["/boxes"]:
            box_polls.append(n)
        if after["/devices"] > before["/devices"]:
            device_polls.append(n)
        if after["/trends"] > before["/trends"]:
            trend_polls.append(n)
        values.append(data["box_stats"]["blocked_flows"]["value"])

    assert device_polls == [0, 13, 26]  # every 600 // 45 = 13 polls
    assert box_polls == device_polls
    assert trend_polls == [0, 20]  # t = 0 s and t = 900 s
    # The last box and trends values are kept between fetches.
    assert values[:20] == [345] * 20
    assert values[20:] == [400] * 7
    assert _requests(api, "/boxes") == 3  # vs. 27 polls


async def test_stats_failure_leaves_rules_working(session, api, caplog):
    api.get(RULES_URL, payload={"results": [], "count": 0}, repeat=True)
    api.get(f"{BASE}/boxes", status=500, body="boom")
    api.get(f"{BASE}/boxes", status=500, body="boom")
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD])
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    # Devices (and so boxes) refresh every 2 polls: polls 1, 3 and 5.
    coord = _coordinator(session, base_poll_interval=45, devices_interval=90)
    # A real rule, so we can see rules still update.
    coord.api.get_rules = MagicMock(side_effect=_rules_response)

    with caplog.at_level(logging.DEBUG, logger="custom_components.firewalla"):
        data = await _poll(coord)
        assert data["box_stats"] is None
        assert "r1" in data["rules"]
        e = _entities(coord)
        assert not any(entity.available for entity in e.values())
        assert sensor.FirewallaRulesSensor(coord).available is True

        for n in range(1, 4):  # poll 3 fails again; polls 2 and 4 don't refetch
            data = await _poll(coord, 1_000_000.0 + n * 45)
            assert data["box_stats"] is None
            assert "r1" in data["rules"]
        data = await _poll(coord, 1_000_000.0 + 4 * 45)  # poll 5: recovered
        assert data["box_stats"]["alarm_count"] == 470
        assert all(entity.available for entity in _entities(coord).values())
        assert _requests(api, "/boxes") == 3

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [r.getMessage() for r in warnings] == [
        "Could not fetch Firewalla box statistics: "
        "MSP API server error (HTTP 500): boom"
    ]


async def _rules_response(query=None):
    return {"results": [{"id": "r1", "action": "block", "status": "active"}]}


async def test_trends_failure_only_affects_blocked_flows(session, api):
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD], repeat=True)
    api.get(f"{BASE}/trends/flows", status=404, body="nope")
    coord = _coordinator(session)
    await _poll(coord)
    e = _entities(coord)
    assert e["blocked_flows"].available is False
    assert all(entity.available for k, entity in e.items() if k != "blocked_flows")


class _SensorPlatform:
    def __init__(self, hass, coord):
        self.entry = MockConfigEntry(domain=DOMAIN, data={})
        self.entry.add_to_hass(hass)
        hass.data.setdefault(DOMAIN, {})[self.entry.entry_id] = coord
        self.hass = hass
        self.coord = coord
        self.added = []
        self.listeners = []
        coord.async_add_listener = lambda cb: self.listeners.append(cb) or (
            lambda: None
        )

    async def setup(self):
        await sensor.async_setup_entry(
            self.hass, self.entry, lambda ents: self.added.extend(ents)
        )
        return {e.unique_id for e in self.added}


async def test_blocked_flows_only_for_single_box_accounts(hass, session, api):
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD, OTHER_BOX], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    await _poll(coord)
    ids = await _SensorPlatform(hass, coord).setup()
    assert f"firewalla_box_{BOX}_alarms" in ids
    assert f"firewalla_box_{BOX}_blocked_flows" not in ids
    # On a multi-box account the box stats are still the configured box's.
    assert coord.data["box_stats"]["alarm_count"] == 470


async def test_blocked_flows_created_for_single_box_account(hass, session, api):
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    await _poll(coord)
    platform = _SensorPlatform(hass, coord)
    ids = await platform.setup()
    assert f"firewalla_box_{BOX}_blocked_flows" in ids
    for cb in platform.listeners:  # later polls don't add it twice
        cb()
    assert len(platform.added) == len(ids)


async def test_firmware_sensor_updates_device_sw_version(hass, session, api):
    api.get(f"{BASE}/boxes", payload=[{**BOX_RECORD, "version": "1.983"}], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    await _poll(coord)

    config_entry = MockConfigEntry(domain=DOMAIN, data={})
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, BOX)},
        sw_version="1.982",
    )
    reg_entry = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"firewalla_box_{BOX}_firmware",
        config_entry=config_entry,
        device_id=device.id,
    )
    firmware = sensor.FirewallaFirmwareSensor(coord)
    firmware.hass = hass
    firmware.registry_entry = reg_entry
    firmware.entity_id = reg_entry.entity_id
    firmware.async_write_ha_state = MagicMock()

    firmware._handle_coordinator_update()

    assert dr.async_get(hass).async_get(device.id).sw_version == "1.983"


async def test_stats_timeout_is_one_quiet_attempt(session, api, caplog):
    api.get(f"{BASE}/boxes", timeout=True, repeat=True)
    coord = _coordinator(session)
    with caplog.at_level(logging.DEBUG, logger="custom_components.firewalla"):
        for at in (1_000_000.0, 1_000_045.0):
            data = await _poll(coord, at)
            assert data["box_stats"] is None
    assert _requests(api, "/boxes") == 1  # one attempt, no retries; not refetched
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage().startswith("Could not fetch Firewalla box")


async def test_hanging_stats_call_is_capped(session, api):
    async def hang(url, **kwargs):
        await asyncio.sleep(60)

    api.get(f"{BASE}/boxes", callback=hang)
    coord = _coordinator(session)
    coord.api.get_rules = MagicMock(side_effect=_rules_response)
    with patch("custom_components.firewalla.coordinator.BOX_STATS_TIMEOUT", 0.05):
        data = await asyncio.wait_for(_poll(coord), timeout=5)
    assert data["box_stats"] is None
    assert "r1" in data["rules"]
