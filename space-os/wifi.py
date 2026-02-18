# wifi.py - WiFi connection with multi-network support and scan-based selection
import time
import network as net


_wlan = None


def _scan_networks():
    """Scan for available WiFi networks. Returns list of (ssid, rssi) tuples."""
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)

    _wlan.active(True)

    try:
        results = _wlan.scan()
        # scan returns list of tuples: (ssid, bssid, channel, RSSI, security, hidden)
        networks = []
        for r in results:
            ssid = r[0].decode("utf-8") if isinstance(r[0], bytes) else r[0]
            rssi = r[3]
            if ssid:  # Skip hidden networks with empty SSID
                networks.append((ssid, rssi))
        # Sort by signal strength (strongest first)
        networks.sort(key=lambda x: x[1], reverse=True)
        print(f"[NET] Scanned {len(networks)} networks")
        for ssid, rssi in networks[:5]:
            print(f"[NET]   {ssid}: {rssi} dBm")
        return networks
    except Exception as e:
        print(f"[NET] Scan failed: {e}")
        return []


def connect_best(known_networks, max_retries=3, retry_delay=3):
    """
    Scan for available networks and connect to the strongest known network.

    Args:
        known_networks: List of dicts with 'ssid' and 'password' keys,
                        ordered by priority (highest first).
        max_retries: Number of retry attempts per network.
        retry_delay: Seconds between retries.

    Returns:
        IP config tuple or None if all attempts fail.
    """
    global _wlan
    _wlan = net.WLAN(net.STA_IF)

    if _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    _wlan.active(True)

    # Scan for available SSIDs
    available = _scan_networks()
    available_ssids = {ssid for ssid, _ in available}

    # Build connection order: known networks that are available, sorted by
    # signal strength among available, but respecting priority ordering
    candidates = []
    for net_info in known_networks:
        ssid = net_info.get("ssid", "")
        password = net_info.get("password", "")
        if ssid in available_ssids:
            # Find the RSSI for this SSID
            rssi = next((r for s, r in available if s == ssid), -100)
            candidates.append((ssid, password, rssi))

    # Sort by RSSI (strongest first) among available known networks
    candidates.sort(key=lambda x: x[2], reverse=True)

    if not candidates:
        print("[NET] No known networks found in scan results.")
        # Fall back to trying all known networks blindly
        candidates = [(n["ssid"], n["password"], -100) for n in known_networks]

    for ssid, password, rssi in candidates:
        print(f"[NET] Trying {ssid} (RSSI: {rssi} dBm)")
        result = connect(ssid, password, max_retries=max_retries, retry_delay=retry_delay)
        if result is not None:
            return result

    print("[NET] All known network connection attempts failed.")
    return None


def connect(ssid, password, max_retries=5, retry_delay=3):
    """Connect to a specific WiFi network with retry logic. Returns IP config or None."""
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)

    if _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    _wlan.active(True)

    for attempt in range(1, max_retries + 1):
        print(f"[NET] Connecting to {ssid} (attempt {attempt}/{max_retries})...")
        _wlan.connect(ssid, password)

        wait = 10
        while wait > 0:
            if _wlan.isconnected():
                config = _wlan.ifconfig()
                print(f"[NET] Connected: {config}")
                return config
            wait -= 1
            time.sleep(1)

        print(f"[NET] Attempt {attempt} failed.")
        _wlan.disconnect()
        time.sleep(retry_delay)

    print(f"[NET] All connection attempts to {ssid} failed.")
    return None


def reconnect(known_networks=None, ssid=None, password=None):
    """
    Attempt to reconnect to WiFi. Used for periodic reconnection from main loop.

    Args:
        known_networks: List of known network dicts (preferred).
        ssid: Single SSID fallback.
        password: Single password fallback.

    Returns:
        IP config tuple or None.
    """
    global _wlan

    # Already connected
    if _wlan and _wlan.isconnected():
        return _wlan.ifconfig()

    # Clean up stale connection
    if _wlan:
        try:
            _wlan.disconnect()
        except Exception:
            pass
        _wlan.active(False)
        time.sleep(1)
        _wlan = None

    if known_networks:
        return connect_best(known_networks, max_retries=2, retry_delay=2)
    elif ssid and password:
        return connect(ssid, password, max_retries=2, retry_delay=2)

    return None


def is_connected():
    """Check if WiFi is currently connected."""
    return _wlan is not None and _wlan.isconnected()


def disconnect():
    """Disconnect WiFi."""
    global _wlan
    if _wlan:
        _wlan.disconnect()
        _wlan.active(False)
        _wlan = None


def get_current_ssid():
    """Return the SSID of the currently connected network, or None."""
    if _wlan and _wlan.isconnected():
        try:
            config = _wlan.config("essid")
            return config if config else None
        except Exception:
            return None
    return None


def get_signal_strength():
    """Return the RSSI of the current connection, or None."""
    if _wlan and _wlan.isconnected():
        try:
            return _wlan.status("rssi")
        except Exception:
            return None
    return None
