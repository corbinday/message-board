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
