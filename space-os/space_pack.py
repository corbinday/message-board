# space_pack.py - Download and parse Space Pack binary from server
import os
import struct
import json
import gc
import urequests

import config


# SP binary format offsets:
# 0:   Magic "SP" (2 bytes)
# 2:   Message ID (16 bytes, raw UUID)
# 18:  Meta length (2 bytes, uint16)
# 20:  Pixel length (4 bytes, uint32)
# 24:  Metadata (variable, JSON string)
# End: Pixel data (variable, raw RGB888)


def download(message_id):
    """
    Download a Space Pack from the server.

    Returns:
        dict with keys: message_id, sender, fps, is_anim, pixel_data
        or None on failure
    """
    url = f"{config.API_URL}/app/space-pack/{message_id}"
    headers = {
        "X-Board-Id": config.BOARD_ID,
        "X-Board-Secret": config.BOARD_SECRET_KEY,
    }

    print(f"[HTTP] GET {url}")

    try:
        response = urequests.get(url, headers=headers)
        data = response.content
        print(f"[HTTP] <- {response.status_code} ({len(data)} bytes)")

        if response.status_code != 200:
            print(f"[HTTP] Body: {response.text[:200]}")
            response.close()
            return None

        response.close()
        gc.collect()

        result = parse(data)
        if result:
            print(
                f"[SP] Parsed OK: id={result['message_id'][:12]}... sender={result['sender']} anim={result['is_anim']} fps={result['fps']}"
            )
        return result

    except Exception as e:
        print(f"[HTTP] GET {url} EXCEPTION: {e}")
        return None


def parse(data):
    """
    Parse a Space Pack binary blob.

    Returns:
        dict with keys: message_id, sender, fps, is_anim, pixel_data
        or None on failure
    """
    if len(data) < 24:
        print("[SP] Data too short for header")
        return None

    # Check magic bytes
    magic = data[0:2]
    if magic != b"SP":
        print(f"[SP] Invalid magic: {magic}")
        return None

    # Extract UUID (16 bytes, raw binary)
    raw_uuid = data[2:18]
    # Convert to hex string for display/storage
    msg_id = "".join("{:02x}".format(b) for b in raw_uuid)
    # Format as UUID string: 8-4-4-4-12
    msg_id = (
        f"{msg_id[:8]}-{msg_id[8:12]}-{msg_id[12:16]}-{msg_id[16:20]}-{msg_id[20:]}"
    )

    # Meta length (uint16, big-endian)
    meta_len = struct.unpack(">H", data[18:20])[0]

    # Pixel data length (uint32, big-endian)
    pixel_len = struct.unpack(">I", data[20:24])[0]

    # Extract metadata JSON
    meta_start = 24
    meta_end = meta_start + meta_len

    if len(data) < meta_end:
        print("[SP] Data too short for metadata")
        return None

    try:
        meta = json.loads(data[meta_start:meta_end])
    except Exception as e:
        print(f"[SP] Metadata parse error: {e}")
        return None

    # Extract pixel data
    pixel_start = meta_end
    pixel_data = data[pixel_start : pixel_start + pixel_len]

    if len(pixel_data) != pixel_len:
        print(
            f"[SP] Pixel data length mismatch: expected {pixel_len}, got {len(pixel_data)}"
        )
        return None

    gc.collect()

    return {
        "message_id": msg_id,
        "sender": meta.get("sender", "Unknown"),
        "fps": meta.get("fps", config.DEFAULT_FPS),
        "is_anim": meta.get("is_anim", False),
        "pixel_data": pixel_data,
    }


def download_streaming(message_id, pixel_out_path):
    """
    Download a Space Pack, streaming pixel data directly to pixel_out_path.

    Avoids the large RAM allocation that download() requires — safe for files
    that exceed free heap (anything over ~150 KB on the Pico).

    Returns a metadata dict (without pixel_data) on success, or None on failure.
    The caller is responsible for cleaning up pixel_out_path on failure.
    """
    url = f"{config.API_URL}/app/space-pack/{message_id}"
    headers = {
        "X-Board-Id": config.BOARD_ID,
        "X-Board-Secret": config.BOARD_SECRET_KEY,
    }

    _CHUNK = 4096

    print(f"[HTTP] GET {url}")
    try:
        response = urequests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"[HTTP] {response.status_code}")
            response.raw.close()
            return None

        # Parse the fixed 24-byte header inline (magic + uuid + meta_len + pixel_len)
        header = response.raw.read(24)
        if len(header) < 24:
            print(f"[SP] Short header ({len(header)} bytes)")
            response.raw.close()
            return None

        if header[:2] != b"SP":
            print(f"[SP] Invalid magic: {header[:2]}")
            response.raw.close()
            return None

        raw_uuid = header[2:18]
        uid_hex = "".join("{:02x}".format(b) for b in raw_uuid)
        msg_id = f"{uid_hex[:8]}-{uid_hex[8:12]}-{uid_hex[12:16]}-{uid_hex[16:20]}-{uid_hex[20:]}"

        meta_len = struct.unpack(">H", header[18:20])[0]
        pixel_len = struct.unpack(">I", header[20:24])[0]

        # Read metadata JSON (always small — a few hundred bytes at most)
        meta_bytes = response.raw.read(meta_len)
        if len(meta_bytes) < meta_len:
            print(f"[SP] Short metadata ({len(meta_bytes)}/{meta_len})")
            response.raw.close()
            return None

        try:
            meta = json.loads(meta_bytes)
        except Exception as e:
            print(f"[SP] Metadata parse error: {e}")
            response.raw.close()
            return None

        gc.collect()

        # Stream pixel data directly to flash — never held in RAM beyond one chunk
        remaining = pixel_len
        try:
            with open(pixel_out_path, "wb") as f:
                while remaining > 0:
                    chunk = response.raw.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
                    gc.collect()
        except Exception as e:
            print(f"[SP] Pixel stream error: {e}")
            response.raw.close()
            try:
                os.remove(pixel_out_path)
            except OSError:
                pass
            return None

        response.raw.close()

        if remaining > 0:
            print(f"[SP] Incomplete pixel data ({remaining} bytes missing)")
            try:
                os.remove(pixel_out_path)
            except OSError:
                pass
            return None

        print(
            f"[SP] Streamed OK: id={msg_id[:12]}... sender={meta.get('sender', '?')} {pixel_len}B pixels"
        )
        gc.collect()
        return {
            "message_id": msg_id,
            "sender": meta.get("sender", "Unknown"),
            "fps": meta.get("fps", config.DEFAULT_FPS),
            "is_anim": meta.get("is_anim", False),
        }

    except Exception as e:
        print(f"[HTTP] GET {url} EXCEPTION: {e}")
        try:
            os.remove(pixel_out_path)
        except OSError:
            pass
        return None
