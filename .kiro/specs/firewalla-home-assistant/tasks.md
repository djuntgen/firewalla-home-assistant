# Implementation Plan

- [x] 1. Set up HACS-compatible project structure and core constants
  - Create directory structure: `custom_components/firewalla/` with all required files
  - Define integration constants in `const.py` (domain, MSP API endpoints, timeouts, rule type mappings)
  - Create HACS-compliant `manifest.json` with proper metadata, dependencies, and version
  - Add `strings.json` for localization support and user-friendly configuration text
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 2. Implement MSP API client with rule-focused endpoints
  - Create `FirewallaMSPClient` class in `coordinator.py` with aiohttp session management
  - Implement MSP authentication using Token header format from official examples
  - Add rule discovery using `/v2/rules` endpoint with query parameter support
  - Implement rule pause/unpause using `/v2/rules/{rule_id}/pause` endpoints
  - Add exponential backoff retry logic and comprehensive error handling
  - _Requirements: 1.1, 1.2, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3. Create user-friendly configuration flow with data persistence
  - Implement `async_step_user()` for MSP URL and token input with format validation
  - Add MSP URL validation for `mydomain.firewalla.net` format
  - Implement data persistence to preserve user input on validation failures
  - Add `async_step_box_selection()` for multiple box scenarios with descriptive names
  - Create comprehensive error handling with specific, actionable error messages
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 4. Implement rule discovery and synchronization coordinator
  - Create `FirewallaDataUpdateCoordinator` inheriting from `DataUpdateCoordinator`
  - Implement `_async_update_data()` to fetch all rules using `/v2/rules` endpoint
  - Add rule change detection to identify new, deleted, and modified rules
  - Implement intelligent caching with minimum 30-second intervals for API rate limiting
  - Add automatic entity creation/removal based on rule discovery results
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.1, 10.2, 10.3_

- [x] 5. Create rule management API methods
  - Implement `async_get_rules()` using `/v2/rules` with optional query filters
  - Add `async_pause_rule(rule_id)` using `POST /v2/rules/{rule_id}/pause`
  - Create `async_unpause_rule(rule_id)` using `POST /v2/rules/{rule_id}/unpause`
  - Implement rule change detection by comparing rule lists and metadata
  - Add comprehensive error handling for rule operations with specific error messages
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 6. Implement integration initialization with rule-focused setup
  - Create `async_setup_entry()` in `__init__.py` to initialize coordinator with rule discovery
  - Set up switch platform for rule control entities with proper async loading
  - Set up sensor platform for rule statistics with proper async loading
  - Implement `async_unload_entry()` for clean resource cleanup and session management
  - Add integration-wide error handling and logging setup
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Create rule control switch entities with rich metadata
  - Implement `FirewallaRuleSwitch` class inheriting from `CoordinatorEntity` and `SwitchEntity`
  - Create unique IDs with format `firewalla_rule_{rule_id}` for consistency across restarts
  - Implement `async_turn_on()` to unpause rules using MSP API with error handling
  - Implement `async_turn_off()` to pause rules using MSP API (preserves rule configuration)
  - Add proper state tracking based on rule paused status (ON = active, OFF = paused)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8. Implement rich rule metadata as entity attributes
  - Add comprehensive rule attributes: type, target, target_name, action, priority
  - Include rule timing information: created_at, modified_at, schedule details
  - Implement descriptive entity names based on rule descriptions and target information
  - Add entity name disambiguation for rules with similar names
  - Ensure attribute updates when rule metadata changes
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 9. Create rule statistics sensor entity
  - Implement `FirewallaRulesSensor` inheriting from `CoordinatorEntity` and `SensorEntity`
  - Use entity ID `firewalla_rules_summary` with total rule count as native value
  - Add comprehensive attributes: total_rules, active_rules, paused_rules, rules_by_type
  - Include integration health information: last_updated, api_status
  - Implement proper device info linking and state classes for Home Assistant UI
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 10. Implement automatic entity lifecycle management
  - Add automatic switch entity creation when new rules are discovered
  - Implement automatic switch entity removal when rules are deleted from Firewalla
  - Create entity update mechanism when rule metadata changes
  - Add debouncing to prevent excessive entity updates during bulk rule changes
  - Ensure entity registry cleanup for removed rules
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 11. Implement comprehensive error handling and structured logging
  - Add `_LOGGER` instances to all modules with appropriate log levels and structured messages
  - Map Firewalla MSP API errors to specific Home Assistant exceptions with user-friendly messages
  - Implement graceful error handling in all entity methods with proper state management
  - Add debug logging for API requests/responses, rule state changes, and entity operations
  - Create error recovery mechanisms and user notification strategies
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 12. Add comprehensive device information and entity attributes
  - Implement device info with manufacturer="Firewalla", model, firmware version, and identifiers
  - Create descriptive entity names based on rule descriptions with fallback to rule type and target
  - Handle multiple Firewalla boxes with proper entity name disambiguation and device grouping
  - Ensure entity attributes refresh efficiently without requiring integration reload
  - Add proper Home Assistant device registry integration for rule entities
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 13. Create comprehensive unit tests with HACS quality standards
  - Write tests for MSP API client with mocked HTTP responses covering rule endpoints and error scenarios
  - Test coordinator rule discovery logic, caching, retry mechanisms, and change detection
  - Create entity tests verifying rule state management, attribute handling, and lifecycle management
  - Test configuration flow with MSP authentication, URL validation, and error scenarios
  - Add integration tests for end-to-end rule control functionality
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 14. Implement integration entry point and platform setup with rule focus
  - Wire together all components in `__init__.py` with proper async setup and error handling
  - Ensure switch and sensor platforms are loaded correctly with proper dependency management
  - Add integration reload capability for configuration updates without service disruption
  - Verify rule discovery and entity creation work together in comprehensive integration tests
  - Implement health checks and integration status monitoring
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 15. Create HACS publication documentation and repository structure
  - Create comprehensive README.md with installation instructions, MSP setup guide, and usage examples
  - Add info.md for HACS with rule control feature overview and integration capabilities
  - Create LICENSE file with appropriate open source license
  - Set up GitHub repository structure with proper workflows and issue templates
  - Add CHANGELOG.md with version history and breaking changes documentation
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 16. Implement HACS validation and quality assurance
  - Validate manifest.json meets all HACS requirements with proper metadata
  - Ensure code follows Home Assistant coding standards and Python best practices
  - Add type hints throughout codebase for better code quality and IDE support
  - Implement GitHub Actions workflow for HACS validation and automated testing
  - Create semantic versioning strategy with proper Git tags and GitHub releases
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 17. Add localization support and user experience enhancements
  - Create translations directory with en.json for English localization
  - Add user-friendly entity names and descriptions in strings.json for rule entities
  - Implement proper error message localization for configuration flow
  - Add entity icons and device classes for better Home Assistant UI integration
  - Create user documentation with MSP setup troubleshooting guide and common issues
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 18. Perform final integration testing and HACS preparation
  - Conduct comprehensive end-to-end testing with real Firewalla MSP API
  - Validate rule discovery, entity creation, and pause/unpause functionality
  - Test error scenarios, recovery mechanisms, and edge cases
  - Verify HACS installation process and integration setup flow
  - Create final documentation review and prepare for HACS submission
  - _Requirements: 6.5, 7.5, 8.5, 9.5, 10.5_