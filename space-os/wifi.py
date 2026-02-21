# wifi.py - WiFi connection with multi-network support and scan-based selection
import time
import rp2
import network as net


_wlan = None
_initialized = False  # Track whether we've done a clean init this boot

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

# Disable WiFi power saving for connection reliability
_PM_NONE = 0xa11140


def _status_str():
    """Return a human-readable string for the current WLAN status code."""
    if _wlan is None:
        return "NO_WLAN"
    try:
        code = _wlan.status()
        return _STAT_NAMES.get(code, f"UNKNOWN({code})")
    except Exception as e:
        return f"ERR({e})"


def _init_wlan():
    """Perform a clean CYW43 initialization from scratch.

    This always does a full power-off/power-on cycle regardless of current
    state, because the CYW43 can report IDLE while actually being in a
    corrupt state where connect() raises EPERM.

    Retries activation with progressive delays if the chip fails to start.
    Returns True if the chip is ready, False otherwise.
    """
    global _wlan, _initialized

    # Set country code before any WLAN operations
    try:
        rp2.country("US")
    except Exception:
        pass

    # Progressive power-off durations for each activation attempt
    off_delays = [1, 2, 3, 5]

    for i, off_delay in enumerate(off_delays):
        attempt = i + 1
        print(f"[NET] Initializing CYW43 (attempt {attempt}/{len(off_delays)})...")

        # Always start from a fully powered-down state
        if _wlan is not None:
            try:
                _wlan.disconnect()
            except Exception:
                pass
            try:
                _wlan.active(False)
            except Exception:
                pass
            time.sleep(off_delay)

        # Create a fresh WLAN object
        _wlan = net.WLAN(net.STA_IF)
        _wlan.active(True)

        # Give the chip time to finish firmware loading and RF calibration
        time.sleep(1)

        # Verify the chip actually came up by trying to read status
        try:
            st = _wlan.status()
            active = _wlan.active()
            print(f"[NET] CYW43 active={active}, status={_STAT_NAMES.get(st, st)}")
        except Exception as e:
            print(f"[NET] CYW43 status check failed: {e}")
            continue

        if not active:
            print(f"[NET] CYW43 not active after attempt {attempt}")
            continue

        # Disable power management for reliability
        try:
            _wlan.config(pm=_PM_NONE)
        except Exception:
            pass

        # Test that connect() won't EPERM by doing a scan (exercises the SPI bus)
        try:
            _wlan.scan()
            print(f"[NET] CYW43 ready (attempt {attempt})")
            _initialized = True
            return True
        except OSError as e:
            print(f"[NET] CYW43 scan test failed: {e} — chip not truly ready")
            continue

    print("[NET] CYW43 failed to initialize after all attempts")
    _initialized = False
    return False


def _scan_networks():
    """Scan for available WiFi networks. Returns list of (ssid, rssi) tuples."""
    if _wlan is None or not _initialized:
        if not _init_wlan():
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
    if _wlan and _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    # Initialize the chip (this also does a scan test)
    if not _initialized:
        if not _init_wlan():
            return None

    # Scan for available SSIDs
    available = _scan_networks()
    available_ssids = {ssid for ssid, _ in available}

    # Build connection order: known networks that are available, sorted by
    # signal strength among available
    candidates = []
    for net_info in known_networks:
        ssid = net_info.get("ssid", "")
        password = net_info.get("password", "")
        if ssid in available_ssids:
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
        )
        if result is not None:
            return result

    print("[NET] All known network connection attempts failed.")
    return None


def connect(ssid, password, max_retries=5, retry_delay=3):
    """Connect to a specific WiFi network with retry logic.

    Returns IP config tuple or None.
    """
    global _wlan, _initialized

    if _wlan and _wlan.isconnected():
        print(f"[NET] Already connected: {_wlan.ifconfig()}")
        return _wlan.ifconfig()

    # Ensure a clean chip init if we haven't done one yet
    if not _initialized:
        if not _init_wlan():
            print(f"[NET] CYW43 chip failed to start — cannot connect to {ssid}")
            return None

    for attempt in range(1, max_retries + 1):
        print(f"[NET] Connecting to {ssid} (attempt {attempt}/{max_retries}, chip={_status_str()})...")

        try:
            _wlan.connect(ssid, password)
        except OSError as e:
            print(f"[NET] connect() raised OSError: {e} (chip={_status_str()})")
            # Chip is in a bad state — do a full re-init
            _initialized = False
            if not _init_wlan():
                print("[NET] CYW43 unrecoverable after OSError")
                return None
            time.sleep(retry_delay)
            continue

        # Poll for up to 30 s; log every 5 s.
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

        # Re-init the chip between retries to get a clean state
        _initialized = False
        if not _init_wlan():
            print("[NET] CYW43 re-init failed between retries")
            return None

    print(f"[NET] All connection attempts to {ssid} failed.")
    return None


def reconnect(known_networks=None, ssid=None, password=None):
    """
    Attempt to reconnect to WiFi. Used for periodic reconnection from main loop.

    Returns IP config tuple or None.
    """
    global _wlan, _initialized

    if _wlan and _wlan.isconnected():
        return _wlan.ifconfig()

    # Force a clean init for reconnection
    _initialized = False

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
    global _wlan, _initialized
    if _wlan:
        try:
            _wlan.disconnect()
        except Exception:
            pass
        try:
            _wlan.active(False)
        except Exception:
            pass
        _wlan = None
    _initialized = False


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
