# storage.py - LittleFS inbox/art management with FIFO cap and eviction telemetry
import os
import json
import gc

import config


# Track last eviction for telemetry
_last_eviction = None


def _ensure_dir(path):
    """Create directory if it doesn't exist."""
    try:
        os.stat(path)
    except OSError:
        os.mkdir(path)
        print(f"[STORE] Created {path}")


def init():
    """Initialize storage directories."""
    _ensure_dir(config.INBOX_DIR)
    _ensure_dir(config.ART_DIR)
    _enforce_fifo(config.INBOX_DIR)
    _enforce_fifo(config.ART_DIR)
    print("[STORE] Storage initialized.")


def save_message(message_id, pixel_data, metadata, directory=None):
    """
    Save a message to a directory.

    Args:
        message_id: UUID string
        pixel_data: Raw RGB bytes
        metadata: Dict with sender, fps, is_anim
        directory: Target directory (defaults to INBOX_DIR)

    Returns:
        Eviction info dict if items were evicted, or None.
        Format: {"evicted": ["uuid1", "uuid2"], "directory": "/inbox"}
    """
    if directory is None:
        directory = config.INBOX_DIR
    _ensure_dir(directory)

    # Save pixel data
    bin_path = f"{directory}/{message_id}.bin"
    with open(bin_path, "wb") as f:
        f.write(pixel_data)

    # Save metadata
    json_path = f"{directory}/{message_id}.json"
    with open(json_path, "w") as f:
        json.dump(metadata, f)

    print(f"[STORE] Saved {message_id} to {directory}")

    # Enforce FIFO cap and collect eviction info
    eviction_info = _enforce_fifo(directory)
    gc.collect()
    return eviction_info


def save_message_from_file(message_id, pixel_tmp_path, metadata, directory=None):
    """
    Save a message where pixel data is already on disk at pixel_tmp_path.

    Renames the temp file into the correct storage location (same filesystem,
    so this is O(1) — no copy). Use this after download_streaming() to avoid
    ever holding large pixel buffers in RAM.

    Returns eviction info dict if items were evicted, or None.
    """
    if directory is None:
        directory = config.INBOX_DIR
    _ensure_dir(directory)

    bin_path = f"{directory}/{message_id}.bin"
    try:
        os.rename(pixel_tmp_path, bin_path)
    except OSError:
        # Fallback: copy then delete (shouldn't happen on single LittleFS volume)
        try:
            with open(pixel_tmp_path, "rb") as src, open(bin_path, "wb") as dst:
                while True:
                    chunk = src.read(4096)
                    if not chunk:
                        break
                    dst.write(chunk)
                    gc.collect()
            os.remove(pixel_tmp_path)
        except Exception as e:
            print(f"[STORE] Failed to move temp file: {e}")
            return None

    json_path = f"{directory}/{message_id}.json"
    with open(json_path, "w") as f:
        json.dump(metadata, f)

    print(f"[STORE] Saved {message_id} to {directory}")

    eviction_info = _enforce_fifo(directory)
    gc.collect()
    return eviction_info


def _enforce_fifo(directory):
    """
    Delete oldest files when over FIFO cap.

    Returns:
        Eviction info dict if items were evicted, or None.
        Format: {"evicted": ["uuid1", "uuid2"], "directory": "/inbox"}
    """
    global _last_eviction

    try:
        files = os.listdir(directory)
    except OSError:
        return None

    # Group by UUID (each message has .bin and .json)
    uuids = set()
    for f in files:
        if f.endswith(".bin") or f.endswith(".json"):
            uuids.add(f.rsplit(".", 1)[0])

    if len(uuids) <= config.FIFO_CAP:
        return None

    # Sort by file modification time (oldest first)
    # Note: MicroPython os.stat returns tuple, st_mtime is index 8
    uuid_times = []
    for uid in uuids:
        bin_path = f"{directory}/{uid}.bin"
        try:
            stat = os.stat(bin_path)
            uuid_times.append((uid, stat[8]))  # st_mtime
        except OSError:
            uuid_times.append((uid, 0))

    uuid_times.sort(key=lambda x: x[1])

    # Delete oldest until at cap
    to_delete = len(uuids) - config.FIFO_CAP
    evicted = []
    for i in range(to_delete):
        uid = uuid_times[i][0]
        evicted.append(uid)
        for ext in (".bin", ".json"):
            path = f"{directory}/{uid}{ext}"
            try:
                os.remove(path)
                print(f"[STORE] FIFO deleted {path}")
            except OSError:
                pass

    gc.collect()

    if evicted:
        _last_eviction = evicted[-1]  # Track most recent eviction
        eviction_info = {
            "evicted": evicted,
            "directory": directory,
        }
        print(f"[STORE] Evicted {len(evicted)} items from {directory}")
        return eviction_info

    return None


def get_last_eviction():
    """Return the UUID of the most recently evicted item, or None."""
    return _last_eviction


def list_messages(directory=None):
    """List message UUIDs in a directory, sorted newest first."""
    if directory is None:
        directory = config.INBOX_DIR

    try:
        files = os.listdir(directory)
    except OSError:
        return []

    uuids = set()
    for f in files:
        if f.endswith(".bin"):
            uuids.add(f[:-4])

    # Sort by mtime, newest first
    uuid_times = []
    for uid in uuids:
        bin_path = f"{directory}/{uid}.bin"
        try:
            stat = os.stat(bin_path)
            uuid_times.append((uid, stat[8]))
        except OSError:
            uuid_times.append((uid, 0))

    uuid_times.sort(key=lambda x: x[1], reverse=True)
    return [uid for uid, _ in uuid_times]


def load_message(message_id, directory=None):
    """
    Load a message's pixel data and metadata.

    Returns:
        (pixel_data_bytes, metadata_dict) or (None, None) if not found
    """
    if directory is None:
        directory = config.INBOX_DIR

    bin_path = f"{directory}/{message_id}.bin"
    json_path = f"{directory}/{message_id}.json"

    try:
        with open(bin_path, "rb") as f:
            pixel_data = f.read()
    except OSError:
        return None, None

    metadata = {}
    try:
        with open(json_path, "r") as f:
            metadata = json.load(f)
    except (OSError, ValueError):
        pass

    return pixel_data, metadata


def delete_message(message_id, directory=None):
    """Delete a message by UUID."""
    if directory is None:
        directory = config.INBOX_DIR

    for ext in (".bin", ".json"):
        path = f"{directory}/{message_id}{ext}"
        try:
            os.remove(path)
        except OSError:
            pass

    print(f"[STORE] Deleted {message_id}")
    gc.collect()


def get_inventory():
    """
    Get a snapshot of the board's current file inventory.

    Returns:
        dict with inbox_count, art_count, inbox_ids, art_ids
    """
    inbox_ids = list_messages(config.INBOX_DIR)
    art_ids = list_messages(config.ART_DIR)
    return {
        "inbox_count": len(inbox_ids),
        "art_count": len(art_ids),
        "inbox_ids": inbox_ids,
        "art_ids": art_ids,
        "last_eviction": _last_eviction,
    }
