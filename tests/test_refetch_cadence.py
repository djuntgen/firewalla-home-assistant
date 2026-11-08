"""Refetch cadence: poll 1 and every ``every``-th poll after it, including every == 1."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.firewalla.coordinator import FirewallaDataUpdateCoordinator
from tests.test_network_stats import (  # noqa: F401 — fixtures
    BASE,
    BOX_RECORD,
    OTHER_BOX,
    TRENDS,
    _coordinator,
    _poll,
    _requests,
    api,
    session,
)
from custom_components.firewalla import binary_sensor

BASE_POLL = 60
POLLS = 14


def _mocked_coordinator(every):
    coord = FirewallaDataUpdateCoordinator(
        hass=MagicMock(),
        session=MagicMock(),
        msp_domain="box.firewalla.invalid",
        access_token="test-token",
        box_gid="box-gid-1",
        base_poll_interval=BASE_POLL,
        full_rules_interval=every * BASE_POLL,
        devices_interval=every * BASE_POLL,
    )
    coord.api._authenticated = True
    coord.api.get_rules = AsyncMock(return_value={"results": [{"id": "r1"}]})
    coord.api.get_devices = AsyncMock(return_value=[{"id": "AA", "online": True}])
    coord.api.get_users = AsyncMock(return_value=[])
    coord.api.get_boxes = AsyncMock(return_value=[])
    coord.api.get_flow_trends = AsyncMock(return_value=[])
    return coord


@pytest.mark.parametrize("every", [1, 2, 3, 6, 13])
async def test_full_rules_and_devices_refetch_cadence(every):
    coord = _mocked_coordinator(every)
    assert coord._full_rules_every == every
    assert coord._devices_every == every

    full_rule_polls, device_polls = [], []
    for poll in range(1, POLLS + 1):
        coord.api.get_rules.reset_mock()
        coord.api.get_devices.reset_mock()
        await coord._async_update_data()
        if any(c.args == () for c in coord.api.get_rules.await_args_list):
            full_rule_polls.append(poll)
        if coord.api.get_devices.await_count:
            device_polls.append(poll)

    expected = list(range(1, POLLS + 1, every))
    assert full_rule_polls == expected
    assert device_polls == expected


async def test_box_online_follows_server_at_60_60(session, api):
    """Base 60 s / devices 60 s (every == 1): box status refreshes every poll."""
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD])
    api.get(f"{BASE}/boxes", payload=[{**BOX_RECORD, "online": False}], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session, base_poll_interval=60, devices_interval=60)
    online = binary_sensor.FirewallaBoxOnlineSensor(coord)

    states = []
    for n in range(4):
        await _poll(coord, 1_000_000.0 + n * 60)
        states.append(online.is_on)

    assert states == [True, False, False, False]
    assert _requests(api, "/boxes") == 4
    assert _requests(api, "/devices") == 4


async def test_no_trends_calls_on_multi_box_accounts(session, api):
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD, OTHER_BOX], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    for n in range(25):  # 0 .. 1080 s: past two 15-minute trend windows
        data = await _poll(coord, 1_000_000.0 + n * 45)
    assert _requests(api, "/trends") == 0
    assert data["box_stats"]["alarm_count"] == 470
    assert data["box_stats"]["blocked_flows"] is None


async def test_trends_still_fetched_on_single_box_accounts(session, api):
    api.get(f"{BASE}/boxes", payload=[BOX_RECORD], repeat=True)
    api.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
    coord = _coordinator(session)
    data = await _poll(coord)
    assert _requests(api, "/trends") == 1
    assert data["box_stats"]["blocked_flows"]["value"] == 345
