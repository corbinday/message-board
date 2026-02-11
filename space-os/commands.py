# commands.py - Handle incoming command payloads from Ably
import config


def validate_command(payload):
    """
    Validate an incoming command payload.
    Returns (message_id, width, height, frames, fps) or None if invalid.

    Expected payload:
        {
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
