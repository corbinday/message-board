# buttons.py - 4-button UI handling per SpaceOS spec
import time


# Button action constants
ACTION_SKIP = "skip"          # A: Skip to next message/art
ACTION_CYCLE = "cycle"        # B: Toggle auto-rotate
ACTION_MODE = "mode"          # C: Toggle inbox/art mode
ACTION_PLAY_PAUSE = "play"    # D short: Play/pause
ACTION_DELETE = "delete"       # D long (2s): Delete current

# Long press threshold in ms
LONG_PRESS_MS = 2000

# Hardware button constants (set by main.py)
_unicorn = None
_SWITCH_A = None
_SWITCH_B = None
_SWITCH_C = None
_SWITCH_D = None

_last_state = {}
_d_press_start = 0


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
    global _d_press_start

    if not _unicorn:
        return []

    actions = []
    now = time.ticks_ms()

    # Button A - Skip
    a_pressed = _unicorn.is_pressed(_SWITCH_A)
    if a_pressed and not _last_state.get("a", False):
        actions.append(ACTION_SKIP)
    _last_state["a"] = a_pressed

    # Button B - Cycle auto-rotate
    b_pressed = _unicorn.is_pressed(_SWITCH_B)
    if b_pressed and not _last_state.get("b", False):
        actions.append(ACTION_CYCLE)
    _last_state["b"] = b_pressed

    # Button C - Mode toggle (inbox/art)
    c_pressed = _unicorn.is_pressed(_SWITCH_C)
    if c_pressed and not _last_state.get("c", False):
        actions.append(ACTION_MODE)
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
