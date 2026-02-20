# app.py - SpaceOS application (OTA-updatable)
# Hardware init, boot sync, Ably connection, and main loop.
# Loaded by main.py (the immutable bootstrapper) after the OTA check passes.
import time
import json
import gc
import machine
import urequests

import config
import wifi
import wifi_store
import ably_mqtt
import commands
import space_pack
import storage
import player
import buttons


# =============================================================================
# Board Detection (self-detecting — no BOARD_TYPE in secrets.py)
# =============================================================================

_BOARD_TYPE = None
_BOARD_WIDTH = 0
_BOARD_HEIGHT = 0
_unicorn_hw = None  # Hardware reference for brightness control


def _detect_board():
    """
    Detect board hardware by trying each Pimoroni module import in sequence.
    Only the matching module exists on each board's firmware, so the first
    successful import wins.

    Returns (unicorn, graphics, sw_a, sw_b, sw_c, sw_d, board_type_str).
    """
    try:
        from cosmic import CosmicUnicorn
        from picographics import PicoGraphics, DISPLAY_COSMIC_UNICORN
        cu = CosmicUnicorn()
        gfx = PicoGraphics(DISPLAY_COSMIC_UNICORN)
        return cu, gfx, cu.SWITCH_A, cu.SWITCH_B, cu.SWITCH_C, cu.SWITCH_D, "Cosmic"
    except ImportError:
        pass

    try:
        from galactic import GalacticUnicorn
        from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
        cu = GalacticUnicorn()
        gfx = PicoGraphics(DISPLAY_GALACTIC_UNICORN)
        return cu, gfx, cu.SWITCH_A, cu.SWITCH_B, cu.SWITCH_C, cu.SWITCH_D, "Galactic"
    except ImportError:
        pass

    from stellar import StellarUnicorn
    from picographics import PicoGraphics, DISPLAY_STELLAR_UNICORN
    cu = StellarUnicorn()
    gfx = PicoGraphics(DISPLAY_STELLAR_UNICORN)
    return cu, gfx, cu.SWITCH_A, cu.SWITCH_B, cu.SWITCH_C, cu.SWITCH_D, "Stellar"


# =============================================================================
# State
# =============================================================================

_current_dir = config.INBOX_DIR  # Current browsing directory
_current_index = 0                # Current message index
_auto_rotate = False              # Auto-rotate mode
_paused = False                   # Playback paused
_brightness = 0.5                 # Current brightness (0.0–1.0)
_message_list = []                # Current directory listing
_pending_commands = []            # Queue of incoming commands
_in_settings_mode = False         # Whether on-board settings menu is active
_settings_index = 0               # Current settings menu item


# =============================================================================
# Local Settings Persistence
# =============================================================================

def _load_local_settings():
    """Load persisted settings from local file."""
    global _auto_rotate, _brightness, _current_dir
    try:
        with open(config.SETTINGS_FILE, "r") as f:
            settings = json.load(f)
        _auto_rotate = settings.get("auto_rotate", False)
        _brightness = settings.get("brightness", 0.5)
        mode = settings.get("display_mode", "inbox")
        _current_dir = config.ART_DIR if mode == "art" else config.INBOX_DIR
        print(f"[SETTINGS] Loaded: mode={mode} auto_rotate={_auto_rotate} brightness={_brightness}")
    except (OSError, ValueError):
        print("[SETTINGS] No local settings file, using defaults.")


def _save_local_settings():
    """Persist current settings to local file."""
    mode = "art" if _current_dir == config.ART_DIR else "inbox"
    settings = {
        "display_mode": mode,
        "auto_rotate": _auto_rotate,
        "brightness": _brightness,
    }
    try:
        with open(config.SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
        print(f"[SETTINGS] Saved: {settings}")
    except Exception as e:
        print(f"[SETTINGS] Save failed: {e}")


# =============================================================================
# Server Settings Fetch
# =============================================================================

def _fetch_server_settings():
    """Fetch board settings from server and apply them."""
    global _auto_rotate, _brightness, _current_dir
    url = f"{config.API_URL}/ably/boards/{config.BOARD_ID}/settings"
    headers = {
        "X-Board-Secret": config.BOARD_SECRET_KEY,
        "Content-Type": "application/json",
    }

    print(f"[HTTP] POST {url}")
    try:
        response = urequests.post(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            response.close()

            mode = data.get("display_mode", "inbox")
            _current_dir = config.ART_DIR if mode == "art" else config.INBOX_DIR
            _auto_rotate = data.get("auto_rotate", False)
            _brightness = data.get("brightness", 0.5)

            _save_local_settings()
            print(f"[SETTINGS] Server settings applied: mode={mode} auto_rotate={_auto_rotate} brightness={_brightness}")
        else:
            response.close()
            print(f"[SETTINGS] Server settings fetch failed: {response.status_code}")
    except Exception as e:
        print(f"[SETTINGS] Server settings fetch error: {e}")


# =============================================================================
# Startup Animation
# =============================================================================

def _show_boot_animation():
    player.show_warp_animation(_BOARD_WIDTH, _BOARD_HEIGHT, duration_ms=1500)


# =============================================================================
# Network & Ably
# =============================================================================

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


def _establish_connection():
    """Connect to WiFi, sync, and establish Ably MQTT. Returns True if online."""
    known = wifi_store.load_networks()

    if len(known) > 1:
        ip_config = wifi.connect_best(known)
    else:
        ip_config = wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    if ip_config is None:
        print("[BOOT] WiFi failed. Running in offline mode.")
        return False

    try:
        import ntptime
        ntptime.settime()
        print("[TIME] NTP sync OK")
    except Exception as e:
        print(f"[TIME] NTP sync failed: {e}")

    _fetch_server_settings()

    print("[BOOT] Syncing messages...")
    _boot_sync()

    token = _get_ably_token()
    if token:
        try:
            ably_mqtt.connect(token, on_command=_on_command)
        except Exception as e:
            print(f"[BOOT] MQTT connection failed: {e}")
    else:
        print("[BOOT] No Ably token. Running without real-time updates.")

    _publish_inventory()
    return True


def _attempt_reconnect():
    """Attempt to reconnect WiFi and re-establish Ably."""
    print("[RECONNECT] Attempting WiFi reconnection...")

    known = wifi_store.load_networks()
    ip_config = wifi.reconnect(
        known_networks=known if len(known) > 1 else None,
        ssid=config.WIFI_SSID,
        password=config.WIFI_PASSWORD,
    )

    if ip_config is None:
        print("[RECONNECT] WiFi reconnection failed.")
        return False

    print(f"[RECONNECT] WiFi reconnected: {ip_config}")

    token = _get_ably_token()
    if token:
        try:
            if ably_mqtt.is_connected():
                ably_mqtt.disconnect()
            ably_mqtt.connect(token, on_command=_on_command)
            print("[RECONNECT] MQTT reconnected.")
        except Exception as e:
            print(f"[RECONNECT] MQTT reconnection failed: {e}")
            return False
    else:
        print("[RECONNECT] Failed to get Ably token after reconnect.")
        return False

    _boot_sync()
    _publish_inventory()
    return True


# =============================================================================
# Boot Sync
# =============================================================================

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

    art_items = data.get("art", [])
    inbox_items = data.get("inbox", [])
    total = len(art_items) + len(inbox_items)

    if total == 0:
        print("[SYNC] No items to sync.")
        return

    print(f"[SYNC] Server has {len(art_items)} art, {len(inbox_items)} inbox")

    synced = 0

    if art_items:
        local_art_ids = set(storage.list_messages(config.ART_DIR))
        print(f"[SYNC] Local art: {len(local_art_ids)}")
        for i, item in enumerate(art_items):
            item_id = item.get("messageId", "")
            status = "LOCAL" if item_id in local_art_ids else "NEW"
            print(f"[SYNC]   art[{i}] {item_id[:12]}... {status}")

        _TMP = "/tmp_sp.bin"
        for item in art_items:
            item_id = item.get("messageId", "")
            if item_id in local_art_ids:
                continue

            print(f"[SYNC] Downloading art {item_id[:12]}...")
            sp = space_pack.download_streaming(item_id, _TMP)
            if sp is None:
                print(f"[SYNC] Failed to download art {item_id[:12]}...")
                continue

            width = item.get("width", _BOARD_WIDTH)
            height = item.get("height", _BOARD_HEIGHT)
            frames = item.get("frames", 1)

            metadata = {
                "sender": sp["sender"],
                "fps": sp["fps"],
                "is_anim": sp["is_anim"],
                "width": width,
                "height": height,
                "frames": frames,
            }
            storage.save_message_from_file(sp["message_id"], _TMP, metadata, directory=config.ART_DIR)
            synced += 1
            gc.collect()

    if inbox_items:
        local_inbox_ids = set(storage.list_messages(config.INBOX_DIR))
        print(f"[SYNC] Local inbox: {len(local_inbox_ids)}")
        for i, item in enumerate(inbox_items):
            item_id = item.get("messageId", "")
            status = "LOCAL" if item_id in local_inbox_ids else "NEW"
            print(f"[SYNC]   inbox[{i}] {item_id[:12]}... {status}")

        _TMP = "/tmp_sp.bin"
        for item in inbox_items:
            item_id = item.get("messageId", "")
            if item_id in local_inbox_ids:
                continue

            print(f"[SYNC] Downloading inbox {item_id[:12]}...")
            sp = space_pack.download_streaming(item_id, _TMP)
            if sp is None:
                print(f"[SYNC] Failed to download inbox {item_id[:12]}...")
                continue

            width = item.get("width", _BOARD_WIDTH)
            height = item.get("height", _BOARD_HEIGHT)
            frames = item.get("frames", 1)

            metadata = {
                "sender": sp["sender"],
                "fps": sp["fps"],
                "is_anim": sp["is_anim"],
                "width": width,
                "height": height,
                "frames": frames,
            }
            storage.save_message_from_file(sp["message_id"], _TMP, metadata, directory=config.INBOX_DIR)
            synced += 1
            gc.collect()

    print(f"[SYNC] Synced {synced} new items (art + inbox).")


# =============================================================================
# Inventory Publishing
# =============================================================================

def _publish_inventory():
    """Publish current board inventory snapshot via HTTP to the server."""
    inbox_ids = storage.list_messages(config.INBOX_DIR)
    art_ids = storage.list_messages(config.ART_DIR)
    last_eviction = storage.get_last_eviction()

    url = f"{config.API_URL}/ably/boards/{config.BOARD_ID}/inventory"
    headers = {
        "X-Board-Secret": config.BOARD_SECRET_KEY,
        "Content-Type": "application/json",
    }
    payload = json.dumps({
        "inbox_count": len(inbox_ids),
        "art_count": len(art_ids),
        "inbox_ids": inbox_ids[:10],
        "art_ids": art_ids[:10],
        "last_eviction": last_eviction,
    })

    try:
        response = urequests.post(url, headers=headers, data=payload)
        response.close()
        print(f"[INVENTORY] Published: inbox={len(inbox_ids)} art={len(art_ids)}")
    except Exception as e:
        print(f"[INVENTORY] Publish failed: {e}")


# =============================================================================
# Command Handling (Typed Routing)
# =============================================================================

def _on_command(payload):
    """Handle incoming Ably command messages."""
    _pending_commands.append(payload)
    cmd_type = payload.get("type", "unknown")
    print(f"[MAIN] Command queued: type={cmd_type}")


def _process_commands():
    """Process pending command queue with typed routing."""
    global _current_index, _message_list, _current_dir, _auto_rotate, _brightness, _paused

    while _pending_commands:
        payload = _pending_commands.pop(0)
        cmd_type = payload.get("type")

        # Legacy untyped command (backwards compat) — treat as message_sync
        if cmd_type is None and payload.get("messageId"):
            cmd_type = "message_sync"

        if cmd_type == "message_sync":
            _handle_content_sync(payload, config.INBOX_DIR)

        elif cmd_type == "art_sync":
            _handle_content_sync(payload, config.ART_DIR)

        elif cmd_type == "set_mode":
            mode = payload.get("mode", "inbox")
            new_dir = config.ART_DIR if mode == "art" else config.INBOX_DIR
            if new_dir != _current_dir:
                _current_dir = new_dir
                _current_index = 0
                _message_list = storage.list_messages(_current_dir)
                _render_current()
                _save_local_settings()
                print(f"[CMD] Mode set to {mode}")

        elif cmd_type == "set_auto_rotate":
            _auto_rotate = payload.get("enabled", False)
            _save_local_settings()
            print(f"[CMD] Auto-rotate set to {_auto_rotate}")

        elif cmd_type == "set_brightness":
            _brightness = max(0.0, min(1.0, payload.get("brightness", 0.5)))
            if _unicorn_hw:
                _unicorn_hw.set_brightness(_brightness)
            _save_local_settings()
            print(f"[CMD] Brightness set to {_brightness}")

        elif cmd_type == "sync_request":
            print("[CMD] Sync request received, re-syncing...")
            _boot_sync()
            _message_list = storage.list_messages(_current_dir)
            _render_current()
            _publish_inventory()

        elif cmd_type == "skip_next":
            if _message_list:
                _current_index = (_current_index + 1) % len(_message_list)
                _render_current()
                print(f"[CMD] Skipped forward to index {_current_index}")
            else:
                print("[CMD] skip_next: no messages to navigate")

        elif cmd_type == "skip_prev":
            if _message_list:
                _current_index = (_current_index - 1) % len(_message_list)
                _render_current()
                print(f"[CMD] Skipped back to index {_current_index}")
            else:
                print("[CMD] skip_prev: no messages to navigate")

        elif cmd_type == "wifi_update":
            print("[CMD] Encrypted WiFi update received")
            wifi_store.handle_wifi_update(payload)

        elif cmd_type == "os_update":
            # A new SpaceOS version is available. Reboot now so main.py
            # can download and apply the update.
            print("[CMD] OTA update available — rebooting to apply...")
            machine.reset()

        else:
            print(f"[CMD] Unknown command type: {cmd_type}")


def _handle_content_sync(payload, target_dir):
    """Handle message_sync or art_sync command: download and save content."""
    global _current_index, _message_list

    result = commands.validate_command(payload, _BOARD_WIDTH, _BOARD_HEIGHT)
    if result is None:
        return

    message_id, width, height, frames, fps = result
    print(f"[MAIN] Processing {payload.get('type', 'sync')} {message_id} ({width}x{height}, {frames}f) -> {target_dir}")

    player.show_warp_animation(width, height)

    sp = space_pack.download(message_id)
    if sp is None:
        print("[MAIN] Space Pack download failed")
        return

    metadata = {
        "sender": sp["sender"],
        "fps": sp["fps"],
        "is_anim": sp["is_anim"],
        "width": width,
        "height": height,
        "frames": frames,
    }
    eviction_info = storage.save_message(sp["message_id"], sp["pixel_data"], metadata, directory=target_dir)

    if eviction_info and eviction_info.get("evicted"):
        _publish_eviction_event(eviction_info)

    if target_dir == _current_dir:
        _message_list = storage.list_messages(_current_dir)
        if sp["message_id"] in _message_list:
            _current_index = _message_list.index(sp["message_id"])
        _render_current()

    if target_dir == config.INBOX_DIR:
        if sp["is_anim"] and frames > 1:
            player.play_animation(
                sp["pixel_data"],
                width, height, frames, fps,
                on_loop_complete=lambda: ably_mqtt.publish_read_receipt(sp["message_id"]),
            )
        else:
            player.render_static(sp["pixel_data"], width, height)
            ably_mqtt.publish_read_receipt(sp["message_id"])

    _publish_inventory()


def _publish_eviction_event(eviction_info):
    """Publish FIFO eviction event via Ably status channel."""
    if not ably_mqtt.is_connected():
        return

    topic = f"status/{config.USER_ID}/{config.BOARD_ID}"
    payload = json.dumps({
        "type": "eviction",
        "evicted": eviction_info.get("evicted", []),
        "directory": eviction_info.get("directory", ""),
    })
    try:
        ably_mqtt.publish_status(topic, payload)
    except Exception as e:
        print(f"[EVICTION] Failed to publish: {e}")


# =============================================================================
# Rendering
# =============================================================================

def _render_current():
    """Render the currently selected message/art."""
    global _message_list

    if _in_settings_mode:
        return

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

    width = metadata.get("width", _BOARD_WIDTH)
    height = metadata.get("height", _BOARD_HEIGHT)
    frames = metadata.get("frames", 1)
    fps = metadata.get("fps", config.DEFAULT_FPS)

    print(f"[RENDER] Drawing {width}x{height} {frames}f {len(pixel_data)}B")
    if frames > 1 and not _paused:
        player.start_animation(pixel_data, width, height, frames, fps)
    else:
        player.render_static(pixel_data, width, height)


# =============================================================================
# Settings Mode (On-Board)
# =============================================================================

_SETTINGS_ITEMS = ["Brightness", "Mode", "Auto-Rotate", "WiFi", "Board Info", "Exit"]


def _enter_settings_mode():
    global _in_settings_mode, _settings_index
    _in_settings_mode = True
    _settings_index = 0
    player.stop_animation()
    _render_settings()
    print("[SETTINGS] Entered settings mode")


def _exit_settings_mode():
    global _in_settings_mode
    _in_settings_mode = False
    _save_local_settings()
    _render_current()
    print("[SETTINGS] Exited settings mode")


def _render_settings():
    if not _in_settings_mode:
        return
    item = _SETTINGS_ITEMS[_settings_index]
    player.render_settings_screen(_BOARD_WIDTH, _BOARD_HEIGHT, item, _get_setting_value(item))


def _get_setting_value(item):
    if item == "Brightness":
        return f"{int(_brightness * 100)}%"
    elif item == "Mode":
        return "Art" if _current_dir == config.ART_DIR else "Inbox"
    elif item == "Auto-Rotate":
        return "On" if _auto_rotate else "Off"
    elif item == "WiFi":
        ssid = wifi.get_current_ssid()
        return ssid if ssid else "Disconnected"
    elif item == "Board Info":
        return config.BOARD_ID[:8]
    return ""


def _handle_settings_action(action):
    global _settings_index, _brightness, _auto_rotate, _current_dir, _current_index, _message_list

    if action == buttons.ACTION_SKIP:
        _settings_index = (_settings_index + 1) % len(_SETTINGS_ITEMS)
        _render_settings()

    elif action == buttons.ACTION_CYCLE:
        _settings_index = (_settings_index - 1) % len(_SETTINGS_ITEMS)
        _render_settings()

    elif action == buttons.ACTION_MODE:
        item = _SETTINGS_ITEMS[_settings_index]

        if item == "Brightness":
            _brightness = round(_brightness + 0.1, 1)
            if _brightness > 1.0:
                _brightness = 0.1
            if _unicorn_hw:
                _unicorn_hw.set_brightness(_brightness)

        elif item == "Mode":
            if _current_dir == config.INBOX_DIR:
                _current_dir = config.ART_DIR
            else:
                _current_dir = config.INBOX_DIR
            _current_index = 0
            _message_list = storage.list_messages(_current_dir)

        elif item == "Auto-Rotate":
            _auto_rotate = not _auto_rotate

        elif item == "Exit":
            _exit_settings_mode()
            return

        _render_settings()

    elif action == buttons.ACTION_PLAY_PAUSE:
        item = _SETTINGS_ITEMS[_settings_index]
        if item == "Exit":
            _exit_settings_mode()
        else:
            _handle_settings_action(buttons.ACTION_MODE)

    elif action == buttons.ACTION_DELETE:
        _exit_settings_mode()


# =============================================================================
# Button Handling
# =============================================================================

def _handle_actions(actions):
    global _current_index, _auto_rotate, _paused, _current_dir, _message_list

    for action in actions:
        if action == buttons.ACTION_SETTINGS:
            if _in_settings_mode:
                _exit_settings_mode()
            else:
                _enter_settings_mode()
            continue

        if _in_settings_mode:
            _handle_settings_action(action)
            continue

        if action == buttons.ACTION_SKIP:
            if _message_list:
                _current_index = (_current_index + 1) % len(_message_list)
                _render_current()

        elif action == buttons.ACTION_CYCLE:
            _auto_rotate = not _auto_rotate
            _save_local_settings()
            print(f"[MAIN] Auto-rotate: {_auto_rotate}")

        elif action == buttons.ACTION_MODE:
            if _current_dir == config.INBOX_DIR:
                _current_dir = config.ART_DIR
            else:
                _current_dir = config.INBOX_DIR
            _current_index = 0
            _message_list = storage.list_messages(_current_dir)
            _render_current()
            _save_local_settings()
            print(f"[MAIN] Mode: {_current_dir}")

        elif action == buttons.ACTION_PLAY_PAUSE:
            _paused = not _paused
            print(f"[MAIN] Paused: {_paused}")
            _render_current()

        elif action == buttons.ACTION_DELETE:
            if _message_list and _current_index < len(_message_list):
                msg_id = _message_list[_current_index]
                storage.delete_message(msg_id, _current_dir)
                _message_list = storage.list_messages(_current_dir)
                if _current_index >= len(_message_list):
                    _current_index = max(0, len(_message_list) - 1)
                _render_current()
                _publish_inventory()
                print(f"[MAIN] Deleted {msg_id}")


# =============================================================================
# App Entry Point (called by main.py bootstrapper)
# =============================================================================

def run():
    """SpaceOS boot sequence and main loop."""
    global _message_list, _current_index, _auto_rotate, _paused, _brightness
    global _BOARD_TYPE, _BOARD_WIDTH, _BOARD_HEIGHT, _unicorn_hw

    # 1. Detect and initialize hardware
    cu, gfx, sw_a, sw_b, sw_c, sw_d, _BOARD_TYPE = _detect_board()
    _BOARD_WIDTH, _BOARD_HEIGHT = gfx.get_bounds()
    _unicorn_hw = cu
    player.init(cu, gfx)
    buttons.init(cu, sw_a, sw_b, sw_c, sw_d)

    print("=" * 40)
    print("  SpaceOS")
    print(f"  Board: {_BOARD_TYPE}")
    print(f"  Size: {_BOARD_WIDTH}x{_BOARD_HEIGHT}")
    print("=" * 40)

    # 2. Initialize storage
    storage.init()

    # 3. Load local settings (persisted from last session)
    _load_local_settings()
    cu.set_brightness(_brightness)

    # 4. Show startup animation
    _show_boot_animation()

    # 5. Connect to WiFi, sync, and establish Ably
    is_online = _establish_connection()
    if not is_online:
        print("[BOOT] Running in offline mode.")

    # 6. Load initial message list
    _message_list = storage.list_messages(_current_dir)
    if _message_list:
        _render_current()
    else:
        player.clear_display()

    print("[BOOT] SpaceOS ready.")

    # 7. Main loop
    auto_rotate_timer = time.ticks_ms()
    reconnect_timer = time.ticks_ms()
    heartbeat_timer = time.ticks_ms()
    AUTO_ROTATE_INTERVAL = 10000   # 10 seconds
    HEARTBEAT_INTERVAL = 240000    # 4 minutes — keeps last_connected_at fresh on server
    _rotate_pending = False

    while True:
        now = time.ticks_ms()

        if ably_mqtt.is_connected():
            ably_mqtt.check_messages()

        if _pending_commands:
            _process_commands()

        if not wifi.is_connected():
            if time.ticks_diff(now, reconnect_timer) > config.RECONNECT_INTERVAL_MS:
                reconnect_timer = now
                if _attempt_reconnect():
                    _message_list = storage.list_messages(_current_dir)
                    _render_current()
        elif not ably_mqtt.is_connected():
            if time.ticks_diff(now, reconnect_timer) > config.RECONNECT_INTERVAL_MS:
                reconnect_timer = now
                token = _get_ably_token()
                if token:
                    try:
                        ably_mqtt.connect(token, on_command=_on_command)
                        print("[RECONNECT] MQTT re-established.")
                    except Exception as e:
                        print(f"[RECONNECT] MQTT reconnect failed: {e}")

        # Heartbeat: re-publish inventory periodically so server sees us as online
        if ably_mqtt.is_connected() and time.ticks_diff(now, heartbeat_timer) > HEARTBEAT_INTERVAL:
            heartbeat_timer = now
            _publish_inventory()

        actions = buttons.poll()
        if actions:
            _handle_actions(actions)
            auto_rotate_timer = now
            _rotate_pending = False

        if not _in_settings_mode:
            loop_done = player.tick()

            if _rotate_pending and loop_done:
                _rotate_pending = False
                _current_index = (_current_index + 1) % len(_message_list)
                _render_current()
                auto_rotate_timer = now

            if _auto_rotate and not _paused and _message_list and not _rotate_pending:
                if time.ticks_diff(now, auto_rotate_timer) > AUTO_ROTATE_INTERVAL:
                    if player.is_animating() and player.loop_count() < 1:
                        _rotate_pending = True
                    elif player.is_animating():
                        _rotate_pending = True
                    else:
                        _current_index = (_current_index + 1) % len(_message_list)
                        _render_current()
                        auto_rotate_timer = now

        time.sleep(0.02)
        gc.collect()
