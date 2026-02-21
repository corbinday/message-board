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


def _ensure_chip_up():
    """Bring the CYW43 chip up reliably, retrying activation if it fails.

    The CYW43 driver can silently fail on active(True) — it prints
    '[CYW43] Failed to start CYW43' but does NOT raise an exception.
    We detect this by checking active() after the call and retry with
    progressively longer power-off periods.

    Returns True if the chip is up, False if all attempts failed.
    """
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)

    # If already active, verify it's responsive
    if _wlan.active():
        try:
            _wlan.status()
            return True
        except Exception:
            pass  # chip is wedged, fall through to reset

    # Progressive power-off durations (seconds) for each attempt
    power_off_delays = [1, 2, 3, 5]

    for i, delay in enumerate(power_off_delays):
        attempt = i + 1
        print(f"[NET] Activating CYW43 (attempt {attempt}/{len(power_off_delays)}, off={delay}s)...")

        # Full power-off cycle
        try:
            _wlan.active(False)
        except Exception:
            pass
        time.sleep(delay)

        # Re-create the WLAN object on later attempts to force a clean driver state
        if attempt >= 3:
            _wlan = net.WLAN(net.STA_IF)

        _wlan.active(True)
        time.sleep(0.5)  # brief settle before checking

        # Verify the chip actually came up
        if not _wlan.active():
            print(f"[NET] CYW43 activation failed (attempt {attempt})")
            continue

        # Wait for IDLE status (chip ready for commands)
        ready = False
        for _ in range(20):  # up to 4 seconds
            try:
                st = _wlan.status()
                if st == _STAT_IDLE:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if ready:
            # Extra settle time for RF calibration after IDLE is reported
            time.sleep(1)
            print(f"[NET] CYW43 up and ready (attempt {attempt}). Status: {_status_str()}")
            return True

        print(f"[NET] CYW43 not reaching IDLE (attempt {attempt}), status: {_status_str()}")

    print("[NET] CYW43 failed to start after all activation attempts")
    return False


def _scan_networks():
    """Scan for available WiFi networks. Returns list of (ssid, rssi) tuples."""
    if not _ensure_chip_up():
        return []

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
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)

    if _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    # Scan for available SSIDs (this also ensures the chip is up)
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
            ssid, password, max_retries=max_retries, retry_delay=retry_delay,
            _chip_ready=True,
        )
        if result is not None:
            return result

    print("[NET] All known network connection attempts failed.")
    return None


def _reset_wlan(hard=False):
    """Deactivate and reactivate the WLAN interface to reset the CYW43 chip.

    hard=True uses a longer sleep and is used after repeated failures.
    Returns True if the chip came back up, False otherwise.
    """
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)
    delay = 3 if hard else 1
    print(f"[NET] Resetting CYW43 ({'hard' if hard else 'soft'}, {delay}s)...")
    try:
        _wlan.active(False)
    except Exception:
        pass
    time.sleep(delay)

    # Re-create the WLAN object on hard resets for a clean driver state
    if hard:
        _wlan = net.WLAN(net.STA_IF)

    _wlan.active(True)
    time.sleep(0.5)

    # Verify activation succeeded
    if not _wlan.active():
        print(f"[NET] CYW43 reset failed — chip not active, retrying via _ensure_chip_up()")
        return _ensure_chip_up()

    # Poll until IDLE rather than sleeping a fixed time.
    for _ in range(delay * 10):
        if _wlan.status() == _STAT_IDLE:
            break
        time.sleep(0.2)
    time.sleep(1)  # let RF finish calibrating after IDLE is reported
    print(f"[NET] CYW43 reset done. Status: {_status_str()}")
    return True


def connect(ssid, password, max_retries=5, retry_delay=3, _chip_ready=False):
    """Connect to a specific WiFi network with retry logic.

    Args:
        ssid: Network SSID.
        password: Network password.
        max_retries: Number of connection attempts.
        retry_delay: Seconds between retries.
        _chip_ready: Internal flag — skip initial reset when called from
                     connect_best() which already ensured the chip is up.

    Returns:
        IP config tuple or None.
    """
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)

    if _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    # Ensure the chip is up before first attempt (skip if caller already did it)
    if not _chip_ready:
        if not _ensure_chip_up():
            print(f"[NET] CYW43 chip failed to start — cannot connect to {ssid}")
            return None

    for attempt in range(1, max_retries + 1):
        print(f"[NET] Connecting to {ssid} (attempt {attempt}/{max_retries}, chip={_status_str()})...")
        try:
            _wlan.connect(ssid, password)
        except OSError as e:
            print(f"[NET] connect() raised OSError: {e} (chip={_status_str()})")
            # The chip is likely wedged — do a full re-init rather than just reset
            if not _ensure_chip_up():
                print(f"[NET] CYW43 chip unrecoverable after OSError")
                return None
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

        # After two consecutive failures, do a hard reset
        if attempt >= 2:
            _reset_wlan(hard=True)
        else:
            _reset_wlan(hard=False)

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
