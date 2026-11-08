"""Integration tests using the real Firewalla MSP API.

These tests talk to a live Firewalla MSP account, so they never run by default.
Opt in with environment variables (never put credentials in this file):

    FIREWALLA_REAL_API=1          run the read-only tests
    FIREWALLA_MSP_DOMAIN=...      your MSP domain, e.g. mydomain.firewalla.net
    FIREWALLA_ACCESS_TOKEN=...    your MSP personal access token
    FIREWALLA_REAL_API_WRITE=1    also run the test that pauses and resumes a
                                  live rule on your firewall

See tests/README.md.
"""

import os

import pytest
import pytest_socket
import aiohttp
import asyncio
from typing import Dict, Any

from custom_components.firewalla.coordinator import (
    FirewallaMSPClient,
    FirewallaDataUpdateCoordinator,
)
from custom_components.firewalla.const import API_ENDPOINTS, MSP_API_V2_BASE

REAL_API_ENABLED = os.environ.get("FIREWALLA_REAL_API") == "1"
REAL_API_WRITE_ENABLED = os.environ.get("FIREWALLA_REAL_API_WRITE") == "1"
TEST_MSP_DOMAIN = os.environ.get("FIREWALLA_MSP_DOMAIN", "")
TEST_ACCESS_TOKEN = os.environ.get("FIREWALLA_ACCESS_TOKEN", "")

if not REAL_API_ENABLED:
    _SKIP_REASON = "Live Firewalla API tests are opt-in: set FIREWALLA_REAL_API=1"
elif not (TEST_MSP_DOMAIN and TEST_ACCESS_TOKEN):
    _SKIP_REASON = (
        "FIREWALLA_REAL_API=1 also needs FIREWALLA_MSP_DOMAIN and "
        "FIREWALLA_ACCESS_TOKEN to be set"
    )
else:
    _SKIP_REASON = ""

pytestmark = pytest.mark.skipif(bool(_SKIP_REASON), reason=_SKIP_REASON)


def _rule_status(rule: Dict[str, Any]) -> str:
    """Return "paused" or "active" for a rule as the MSP API reports it."""
    if rule.get("status") == "paused" or rule.get("paused") is True:
        return "paused"
    return rule.get("status") or "active"


def _live_session() -> aiohttp.ClientSession:
    """Create a session for talking to the real MSP API.

    Uses aiohttp's ThreadedResolver (the OS resolver) instead of aiodns: with
    Home Assistant 2025.1.4's test dependencies, aiodns 3.2.0 fails with pycares 5 ("getaddrinfo()
    takes 3 positional arguments") and pycares leaves a shutdown thread that
    the Home Assistant test plugin reports as a lingering thread.
    """
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    )


@pytest.fixture(autouse=True)
def allow_network():
    """Let the opted-in live tests open real network connections.

    pytest-homeassistant-custom-component blocks sockets before every test
    (socket_allow_hosts(["127.0.0.1"]) then disable_socket()). This module only
    runs when FIREWALLA_REAL_API=1, so lift both restrictions for its tests and
    put them back afterwards so other tests stay blocked.
    """
    # _remove_restrictions() is private pytest_socket API (0.7.0): it undoes
    # both disable_socket() and socket_allow_hosts(). The public socket_enabled
    # fixture lifts only the first.
    pytest_socket._remove_restrictions()
    yield
    pytest_socket.socket_allow_hosts(["127.0.0.1"])
    pytest_socket.disable_socket(allow_unix_socket=True)


@pytest.fixture
async def real_api_session():
    """Create a real aiohttp session for API testing."""
    session = _live_session()
    yield session
    await session.close()


@pytest.fixture
def real_msp_client(real_api_session):
    """Create a real MSP client for testing."""
    return FirewallaMSPClient(
        session=real_api_session,
        msp_domain=TEST_MSP_DOMAIN,
        access_token=TEST_ACCESS_TOKEN,
    )


class TestRealFirewallaMSPAPI:
    """Test against real Firewalla MSP API to validate data structures and functionality."""

    @pytest.mark.asyncio
    async def test_real_api_authentication(self, real_msp_client):
        """Test authentication against real MSP API."""
        result = await real_msp_client.authenticate()

        assert result is True, "Authentication should succeed with valid credentials"
        assert real_msp_client.is_authenticated is True

    @pytest.mark.asyncio
    async def test_real_api_get_rules(self, real_msp_client):
        """Test getting rules from real MSP API and validate data structure."""
        # Authenticate first
        auth_result = await real_msp_client.authenticate()
        assert auth_result is True, "Authentication must succeed before testing rules"

        # Get all rules
        rules_response = await real_msp_client.get_rules()

        assert rules_response is not None, "Rules response should not be None"

        # Log the actual response structure for debugging
        print(f"\nActual rules response type: {type(rules_response)}")

        if isinstance(rules_response, dict):
            print(f"Response keys: {list(rules_response.keys())}")
            if "results" in rules_response:
                print(f"Number of rules in results: {len(rules_response['results'])}")
                if rules_response["results"]:
                    sample_rule = rules_response["results"][0]
                    print(f"Sample rule keys: {list(sample_rule.keys())}")
                    print(f"Sample rule: {sample_rule}")
        elif isinstance(rules_response, list):
            print(f"Direct list with {len(rules_response)} rules")
            if rules_response:
                sample_rule = rules_response[0]
                print(f"Sample rule keys: {list(sample_rule.keys())}")
                print(f"Sample rule: {sample_rule}")

        # Validate we got some rules
        if isinstance(rules_response, dict) and "results" in rules_response:
            assert len(rules_response["results"]) > 0, "Should have at least one rule"
        elif isinstance(rules_response, list):
            assert len(rules_response) > 0, "Should have at least one rule"
        else:
            pytest.fail(f"Unexpected rules response format: {type(rules_response)}")

    @pytest.mark.asyncio
    async def test_real_api_get_rules_with_query(self, real_msp_client):
        """Test getting rules with query parameters."""
        # Authenticate first
        auth_result = await real_msp_client.authenticate()
        assert auth_result is True

        # Test different query parameters
        queries = [
            "status:active",
            "status:paused",
            "action:block",
            "action:allow",
        ]

        for query in queries:
            print(f"\nTesting query: {query}")
            rules_response = await real_msp_client.get_rules(query)

            assert (
                rules_response is not None
            ), f"Query '{query}' should return a response"

            # Log results for each query
            if isinstance(rules_response, dict) and "results" in rules_response:
                print(
                    f"Query '{query}' returned {len(rules_response['results'])} rules"
                )
            elif isinstance(rules_response, list):
                print(f"Query '{query}' returned {len(rules_response)} rules")

    @pytest.mark.asyncio
    async def test_real_api_rule_data_structure(self, real_msp_client):
        """Test and document the actual rule data structure from the API."""
        # Authenticate first
        auth_result = await real_msp_client.authenticate()
        assert auth_result is True

        # Get rules to analyze structure
        rules_response = await real_msp_client.get_rules()

        # Extract rules list
        rules_list = []
        if isinstance(rules_response, dict) and "results" in rules_response:
            rules_list = rules_response["results"]
        elif isinstance(rules_response, list):
            rules_list = rules_response

        assert len(rules_list) > 0, "Need at least one rule to analyze structure"

        # Analyze the first few rules to understand the data structure
        print(f"\nAnalyzing {min(3, len(rules_list))} rules for data structure:")

        common_fields = set()
        all_fields = set()

        for i, rule in enumerate(rules_list[:3]):
            print(f"\nRule {i+1}:")
            print(f"  Type: {type(rule)}")
            print(
                f"  Keys: {list(rule.keys()) if isinstance(rule, dict) else 'Not a dict'}"
            )

            if isinstance(rule, dict):
                for key, value in rule.items():
                    print(f"  {key}: {value} ({type(value).__name__})")
                    all_fields.add(key)
                    if i == 0:
                        common_fields = set(rule.keys())
                    else:
                        common_fields &= set(rule.keys())

        print(f"\nCommon fields across all rules: {sorted(common_fields)}")
        print(f"All fields found: {sorted(all_fields)}")

        # Validate expected fields exist
        expected_fields = ["id", "type"]
        for field in expected_fields:
            assert (
                field in all_fields
            ), f"Expected field '{field}' not found in rule data"

    @pytest.mark.skipif(
        not _SKIP_REASON and not REAL_API_WRITE_ENABLED,
        reason="Pauses and resumes a live firewall rule: set FIREWALLA_REAL_API_WRITE=1",
    )
    @pytest.mark.asyncio
    async def test_real_api_pause_resume_cycle(self, real_msp_client):
        """Test pause/resume cycle with a real rule (if safe to do so)."""
        # Authenticate first
        auth_result = await real_msp_client.authenticate()
        assert auth_result is True

        # Get rules to find one we can safely test with
        rules_response = await real_msp_client.get_rules()

        # Extract rules list
        rules_list = []
        if isinstance(rules_response, dict) and "results" in rules_response:
            rules_list = rules_response["results"]
        elif isinstance(rules_response, list):
            rules_list = rules_response

        if not rules_list:
            pytest.skip("No rules available for pause/resume testing")

        # Find a rule that's currently active (not paused) for testing
        test_rule = None
        for rule in rules_list:
            if isinstance(rule, dict) and _rule_status(rule) == "active":
                test_rule = rule
                break

        if not test_rule:
            pytest.skip("No active rules available for pause/resume testing")

        rule_id = test_rule.get("id")
        assert rule_id, "Test rule must have an ID"

        print(f"\nTesting pause/resume cycle with rule: {rule_id}")

        # From the moment we ask to pause, always try to resume the rule, even
        # if a later step fails, so a live rule is never left paused. Failures
        # fail the test; they are never turned into skips.
        try:
            await real_msp_client.pause_rule(rule_id)
            await asyncio.sleep(2)

            paused_status = await real_msp_client.get_rule_status(rule_id)
            assert (
                _rule_status(paused_status) == "paused"
            ), f"Rule {rule_id} should be paused after pause_rule"
        finally:
            try:
                await real_msp_client.resume_rule(rule_id)
            except Exception as err:
                pytest.fail(
                    f"Could not resume rule {rule_id} after pausing it; it may still be "
                    f"PAUSED on the firewall and needs resuming by hand: {err!r}"
                )

        await asyncio.sleep(2)
        final_status = await real_msp_client.get_rule_status(rule_id)
        assert (
            _rule_status(final_status) == "active"
        ), f"Rule {rule_id} should be active again after resume_rule"

    @pytest.mark.asyncio
    async def test_real_api_error_handling(self, real_api_session):
        """Test error handling with real API using invalid credentials."""
        # Test with invalid token
        invalid_client = FirewallaMSPClient(
            session=real_api_session,
            msp_domain=TEST_MSP_DOMAIN,
            access_token="invalid_token_123",
        )

        result = await invalid_client.authenticate()
        assert result is False, "Authentication should fail with invalid token"

        # Test with invalid domain
        invalid_domain_client = FirewallaMSPClient(
            session=real_api_session,
            msp_domain="invalid.firewalla.net",
            access_token="invalid_token_123",
        )

        result = await invalid_domain_client.authenticate()
        assert result is False, "Authentication should fail with invalid domain"


class TestRealDataProcessing:
    """Test data processing with real API data structures."""

    @pytest.mark.asyncio
    async def test_coordinator_with_real_data(self, real_api_session):
        """Test coordinator data processing with real API data."""

        # Create a mock hass object
        class MockHass:
            pass

        mock_hass = MockHass()

        # Create coordinator with real credentials
        coordinator = FirewallaDataUpdateCoordinator(
            hass=mock_hass,
            session=real_api_session,
            msp_domain=TEST_MSP_DOMAIN,
            access_token=TEST_ACCESS_TOKEN,
            box_gid="test-box",
        )

        try:
            # Test data update
            data = await coordinator._async_update_data()

            print(f"\nCoordinator data structure:")
            print(f"Data keys: {list(data.keys())}")

            if "rules" in data:
                rules = data["rules"]
                print(f"Number of processed rules: {len(rules)}")

                if rules:
                    sample_rule_id = list(rules.keys())[0]
                    sample_rule = rules[sample_rule_id]
                    print(f"Sample processed rule keys: {list(sample_rule.keys())}")
                    print(f"Sample processed rule: {sample_rule}")

            if "rule_count" in data:
                rule_count = data["rule_count"]
                print(f"Rule count statistics: {rule_count}")

            # Validate data structure
            assert "rules" in data, "Data should contain rules"
            assert "rule_count" in data, "Data should contain rule_count"
            assert isinstance(data["rules"], dict), "Rules should be a dictionary"
            assert isinstance(
                data["rule_count"], dict
            ), "Rule count should be a dictionary"

        except Exception as e:
            print(f"Error testing coordinator with real data: {e}")
            raise

    @pytest.mark.asyncio
    async def test_rule_name_generation_with_real_data(self, real_api_session):
        """Test entity name generation with real rule data."""
        from custom_components.firewalla.switch import FirewallaRuleSwitch
        from unittest.mock import MagicMock

        # Get real rule data
        client = FirewallaMSPClient(
            session=real_api_session,
            msp_domain=TEST_MSP_DOMAIN,
            access_token=TEST_ACCESS_TOKEN,
        )

        auth_result = await client.authenticate()
        assert auth_result is True

        rules_response = await client.get_rules()

        # Extract rules list
        rules_list = []
        if isinstance(rules_response, dict) and "results" in rules_response:
            rules_list = rules_response["results"]
        elif isinstance(rules_response, list):
            rules_list = rules_response

        assert len(rules_list) > 0, "Need rules to test name generation"

        # Test name generation with first few rules
        mock_coordinator = MagicMock()

        print(
            f"\nTesting entity name generation with {min(5, len(rules_list))} real rules:"
        )

        for i, rule_data in enumerate(rules_list[:5]):
            rule_id = rule_data.get("id", f"rule-{i}")

            # Create switch entity
            switch = FirewallaRuleSwitch(mock_coordinator, rule_id, rule_data)

            print(f"\nRule {i+1}:")
            print(f"  Rule ID: {rule_id}")
            print(f"  Rule Data: {rule_data}")
            print(f"  Generated Name: {switch._generate_entity_name(rule_data)}")
            print(f"  Entity Unique ID: {switch.unique_id}")

            # Validate name generation
            generated_name = switch._generate_entity_name(rule_data)
            assert (
                generated_name != "Unknown"
            ), f"Generated name should not be 'Unknown' for rule {rule_id}"
            assert (
                len(generated_name) > 0
            ), f"Generated name should not be empty for rule {rule_id}"


@pytest.mark.asyncio
async def test_api_endpoints_validation():
    """Test that our API endpoints work with the real API."""
    async with _live_session() as session:
        base_url = MSP_API_V2_BASE.format(domain=TEST_MSP_DOMAIN)
        headers = {
            "Authorization": f"Token {TEST_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        print(f"\nTesting API endpoints against: {base_url}")

        # Test rules endpoint
        rules_url = f"{base_url}{API_ENDPOINTS['rules']}"
        print(f"Testing rules endpoint: {rules_url}")

        try:
            async with session.get(
                rules_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                print(f"Rules endpoint status: {response.status}")

                if response.status == 200:
                    data = await response.json()
                    print(f"Rules endpoint response type: {type(data)}")
                    print(
                        f"Rules endpoint response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
                    )
                else:
                    error_text = await response.text()
                    print(f"Rules endpoint error: {error_text}")

        except Exception as e:
            print(f"Error testing rules endpoint: {e}")
            raise


if __name__ == "__main__":
    # Run a quick test to validate API access
    if not (TEST_MSP_DOMAIN and TEST_ACCESS_TOKEN):
        raise SystemExit(
            "Set FIREWALLA_MSP_DOMAIN and FIREWALLA_ACCESS_TOKEN to run this check"
        )

    async def quick_test():
        async with _live_session() as session:
            client = FirewallaMSPClient(
                session=session,
                msp_domain=TEST_MSP_DOMAIN,
                access_token=TEST_ACCESS_TOKEN,
            )

            print("Testing authentication...")
            auth_result = await client.authenticate()
            print(f"Authentication result: {auth_result}")

            if auth_result:
                print("Getting rules...")
                rules = await client.get_rules()
                print(f"Rules response type: {type(rules)}")

                if isinstance(rules, dict) and "results" in rules:
                    print(f"Found {len(rules['results'])} rules")
                    if rules["results"]:
                        print(f"Sample rule: {rules['results'][0]}")
                elif isinstance(rules, list):
                    print(f"Found {len(rules)} rules")
                    if rules:
                        print(f"Sample rule: {rules[0]}")

    asyncio.run(quick_test())
