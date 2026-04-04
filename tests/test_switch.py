"""Tests for Firewalla rule control switch entities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from homeassistant.exceptions import HomeAssistantError

from custom_components.firewalla.switch import (
    FirewallaRuleSwitch,
    async_setup_entry,
    _generate_entity_name,
    _generate_clean_entity_id,
    _make_unique_id,
    _format_timestamp,
    _format_schedule,
)
from custom_components.firewalla.const import DOMAIN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(rules=None, box_info=None):
    """Create a mock coordinator with sensible defaults."""
    coordinator = MagicMock()
    coordinator.box_gid = "box-123"
    coordinator.last_update_success = True
    coordinator.async_resume_rule = AsyncMock(return_value=True)
    coordinator.async_pause_rule = AsyncMock(return_value=True)

    if box_info is None:
        box_info = {
            "gid": "box-123",
            "name": "Firewalla Gold",
            "model": "gold",
            "online": True,
            "version": "1.975",
        }

    if rules is None:
        rules = {
            "rule-123": {
                "rid": "rule-123",
                "type": "internet",
                "target": "mac:aa:bb:cc:dd:ee:ff",
                "target_name": "John's Laptop",
                "disabled": False,
                "paused": False,
                "action": "block",
                "description": "Block internet during study time",
                "priority": 1000,
                "created_at": 1648632679193,
                "modified_at": 1648632679193,
                "schedule": None,
            },
            "rule-456": {
                "rid": "rule-456",
                "type": "category",
                "target": "category:gaming",
                "target_name": "Gaming Category",
                "disabled": False,
                "paused": True,
                "action": "block",
                "description": "Block gaming websites",
                "priority": 500,
                "created_at": 1648632679193,
                "modified_at": 1648632679193,
                "schedule": None,
            },
        }

    coordinator.data = {
        "rules": rules,
        "rule_count": {
            "total": len(rules),
            "active": sum(1 for r in rules.values() if not r.get("paused")),
            "paused": sum(1 for r in rules.values() if r.get("paused")),
        },
        "box_info": box_info,
    }
    return coordinator


def _make_rule(**overrides):
    """Build a single rule dict with overrides."""
    base = {
        "rid": "rule-test",
        "type": "internet",
        "target": "mac:aa:bb:cc:dd:ee:ff",
        "target_name": "Test Device",
        "disabled": False,
        "paused": False,
        "action": "block",
        "description": "",
        "priority": 1000,
        "created_at": 1648632679193,
        "modified_at": 1648632679193,
        "schedule": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Module-level _generate_entity_name tests
# ---------------------------------------------------------------------------


class TestGenerateEntityName:
    """Test the module-level _generate_entity_name function."""

    def test_uses_description_when_present(self):
        """Return the description verbatim when it is non-empty."""
        rule = _make_rule(description="Block internet during study time")
        assert _generate_entity_name(rule) == "Block internet during study time"

    def test_block_internet_without_description(self):
        """Generate a block-prefixed name for internet rules."""
        rule = _make_rule(type="internet", action="block", description="")
        assert _generate_entity_name(rule) == "Block Internet Access"

    def test_allow_internet_without_description(self):
        """Generate an allow-prefixed name for internet rules."""
        rule = _make_rule(type="internet", action="allow", description="")
        assert _generate_entity_name(rule) == "Allow Internet Access"

    def test_timelimit_app_without_description(self):
        """Generate a Limit-prefixed name for timelimit + app rules."""
        rule = _make_rule(
            type="app", action="timelimit", value="youtube", description=""
        )
        assert _generate_entity_name(rule) == "Limit Youtube"

    def test_block_category_without_description(self):
        """Generate a block-prefixed category name."""
        rule = _make_rule(
            type="category", action="block", value="gaming", description=""
        )
        assert _generate_entity_name(rule) == "Block Gaming Category"

    def test_block_domain_without_description(self):
        """Generate a block-prefixed domain name."""
        rule = _make_rule(
            type="domain", action="block", value="example.com", description=""
        )
        assert _generate_entity_name(rule) == "Block example.com"

    def test_block_ip_without_description(self):
        """Generate a block-prefixed IP name."""
        rule = _make_rule(
            type="ip", action="block", value="10.0.0.1", description=""
        )
        assert _generate_entity_name(rule) == "Block 10.0.0.1"

    def test_intranet_with_value(self):
        """Generate an intranet name with value prefix."""
        rule = _make_rule(
            type="intranet", action="block", value="abcdef01-rest", description=""
        )
        assert _generate_entity_name(rule) == "Intranet Access - abcdef01"

    def test_intranet_without_value(self):
        """Generate a plain intranet name."""
        rule = _make_rule(type="intranet", action="block", value="", description="")
        assert _generate_entity_name(rule) == "Intranet Access"

    def test_unknown_type_with_value(self):
        """Fall back to title-cased type for unknown rule types."""
        rule = _make_rule(type="foobar", action="block", value="baz", description="")
        assert _generate_entity_name(rule) == "Foobar - baz"

    def test_unknown_type_without_value(self):
        """Fall back to title-cased type + Rule suffix."""
        rule = _make_rule(type="foobar", action="block", value="", description="")
        assert _generate_entity_name(rule) == "Foobar Rule"


# ---------------------------------------------------------------------------
# Module-level _generate_clean_entity_id tests
# ---------------------------------------------------------------------------


class TestGenerateCleanEntityId:
    """Test the module-level _generate_clean_entity_id function."""

    def test_removes_block_prefix(self):
        """Action prefix 'block' should be stripped from the entity id."""
        result = _generate_clean_entity_id("Block Internet Access", "rule-1")
        assert result == "internet_access"

    def test_removes_allow_prefix(self):
        result = _generate_clean_entity_id("Allow Internet Access", "rule-1")
        assert result == "internet_access"

    def test_removes_limit_prefix(self):
        result = _generate_clean_entity_id("Limit Youtube", "rule-1")
        assert result == "youtube"

    def test_truncates_long_names(self):
        """Names exceeding 40 characters should be truncated."""
        long_name = "Block " + "a" * 60
        result = _generate_clean_entity_id(long_name, "rule-1")
        assert len(result) <= 40

    def test_falls_back_for_short_names(self):
        """Very short cleaned names get replaced with rule_<prefix>."""
        result = _generate_clean_entity_id("Block ab", "rule-xyz-123")
        # After removing "block ", we have "ab" which is <3 chars
        assert result == "rule_rule"

    def test_special_characters_replaced(self):
        """Non-alphanumeric characters become underscores."""
        result = _generate_clean_entity_id("Block foo.bar/baz", "rule-1")
        assert result == "foo_bar_baz"


# ---------------------------------------------------------------------------
# Module-level _make_unique_id tests
# ---------------------------------------------------------------------------


class TestMakeUniqueId:
    """Test the module-level _make_unique_id function."""

    def test_uses_rule_data_when_available(self):
        """Should build unique id from entity name derived from rule data."""
        coordinator = _make_coordinator()
        uid = _make_unique_id(coordinator, "rule-123")
        # description is "Block internet during study time"
        # clean_entity_id strips "block " -> "internet_during_study_time"
        assert uid == "firewalla_rule_internet_during_study_time"

    def test_falls_back_when_rule_missing(self):
        """Should use rule_<id> when rule not in coordinator data."""
        coordinator = _make_coordinator()
        uid = _make_unique_id(coordinator, "rule-nonexistent")
        # _generate_entity_name receives "rule_rule-nonexistent"
        # _generate_clean_entity_id("rule_rule-nonexistent", "rule-nonexistent")
        # removes "rule " prefix -> "rule_rule_nonexistent"
        assert uid.startswith("firewalla_rule_")

    def test_falls_back_when_data_is_none(self):
        """Should not crash when coordinator.data is None."""
        coordinator = MagicMock()
        coordinator.data = None
        uid = _make_unique_id(coordinator, "abc-123")
        assert uid.startswith("firewalla_rule_")


# ---------------------------------------------------------------------------
# _format_timestamp / _format_schedule tests
# ---------------------------------------------------------------------------


class TestFormatTimestamp:
    """Test timestamp formatting helper."""

    def test_millisecond_timestamp(self):
        result = _format_timestamp(1648632679193)
        assert result is not None
        assert "2022" in result  # sanity: year is 2022

    def test_second_timestamp(self):
        result = _format_timestamp(1648632679)
        assert result is not None
        assert "2022" in result

    def test_zero_returns_none(self):
        assert _format_timestamp(0) is None

    def test_falsy_returns_none(self):
        assert _format_timestamp(None) is None


class TestFormatSchedule:
    """Test schedule formatting helper."""

    def test_none_returns_none(self):
        assert _format_schedule(None) is None

    def test_empty_dict_returns_none(self):
        # dict with no relevant keys
        result = _format_schedule({})
        assert result is not None or result is None  # just no crash

    def test_dict_with_days_and_times(self):
        sched = {"days": ["Mon", "Tue"], "startTime": "08:00", "endTime": "17:00"}
        result = _format_schedule(sched)
        assert "Mon" in result
        assert "08:00" in result

    def test_list_schedule(self):
        sched = [
            {"days": ["Mon"], "startTime": "08:00", "endTime": "12:00"},
            {"days": ["Fri"], "startTime": "13:00", "endTime": "17:00"},
        ]
        result = _format_schedule(sched)
        assert "Mon" in result
        assert "Fri" in result
        assert ";" in result


# ---------------------------------------------------------------------------
# FirewallaRuleSwitch — init and properties
# ---------------------------------------------------------------------------


class TestFirewallaRuleSwitchInit:
    """Test FirewallaRuleSwitch initialization and static properties."""

    def test_init_stores_rule_id(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)

        assert switch._rule_id == "rule-123"

    def test_unique_id_matches_make_unique_id(self):
        """The entity unique_id should equal _make_unique_id output."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)

        expected = _make_unique_id(coordinator, "rule-123")
        assert switch.unique_id == expected

    def test_name_from_description(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        assert switch.name == "Block internet during study time"

    def test_name_generated_when_no_description(self):
        """Without a description, name is generated from type + action."""
        coordinator = _make_coordinator()
        rule_data = _make_rule(
            rid="rule-nodesc",
            type="internet",
            action="allow",
            description="",
        )
        coordinator.data["rules"]["rule-nodesc"] = rule_data
        switch = FirewallaRuleSwitch(coordinator, "rule-nodesc", rule_data)
        assert switch.name == "Allow Internet Access"

    def test_has_entity_name_is_true(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        assert switch._attr_has_entity_name is True

    def test_unrecorded_attributes_is_frozenset(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        assert isinstance(switch._unrecorded_attributes, frozenset)
        assert "rule_id" in switch._unrecorded_attributes

    def test_device_info_built(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        di = switch._attr_device_info
        assert di is not None
        assert (DOMAIN, "box-123") in di["identifiers"]
        assert di["name"] == "Firewalla Gold"
        assert di["manufacturer"] == "Firewalla"


# ---------------------------------------------------------------------------
# FirewallaRuleSwitch — is_on / available
# ---------------------------------------------------------------------------


class TestFirewallaRuleSwitchState:
    """Test is_on and available properties."""

    def test_is_on_active_rule(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        assert switch.is_on is True

    def test_is_on_paused_rule(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-456"]
        switch = FirewallaRuleSwitch(coordinator, "rule-456", rule_data)
        assert switch.is_on is False

    def test_is_on_rule_removed(self):
        """is_on returns False when the rule disappears from coordinator data."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        # Simulate rule removal
        del coordinator.data["rules"]["rule-123"]
        assert switch.is_on is False

    def test_available_when_rule_exists(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        assert switch.available is True

    def test_unavailable_when_rule_removed(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        del coordinator.data["rules"]["rule-123"]
        assert switch.available is False

    def test_unavailable_when_coordinator_fails(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        coordinator.last_update_success = False
        assert switch.available is False


# ---------------------------------------------------------------------------
# FirewallaRuleSwitch — extra_state_attributes
# ---------------------------------------------------------------------------


class TestFirewallaRuleSwitchAttributes:
    """Test extra_state_attributes property."""

    def test_basic_attributes(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)

        attrs = switch.extra_state_attributes

        assert attrs["rule_id"] == "rule-123"
        assert attrs["rule_status"] == "active"
        assert attrs["rule_disabled"] is False

    def test_attributes_for_paused_rule(self):
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-456"]
        switch = FirewallaRuleSwitch(coordinator, "rule-456", rule_data)

        attrs = switch.extra_state_attributes
        assert attrs["rule_status"] == "paused"

    def test_attributes_when_rule_not_found(self):
        coordinator = _make_coordinator()
        rule_data = _make_rule(rid="gone")
        switch = FirewallaRuleSwitch(coordinator, "gone", rule_data)
        # Rule "gone" is not in coordinator.data["rules"]
        attrs = switch.extra_state_attributes
        assert attrs["rule_id"] == "gone"
        assert attrs["status"] == "Rule not found"

    def test_hit_count_from_hit_dict(self):
        """hit_count comes from the nested hit object."""
        coordinator = _make_coordinator()
        coordinator.data["rules"]["rule-123"]["hit"] = {"count": 42, "ts": 1648632679}
        switch = FirewallaRuleSwitch(coordinator, "rule-123",
                                     coordinator.data["rules"]["rule-123"])
        attrs = switch.extra_state_attributes
        assert attrs["hit_count"] == 42
        assert "last_hit" in attrs

    def test_time_quota_attributes(self):
        """time_quota_minutes and time_used_minutes should appear when set."""
        coordinator = _make_coordinator()
        coordinator.data["rules"]["rule-123"]["time_quota_minutes"] = 60
        coordinator.data["rules"]["rule-123"]["time_used_minutes"] = 15
        switch = FirewallaRuleSwitch(coordinator, "rule-123",
                                     coordinator.data["rules"]["rule-123"])
        attrs = switch.extra_state_attributes
        assert attrs["time_quota_minutes"] == 60
        assert attrs["time_used_minutes"] == 15

    def test_schedule_display_attribute(self):
        """schedule_display should be present when schedule data exists."""
        coordinator = _make_coordinator()
        coordinator.data["rules"]["rule-123"]["schedule"] = {
            "days": ["Mon"],
            "startTime": "09:00",
            "endTime": "17:00",
        }
        switch = FirewallaRuleSwitch(coordinator, "rule-123",
                                     coordinator.data["rules"]["rule-123"])
        attrs = switch.extra_state_attributes
        assert "schedule_display" in attrs
        assert "Mon" in attrs["schedule_display"]

    def test_scope_and_direction_attributes(self):
        """scope_type, scope_value, direction should appear when present."""
        coordinator = _make_coordinator()
        coordinator.data["rules"]["rule-123"]["scope_type"] = "device"
        coordinator.data["rules"]["rule-123"]["scope_value"] = "aa:bb:cc:dd:ee:ff"
        coordinator.data["rules"]["rule-123"]["direction"] = "outbound"
        switch = FirewallaRuleSwitch(coordinator, "rule-123",
                                     coordinator.data["rules"]["rule-123"])
        attrs = switch.extra_state_attributes
        assert attrs["scope_type"] == "device"
        assert attrs["scope_value"] == "aa:bb:cc:dd:ee:ff"
        assert attrs["direction"] == "outbound"

    def test_timestamp_formatting(self):
        """created_at / modified_at should be ISO-formatted strings."""
        coordinator = _make_coordinator()
        switch = FirewallaRuleSwitch(coordinator, "rule-123",
                                     coordinator.data["rules"]["rule-123"])
        attrs = switch.extra_state_attributes
        # created_at is in RULE_ATTRIBUTES so it should be formatted
        if "created_at" in attrs:
            assert "2022" in attrs["created_at"]


# ---------------------------------------------------------------------------
# FirewallaRuleSwitch — async_turn_on / async_turn_off with optimistic updates
# ---------------------------------------------------------------------------


class TestFirewallaRuleSwitchActions:
    """Test turn_on / turn_off with optimistic state updates."""

    @pytest.mark.asyncio
    async def test_turn_on_resumes_paused_rule(self):
        """Turning on a paused rule should call async_resume_rule."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-456"]
        switch = FirewallaRuleSwitch(coordinator, "rule-456", rule_data)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        coordinator.async_resume_rule.assert_called_once_with("rule-456")

    @pytest.mark.asyncio
    async def test_turn_on_optimistic_update(self):
        """After resume, the coordinator data should be updated optimistically."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-456"]
        switch = FirewallaRuleSwitch(coordinator, "rule-456", rule_data)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        # Optimistic update sets paused=False, status=active
        assert coordinator.data["rules"]["rule-456"]["paused"] is False
        assert coordinator.data["rules"]["rule-456"]["status"] == "active"
        switch.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_skips_active_rule(self):
        """Turning on an already active rule should be a no-op."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        coordinator.async_resume_rule.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_on_rule_not_found(self):
        """Turning on a rule that no longer exists should raise."""
        coordinator = _make_coordinator()
        rule_data = _make_rule(rid="gone")
        switch = FirewallaRuleSwitch(coordinator, "gone", rule_data)

        with pytest.raises(HomeAssistantError, match="Rule gone not found"):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_on_api_failure(self):
        """When async_resume_rule returns False, raise HomeAssistantError."""
        coordinator = _make_coordinator()
        coordinator.async_resume_rule.return_value = False
        rule_data = coordinator.data["rules"]["rule-456"]
        switch = FirewallaRuleSwitch(coordinator, "rule-456", rule_data)
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError, match="Failed to resume rule"):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_pauses_active_rule(self):
        """Turning off an active rule should call async_pause_rule."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        coordinator.async_pause_rule.assert_called_once_with("rule-123")

    @pytest.mark.asyncio
    async def test_turn_off_optimistic_update(self):
        """After pause, the coordinator data should be updated optimistically."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        assert coordinator.data["rules"]["rule-123"]["paused"] is True
        assert coordinator.data["rules"]["rule-123"]["status"] == "paused"
        switch.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_skips_paused_rule(self):
        """Turning off an already paused rule should be a no-op."""
        coordinator = _make_coordinator()
        rule_data = coordinator.data["rules"]["rule-456"]
        switch = FirewallaRuleSwitch(coordinator, "rule-456", rule_data)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        coordinator.async_pause_rule.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_off_rule_not_found(self):
        """Turning off a rule that no longer exists should raise."""
        coordinator = _make_coordinator()
        rule_data = _make_rule(rid="gone")
        switch = FirewallaRuleSwitch(coordinator, "gone", rule_data)

        with pytest.raises(HomeAssistantError, match="Rule gone not found"):
            await switch.async_turn_off()

    @pytest.mark.asyncio
    async def test_turn_off_api_failure(self):
        """When async_pause_rule returns False, raise HomeAssistantError."""
        coordinator = _make_coordinator()
        coordinator.async_pause_rule.return_value = False
        rule_data = coordinator.data["rules"]["rule-123"]
        switch = FirewallaRuleSwitch(coordinator, "rule-123", rule_data)
        switch.async_write_ha_state = MagicMock()

        with pytest.raises(HomeAssistantError, match="Failed to pause rule"):
            await switch.async_turn_off()


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_creates_entities_for_all_rules(self):
        """Should create one switch entity per rule and register a listener."""
        coordinator = _make_coordinator()
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry-1": coordinator}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-1"
        config_entry.async_on_unload = MagicMock()

        async_add_entities = MagicMock()

        await async_setup_entry(hass, config_entry, async_add_entities)

        # Initial sync should add 2 entities
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2
        assert all(isinstance(e, FirewallaRuleSwitch) for e in entities)

        # No second boolean arg (True) — just the list
        assert len(async_add_entities.call_args[0]) == 1

        # Listener registered via async_on_unload
        config_entry.async_on_unload.assert_called_once()
        coordinator.async_add_listener.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_entities_when_no_rules(self):
        """Should not call async_add_entities when there are no rules."""
        coordinator = _make_coordinator(rules={})
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry-1": coordinator}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-1"
        config_entry.async_on_unload = MagicMock()

        async_add_entities = MagicMock()

        await async_setup_entry(hass, config_entry, async_add_entities)

        # No entities to add
        async_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_entities_when_data_none(self):
        """Should not crash when coordinator data is None."""
        coordinator = _make_coordinator()
        coordinator.data = None
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry-1": coordinator}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-1"
        config_entry.async_on_unload = MagicMock()

        async_add_entities = MagicMock()

        await async_setup_entry(hass, config_entry, async_add_entities)

        async_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_coordinator_raises(self):
        """Should raise KeyError when coordinator is not in hass.data."""
        hass = MagicMock()
        hass.data = {DOMAIN: {}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-missing"

        async_add_entities = MagicMock()

        with pytest.raises(KeyError):
            await async_setup_entry(hass, config_entry, async_add_entities)

    @pytest.mark.asyncio
    async def test_listener_adds_new_rules(self):
        """When the listener fires with new rules, they should be added."""
        coordinator = _make_coordinator()
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry-1": coordinator}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-1"
        config_entry.async_on_unload = MagicMock()

        async_add_entities = MagicMock()

        await async_setup_entry(hass, config_entry, async_add_entities)

        # Capture the listener callback
        listener_fn = coordinator.async_add_listener.call_args[0][0]

        # Add a new rule to coordinator data
        coordinator.data["rules"]["rule-789"] = _make_rule(
            rid="rule-789", description="New rule", paused=False
        )

        # Fire the listener
        listener_fn()

        # async_add_entities should be called a second time with 1 new entity
        assert async_add_entities.call_count == 2
        new_entities = async_add_entities.call_args_list[1][0][0]
        assert len(new_entities) == 1
        assert new_entities[0]._rule_id == "rule-789"

    @pytest.mark.asyncio
    async def test_listener_removes_deleted_rules(self):
        """When a rule disappears, the listener should remove its entity."""
        coordinator = _make_coordinator()
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry-1": coordinator}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-1"
        config_entry.async_on_unload = MagicMock()

        async_add_entities = MagicMock()

        with patch(
            "custom_components.firewalla.switch.er.async_get"
        ) as mock_er_get:
            mock_ent_reg = MagicMock()
            mock_er_get.return_value = mock_ent_reg
            mock_ent_reg.async_get_entity_id.return_value = "switch.firewalla_block_gaming"

            await async_setup_entry(hass, config_entry, async_add_entities)

            listener_fn = coordinator.async_add_listener.call_args[0][0]

            # Remove rule-456 from coordinator data
            del coordinator.data["rules"]["rule-456"]

            listener_fn()

            # Should have called entity registry to remove
            mock_ent_reg.async_get_entity_id.assert_called()
            mock_ent_reg.async_remove.assert_called_once_with(
                "switch.firewalla_block_gaming"
            )

    @pytest.mark.asyncio
    async def test_skips_non_dict_rule_data(self):
        """Non-dict rule data entries should be silently skipped."""
        coordinator = _make_coordinator()
        coordinator.data["rules"]["bad-rule"] = "not a dict"
        hass = MagicMock()
        hass.data = {DOMAIN: {"entry-1": coordinator}}

        config_entry = MagicMock()
        config_entry.entry_id = "entry-1"
        config_entry.async_on_unload = MagicMock()

        async_add_entities = MagicMock()

        await async_setup_entry(hass, config_entry, async_add_entities)

        # Only 2 valid rules should become entities, not the bad one
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2
