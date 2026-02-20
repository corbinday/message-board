# command_schema.py - Typed command envelopes for SpaceOS Ably communication
#
# Shared command types used between the web backend and SpaceOS firmware.
# The backend publishes these via Ably; the firmware validates and routes them.
#
# WiFi credentials are encrypted with AES-128-CBC using a per-board symmetric
# key before being sent over Ably. The key is generated at provisioning and
# lives only in the DB (for encryption) and in secrets.py on the device
# (for decryption). WiFi passwords are NEVER stored in the database.

import base64
import json
import os
from enum import Enum
from typing import Optional


class CommandType(str, Enum):
    """Command types sent over the Ably commands channel."""

    # Content sync commands
    MESSAGE_SYNC = "message_sync"  # New message -> /inbox
    ART_SYNC = "art_sync"          # New art -> /art

    # Board control commands
    SET_MODE = "set_mode"                # Change display mode (inbox/art)
    SET_AUTO_ROTATE = "set_auto_rotate"  # Toggle auto-rotate
    SET_BRIGHTNESS = "set_brightness"    # Set brightness level

    # Sync commands
    SYNC_REQUEST = "sync_request"        # Request board to re-sync from server

    # Navigation commands
    SKIP_NEXT = "skip_next"              # Skip to next animation
    SKIP_PREV = "skip_prev"              # Skip to previous animation

    # WiFi commands (encrypted payload)
    WIFI_UPDATE = "wifi_update"          # Send encrypted WiFi creds to board


def build_message_sync(message_id: str, width: int, height: int, frames: int, fps: int) -> dict:
    """Build a message_sync command envelope for inbox delivery."""
    return {
        "type": CommandType.MESSAGE_SYNC.value,
        "messageId": message_id,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
    }


def build_art_sync(message_id: str, width: int, height: int, frames: int, fps: int) -> dict:
    """Build an art_sync command envelope for art directory delivery."""
    return {
        "type": CommandType.ART_SYNC.value,
        "messageId": message_id,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
    }


def build_set_mode(mode: str) -> dict:
    """Build a set_mode command envelope."""
    return {
        "type": CommandType.SET_MODE.value,
        "mode": mode,  # "inbox" or "art"
    }


def build_set_auto_rotate(enabled: bool) -> dict:
    """Build a set_auto_rotate command envelope."""
    return {
        "type": CommandType.SET_AUTO_ROTATE.value,
        "enabled": enabled,
    }


def build_set_brightness(brightness: float) -> dict:
    """Build a set_brightness command envelope."""
    return {
        "type": CommandType.SET_BRIGHTNESS.value,
        "brightness": max(0.0, min(1.0, brightness)),
    }


def build_sync_request() -> dict:
    """Build a sync_request command envelope."""
    return {
        "type": CommandType.SYNC_REQUEST.value,
    }


def build_skip_next() -> dict:
    """Build a skip_next command envelope."""
    return {
        "type": CommandType.SKIP_NEXT.value,
    }


def build_skip_prev() -> dict:
    """Build a skip_prev command envelope."""
    return {
        "type": CommandType.SKIP_PREV.value,
    }


def build_wifi_update(networks: list[dict], wifi_encryption_key: str) -> dict:
    """
    Build an encrypted wifi_update command envelope.

    The WiFi credentials are AES-128-CBC encrypted so they are opaque to Ably
    and to anyone without the board's wifi_encryption_key.

    Args:
        networks: List of {"ssid": "...", "password": "...", "priority": 0}
        wifi_encryption_key: Base64-encoded 16-byte AES key (from Board model)

    Returns:
        Command envelope with encrypted payload.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding

    key = base64.b64decode(wifi_encryption_key)
    iv = os.urandom(16)

    plaintext = json.dumps(networks).encode("utf-8")

    # PKCS7 pad to AES block size
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return {
        "type": CommandType.WIFI_UPDATE.value,
        "iv": base64.b64encode(iv).decode("ascii"),
        "payload": base64.b64encode(ciphertext).decode("ascii"),
    }


def generate_wifi_encryption_key() -> str:
    """Generate a new random AES-128 key, returned as base64 string."""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def validate_command_envelope(payload: dict) -> Optional[str]:
    """
    Validate a command envelope's type field.

    Returns the command type string if valid, None if invalid.
    """
    cmd_type = payload.get("type")
    if cmd_type is None:
        return None

    valid_types = {t.value for t in CommandType}
    if cmd_type not in valid_types:
        return None

    return cmd_type
