"""Constants for the Card Installer integration."""

DOMAIN = "card_installer"

# Configuration keys
CONF_REPO_URL = "repo_url"
CONF_BRANCH = "branch"
CONF_AUTO_UPDATE = "auto_update"
CONF_UPDATE_INTERVAL = "update_interval"

# Configuration keys (alternative names for compatibility)
REPO_URL = "repo_url"
BRANCH = "branch"
AUTO_UPDATE = "auto_update"
UPDATE_INTERVAL = "update_interval"

# Default values
DEFAULT_BRANCH = "master"
DEFAULT_AUTO_UPDATE = True
DEFAULT_UPDATE_INTERVAL = 3600  # 1 hour in seconds

# Storage paths
WWW_DIR = "www"
COMMUNITY_DIR = "community"
RESOURCES_FILE = ".storage/lovelace_resources"

# Service names
SERVICE_INSTALL_CARDS = "install_cards"
SERVICE_UPDATE_CARDS = "update_cards"
SERVICE_REMOVE_CARD = "remove_card"

# Service data keys
SERVICE_DATA_URL = "url"
SERVICE_DATA_FILENAME = "filename"

