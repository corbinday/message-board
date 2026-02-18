# config.py - SpaceOS Configuration
# Load device-specific settings from secrets.py on the Pico filesystem

try:
    from secrets import secrets
except ImportError:
    print("[FATAL] secrets.py not found. Generate one from the web dashboard.")
    raise SystemExit

# WiFi - primary network from secrets.py (provisioned via secrets.py download)
WIFI_SSID = secrets["ssid"]
WIFI_PASSWORD = secrets["password"]

# WiFi encryption key — AES-128 key (base64) for decrypting WiFi credentials
# received via Ably. Generated at provisioning, stored in secrets.py.
WIFI_ENCRYPTION_KEY = secrets.get("wifi_encryption_key", "")

# WiFi networks file — additional networks received via encrypted Ably commands
# are stored here on the device's local filesystem (never sent to the server DB).
WIFI_NETWORKS_FILE = "/wifi_networks.json"

# Server
API_URL = secrets["api_url"]
BOARD_SECRET_KEY = secrets["pmb_secret_key"]

# Board identity (set after first token exchange)
BOARD_ID = secrets.get("board_id", "")
USER_ID = secrets.get("user_id", "")

# Display dimensions (set based on board type)
# Stellar: 16x16, Galactic: 53x11, Cosmic: 32x32
BOARD_WIDTH = int(secrets.get("board_width", 32))
BOARD_HEIGHT = int(secrets.get("board_height", 32))
BOARD_TYPE = secrets.get("board_type", "Cosmic")

# Ably MQTT
ABLY_MQTT_HOST = "mqtt.ably.io"
ABLY_MQTT_PORT = 8883

# Storage
INBOX_DIR = "/inbox"
ART_DIR = "/art"
FIFO_CAP = 20

# Animation
DEFAULT_FPS = 10

# Reconnection
RECONNECT_INTERVAL_MS = 60000  # 60 seconds between reconnection attempts

# Local settings file (persisted on device between reboots)
SETTINGS_FILE = "/settings.json"
