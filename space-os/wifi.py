# network.py - WiFi connection with retry logic
import time
import network as net


_wlan = None


def connect(ssid, password, max_retries=5, retry_delay=3):
    """Connect to WiFi with retry logic. Returns IP config or None."""
    global _wlan
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

    print("[NET] All connection attempts failed.")
    _wlan.active(False)
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
