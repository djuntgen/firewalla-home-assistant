"""#24 regression: setup must save the gid that box statistics look up.

The MSP API is mocked only at the HTTP layer (aioresponses), so the config flow,
the client, the coordinator and the platforms all run for real. v1.2.0 missed
#24 because setup and statistics were each tested with invented gids that
happened to agree.
"""

import re
from unittest.mock import patch

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er

from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_MSP_URL,
    DOMAIN,
)

DOMAIN_NAME = "testbox.firewalla.net"
BASE = f"https://{DOMAIN_NAME}/v2"
RULES_URL = re.compile(r"^https://testbox\.firewalla\.net/v2/rules(\?.*)?$")
TOKEN = "test-token-0123456789"

BOX = "3a7c9f1e-real-box-gid"
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
OTHER_RECORD = {**BOX_RECORD, "gid": "5d21b8c4-other-box-gid", "name": "Cabin"}
TRENDS = [{"ts": 1793595600, "value": 345}]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/firewalla as a real integration."""
    yield


@pytest.fixture
async def session():
    # ThreadedResolver: the default aiodns resolver leaves a pycares thread
    # behind, which the HA test harness rejects. aioresponses answers every
    # request, so nothing is resolved or connected either way.
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as s:
        yield s


@pytest.fixture
def api(session):
    """MSP API at the HTTP boundary; every module shares the one session."""
    with (
        aioresponses() as m,
        patch(
            "custom_components.firewalla.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.firewalla.async_get_clientsession",
            return_value=session,
        ),
    ):
        m.get(RULES_URL, payload={"results": [], "count": 0}, repeat=True)
        m.get(f"{BASE}/devices", payload=[], repeat=True)
        m.get(f"{BASE}/users", payload=[], repeat=True)
        m.get(f"{BASE}/trends/flows", payload=TRENDS, repeat=True)
        yield m


def _box_entity_id(hass, key):
    """entity_id of this integration's box entity whose unique_id ends in key."""
    ent_reg = er.async_get(hass)
    matches = [
        e.entity_id
        for e in ent_reg.entities.values()
        if e.platform == DOMAIN
        and e.unique_id.startswith("firewalla_box_")
        and e.unique_id.endswith(f"_{key}")
    ]
    assert len(matches) == 1, matches
    return matches[0]


async def _submit_credentials(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MSP_URL: DOMAIN_NAME, CONF_ACCESS_TOKEN: TOKEN}
    )


async def _assert_box_statistics_join(hass, result, title):
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state is config_entries.ConfigEntryState.LOADED

    # The reported symptom: box entities stay unavailable on every start.
    online = hass.states.get(_box_entity_id(hass, "online"))
    assert online is not None
    assert online.state == "on"
    assert hass.states.get(_box_entity_id(hass, "public_ip")).state == "203.0.113.7"
    assert hass.states.get(_box_entity_id(hass, "alarms")).state == "470"

    # And the cause: setup saved the real gid, not a placeholder.
    assert entry.data[CONF_BOX_GID] == BOX
    assert entry.unique_id == BOX
    assert entry.title == title

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_then_box_statistics_join(hass, api):
    """#24: the gid the config flow saves is the gid statistics find in /v2/boxes."""
    # Records without a usable gid are skipped, leaving the one real box.
    api.get(
        f"{BASE}/boxes",
        payload=[{"name": "no gid"}, "junk", BOX_RECORD],
        repeat=True,
    )
    result = await _submit_credentials(hass)
    await _assert_box_statistics_join(hass, result, "Home")


async def test_choose_box_then_box_statistics_join(hass, api):
    """With several boxes the user picks one, and statistics follow that pick."""
    api.get(f"{BASE}/boxes", payload=[OTHER_RECORD, BOX_RECORD], repeat=True)
    result = await _submit_credentials(hass)
    assert result["type"] == "form", result
    assert result["step_id"] == "box_selection"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOX_GID: BOX}
    )
    await _assert_box_statistics_join(hass, result, "Home")


@pytest.mark.parametrize(
    "payload", [[], {}, [{"name": "no gid"}]], ids=["empty", "not-a-list", "no-gid"]
)
async def test_no_usable_box_is_an_error(hass, api, payload):
    """No usable box record: the form says so and nothing is created."""
    api.get(f"{BASE}/boxes", payload=payload, repeat=True)
    result = await _submit_credentials(hass)
    assert result["type"] == "form", result
    assert result["errors"] == {"base": "no_boxes"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_box_list_unreadable_is_an_error(hass, api):
    """/v2/boxes failing: the form shows an error and nothing is created."""
    api.get(f"{BASE}/boxes", status=500, body="boom", repeat=True)
    result = await _submit_credentials(hass)
    assert result["type"] == "form", result
    assert result["errors"].get("base")
    assert not hass.config_entries.async_entries(DOMAIN)
