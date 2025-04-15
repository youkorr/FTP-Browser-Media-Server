"""Constants for the FTP Browser integration."""

DOMAIN = "ftp_browser"

# Configuration
CONF_FTP_SERVER = "ftp_server"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PORT = "port"
CONF_SSL = "ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SHARE_DURATION = "share_duration"
CONF_ROOT_PATH = "root_path"

# Defaults
DEFAULT_PORT = 21
DEFAULT_SSL = False
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
DEFAULT_SHARE_DURATION = 24  # 24 hours
DEFAULT_ROOT_PATH = "/sdcard"  # Chemin racine par défaut

# Services
SERVICE_CREATE_SHARE = "create_share"
SERVICE_DELETE_SHARE = "delete_share"

# Storage
STORAGE_KEY = "ftp_browser.shared_links"
STORAGE_VERSION = 1

