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
    url = f"{config.API_URL}/ably/boards/{config.BOARD_ID}/token"
    headers = {
        "X-Board-Secret": config.BOARD_SECRET_KEY,
        "Content-Type": "application/json",
    }

    print(f"[HTTP] POST {url}")
    try:
        response = urequests.post(url, headers=headers)
        print(f"[HTTP] <- {response.status_code} ({len(response.content)} bytes)")
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            print(f"[HTTP] Token received: {token[:20]}..." if token else "[HTTP] No token in response")
            response.close()
            return token
        else:
            print(f"[HTTP] Body: {response.text[:200]}")
            response.close()
            return None
    except Exception as e:
        print(f"[HTTP] POST {url} EXCEPTION: {e}")
        return None


def _boot_sync():
    """Fetch recent messages from server and download any we don't have locally."""
    url = f"{config.API_URL}/app/boards/{config.BOARD_ID}/sync"
    headers = {
        "X-Board-Secret": config.BOARD_SECRET_KEY,
    }

    print(f"[HTTP] GET {url}")
    try:
        response = urequests.get(url, headers=headers)
        print(f"[HTTP] <- {response.status_code} ({len(response.content)} bytes)")
        if response.status_code != 200:
            print(f"[HTTP] Body: {response.text[:200]}")
            response.close()
            return
        data = response.json()
        response.close()
    except Exception as e:
        print(f"[HTTP] GET {url} EXCEPTION: {e}")
        return

    messages = data.get("messages", [])
    if not messages:
        print("[SYNC] No messages to sync.")
        return

    # Get local message IDs already on disk
    local_ids = set(storage.list_messages(config.INBOX_DIR))
    print(f"[SYNC] Server has {len(messages)} recent, local has {len(local_ids)}")
    for i, msg in enumerate(messages):
        status = "LOCAL" if msg.get("messageId", "") in local_ids else "NEW"
        print(f"[SYNC]   [{i}] {msg.get('messageId', '?')[:12]}... {status}")

    synced = 0
    for msg in messages:
        msg_id = msg.get("messageId", "")
        if msg_id in local_ids:
            continue

        width = msg.get("width", config.BOARD_WIDTH)
        height = msg.get("height", config.BOARD_HEIGHT)
        frames = msg.get("frames", 1)
        fps = msg.get("fps", config.DEFAULT_FPS)

        print(f"[SYNC] Downloading {msg_id}")
        sp = space_pack.download(msg_id)
        if sp is None:
            print(f"[SYNC] Failed to download {msg_id}")
            continue

        metadata = {
            "sender": sp["sender"],
            "fps": sp["fps"],
            "is_anim": sp["is_anim"],
            "width": width,
            "height": height,
            "frames": frames,
        }
        storage.save_message(sp["message_id"], sp["pixel_data"], metadata)
        synced += 1
        gc.collect()

    print(f"[SYNC] Synced {synced} new messages.")


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
        print(f"[RENDER] No messages in {_current_dir}")
        player.clear_display()
        return

    if _current_index >= len(_message_list):
        print(f"[RENDER] Index {_current_index} out of range (list has {len(_message_list)})")
        return

    msg_id = _message_list[_current_index]
    print(f"[RENDER] Loading {msg_id[:12]}... [{_current_index}/{len(_message_list)}] from {_current_dir}")
    pixel_data, metadata = storage.load_message(msg_id, _current_dir)

    if pixel_data is None:
        print(f"[RENDER] pixel_data is None for {msg_id[:12]}...")
        return

    width = metadata.get("width", config.BOARD_WIDTH)
    height = metadata.get("height", config.BOARD_HEIGHT)
    frames = metadata.get("frames", 1)
    fps = metadata.get("fps", config.DEFAULT_FPS)

    print(f"[RENDER] Drawing {width}x{height} {frames}f {len(pixel_data)}B")
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
        # 4. Sync recent messages from server
        print("[BOOT] Syncing messages...")
        _boot_sync()

        # 5. Get Ably token and connect MQTT
        token = _get_ably_token()
        if token:
            try:
                ably_mqtt.connect(token, on_command=_on_command)
            except Exception as e:
                print(f"[BOOT] MQTT connection failed: {e}")
        else:
            print("[BOOT] No Ably token. Running without real-time updates.")

    # 6. Load initial message list
    _message_list = storage.list_messages(_current_dir)
    if _message_list:
        _render_current()
    else:
        player.clear_display()

    print("[BOOT] SpaceOS ready.")

    # 7. Main loop
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
