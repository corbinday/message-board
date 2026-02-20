# main.py - SpaceOS Bootstrapper
# IMMUTABLE — never included in OTA update bundles.
#
# Responsibilities (in order):
#   1. Detect and recover from interrupted updates (.updating flag).
#   2. Connect to WiFi.
#   3. Check for a new OTA bundle from the server.
#   4. If update available: verify Ed25519 signature, apply files, reboot.
#   5. Hand off to app.py (the updatable OS entry point).
#
# This file intentionally stays small. All normal OS functionality lives in app.py.
import os
import time
import json
import machine
import uhashlib
import urequests

import config
import wifi
import wifi_store
import ed25519
import update_key


# =============================================================================
# Constants
# =============================================================================

OS_HASH_FILE = "/os_hash"
UPDATING_FLAG = "/.updating"


# =============================================================================
# Hash helpers
# =============================================================================

def _read_os_hash():
    """Read the hash of the last successfully applied bundle."""
    try:
        with open(OS_HASH_FILE, "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def _write_os_hash(hash_hex):
    with open(OS_HASH_FILE, "w") as f:
        f.write(hash_hex)


def _sha256_hex(data):
    h = uhashlib.sha256()
    h.update(data)
    return "".join("{:02x}".format(b) for b in h.digest())


# =============================================================================
# Interrupted-update recovery
# =============================================================================

def _cleanup_partial_files():
    """Remove any .new files left by an interrupted update."""
    try:
        for name in os.listdir("/"):
            if name.endswith(".new"):
                try:
                    os.remove("/" + name)
                    print(f"[UPDATE] Cleaned up /{name}")
                except OSError as e:
                    print(f"[UPDATE] Could not remove /{name}: {e}")
    except Exception as e:
        print(f"[UPDATE] listdir error during cleanup: {e}")


# =============================================================================
# Bundle application (safe write with .updating flag)
# =============================================================================

def _apply_bundle(bundle_data):
    """
    Verify Ed25519 signature and apply an OTA bundle.

    Bundle format:
        [64 bytes: Ed25519 signature of everything after]
        [4 bytes: file count, big-endian uint32]
        for each file:
            [2 bytes: filename length, big-endian uint16]
            [N bytes: filename (UTF-8, basename only)]
            [4 bytes: file content length, big-endian uint32]
            [M bytes: file content]

    Returns True on success (board will machine.reset() after return).
    Returns False if verification or parsing fails (caller continues normally).
    """
    if len(bundle_data) < 68:  # 64-byte sig + at least 4 bytes
        print("[UPDATE] Bundle too small to be valid")
        return False

    signature = bundle_data[:64]
    payload = bundle_data[64:]

    # --- Ed25519 signature verification ---
    print("[UPDATE] Verifying signature (this may take a moment)...")
    if not ed25519.verify(update_key.PUBLIC_KEY, payload, signature):
        print("[UPDATE] Signature verification FAILED — aborting update")
        return False
    print("[UPDATE] Signature OK")

    # --- Parse bundle ---
    if len(payload) < 4:
        print("[UPDATE] Malformed bundle: missing file count")
        return False

    file_count = int.from_bytes(payload[0:4], "big")
    offset = 4
    files = []

    for _ in range(file_count):
        if offset + 2 > len(payload):
            print("[UPDATE] Malformed bundle: truncated name length")
            return False
        name_len = int.from_bytes(payload[offset:offset + 2], "big")
        offset += 2

        if offset + name_len > len(payload):
            print("[UPDATE] Malformed bundle: truncated filename")
            return False
        name = payload[offset:offset + name_len].decode("utf-8")
        offset += name_len

        if offset + 4 > len(payload):
            print("[UPDATE] Malformed bundle: truncated content length")
            return False
        content_len = int.from_bytes(payload[offset:offset + 4], "big")
        offset += 4

        if offset + content_len > len(payload):
            print("[UPDATE] Malformed bundle: truncated content for " + name)
            return False
        content = payload[offset:offset + content_len]
        offset += content_len

        files.append((name, content))
        print(f"[UPDATE] Parsed: {name} ({content_len} bytes)")

    new_hash = _sha256_hex(bundle_data)

    # --- Safe write: set flag, write .new, rename ---
    # Step 1: Write .updating flag
    try:
        with open(UPDATING_FLAG, "w") as f:
            f.write("1")
    except Exception as e:
        print(f"[UPDATE] Could not write .updating flag: {e}")
        return False

    # Step 2: Write all files with .new suffix
    for name, content in files:
        new_path = "/" + name + ".new"
        try:
            with open(new_path, "wb") as f:
                f.write(content)
            print(f"[UPDATE] Wrote {new_path}")
        except Exception as e:
            print(f"[UPDATE] Failed to write {new_path}: {e}")
            # Continue — cleanup on next boot will retry the update

    # Step 3: Rename .new -> original
    for name, _ in files:
        src = "/" + name + ".new"
        dst = "/" + name
        try:
            try:
                os.remove(dst)
            except OSError:
                pass
            os.rename(src, dst)
            print(f"[UPDATE] {src} -> {dst}")
        except Exception as e:
            print(f"[UPDATE] Rename failed: {src} -> {dst}: {e}")

    # Step 4: Write new hash
    _write_os_hash(new_hash)

    # Step 5: Remove .updating flag
    try:
        os.remove(UPDATING_FLAG)
    except OSError:
        pass

    print(f"[UPDATE] Update applied. New hash: {new_hash[:16]}...")
    return True


# =============================================================================
# OTA check
# =============================================================================

def _check_for_update():
    """
    Query the server for an OTA update.
    Returns True if a successful update was applied (caller should machine.reset()).
    Returns False if already up to date, OTA disabled, or any error.
    """
    os_hash = _read_os_hash()
    url = f"{config.API_URL}/api/spaceos/check?hash={os_hash}"
    headers = {
        "X-Board-Id": config.BOARD_ID,
        "X-Board-Secret": config.BOARD_SECRET_KEY,
    }

    print(f"[UPDATE] GET {url}")
    try:
        response = urequests.get(url, headers=headers)
        status = response.status_code

        if status == 204:
            response.close()
            print("[UPDATE] Already up to date.")
            return False

        if status == 200:
            bundle_data = response.content
            response.close()
            size = len(bundle_data)
            print(f"[UPDATE] Bundle received: {size} bytes")

            if _apply_bundle(bundle_data):
                return True
            else:
                print("[UPDATE] Bundle apply failed — continuing with current OS")
                return False

        response.close()
        print(f"[UPDATE] Unexpected status: {status}")
        return False

    except Exception as e:
        print(f"[UPDATE] OTA check error: {e}")
        return False


# =============================================================================
# Boot sequence
# =============================================================================

def main():
    print("=" * 40)
    print("  SpaceOS Bootstrapper")
    print(f"  Board: {config.BOARD_ID[:8] if config.BOARD_ID else 'unregistered'}")
    print("=" * 40)

    # 1. Recover from interrupted update
    try:
        os.stat(UPDATING_FLAG)
        print("[BOOT] Interrupted update detected — cleaning up and retrying")
        _cleanup_partial_files()
        try:
            os.remove(UPDATING_FLAG)
        except OSError:
            pass
        # Fall through to WiFi + OTA check so the update is retried this boot
    except OSError:
        pass  # No .updating flag — normal boot

    # 2. Connect to WiFi
    known = wifi_store.load_networks()
    if len(known) > 1:
        ip_config = wifi.connect_best(known)
    else:
        ip_config = wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    if ip_config is None:
        print("[BOOT] WiFi failed — skipping OTA check, launching OS directly")
    elif config.BOARD_ID:
        # 3. Check for OTA update (only if the board is registered)
        updated = _check_for_update()
        if updated:
            print("[BOOT] Update applied — rebooting...")
            machine.reset()
            # never reached

    # 4. Hand off to the updatable OS
    print("[BOOT] Launching SpaceOS...")
    import app
    app.run()


if __name__ == "__main__":
    main()
