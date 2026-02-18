# player.py - Render frames and manage animation playback
import time
import gc

import config


# Hardware references (set by main.py after board detection)
_unicorn = None
_graphics = None

# Active animation state (non-blocking playback)
_anim_data = None       # pixel_data bytes
_anim_width = 0
_anim_height = 0
_anim_frames = 0        # total frames
_anim_frame_index = 0   # current frame
_anim_delay_ms = 100    # ms between frames
_anim_last_frame = 0    # ticks_ms of last frame render
_anim_loops = 0         # number of completed loops
_anim_active = False     # whether an animation is playing


def init(unicorn, graphics):
    """Initialize with hardware references."""
    global _unicorn, _graphics
    _unicorn = unicorn
    _graphics = graphics


def render_frame(pixel_data, width, height, frame_index=0):
    """
    Render a single frame of RGB888 pixel data to the display.

    Args:
        pixel_data: Raw bytes (R,G,B per pixel, all frames concatenated)
        width: Frame width in pixels
        height: Frame height in pixels
        frame_index: Which frame to render (0-based)
    """
    if not _graphics or not _unicorn:
        print("[PLAYER] No graphics/unicorn reference!")
        return

    frame_size = width * height * 3
    offset = frame_index * frame_size

    if offset + frame_size > len(pixel_data):
        print(f"[PLAYER] Frame {frame_index} overflows data: need {offset + frame_size}, have {len(pixel_data)}")
        return

    _graphics.set_pen(_graphics.create_pen(0, 0, 0))
    _graphics.clear()

    drawn = 0
    ptr = offset
    for y in range(height):
        for x in range(width):
            if ptr + 2 >= len(pixel_data):
                break
            r = pixel_data[ptr]
            g = pixel_data[ptr + 1]
            b = pixel_data[ptr + 2]

            if r > 0 or g > 0 or b > 0:
                pen = _graphics.create_pen(r, g, b)
                _graphics.set_pen(pen)
                _graphics.pixel(x, y)
                drawn += 1

            ptr += 3

    _unicorn.update(_graphics)
    if frame_index == 0 and _anim_loops == 0:
        print(f"[PLAYER] Frame 0 rendered: {drawn} lit pixels out of {width * height}")
    gc.collect()


def start_animation(pixel_data, width, height, total_frames, fps):
    """
    Begin non-blocking animation playback. Call tick() in the main loop
    to advance frames.

    Args:
        pixel_data: Raw RGB bytes for all frames concatenated
        width: Frame width
        height: Frame height
        total_frames: Number of frames
        fps: Frames per second
    """
    global _anim_data, _anim_width, _anim_height, _anim_frames
    global _anim_frame_index, _anim_delay_ms, _anim_last_frame
    global _anim_loops, _anim_active

    _anim_data = pixel_data
    _anim_width = width
    _anim_height = height
    _anim_frames = total_frames
    _anim_frame_index = 0
    _anim_delay_ms = (1000 // fps) if fps > 0 else 100
    _anim_loops = 0
    _anim_active = True

    # Render frame 0 immediately
    render_frame(pixel_data, width, height, 0)
    _anim_last_frame = time.ticks_ms()


def tick():
    """
    Advance animation by one frame if enough time has elapsed.
    Call this every main loop iteration.

    Returns:
        True if a loop just completed, False otherwise.
    """
    global _anim_frame_index, _anim_last_frame, _anim_loops

    if not _anim_active:
        return False

    now = time.ticks_ms()
    if time.ticks_diff(now, _anim_last_frame) < _anim_delay_ms:
        return False

    # Advance to next frame
    _anim_frame_index += 1
    loop_completed = False

    if _anim_frame_index >= _anim_frames:
        _anim_frame_index = 0
        _anim_loops += 1
        loop_completed = True

    render_frame(_anim_data, _anim_width, _anim_height, _anim_frame_index)
    _anim_last_frame = now

    return loop_completed


def stop_animation():
    """Stop the current animation."""
    global _anim_active, _anim_data
    _anim_active = False
    _anim_data = None
    gc.collect()


def is_animating():
    """Check if an animation is currently playing."""
    return _anim_active


def loop_count():
    """Return how many full loops the current animation has completed."""
    return _anim_loops


def play_animation(pixel_data, width, height, total_frames, fps, on_loop_complete=None):
    """
    Play one full animation loop (blocking). Used for incoming message display.

    Args:
        pixel_data: Raw RGB bytes for all frames concatenated
        width: Frame width
        height: Frame height
        total_frames: Number of frames
        fps: Frames per second
        on_loop_complete: Callback after first complete loop

    Returns:
        True when loop completes
    """
    delay = 1.0 / fps if fps > 0 else 0.1

    for frame_index in range(total_frames):
        render_frame(pixel_data, width, height, frame_index)
        time.sleep(delay)

    if on_loop_complete:
        on_loop_complete()

    return True


def render_static(pixel_data, width, height):
    """Render a single static image."""
    global _anim_active
    _anim_active = False
    render_frame(pixel_data, width, height, 0)


def show_warp_animation(width, height, duration_ms=2000):
    """
    Show a warp-speed animation while downloading.
    Displays streaking lines effect.
    """
    if not _graphics or not _unicorn:
        return

    import random

    start = time.ticks_ms()
    stars = [(random.randint(0, width - 1), random.randint(0, height - 1)) for _ in range(15)]

    while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
        _graphics.set_pen(_graphics.create_pen(0, 0, 5))
        _graphics.clear()

        for i, (x, y) in enumerate(stars):
            # Draw streaking star
            brightness = random.randint(100, 255)
            pen = _graphics.create_pen(brightness, brightness, brightness)
            _graphics.set_pen(pen)
            _graphics.pixel(x, y)

            # Trail
            if y > 0:
                trail_pen = _graphics.create_pen(0, 0, brightness // 3)
                _graphics.set_pen(trail_pen)
                _graphics.pixel(x, y - 1)

            # Move star
            new_y = (y + random.randint(1, 3)) % height
            stars[i] = (x, new_y)

        _unicorn.update(_graphics)
        time.sleep(0.03)

    gc.collect()


def clear_display():
    """Turn off all pixels."""
    global _anim_active
    _anim_active = False
    if not _graphics or not _unicorn:
        return
    _graphics.set_pen(_graphics.create_pen(0, 0, 0))
    _graphics.clear()
    _unicorn.update(_graphics)


# =============================================================================
# Settings Screen Rendering
# =============================================================================

# Color scheme for settings menu items
_SETTINGS_COLORS = {
    "Brightness": (255, 200, 50),   # Yellow
    "Mode": (50, 150, 255),         # Blue
    "Auto-Rotate": (50, 255, 100),  # Green
    "WiFi": (200, 100, 255),        # Purple
    "Board Info": (100, 200, 200),  # Cyan
    "Exit": (255, 80, 80),          # Red
}


def render_settings_screen(width, height, item_name, value_str):
    """
    Render a settings screen on the pixel display.

    Since these are small pixel matrices (16x16 to 53x11), we use a
    visual indicator approach:
    - Top section: colored bar identifying the setting
    - Middle: value indicator (brightness bar, mode icon, toggle dot)
    - Bottom: navigation hints
    """
    if not _graphics or not _unicorn:
        return

    global _anim_active
    _anim_active = False

    _graphics.set_pen(_graphics.create_pen(0, 0, 0))
    _graphics.clear()

    color = _SETTINGS_COLORS.get(item_name, (200, 200, 200))
    r, g, b = color

    # Top bar: colored indicator for the current setting (2 rows)
    bar_pen = _graphics.create_pen(r, g, b)
    _graphics.set_pen(bar_pen)
    for x in range(width):
        _graphics.pixel(x, 0)
        _graphics.pixel(x, 1)

    # Middle section: value visualization
    mid_y = height // 2

    if item_name == "Brightness":
        # Brightness bar: fill proportional to value
        try:
            pct = int(value_str.replace("%", "")) / 100.0
        except (ValueError, AttributeError):
            pct = 0.5
        fill_width = max(1, int(width * pct))
        bright_pen = _graphics.create_pen(
            int(255 * pct), int(200 * pct), int(50 * pct)
        )
        _graphics.set_pen(bright_pen)
        for x in range(fill_width):
            for y_off in range(-1, 2):
                py = mid_y + y_off
                if 0 <= py < height:
                    _graphics.pixel(x, py)

    elif item_name == "Mode":
        # Mode: show "I" pattern for inbox, "A" pattern for art
        mode_pen = _graphics.create_pen(r, g, b)
        _graphics.set_pen(mode_pen)
        cx = width // 2
        if value_str == "Inbox":
            # Vertical bar for "I"
            for y_off in range(-2, 3):
                py = mid_y + y_off
                if 0 <= py < height:
                    _graphics.pixel(cx, py)
            # Top and bottom horizontal bars
            for x_off in range(-1, 2):
                px = cx + x_off
                if 0 <= px < width:
                    _graphics.pixel(px, mid_y - 2)
                    _graphics.pixel(px, mid_y + 2)
        else:
            # Diamond for "A"
            offsets = [(0, -2), (-1, -1), (1, -1), (-2, 0), (2, 0),
                       (-1, 0), (1, 0), (-2, 1), (2, 1), (-2, 2), (2, 2)]
            for dx, dy in offsets:
                px, py = cx + dx, mid_y + dy
                if 0 <= px < width and 0 <= py < height:
                    _graphics.pixel(px, py)

    elif item_name == "Auto-Rotate":
        # Toggle: green dot for On, dim dot for Off
        if value_str == "On":
            on_pen = _graphics.create_pen(0, 255, 0)
        else:
            on_pen = _graphics.create_pen(60, 60, 60)
        _graphics.set_pen(on_pen)
        cx = width // 2
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                px, py = cx + dx, mid_y + dy
                if 0 <= px < width and 0 <= py < height:
                    _graphics.pixel(px, py)

    elif item_name == "WiFi":
        # WiFi: show signal strength arcs or disconnected X
        wifi_pen = _graphics.create_pen(r, g, b)
        _graphics.set_pen(wifi_pen)
        cx = width // 2
        if value_str == "Disconnected":
            # Draw X
            for i in range(-2, 3):
                px1, py1 = cx + i, mid_y + i
                px2, py2 = cx + i, mid_y - i
                if 0 <= px1 < width and 0 <= py1 < height:
                    _graphics.pixel(px1, py1)
                if 0 <= px2 < width and 0 <= py2 < height:
                    _graphics.pixel(px2, py2)
        else:
            # Draw simple arc pattern
            _graphics.pixel(cx, mid_y + 1)
            for dx in range(-1, 2):
                py = mid_y
                px = cx + dx
                if 0 <= px < width and 0 <= py < height:
                    _graphics.pixel(px, py)
            for dx in range(-2, 3):
                py = mid_y - 1
                px = cx + dx
                if 0 <= px < width and 0 <= py < height:
                    _graphics.pixel(px, py)

    elif item_name == "Board Info":
        # Show board ID as a pattern of lit pixels
        info_pen = _graphics.create_pen(r, g, b)
        _graphics.set_pen(info_pen)
        # Use hash of value to create a unique pattern
        for i, ch in enumerate(value_str[:8]):
            val = ord(ch)
            x = (i * 3) % width
            y = mid_y + (val % 3) - 1
            if 0 <= x < width and 0 <= y < height:
                _graphics.pixel(x, y)
                if x + 1 < width:
                    _graphics.pixel(x + 1, y)

    elif item_name == "Exit":
        # Arrow pointing right (exit)
        exit_pen = _graphics.create_pen(r, g, b)
        _graphics.set_pen(exit_pen)
        cx = width // 2
        for dx in range(-2, 3):
            _graphics.pixel(cx + dx, mid_y)
        _graphics.pixel(cx + 2, mid_y - 1)
        _graphics.pixel(cx + 2, mid_y + 1)
        _graphics.pixel(cx + 1, mid_y - 2)
        _graphics.pixel(cx + 1, mid_y + 2)

    # Bottom row: dim navigation hint dots
    hint_pen = _graphics.create_pen(30, 30, 30)
    _graphics.set_pen(hint_pen)
    for x in range(0, width, 3):
        _graphics.pixel(x, height - 1)

    _unicorn.update(_graphics)
    gc.collect()
