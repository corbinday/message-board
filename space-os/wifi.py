# wifi.py - WiFi connection with multi-network support and scan-based selection
import time
import network as net


_wlan = None

# CYW43 status codes returned by _wlan.status()
_STAT_IDLE          =  0
_STAT_CONNECTING    =  1
_STAT_NOIP          =  2  # Associated at 802.11 level but DHCP not complete yet
_STAT_GOT_IP        =  3
_STAT_CONNECT_FAIL  = -1
_STAT_NO_AP         = -2
_STAT_WRONG_PASS    = -3

_STAT_NAMES = {
    _STAT_IDLE:         "IDLE",
    _STAT_CONNECTING:   "CONNECTING",
    _STAT_NOIP:         "NOIP(associated,DHCP_pending)",
    _STAT_GOT_IP:       "GOT_IP",
    _STAT_CONNECT_FAIL: "CONNECT_FAIL",
    _STAT_NO_AP:        "NO_AP_FOUND",
    _STAT_WRONG_PASS:   "WRONG_PASSWORD",
}

# Status codes where retrying the same network is pointless
_FATAL_STATUSES = {_STAT_WRONG_PASS, _STAT_NO_AP}


def _status_str():
    """Return a human-readable string for the current WLAN status code."""
    if _wlan is None:
        return "NO_WLAN"
    try:
        code = _wlan.status()
        return _STAT_NAMES.get(code, f"UNKNOWN({code})")
    except Exception as e:
        return f"ERR({e})"


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

    print(f"[NET] connect_best: chip status before reset = {_status_str()}")
    # Ensure a clean CYW43 state before scanning
    _reset_wlan()

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
        result = connect(
            ssid, password, max_retries=max_retries, retry_delay=retry_delay
        )
        if result is not None:
            return result

    print("[NET] All known network connection attempts failed.")
    return None


def _reset_wlan(hard=False):
    """Deactivate and reactivate the WLAN interface to reset the CYW43 chip.

    hard=True uses a longer sleep and is used after repeated failures.
    """
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)
    delay = 3 if hard else 1
    print(f"[NET] Resetting CYW43 ({'hard' if hard else 'soft'}, {delay}s)...")
    # Disconnect first so the chip doesn't auto-reconnect on activate
    try:
        _wlan.disconnect()
    except Exception:
        pass
    _wlan.active(False)
    time.sleep(delay)
    _wlan.active(True)
    # Poll until IDLE rather than sleeping a fixed time
    for _ in range(delay * 10):
        if _wlan.status() == _STAT_IDLE:
            break
        time.sleep(0.2)
    print(f"[NET] CYW43 reset done. Status: {_status_str()}")


def connect(ssid, password, max_retries=5, retry_delay=3):
    """Connect to a specific WiFi network with retry logic. Returns IP config or None."""
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)

    if _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    # Ensure a clean CYW43 state before first connection attempt
    _reset_wlan()

    for attempt in range(1, max_retries + 1):
        print(f"[NET] Connecting to {ssid} (attempt {attempt}/{max_retries}, chip={_status_str()})...")
        try:
            _wlan.connect(ssid, password)
        except OSError as e:
            print(f"[NET] connect() raised OSError: {e} (chip={_status_str()})")
            _reset_wlan(hard=(attempt > 1))
            time.sleep(retry_delay)
            continue

        # Poll for up to 30 s; log every 5 s.
        # NOIP (status 2) means associated but DHCP still in progress — be patient.
        connected = False
        for tick in range(30):
            if _wlan.isconnected():
                connected = True
                break
            if tick % 5 == 4:
                print(f"[NET]   {tick+1}s elapsed, chip={_status_str()}")
            time.sleep(1)

        if connected:
            config = _wlan.ifconfig()
            print(f"[NET] Connected to {ssid}: ip={config[0]} gw={config[2]}")
            return config

        status_code = None
        try:
            status_code = _wlan.status()
        except Exception:
            pass
        status_label = _STAT_NAMES.get(status_code, f"UNKNOWN({status_code})")
        print(f"[NET] Attempt {attempt} failed — chip status: {status_label}")

        # Don't retry if the failure is definitive
        if status_code in _FATAL_STATUSES:
            print(f"[NET] Fatal status ({status_label}) — skipping remaining retries for {ssid}")
            break

        try:
            _wlan.disconnect()
        except Exception:
            pass

        # After two consecutive soft failures, do a hard reset
        if attempt >= 2:
            _reset_wlan(hard=True)
        else:
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
        _wlan = None
    _reset_wlan()

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
