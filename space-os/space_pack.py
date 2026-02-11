# space_pack.py - Download and parse Space Pack binary from server
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
    url = f"{config.API_URL}/space-pack/{message_id}"
    headers = {
        "X-Board-Id": config.BOARD_ID,
        "X-Board-Secret": config.BOARD_SECRET_KEY,
    }

    print(f"[SP] Downloading from {url}")

    try:
        response = urequests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"[SP] Server error: HTTP {response.status_code}")
            response.close()
            return None

        data = response.content
        response.close()
        gc.collect()

        return parse(data)

    except Exception as e:
        print(f"[SP] Download error: {e}")
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
    msg_id = f"{msg_id[:8]}-{msg_id[8:12]}-{msg_id[12:16]}-{msg_id[16:20]}-{msg_id[20:]}"

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
        print(f"[SP] Pixel data length mismatch: expected {pixel_len}, got {len(pixel_data)}")
        return None

    gc.collect()

    return {
        "message_id": msg_id,
        "sender": meta.get("sender", "Unknown"),
        "fps": meta.get("fps", config.DEFAULT_FPS),
        "is_anim": meta.get("is_anim", False),
        "pixel_data": pixel_data,
    }
