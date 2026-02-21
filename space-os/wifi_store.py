# wifi_store.py - Local WiFi credential storage and AES decryption
#
# WiFi credentials are received as AES-128-CBC encrypted Ably messages,
# decrypted using the board's wifi_encryption_key from secrets.py,
# and stored locally on the device filesystem. They NEVER touch the server DB.

import json
from ubinascii import a2b_base64

import config


def _decrypt_wifi_payload(iv_b64, ciphertext_b64):
    """
    Decrypt an AES-128-CBC encrypted WiFi payload.

    Args:
        iv_b64: Base64-encoded 16-byte IV
        ciphertext_b64: Base64-encoded ciphertext (PKCS7 padded)

    Returns:
        List of network dicts [{"ssid": ..., "password": ..., "priority": ...}]
        or None on failure.
    """
    if not config.WIFI_ENCRYPTION_KEY:
        print("[WIFI] No wifi_encryption_key configured, cannot decrypt")
        return None

    try:
        from ucryptolib import aes

        key = a2b_base64(config.WIFI_ENCRYPTION_KEY)
        iv = a2b_base64(iv_b64)
        ciphertext = a2b_base64(ciphertext_b64)

        # AES-128-CBC decrypt (mode 2 = CBC in MicroPython ucryptolib)
        cipher = aes(key, 2, iv)
        plaintext = cipher.decrypt(ciphertext)

        # Remove PKCS7 padding
        pad_len = plaintext[-1]
        if pad_len < 1 or pad_len > 16:
            print(f"[WIFI] Invalid PKCS7 padding: {pad_len}")
            return None
        plaintext = plaintext[:-pad_len]

        networks = json.loads(plaintext)
        print(f"[WIFI] Decrypted {len(networks)} network(s)")
        return networks

    except Exception as e:
        print(f"[WIFI] Decryption failed: {e}")
        return None


def load_networks():
    """
    Load WiFi networks from local storage file.

    Returns a list of network dicts. Always includes the primary
    network from secrets.py as fallback.
    """
    networks = []

    # Load saved networks from local file
    try:
        with open(config.WIFI_NETWORKS_FILE, "r") as f:
            networks = json.load(f)
        print(
            f"[WIFI] Loaded {len(networks)} network(s) from {config.WIFI_NETWORKS_FILE}"
        )
    except (OSError, ValueError):
        pass

    # Ensure the primary provisioned network is always included as fallback
    if config.WIFI_SSID and not any(
        n.get("ssid") == config.WIFI_SSID for n in networks
    ):
        networks.append(
            {
                "ssid": config.WIFI_SSID,
                "password": config.WIFI_PASSWORD,
                "priority": -1,  # Lowest priority — other networks take precedence
            }
        )

    return networks


def save_networks(networks):
    """
    Save WiFi networks to local storage file.

    Only saves the non-primary networks — the primary network from secrets.py
    doesn't need to be duplicated in the file.
    """
    # Filter out the primary provisioned network to avoid duplication
    to_save = [n for n in networks if n.get("ssid") != config.WIFI_SSID]

    try:
        with open(config.WIFI_NETWORKS_FILE, "w") as f:
            json.dump(to_save, f)
        print(f"[WIFI] Saved {len(to_save)} network(s) to {config.WIFI_NETWORKS_FILE}")
    except Exception as e:
        print(f"[WIFI] Save failed: {e}")


def handle_wifi_update(payload):
    """
    Handle an incoming wifi_update command.

    Decrypts the AES-encrypted WiFi credentials and merges them into
    the local network list stored on the device filesystem.

    Args:
        payload: Command dict with "iv" and "payload" fields (base64).

    Returns:
        True if new networks were saved, False otherwise.
    """
    iv_b64 = payload.get("iv")
    ciphertext_b64 = payload.get("payload")

    if not iv_b64 or not ciphertext_b64:
        print("[WIFI] wifi_update missing iv or payload fields")
        return False

    new_networks = _decrypt_wifi_payload(iv_b64, ciphertext_b64)
    if not new_networks:
        return False

    # Load existing networks
    existing = load_networks()

    # Merge: update existing entries by SSID, or append new ones
    existing_ssids = {n["ssid"]: i for i, n in enumerate(existing)}

    for net in new_networks:
        ssid = net.get("ssid", "")
        if not ssid:
            continue
        if ssid in existing_ssids:
            # Update existing entry
            idx = existing_ssids[ssid]
            existing[idx] = net
            print(f"[WIFI] Updated network: {ssid}")
        else:
            # Add new entry
            existing.append(net)
            print(f"[WIFI] Added network: {ssid}")

    save_networks(existing)
    return True
