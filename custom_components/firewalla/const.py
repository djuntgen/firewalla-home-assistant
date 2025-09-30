"""Constants for the Firewalla integration."""

# Integration domain
DOMAIN = "firewalla"

# Configuration keys
CONF_MSP_URL = "msp_url"
CONF_ACCESS_TOKEN = "access_token"
CONF_BOX_GID = "box_gid"

# Default MSP API URL format (user should replace 'mydomain' with their actual domain)
DEFAULT_MSP_URL = "https://mydomain.firewalla.net"

# API endpoints (based on MSP API examples)
API_ENDPOINTS = {
    "boxes": "/boxes",
    "box_info": "/boxes/{gid}",
    "devices": "/devices",
    "rules": "/rules",
    "create_rule": "/rules",
    "pause_rule": "/rules/{rid}/pause",
    "unpause_rule": "/rules/{rid}/unpause",
}

# Timeouts and intervals
API_TIMEOUT = 30  # seconds
UPDATE_INTERVAL = 30  # seconds
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2

# Entity types
ENTITY_TYPES = {
    "block_switch": "block",
    "gaming_switch": "gaming",
    "device_sensor": "status",
    "rules_sensor": "rules",
}

# Device classes for gaming detection
GAMING_DEVICE_CLASSES = [
    "gaming_console",
    "xbox",
    "playstation",
    "nintendo",
    "steam",
]

# Rule types
RULE_TYPES = {
    "INTERNET_BLOCK": "internet",
    "GAMING_PAUSE": "gaming",
    "DEVICE_BLOCK": "device",
    "CATEGORY_BLOCK": "category",
}

# Rule actions
RULE_ACTIONS = {
    "BLOCK": "block",
    "ALLOW": "allow",
}

# Rule status values
RULE_STATUS = {
    "ACTIVE": "active",
    "PAUSED": "paused",
    "DISABLED": "disabled",
}

# Target prefixes for different rule targets
TARGET_PREFIXES = {
    "MAC": "mac:",
    "IP": "ip:",
    "CATEGORY": "category:",
    "DOMAIN": "domain:",
}

# Platforms
PLATFORMS = ["switch", "sensor"]

# Device information constants
DEVICE_INFO_FIELDS = [
    "name",
    "hostname", 
    "deviceClass",
    "ip",
    "mac",
    "online",
    "lastActiveTimestamp",
]

# Device class mappings for better model names
DEVICE_CLASS_MAPPINGS = {
    "gaming_console": "Gaming Console",
    "smart_tv": "Smart TV", 
    "mobile_phone": "Mobile Phone",
    "laptop": "Laptop",
    "desktop": "Desktop Computer",
    "tablet": "Tablet",
    "smart_speaker": "Smart Speaker",
    "iot_device": "IoT Device",
    "router": "Router",
    "access_point": "Access Point",
}