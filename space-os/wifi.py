# wifi.py - The "First-Time Success" Version
import time
import rp2
import network as net
import gc

STAT_GOT_IP = 3

def connect(ssid, password, max_retries=3):
    wlan = net.WLAN(net.STA_IF)
    
    # 1. THE "SILENCE" PERIOD
    # If we just rebooted, the router needs a moment to realize we're gone.
    print("[NET] Cooling down radio...")
    wlan.active(False)
    time.sleep(3.0) 
    
    wlan.active(True)
    try:
        rp2.country("US")
    except:
        pass

    # 2. THE "PRE-FLIGHT" SCAN
    # This wakes up the antenna and finds the correct channel frequency.
    # Without this, the first connect() call often 'misses' the router.
    print("[NET] Scanning for channel calibration...")
    try:
        wlan.scan()
        time.sleep(1.0)
    except:
        pass

    # 3. DISABLE POWER MANAGEMENT IMMEDIATELY
    try:
        wlan.config(pm=0xa11140)
    except:
        pass

    for attempt in range(1, max_retries + 1):
        print(f"[NET] Connecting to {ssid} (Attempt {attempt})...")
        wlan.connect(ssid, password)
        
        # 4. PATIENT DHCP WAIT
        # Xfinity gateways are slow. We wait up to 30 seconds.
        for i in range(30):
            status = wlan.status()
            if status == STAT_GOT_IP:
                conf = wlan.ifconfig()
                print(f"[NET] Connected! IP: {conf[0]}")
                return conf
            
            if i % 5 == 0 and i > 0:
                print(f"[NET]   ...still waiting for IP ({i}s)")
            
            time.sleep(1)
        
        print(f"[NET] Attempt {attempt} timed out. Resetting...")
        wlan.disconnect()
        time.sleep(2.0)

    return None