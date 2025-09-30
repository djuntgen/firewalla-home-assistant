# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-12-19

### Added
- Initial release of Firewalla Home Assistant integration
- MSP API client with comprehensive error handling and retry logic
- Configuration flow for MSP setup with device discovery
- Internet blocking switch entities for device control
- Gaming pause switch entities with smart device detection
- Device status sensor entities with rich attributes
- Rules count sensor entity for monitoring active rules
- Comprehensive unit tests with HACS quality standards
- Full HACS compatibility and documentation
- Automatic device discovery and selection
- Rate limiting and intelligent caching
- Robust error handling and recovery mechanisms
- Localization support with user-friendly messages

### Features
- **Device Control**: Block/unblock internet access for individual devices
- **Gaming Management**: Pause/resume gaming for gaming-capable devices
- **Device Monitoring**: Real-time online/offline status tracking
- **Rules Management**: Track and manage integration-created rules
- **Smart Detection**: Automatic identification of gaming devices
- **Error Recovery**: Automatic retry with exponential backoff
- **API Integration**: Full Firewalla MSP API integration
- **HACS Support**: Full HACS compatibility for easy installation

### Technical Details
- Minimum Home Assistant version: 2023.1.0
- Python 3.10+ compatibility
- Async/await throughout for optimal performance
- Type hints for better code quality
- Comprehensive logging for debugging
- Extensive test coverage (>95%)

### Requirements
- Firewalla MSP (Managed Service Provider) account
- Personal Access Token from MSP account
- Firewalla device accessible via MSP API
- Home Assistant 2023.1.0 or later

### Known Limitations
- Requires MSP API access (not available for all Firewalla users)
- Gaming device detection based on device class and naming patterns
- API rate limits may affect rapid state changes
- Rules are managed per-device (not per-application)

### Breaking Changes
- None (initial release)

### Migration Notes
- None (initial release)

## [Unreleased]

### Planned Features
- Support for additional rule types (category blocking, time-based rules)
- Enhanced gaming device detection algorithms
- Integration with Firewalla's alarm system
- Support for multiple Firewalla devices in single integration
- Advanced scheduling and automation features
- Performance optimizations and caching improvements

### Under Consideration
- Direct API support (non-MSP) for broader compatibility
- Mobile app integration for remote control
- Advanced reporting and analytics
- Integration with other security platforms
- Custom rule templates and presets