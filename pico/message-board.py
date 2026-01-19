import time
import network
import gc
# NOTE: We assume 'urequests' is installed on your Pico W (via pip install micropython-urequests)
import urequests 
from cosmic import CosmicUnicorn
from picographics import PicoGraphics, DISPLAY_COSMIC_UNICORN as DISPLAY

# --- Global Hardware Initialization ---
cu = CosmicUnicorn()
graphics = PicoGraphics(DISPLAY)
cu.set_brightness(0.5)

# --- Button Constants & Configuration ---
WIFI_SSID = "badrobot"
WIFI_PASSWORD = "metalEater7"
BOARD_WIDTH = 32
BOARD_HEIGHT = 32
BYTE_SIZE = BOARD_WIDTH * BOARD_HEIGHT * 3

# Your Server Endpoint for fetching data
SERVER_ENDPOINT = "http://192.168.4.123:3000/message/get_canvas" 

# --- State Management ---
MODE_VIEW = 'VIEW'        
MODE_A = 'A'              
MODE_B = 'B'              
MODE_C = 'C'              
MODE_D_FETCH = 'D_FETCH' 
current_mode = MODE_A
last_button_state = 0 

# --- Helper Functions (RESTORED CONTENT) ---

def read_all_buttons():
    """Constructs the button state bitmask using official constants."""
    state = 0
    
    # Mode button (mapped to SWITCH_SLEEP for mode cycle/control)
    if cu.is_pressed(CosmicUnicorn.SWITCH_SLEEP): 
        state |= 0b00001
    # Buttons A, B, C, D
    if cu.is_pressed(CosmicUnicorn.SWITCH_A):
        state |= 0b00010 
    if cu.is_pressed(CosmicUnicorn.SWITCH_B):
        state |= 0b00100
    if cu.is_pressed(CosmicUnicorn.SWITCH_C):
        state |= 0b01000
    if cu.is_pressed(CosmicUnicorn.SWITCH_D):
        state |= 0b10000 
    return state 

def set_pixel(data, x, y, r, g, b):
    """
    Updates the bytearray 'data' at the specific x, y coordinate
    with the given r, g, b values.
    """
    pixel_index = (y * BOARD_WIDTH) + x
    offset = pixel_index * 3
    data[offset] = r
    data[offset + 1] = g
    data[offset + 2] = b
    gc.collect()

def generate_mock_message():
    """
    Generates a mock 32x32 RGB bytearray (3072 bytes) for display.
    This content was missing and is now restored.
    """
    # Initialize a bytearray with 3072 zeros (Black 32x32 grid)
    data = bytearray(BYTE_SIZE)

    # Example: Draw a Blue diagonal line
    for i in range(BOARD_WIDTH):
        set_pixel(data, x=i, y=i, r=0, g=0, b=255)

    # Example: Draw a Red square in the top right corner
    for y in range(5):
        for x in range(BOARD_WIDTH - 5, BOARD_WIDTH):
            set_pixel(data, x=x, y=y, r=255, g=0, b=0)

    # Example: specific individual dots to form an arrow
    set_pixel(data, 0, 0, 255, 0, 100)
    set_pixel(data, 0, 1, 255, 0, 100)
    set_pixel(data, 0, 2, 255, 0, 100)
    set_pixel(data, 0, 3, 255, 0, 100)
    set_pixel(data, 1, 0, 255, 0, 100)
    set_pixel(data, 2, 0, 255, 0, 100)
    set_pixel(data, 3, 0, 255, 0, 100)
    set_pixel(data, 1, 1, 255, 0, 100)
    set_pixel(data, 2, 2, 255, 0, 100)
    
    gc.collect()
    return data

def draw_from_bytes(binary_data):
    """Draws the 3072-byte array onto the Cosmic Unicorn display."""
    graphics.set_pen(graphics.create_pen(0, 0, 0))
    graphics.clear()

    ptr = 0
    for y in range(BOARD_HEIGHT):
        for x in range(BOARD_WIDTH):
            r = binary_data[ptr]
            g = binary_data[ptr + 1]
            b = binary_data[ptr + 2]

            pen = graphics.create_pen(r, g, b)
            graphics.set_pen(pen)
            graphics.pixel(x, y)

            ptr += 3
            
    cu.update(graphics)
    gc.collect()

def do_connect(ssid, password):
    """Attempts to connect the Pico W to the specified Wi-Fi network."""
    sta_if = network.WLAN(network.STA_IF)
    if sta_if.isconnected():
        print("Already connected.")
        return sta_if.ifconfig()

    print(f"Connecting to network: {ssid}...")
    sta_if.active(True)
    sta_if.connect(ssid, password)
    
    max_wait = 10
    while max_wait > 0:
        if sta_if.isconnected():
            break
        max_wait -= 1
        print("waiting for connection...")
        time.sleep(1)

    if sta_if.isconnected():
        config = sta_if.ifconfig()
        print(f"Network config: {config}")
        return config
    else:
        print("Connection failed!")
        sta_if.active(False)
        return None

def fetch_new_message_data():
    """
    Makes an HTTP request to the server, fetches the Base64 pixel data,
    decodes it, and returns the raw bytearray.
    """
    print(f"Requesting new canvas data from: {SERVER_ENDPOINT}")
    
    try:
        response = urequests.get(SERVER_ENDPOINT)
    except Exception as e:
        print(f"Network error during fetch: {e}")
        return None 

    if response.status_code != 200:
        print(f"Server error: HTTP {response.status_code}")
        response.close()
        return None

    try:
        json_data = response.json()
        base64_data = json_data.get('pixel_data_b64')
        
        response.close()
        
        if not base64_data:
            print("Server response missing 'pixel_data_b64' key.")
            return None
            
        import ubinascii
        raw_binary_data = ubinascii.a2b_base64(base64_data)
        
        if len(raw_binary_data) != BYTE_SIZE:
             print(f"Data size mismatch. Expected {BYTE_SIZE}, got {len(raw_binary_data)}")
             return None
        
        print("Fetch successful. Data decoded.")
        return raw_binary_data
        
    except Exception as e:
        print(f"Data processing error: {e}")
        return None

def handle_button_press(new_state, old_state):
    """
    Checks for button presses (edge detection) and updates current_mode.
    """
    global current_mode
    
    # Ignore MODE button for this A/B/C/D flow
    if (new_state & 0b00001) and not (old_state & 0b00001):
        print("MODE button pressed (ignored).")
        return True

    # Check for A, B, C, D button presses (set the mode directly)
    if (new_state & 0b00010) and not (old_state & 0b00010): # Button A
        current_mode = MODE_A
        print("Mode set to A (Display View)")
        return True
    
    if (new_state & 0b00100) and not (old_state & 0b00100): # Button B
        current_mode = MODE_B
        print("Mode set to B (Settings/Animation)")
        return True
        
    if (new_state & 0b01000) and not (old_state & 0b01000): # Button C
        current_mode = MODE_C
        print("Mode set to C (Status Display)")
        return True
        
    if (new_state & 0b10000) and not (old_state & 0b10000): # Button D
        current_mode = MODE_D_FETCH # Trigger the fetch process
        print("Mode set to D_FETCH (Initiating network request)")
        return True
        
    return False

def main_loop():
    """
    The main control loop of the application with mode-based execution.
    """
    global last_button_state, current_mode
    
    # --- 1. CONNECT TO WIFI ---
    wifi_config = do_connect(WIFI_SSID, WIFI_PASSWORD)
    if wifi_config is None:
        print("Application stopping due to network failure.")
        return 

    # --- 2. INITIALIZE STATE ---
    current_pixel_data = generate_mock_message()
    last_button_state = read_all_buttons()
    
    # 3. Main Application Loop
    while True:
        # --- BUTTON POLLING ---
        new_state = read_all_buttons()
        if new_state != last_button_state:
            handle_button_press(new_state, last_button_state)
            last_button_state = new_state
            
        # --- MAIN CONTROL FLOW ---
        
        # Mode A / VIEW: Default Display Mode
        if current_mode == MODE_A or current_mode == MODE_VIEW:
            draw_from_bytes(current_pixel_data)
            time.sleep(0.1) 
            
        # Mode B: Example Action/Animation
        elif current_mode == MODE_B:
            graphics.set_pen(graphics.create_pen(0, 255, 0))
            graphics.clear()
            graphics.text("MODE B", 1, 1, scale=1)
            cu.update(graphics)
            time.sleep(0.5) 
            current_mode = MODE_A 

        # Mode C: Status Display
        elif current_mode == MODE_C:
            graphics.set_pen(graphics.create_pen(255, 255, 0))
            graphics.clear()
            graphics.text("IP STATUS", 1, 1, scale=1)
            graphics.text(f"IP:{wifi_config[0]}", 1, 10, scale=1)
            cu.update(graphics)
            time.sleep(1) 
            current_mode = MODE_A 

        # Mode D_FETCH: Network Fetch Mode
        elif current_mode == MODE_D_FETCH:
            # 1. Show fetching status on the board 
            graphics.set_pen(graphics.create_pen(255, 0, 255))
            graphics.clear()
            graphics.text("FETCHING...", 1, 1, scale=1)
            cu.update(graphics)
            
            # 2. Execute the network request
            new_data = fetch_new_message_data()
            
            # 3. Update data state if successful
            if new_data is not None:
                current_pixel_data = new_data
                print("New message loaded successfully.")
                
            # 4. Revert to the default display mode (A)
            current_mode = MODE_A
            
            time.sleep(0.5) 
        
        gc.collect()

# --- Entry Point ---
if __name__ == "__main__":
    main_loop()