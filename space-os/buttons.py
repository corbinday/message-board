# buttons.py - 4-button UI handling per SpaceOS spec
# Supports normal mode actions + settings mode entry via B+C combo.
import time


# Button action constants
ACTION_SKIP = "skip"          # A: Skip to next message/art
ACTION_CYCLE = "cycle"        # B: Toggle auto-rotate
ACTION_MODE = "mode"          # C: Toggle inbox/art mode
ACTION_PLAY_PAUSE = "play"    # D short: Play/pause
ACTION_DELETE = "delete"       # D long (2s): Delete current
ACTION_SETTINGS = "settings"   # B+C simultaneous: Enter/exit settings mode

# Long press threshold in ms
LONG_PRESS_MS = 2000
# Window in ms for detecting simultaneous B+C press
COMBO_WINDOW_MS = 150

# Hardware button constants (set by main.py)
_unicorn = None
_SWITCH_A = None
_SWITCH_B = None
_SWITCH_C = None
_SWITCH_D = None

_last_state = {}
_d_press_start = 0
_b_press_time = 0  # Time B was pressed (for combo detection)
_c_press_time = 0  # Time C was pressed (for combo detection)
_combo_fired = False  # True if B+C combo was already fired this press cycle


def init(unicorn, switch_a, switch_b, switch_c, switch_d):
    """Initialize with hardware references and button constants."""
    global _unicorn, _SWITCH_A, _SWITCH_B, _SWITCH_C, _SWITCH_D
    _unicorn = unicorn
    _SWITCH_A = switch_a
    _SWITCH_B = switch_b
    _SWITCH_C = switch_c
    _SWITCH_D = switch_d


def poll():
    """
    Poll buttons and return a list of actions triggered this frame.

    Returns:
        List of action strings (e.g., [ACTION_SKIP], [ACTION_DELETE])
    """
    global _d_press_start, _b_press_time, _c_press_time, _combo_fired

    if not _unicorn:
        return []

    actions = []
    now = time.ticks_ms()

    # Button A - Skip
    a_pressed = _unicorn.is_pressed(_SWITCH_A)
    if a_pressed and not _last_state.get("a", False):
        actions.append(ACTION_SKIP)
    _last_state["a"] = a_pressed

    # Button B - Cycle auto-rotate (or settings combo with C)
    b_pressed = _unicorn.is_pressed(_SWITCH_B)
    b_was_pressed = _last_state.get("b", False)
    if b_pressed and not b_was_pressed:
        _b_press_time = now

    # Button C - Mode toggle (or settings combo with B)
    c_pressed = _unicorn.is_pressed(_SWITCH_C)
    c_was_pressed = _last_state.get("c", False)
    if c_pressed and not c_was_pressed:
        _c_press_time = now

    # Check for B+C simultaneous combo (both pressed within COMBO_WINDOW_MS)
    if b_pressed and c_pressed and not _combo_fired:
        if (abs(time.ticks_diff(_b_press_time, _c_press_time)) < COMBO_WINDOW_MS):
            actions.append(ACTION_SETTINGS)
            _combo_fired = True

    # When both are released, reset combo state
    if not b_pressed and not c_pressed:
        _combo_fired = False

    # Individual B release (only if combo wasn't fired)
    if not b_pressed and b_was_pressed and not _combo_fired:
        actions.append(ACTION_CYCLE)

    # Individual C release (only if combo wasn't fired)
    if not c_pressed and c_was_pressed and not _combo_fired:
        actions.append(ACTION_MODE)

    _last_state["b"] = b_pressed
    _last_state["c"] = c_pressed

    # Button D - Short press: play/pause, Long press (2s): delete
    d_pressed = _unicorn.is_pressed(_SWITCH_D)
    d_was_pressed = _last_state.get("d", False)

    if d_pressed and not d_was_pressed:
        # Button just pressed - record start time
        _d_press_start = now
    elif not d_pressed and d_was_pressed:
        # Button just released - check duration
        hold_duration = time.ticks_diff(now, _d_press_start)
        if hold_duration >= LONG_PRESS_MS:
            actions.append(ACTION_DELETE)
        else:
            actions.append(ACTION_PLAY_PAUSE)

    _last_state["d"] = d_pressed

    return actions
