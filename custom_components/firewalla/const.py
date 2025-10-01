"""Constants for the Firewalla integration."""

# Integration domain
DOMAIN = "firewalla"

# Configuration keys
CONF_MSP_URL = "msp_url"
CONF_ACCESS_TOKEN = "access_token"
CONF_BOX_GID = "box_gid"
CONF_RULE_FILTERS = "rule_filters"
CONF_INCLUDE_FILTERS = "include_filters"
CONF_EXCLUDE_FILTERS = "exclude_filters"

# Default MSP URL format (user should replace 'mydomain' with their actual domain)
DEFAULT_MSP_URL_FORMAT = "mydomain.firewalla.net"

# MSP API base URLs
MSP_API_V1_BASE = "https://{domain}/v1"
MSP_API_V2_BASE = "https://{domain}/v2"

# API endpoints (based on official MSP API examples)
API_ENDPOINTS = {
    # V2 endpoints (preferred)
    "rules": "/rules",
    "rule_pause": "/rules/{rule_id}/pause",
    "rule_unpause": "/rules/{rule_id}/unpause",
    "rule_detail": "/rules/{rule_id}",
    
    # V1 endpoints (legacy, for fallback)
    "legacy_rules": "/rule/list",
}

# Rule filtering options
DEFAULT_RULE_FILTERS = {
    "include_filters": [],
    "exclude_filters": []
}

# Common rule filter examples for users
RULE_FILTER_EXAMPLES = {
    "status_filters": {
        "active_only": "status:active",
        "paused_only": "status:paused",
    },
    "action_filters": {
        "block_rules_only": "action:block",
        "allow_rules_only": "action:allow",
    },
    "type_filters": {
        "app_rules_only": "target.type:app",
        "category_rules_only": "target.type:category", 
        "domain_rules_only": "target.type:domain",
        "ip_rules_only": "target.type:ip",
        "internet_rules_only": "target.type:internet",
    },
    "device_filters": {
        "specific_device": 'device.id:"AA:BB:CC:DD:EE:FF"',
        "device_name_contains": "device.name:*iphone*",
    },
    "exclude_examples": {
        "exclude_paused": "-status:paused",
        "exclude_allow_rules": "-action:allow",
        "exclude_category_rules": "-target.type:category",
    }
}

# Query parameters for rule discovery
RULE_QUERY_PARAMS = {
    "status_active": "status:active",
    "status_paused": "status:paused", 
    "action_allow": "action:allow",
    "action_block": "action:block",
}

# Timeouts and intervals
API_TIMEOUT = 30  # seconds
UPDATE_INTERVAL = 30  # seconds minimum for API rate limiting
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2
RETRY_DELAYS = [1, 2, 4, 8]  # Exponential backoff delays in seconds

# Authentication
AUTH_HEADER_FORMAT = "Token {token}"
CONTENT_TYPE = "application/json"

# Entity ID formats
ENTITY_ID_FORMATS = {
    # Rule switch IDs are generated dynamically based on rule names
    "rules_sensor": "firewalla_rules_summary",
}

# Rule types from Firewalla API
RULE_TYPES = {
    "internet": "Internet Access",
    "category": "Category Block", 
    "domain": "Domain Block",
    "device": "Device Block",
    "gaming": "Gaming Block",
    "time": "Time-based Rule",
    "app": "Application Block",
}

# Rule actions
RULE_ACTIONS = {
    "block": "Block",
    "allow": "Allow",
    "qos": "QoS",
}

# Rule status values
RULE_STATUS = {
    "active": "Active",
    "paused": "Paused", 
    "disabled": "Disabled",
}

# Target type prefixes
TARGET_PREFIXES = {
    "mac": "MAC Address",
    "ip": "IP Address", 
    "category": "Category",
    "domain": "Domain",
    "app": "Application",
}

# Platforms
PLATFORMS = ["switch", "sensor"]

# Device information constants
DEVICE_MANUFACTURER = "Firewalla"
DEVICE_MODEL_MAPPINGS = {
    "gold": "Firewalla Gold",
    "purple": "Firewalla Purple", 
    "blue": "Firewalla Blue",
    "red": "Firewalla Red",
    "gold_se": "Firewalla Gold SE",
    "purple_se": "Firewalla Purple SE",
}

# Error messages for configuration flow
ERROR_MESSAGES = {
    "invalid_url_format": "MSP URL should be in format 'mydomain.firewalla.net' or 'https://mydomain.firewalla.net'",
    "auth_failed": "Invalid access token. Please check your token in MSP settings.",
    "connection_failed": "Cannot connect to MSP service. Please check your internet connection and MSP URL. Make sure the domain is correct (e.g., mydomain.firewalla.net).",
    "no_boxes": "No Firewalla boxes found in your MSP account. Please ensure your box is properly registered.",
    "rule_access_failed": "Cannot access rules. Please check your MSP permissions.",
    "timeout": "Connection timed out. Please try again.",
    "unknown_error": "An unexpected error occurred. Please check your configuration.",
}

# Rule attribute keys for entity attributes
RULE_ATTRIBUTES = [
    "rule_id",
    "rule_type", 
    "target",
    "target_name",
    "action",
    "priority",
    "schedule",
    "created_at",
    "modified_at",
    "description",
]

# Sensor attributes for rules summary
SENSOR_ATTRIBUTES = [
    "total_rules",
    "active_rules",
    "paused_rules", 
    "rules_by_type",
    "last_updated",
    "api_status",
]