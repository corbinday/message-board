# main.py - SpaceOS boot orchestration and main loop
import time
import gc
import urequests
import json

import config
import wifi
import ably_mqtt
import commands
import space_pack
import storage
import player
import buttons


# State
_current_dir = config.INBOX_DIR  # Current browsing directory
_current_index = 0                # Current message index
_auto_rotate = False              # Auto-rotate mode
_paused = False                   # Playback paused
_message_list = []                # Current directory listing
_pending_commands = []            # Queue of incoming commands


def _detect_board():
    """Detect board hardware and return (unicorn, graphics, switch constants)."""
    board_type = config.BOARD_TYPE

    if board_type == "Stellar":
        from stellar import StellarUnicorn
        from picographics import PicoGraphics, DISPLAY_STELLAR_UNICORN
        cu = StellarUnicorn()
        gfx = PicoGraphics(DISPLAY_STELLAR_UNICORN)
        return cu, gfx, cu.SWITCH_A, cu.SWITCH_B, cu.SWITCH_C, cu.SWITCH_D

    elif board_type == "Galactic":
        from galactic import GalacticUnicorn
        from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
        cu = GalacticUnicorn()
        gfx = PicoGraphics(DISPLAY_GALACTIC_UNICORN)
        return cu, gfx, cu.SWITCH_A, cu.SWITCH_B, cu.SWITCH_C, cu.SWITCH_D

    else:  # Cosmic (default)
        from cosmic import CosmicUnicorn
        from picographics import PicoGraphics, DISPLAY_COSMIC_UNICORN
        cu = CosmicUnicorn()
        gfx = PicoGraphics(DISPLAY_COSMIC_UNICORN)
        return cu, gfx, cu.SWITCH_A, cu.SWITCH_B, cu.SWITCH_C, cu.SWITCH_D


def _get_ably_token():
    """Request an Ably token from the server."""
    url = f"{config.API_URL}/boards/{config.BOARD_ID}/ably-token"
    headers = {
        "X-Board-Secret": config.BOARD_SECRET_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = urequests.post(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            response.close()
            return data.get("token")
        else:
            print(f"[BOOT] Token request failed: HTTP {response.status_code}")
            response.close()
            return None
    except Exception as e:
        print(f"[BOOT] Token request error: {e}")
        return None


def _on_command(payload):
    """Handle incoming Ably command messages."""
    _pending_commands.append(payload)
    print(f"[MAIN] Command queued: {payload.get('messageId', 'unknown')}")


def _process_commands():
    """Process pending command queue."""
    global _current_index, _message_list

    while _pending_commands:
        payload = _pending_commands.pop(0)
        result = commands.validate_command(payload)

        if result is None:
            continue

        message_id, width, height, frames, fps = result
        print(f"[MAIN] Processing message {message_id} ({width}x{height}, {frames}f)")

        # Show warp animation while downloading
        player.show_warp_animation(width, height)

        # Download Space Pack
        sp = space_pack.download(message_id)

        if sp is None:
            print("[MAIN] Space Pack download failed")
            continue

        # Save to inbox
        metadata = {
            "sender": sp["sender"],
            "fps": sp["fps"],
            "is_anim": sp["is_anim"],
            "width": width,
            "height": height,
            "frames": frames,
        }
        storage.save_message(sp["message_id"], sp["pixel_data"], metadata)

        # Refresh message list and display new message
        _message_list = storage.list_messages(_current_dir)
        if sp["message_id"] in _message_list:
            _current_index = _message_list.index(sp["message_id"])

        # Render the new message immediately
        _render_current()

        # Send read receipt after first animation loop
        if sp["is_anim"] and frames > 1:
            player.play_animation(
                sp["pixel_data"],
                width, height, frames, fps,
                on_loop_complete=lambda: ably_mqtt.publish_read_receipt(sp["message_id"]),
            )
        else:
            player.render_static(sp["pixel_data"], width, height)
            ably_mqtt.publish_read_receipt(sp["message_id"])


def _render_current():
    """Render the currently selected message/art."""
    global _message_list

    if not _message_list:
        _message_list = storage.list_messages(_current_dir)

    if not _message_list:
        player.clear_display()
        return

    if _current_index >= len(_message_list):
        return

    msg_id = _message_list[_current_index]
    pixel_data, metadata = storage.load_message(msg_id, _current_dir)

    if pixel_data is None:
        return

    width = metadata.get("width", config.BOARD_WIDTH)
    height = metadata.get("height", config.BOARD_HEIGHT)
    frames = metadata.get("frames", 1)
    fps = metadata.get("fps", config.DEFAULT_FPS)

    if frames > 1 and not _paused:
        player.play_animation(pixel_data, width, height, frames, fps)
    else:
        player.render_static(pixel_data, width, height)


def _handle_actions(actions):
    """Handle button actions."""
    global _current_index, _auto_rotate, _paused, _current_dir, _message_list

    for action in actions:
        if action == buttons.ACTION_SKIP:
            # A: Skip to next message
            if _message_list:
                _current_index = (_current_index + 1) % len(_message_list)
                _render_current()

        elif action == buttons.ACTION_CYCLE:
            # B: Toggle auto-rotate
            _auto_rotate = not _auto_rotate
            print(f"[MAIN] Auto-rotate: {_auto_rotate}")

        elif action == buttons.ACTION_MODE:
            # C: Toggle between inbox and art directories
            if _current_dir == config.INBOX_DIR:
                _current_dir = config.ART_DIR
            else:
                _current_dir = config.INBOX_DIR
            _current_index = 0
            _message_list = storage.list_messages(_current_dir)
            _render_current()
            print(f"[MAIN] Mode: {_current_dir}")

        elif action == buttons.ACTION_PLAY_PAUSE:
            # D short: Toggle play/pause
            _paused = not _paused
            print(f"[MAIN] Paused: {_paused}")
            _render_current()

        elif action == buttons.ACTION_DELETE:
            # D long: Delete current message
            if _message_list and _current_index < len(_message_list):
                msg_id = _message_list[_current_index]
                storage.delete_message(msg_id, _current_dir)
                _message_list = storage.list_messages(_current_dir)
                if _current_index >= len(_message_list):
                    _current_index = max(0, len(_message_list) - 1)
                _render_current()
                print(f"[MAIN] Deleted {msg_id}")


def main():
    """SpaceOS boot sequence and main loop."""
    global _message_list

    print("=" * 40)
    print("  SpaceOS v1.1")
    print(f"  Board: {config.BOARD_TYPE}")
    print(f"  Size: {config.BOARD_WIDTH}x{config.BOARD_HEIGHT}")
    print("=" * 40)

    # 1. Detect and initialize hardware
    cu, gfx, sw_a, sw_b, sw_c, sw_d = _detect_board()
    cu.set_brightness(0.5)
    player.init(cu, gfx)
    buttons.init(cu, sw_a, sw_b, sw_c, sw_d)

    # 2. Initialize storage
    storage.init()

    # 3. Connect to WiFi
    ip_config = wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    if ip_config is None:
        print("[BOOT] WiFi failed. Running in offline mode.")
    else:
        # 4. Get Ably token and connect MQTT
        token = _get_ably_token()
        if token:
            try:
                ably_mqtt.connect(token, on_command=_on_command)
            except Exception as e:
                print(f"[BOOT] MQTT connection failed: {e}")
        else:
            print("[BOOT] No Ably token. Running without real-time updates.")

    # 5. Load initial message list
    _message_list = storage.list_messages(_current_dir)
    if _message_list:
        _render_current()
    else:
        player.clear_display()

    print("[BOOT] SpaceOS ready.")

    # 6. Main loop
    auto_rotate_timer = time.ticks_ms()
    AUTO_ROTATE_INTERVAL = 10000  # 10 seconds

    while True:
        # Check MQTT messages
        if ably_mqtt.is_connected():
            ably_mqtt.check_messages()

        # Process any pending commands
        if _pending_commands:
            _process_commands()

        # Poll buttons
        actions = buttons.poll()
        if actions:
            _handle_actions(actions)

        # Auto-rotate
        if _auto_rotate and not _paused and _message_list:
            if time.ticks_diff(time.ticks_ms(), auto_rotate_timer) > AUTO_ROTATE_INTERVAL:
                _current_index = (_current_index + 1) % len(_message_list)
                _render_current()
                auto_rotate_timer = time.ticks_ms()

        # Small delay to prevent tight loop
        time.sleep(0.05)
        gc.collect()


if __name__ == "__main__":
    main()
