# Firewalla Integration Test Suite

This directory contains comprehensive unit tests for the Firewalla Home Assistant integration.

## Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Shared test fixtures and configuration
├── requirements.txt            # Test dependencies
├── test_coordinator.py         # Tests for MSP API client and data coordinator
├── test_config_flow.py         # Tests for configuration flow
├── test_switch.py              # Tests for switch entities (block/gaming)
├── test_sensor.py              # Tests for sensor entities (device status/rules)
├── test_init.py                # Tests for integration initialization
├── test_error_handling.py      # Tests for error scenarios and edge cases
└── README.md                   # This file
```

## Test Coverage

The test suite provides comprehensive coverage for:

### 1. MSP API Client (`test_coordinator.py`)
- ✅ Authentication success and failure scenarios
- ✅ HTTP request handling with retry logic
- ✅ Rate limiting and timeout handling
- ✅ Authentication refresh on 401 errors
- ✅ All API endpoints (boxes, devices, rules, create/pause/unpause)
- ✅ Response parsing and error mapping

### 2. Data Update Coordinator (`test_coordinator.py`)
- ✅ Data fetching and processing
- ✅ Device and rules data normalization
- ✅ Error handling and UpdateFailed scenarios
- ✅ Rule creation, pausing, and unpausing
- ✅ Cached data access methods

### 3. Configuration Flow (`test_config_flow.py`)
- ✅ User input validation
- ✅ MSP authentication testing
- ✅ Device discovery and selection
- ✅ Error handling for various failure modes
- ✅ Form validation and user feedback

### 4. Switch Entities (`test_switch.py`)
- ✅ Block switch functionality
- ✅ Gaming switch functionality
- ✅ Gaming device detection logic
- ✅ Entity state management
- ✅ Rule creation and management
- ✅ Device availability checking

### 5. Sensor Entities (`test_sensor.py`)
- ✅ Device status sensors
- ✅ Rules count sensor
- ✅ State attribute handling
- ✅ Timestamp processing
- ✅ Icon selection logic

### 6. Integration Setup (`test_init.py`)
- ✅ Entry setup and teardown
- ✅ Platform loading
- ✅ Error handling during setup
- ✅ Reload functionality
- ✅ Logging configuration

### 7. Error Handling (`test_error_handling.py`)
- ✅ Network timeouts and retries
- ✅ Connection failures
- ✅ Rate limiting responses
- ✅ Invalid API responses
- ✅ Data corruption scenarios
- ✅ Authentication failures

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install -r tests/requirements.txt
```

### Run All Tests

Using the test runner script:
```bash
python run_tests.py
```

Using pytest directly:
```bash
pytest tests/ -v
```

### Run Specific Tests

Run tests for a specific module:
```bash
python run_tests.py coordinator
pytest tests/test_coordinator.py -v
```

Run tests matching a pattern:
```bash
python run_tests.py "test_auth"
pytest -k "test_auth" -v
```

Run a specific test:
```bash
pytest tests/test_coordinator.py::TestFirewallaMSPClient::test_authenticate_success -v
```

### Run with Coverage

```bash
pytest tests/ --cov=custom_components.firewalla --cov-report=html --cov-report=term-missing
```

## Test Fixtures

The `conftest.py` file provides shared fixtures:

- `mock_config_entry`: Mock Home Assistant config entry
- `mock_box_info`: Mock Firewalla box information
- `mock_devices_data`: Mock device data from API
- `mock_rules_data`: Mock rules data from API
- `mock_coordinator_data`: Complete mock coordinator data
- `mock_aiohttp_session`: Mock aiohttp session
- `mock_hass`: Mock Home Assistant instance
- `mock_api_responses`: Mock API response data

## Test Categories

### Unit Tests
All tests are unit tests that mock external dependencies:
- No actual network calls to Firewalla API
- No Home Assistant core dependencies
- Fast execution (< 1 second per test)

### Mocking Strategy
- `aiohttp.ClientSession` for HTTP requests
- Home Assistant core components
- Time-dependent functions
- File system operations

### Async Testing
Uses `pytest-asyncio` for testing async functions:
- Automatic async test detection
- Proper event loop handling
- AsyncMock for async mocks

## Test Data

Mock data is designed to be realistic:
- Valid MAC addresses and IP addresses
- Realistic device names and types
- Proper Firewalla API response formats
- Edge cases and error conditions

## Continuous Integration

Tests are designed to run in CI environments:
- No external dependencies
- Deterministic results
- Clear error messages
- Proper exit codes

## Adding New Tests

When adding new functionality:

1. **Add test fixtures** in `conftest.py` if needed
2. **Create test file** following naming convention `test_*.py`
3. **Use descriptive test names** that explain what is being tested
4. **Mock external dependencies** to ensure isolation
5. **Test both success and failure scenarios**
6. **Include edge cases** and error conditions

### Test Naming Convention

```python
def test_<component>_<scenario>_<expected_result>():
    """Test description explaining what is being verified."""
```

Examples:
- `test_authenticate_success()` - Tests successful authentication
- `test_create_rule_missing_fields()` - Tests rule creation with missing data
- `test_switch_turn_on_api_failure()` - Tests switch behavior when API fails

## Debugging Tests

### Verbose Output
```bash
pytest tests/ -v -s
```

### Stop on First Failure
```bash
pytest tests/ -x
```

### Debug Specific Test
```bash
pytest tests/test_coordinator.py::TestFirewallaMSPClient::test_authenticate_success -v -s --pdb
```

### Show Warnings
```bash
pytest tests/ --disable-warnings=false
```

## Performance

The test suite is optimized for speed:
- All tests should complete in under 30 seconds
- Individual tests should complete in under 1 second
- Mocks are used to avoid I/O operations
- Fixtures are cached when appropriate

## Quality Assurance

Tests ensure:
- ✅ Code correctness
- ✅ Error handling robustness
- ✅ API contract compliance
- ✅ Home Assistant integration standards
- ✅ Backward compatibility
- ✅ Security best practices