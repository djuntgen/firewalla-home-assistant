"""Dashboard generation (#8, #12) with Home Assistant's real lovelace component.

The pinned test HA (2025.1.4) stores lovelace data as a dict; HA 2025.2+ stores a
LovelaceData object with a ``.dashboards`` attribute, covered by a stand-in.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import ServiceCall
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla import (
    DASHBOARD_URL_PATH,
    _async_generate_dashboard,
    _build_user_section,
)
from custom_components.firewalla.const import (
    CONF_ACCESS_TOKEN,
    CONF_BOX_GID,
    CONF_DASHBOARD_USERS,
    CONF_MSP_URL,
    DOMAIN,
)
from custom_components.firewalla.coordinator import FirewallaMSPClient

LOGGER = "custom_components.firewalla"


@pytest.fixture
async def lovelace(hass):
    assert await async_setup_component(hass, "lovelace", {})
    return hass.data["lovelace"]


async def _create_storage_dashboard(lovelace_data):
    await lovelace_data["dashboards_collection"].async_create_item(
        {
            "url_path": DASHBOARD_URL_PATH,
            "title": "Firewalla",
            "mode": "storage",
            "require_admin": False,
            "show_in_sidebar": True,
        }
    )


@pytest.fixture
def save_config_calls(hass):
    """A lovelace.save_config service (which HA doesn't have) recording any call."""
    calls: list[ServiceCall] = []
    hass.services.async_register("lovelace", "save_config", calls.append)
    return calls


async def test_setup_saves_one_section_per_user(
    hass, enable_custom_integrations, lovelace, save_config_calls
):
    await _create_storage_dashboard(lovelace)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_MSP_URL: "box.firewalla.invalid",
            CONF_ACCESS_TOKEN: "test-token",
            CONF_BOX_GID: "box-gid",
        },
        options={CONF_DASHBOARD_USERS: "Alice, Bob"},
    )
    entry.add_to_hass(hass)

    # The client's HTTP methods are patched, so no session is used; patching it out
    # also avoids HA's aiodns resolver thread, which the harness's thread check rejects.
    with (
        patch("custom_components.firewalla.async_get_clientsession"),
        patch.object(FirewallaMSPClient, "authenticate", AsyncMock(return_value=True)),
        patch.object(
            FirewallaMSPClient, "get_rules", AsyncMock(return_value={"results": []})
        ),
        patch.object(FirewallaMSPClient, "get_devices", AsyncMock(return_value=[])),
        patch.object(FirewallaMSPClient, "get_users", AsyncMock(return_value=[])),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    saved = await lovelace["dashboards"][DASHBOARD_URL_PATH].async_load(False)
    assert saved["views"][0]["sections"] == [
        _build_user_section("Alice"),
        _build_user_section("Bob"),
    ]
    assert save_config_calls == []

    await hass.config_entries.async_unload(entry.entry_id)


async def test_missing_dashboard_warns_and_does_not_raise(
    hass, lovelace, save_config_calls, caplog
):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await _async_generate_dashboard(hass, "Alice")

    messages = [r.getMessage() for r in caplog.records if r.name.startswith(LOGGER)]
    assert messages == [
        f"Dashboard '{DASHBOARD_URL_PATH}' does not exist — create it in "
        "Settings > Dashboards first, then reload the integration"
    ]
    assert save_config_calls == []


async def test_save_failure_reports_the_error(hass, lovelace, caplog):
    await _create_storage_dashboard(lovelace)
    dashboard = lovelace["dashboards"][DASHBOARD_URL_PATH]

    with (
        patch.object(dashboard, "async_save", AsyncMock(side_effect=OSError("boom"))),
        caplog.at_level(logging.WARNING, logger=LOGGER),
    ):
        await _async_generate_dashboard(hass, "Alice")

    messages = [r.getMessage() for r in caplog.records if r.name.startswith(LOGGER)]
    # The dashboard exists, so the message must not tell the user to create it.
    assert messages == [f"Could not generate the '{DASHBOARD_URL_PATH}' dashboard: boom"]


async def test_lovelace_data_object_shape(hass, save_config_calls):
    """HA 2025.2+ keeps dashboards on a LovelaceData object, not in a dict."""
    dashboard = SimpleNamespace(async_save=AsyncMock())
    hass.data["lovelace"] = SimpleNamespace(dashboards={DASHBOARD_URL_PATH: dashboard})

    await _async_generate_dashboard(hass, "Alice, Bob")

    dashboard.async_save.assert_awaited_once()
    config = dashboard.async_save.await_args.args[0]
    assert config["views"][0]["sections"] == [
        _build_user_section("Alice"),
        _build_user_section("Bob"),
    ]
    assert save_config_calls == []
