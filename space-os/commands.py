# commands.py - Handle incoming command payloads from Ably
# Supports typed command envelopes with strict validation.
import config


# Valid command types
VALID_TYPES = {
    "message_sync",   # Inbox content delivery
    "art_sync",       # Art content delivery
    "set_mode",       # Change display mode
    "set_auto_rotate",# Toggle auto-rotate
    "set_brightness", # Set brightness level
    "sync_request",   # Request full re-sync
    "wifi_update",    # Encrypted WiFi credentials
}


def validate_command(payload):
    """
    Validate an incoming content sync command payload.
    Returns (message_id, width, height, frames, fps) or None if invalid.

    Used for message_sync and art_sync commands that carry content references.

    Expected payload:
        {
            "type": "message_sync" | "art_sync",
            "messageId": "uuid-string",
            "width": 32,
            "height": 32,
            "frames": 3,
            "fps": 10
        }
    """
    try:
        message_id = payload.get("messageId")
        width = payload.get("width", 0)
        height = payload.get("height", 0)
        frames = payload.get("frames", 1)
        fps = payload.get("fps", config.DEFAULT_FPS)

        if not message_id:
            print("[CMD] Missing messageId")
            return None

        # Validate dimensions match this board
        if width != config.BOARD_WIDTH or height != config.BOARD_HEIGHT:
            print(
                f"[CMD] Size mismatch: got {width}x{height}, "
                f"board is {config.BOARD_WIDTH}x{config.BOARD_HEIGHT}"
            )
            return None

        return (message_id, width, height, frames, fps)

    except Exception as e:
        print(f"[CMD] Validation error: {e}")
        return None


def validate_control_command(payload):
    """
    Validate a control command payload (non-content commands).
    Returns the command type string if valid, None otherwise.
    """
    cmd_type = payload.get("type")
    if cmd_type not in VALID_TYPES:
        print(f"[CMD] Unknown command type: {cmd_type}")
        return None
    return cmd_type


def get_command_type(payload):
    """
    Extract and validate the command type from a payload.
    Returns the type string, or None for legacy untyped payloads.
    """
    cmd_type = payload.get("type")

    # Legacy untyped command — has messageId but no type
    if cmd_type is None and payload.get("messageId"):
        return "message_sync"

    if cmd_type in VALID_TYPES:
        return cmd_type

    return None
