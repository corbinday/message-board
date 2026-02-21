# wifi.py - Streamlined, Patient WiFi for Pico 2 W / Space Unicorn
import time
import rp2
import network as net

# Status Codes
STAT_IDLE = 0
STAT_CONNECTING = 1
STAT_NOIP = 2 
STAT_GOT_IP = 3
STAT_WRONG_PASS = -3
STAT_NO_AP = -2

_wlan = None

def get_wlan():
    global _wlan
    if _wlan is None:
        _wlan = net.WLAN(net.STA_IF)
    return _wlan

def _setup_chip():
    """Configure radio settings once per boot."""
    wlan = get_wlan()
    try:
        rp2.country("US")
    except:
        pass
    wlan.active(True)
    # Disable power management for stable OTA transfers
    # 0xa11140 is the 'High Performance' magic constant
    try:
        wlan.config(pm=0xa11140)
    except:
        pass
    return wlan

def connect(ssid, password, max_retries=3):
    wlan = _setup_chip()
    
    if wlan.isconnected():
        return wlan.ifconfig()

    for attempt in range(1, max_retries + 1):
        print(f"[NET] Connecting to {ssid} (Attempt {attempt})...")
        wlan.connect(ssid, password)
        
        # Patience loop: Wait up to 20 seconds for IP
        for _ in range(20):
            status = wlan.status()
            
            if status == STAT_GOT_IP:
                conf = wlan.ifconfig()
                print(f"[NET] Connected! IP: {conf[0]}")
                return conf
            
            if status == STAT_WRONG_PASS:
                print("[NET] Fatal: Wrong Password")
                return None
            
            if status == STAT_NOIP:
                # Progress! We are associated, just waiting on Xfinity DHCP
                if _ % 5 == 0: print("[NET] Associated, waiting for IP...")
            
            time.sleep(1)
        
        print(f"[NET] Attempt {attempt} timed out. Resetting radio...")
        wlan.disconnect()
        time.sleep(1)

    return None

def connect_best(known_networks):
    """Simple scan-and-connect."""
    wlan = _setup_chip()
    print("[NET] Scanning...")
    try:
        # Get visible SSIDs
        visible = [r[0].decode('utf-8') for r in wlan.scan() if r[0]]
    except:
        visible = []

    # Filter known networks to only those visible
    to_try = [n for n in known_networks if n['ssid'] in visible]
    
    # If scan failed or found nothing, try all known blindly
    if not to_try:
        to_try = known_networks

    for net_info in to_try:
        res = connect(net_info['ssid'], net_info['password'])
        if res: return res
    return None

def is_connected():
    return get_wlan().isconnected()

def disconnect():
    wlan = get_wlan()
    wlan.disconnect()
    wlan.active(False)