# player.py - Render frames and manage animation playback
import time
import gc

import config


# Hardware references (set by main.py after board detection)
_unicorn = None
_graphics = None


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
    if frame_index == 0:
        print(f"[PLAYER] Frame 0 rendered: {drawn} lit pixels out of {width * height}")
    gc.collect()


def play_animation(pixel_data, width, height, total_frames, fps, on_loop_complete=None):
    """
    Play an animation loop. Blocks until interrupted or one full loop completes.

    Args:
        pixel_data: Raw RGB bytes for all frames concatenated
        width: Frame width
        height: Frame height
        total_frames: Number of frames
        fps: Frames per second
        on_loop_complete: Callback called after first complete loop (for read receipts)

    Returns:
        True if completed a loop, False if interrupted
    """
    delay = 1.0 / fps if fps > 0 else 0.1
    frame_index = 0
    first_loop_done = False

    while True:
        render_frame(pixel_data, width, height, frame_index)
        time.sleep(delay)

        frame_index += 1

        if frame_index >= total_frames:
            if not first_loop_done:
                first_loop_done = True
                if on_loop_complete:
                    on_loop_complete()
            frame_index = 0
            return True  # Return after one loop for main loop to check buttons


def render_static(pixel_data, width, height):
    """Render a single static image."""
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
    if not _graphics or not _unicorn:
        return
    _graphics.set_pen(_graphics.create_pen(0, 0, 0))
    _graphics.clear()
    _unicorn.update(_graphics)
