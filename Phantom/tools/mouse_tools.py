"""
tools/mouse_tools.py — Mouse control tools for Phantom AI.

Enables clicking (LMB, RMB, MMB, double-click), cursor movement (absolute X,Y,
screen presets like center, and relative directions like "move mouse a little up"),
scrolling (up, down, left, right), mouse dragging, and querying mouse position.

TOOL CONTRACT
=============
  ALL_TOOLS   list   -> OpenAI tool schemas
  execute     func   -> execute(name: str, args: dict) -> str
"""

import time
import pyautogui

# Disable fail-safe popup when moving cursor to screen corners during automation
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

PRESET_LOCATIONS = {
    "center": (0.5, 0.5),
    "top_left": (0.25, 0.25),
    "top_right": (0.75, 0.25),
    "bottom_left": (0.25, 0.75),
    "bottom_right": (0.75, 0.75),
    "top_center": (0.5, 0.25),
    "bottom_center": (0.5, 0.75),
    "center_left": (0.25, 0.5),
    "center_right": (0.75, 0.5),
}

DIRECTION_OFFSETS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
}


def _get_screen_bounds():
    """Return current screen width and height in pixels."""
    return pyautogui.size()


def _clamp_coords(x: int, y: int, width: int, height: int):
    """Clamp target X, Y within valid screen resolution bounds."""
    clamped_x = max(0, min(int(x), width - 1))
    clamped_y = max(0, min(int(y), height - 1))
    return clamped_x, clamped_y


def get_mouse_position() -> str:
    """Return current mouse position and screen resolution."""
    cur_x, cur_y = pyautogui.position()
    w, h = _get_screen_bounds()
    return f"Current mouse position: ({cur_x}, {cur_y}) on screen ({w}x{h})."


def move_mouse(preset: str = "", direction: str = "", distance: int = 100, x: int = None, y: int = None) -> str:
    """
    Move mouse cursor to absolute (X, Y) coordinates, a preset screen region (e.g. center),
    or relatively in a direction (up, down, left, right).
    """
    w, h = _get_screen_bounds()

    # 1. Absolute X, Y positioning
    if x is not None and y is not None:
        target_x, target_y = _clamp_coords(x, y, w, h)
        pyautogui.moveTo(target_x, target_y, duration=0.1)
        return f"Moved mouse cursor to ({target_x}, {target_y})."

    # 2. Preset location positioning (e.g. center)
    preset_clean = str(preset or "").lower().strip().replace(" ", "_").replace("-", "_")
    if preset_clean in PRESET_LOCATIONS:
        ratio_x, ratio_y = PRESET_LOCATIONS[preset_clean]
        target_x = int(w * ratio_x)
        target_y = int(h * ratio_y)
        pyautogui.moveTo(target_x, target_y, duration=0.1)
        readable_preset = preset_clean.replace("_", " ").title()
        return f"Moved mouse cursor to {readable_preset} of screen ({target_x}, {target_y})."

    # 3. Relative directional movement (e.g. up, down, left, right)
    dir_clean = str(direction or "").lower().strip().replace(" ", "_").replace("-", "_")
    if dir_clean in DIRECTION_OFFSETS:
        dist_px = max(1, min(int(distance or 100), 2000))
        dx_mult, dy_mult = DIRECTION_OFFSETS[dir_clean]
        dx = dx_mult * dist_px
        dy = dy_mult * dist_px
        pyautogui.moveRel(dx, dy, duration=0.1)
        cur_x, cur_y = pyautogui.position()
        readable_dir = dir_clean.replace("_", " ")
        return f"Moved mouse {readable_dir} by {dist_px} pixels to ({cur_x}, {cur_y})."

    return "Error: Invalid move parameters. Specify either target 'x' and 'y' coordinates, a 'preset' (e.g. 'center'), or a 'direction' (e.g. 'up')."


def mouse_click(button: str = "left", clicks: int = 1, x: int = None, y: int = None) -> str:
    """Click mouse button (left/LMB, right/RMB, middle/MMB, double click) at current location or specified (X, Y)."""
    w, h = _get_screen_bounds()
    btn_clean = str(button or "left").lower().strip()
    if btn_clean in ["lmb", "primary"]:
        btn_clean = "left"
    elif btn_clean in ["rmb", "secondary"]:
        btn_clean = "right"
    elif btn_clean in ["mmb"]:
        btn_clean = "middle"

    if btn_clean not in ["left", "right", "middle"]:
        btn_clean = "left"

    count = max(1, min(int(clicks or 1), 10))

    if x is not None and y is not None:
        target_x, target_y = _clamp_coords(x, y, w, h)
        pyautogui.moveTo(target_x, target_y, duration=0.05)

    cur_x, cur_y = pyautogui.position()

    if count == 2 and btn_clean == "left":
        pyautogui.doubleClick(button="left")
        click_type_str = "Double-clicked"
    elif count == 3 and btn_clean == "left":
        pyautogui.tripleClick(button="left")
        click_type_str = "Triple-clicked"
    else:
        pyautogui.click(button=btn_clean, clicks=count, interval=0.05)
        button_name = "Left (LMB)" if btn_clean == "left" else ("Right (RMB)" if btn_clean == "right" else "Middle (MMB)")
        click_type_str = f"Clicked {button_name} mouse button" + (f" {count} times" if count > 1 else "")

    return f"{click_type_str} at position ({cur_x}, {cur_y})."


def mouse_scroll(direction: str = "down", scroll_amount: int = 5) -> str:
    """Scroll mouse wheel up, down, left, or right by scroll_amount notches."""
    dir_clean = str(direction or "down").lower().strip()
    amount = max(1, min(int(abs(scroll_amount or 5)), 100))

    # PyAutoGUI scroll units: 1 notch = ~100 units on Windows
    scroll_units = amount * 100

    if dir_clean in ["down", "south"]:
        pyautogui.scroll(-scroll_units)
        return f"Scrolled down by {amount} notches."
    elif dir_clean in ["up", "north"]:
        pyautogui.scroll(scroll_units)
        return f"Scrolled up by {amount} notches."
    elif dir_clean in ["left", "west"]:
        try:
            pyautogui.hscroll(-scroll_units)
            return f"Scrolled left by {amount} notches."
        except Exception:
            return f"Error: Horizontal scrolling is not supported on this system."
    elif dir_clean in ["right", "east"]:
        try:
            pyautogui.hscroll(scroll_units)
            return f"Scrolled right by {amount} notches."
        except Exception:
            return f"Error: Horizontal scrolling is not supported on this system."
    else:
        return f"Error: Invalid scroll direction '{direction}'. Must be 'up', 'down', 'left', or 'right'."


def mouse_drag(direction: str = "", distance: int = 100, x: int = None, y: int = None, button: str = "left") -> str:
    """Click and drag mouse cursor relative or to target (X, Y)."""
    w, h = _get_screen_bounds()
    btn_clean = "left" if str(button).lower().strip() not in ["left", "right", "middle"] else str(button).lower().strip()

    start_x, start_y = pyautogui.position()

    if x is not None and y is not None:
        target_x, target_y = _clamp_coords(x, y, w, h)
        pyautogui.dragTo(target_x, target_y, duration=0.25, button=btn_clean)
        return f"Dragged mouse from ({start_x}, {start_y}) to ({target_x}, {target_y})."

    dir_clean = str(direction or "").lower().strip().replace(" ", "_").replace("-", "_")
    if dir_clean in DIRECTION_OFFSETS:
        dist_px = max(1, min(int(distance or 100), 2000))
        dx_mult, dy_mult = DIRECTION_OFFSETS[dir_clean]
        dx = dx_mult * dist_px
        dy = dy_mult * dist_px
        pyautogui.dragRel(dx, dy, duration=0.25, button=btn_clean)
        end_x, end_y = pyautogui.position()
        readable_dir = dir_clean.replace("_", " ")
        return f"Dragged mouse {readable_dir} by {dist_px} pixels from ({start_x}, {start_y}) to ({end_x}, {end_y})."

    return "Error: Invalid drag parameters. Specify either target 'x' and 'y' coordinates or a 'direction'."


def mouse_action(
    action_type: str,
    button: str = "left",
    preset: str = "",
    direction: str = "",
    distance: int = 100,
    x: int = None,
    y: int = None,
    clicks: int = 1,
    scroll_amount: int = 5
) -> str:
    """Unified handler for performing mouse actions: click, move, scroll, drag, or get position."""
    if not action_type:
        return "Error: No action_type provided for mouse_action."

    action_clean = str(action_type or "").lower().strip().replace(" ", "_").replace("-", "_")

    try:
        if action_clean in ["click", "left_click", "lmb", "right_click", "rmb", "middle_click", "mmb", "double_click", "triple_click"]:
            # Route button type if explicit in action_clean
            target_button = button
            if action_clean in ["right_click", "rmb"]:
                target_button = "right"
            elif action_clean in ["middle_click", "mmb"]:
                target_button = "middle"

            target_clicks = clicks
            if action_clean == "double_click":
                target_clicks = 2
            elif action_clean == "triple_click":
                target_clicks = 3

            return mouse_click(button=target_button, clicks=target_clicks, x=x, y=y)

        elif action_clean in ["move", "move_to", "move_relative", "move_cursor"]:
            return move_mouse(preset=preset, direction=direction, distance=distance, x=x, y=y)

        elif action_clean in ["scroll", "scroll_wheel", "mouse_scroll"]:
            return mouse_scroll(direction=direction, scroll_amount=scroll_amount)

        elif action_clean in ["drag", "mouse_drag", "click_and_drag"]:
            return mouse_drag(direction=direction, distance=distance, x=x, y=y, button=button)

        elif action_clean in ["get_position", "position", "where"]:
            return get_mouse_position()

        else:
            return (
                f"Error: Unknown action_type '{action_type}'. "
                f"Must be 'click', 'double_click', 'right_click', 'move', 'scroll', 'drag', or 'get_position'."
            )

    except Exception as e:
        return f"Error performing mouse action: {e}"


# ── Tool schema (OpenAI function-calling format) ─────────────────────────────

ALL_TOOLS = [
    {
        "type": "function",
        "name": "mouse_action",
        "description": (
            "Perform mouse interactions on the computer: mouse clicks (LMB, RMB, MMB, double click), "
            "moving the cursor (to center, screen presets, absolute (X, Y) coordinates, or relative directions like 'up'/'down'), "
            "scrolling the mouse wheel, dragging, or getting current cursor position.\n\n"
            "WHEN AND HOW TO USE THIS TOOL:\n\n"
            "1. Mouse Clicks (`action_type='click'`):\n"
            "   - 'click' / 'left click' / 'LMB': set action_type='click', button='left'.\n"
            "   - 'right click' / 'RMB': set action_type='click', button='right' (or action_type='right_click').\n"
            "   - 'middle click' / 'MMB': set action_type='click', button='middle'.\n"
            "   - 'double click': set action_type='double_click' (or action_type='click', clicks=2).\n"
            "   - Optional target position: pass x and y to move cursor to (x, y) before clicking.\n\n"
            "2. Moving Mouse (`action_type='move'`):\n"
            "   - 'move mouse to [x], [y]': set action_type='move', x=[x], y=[y]. E.g. x=500, y=300.\n"
            "   - 'move mouse to centre' / 'center': set action_type='move', preset='center'.\n"
            "   - Screen Presets: 'center', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'top_center', 'bottom_center', 'center_left', 'center_right'.\n"
            "   - Relative Directions ('move mouse a little up'): set action_type='move', direction='up', distance=50.\n"
            "   - Relative Directions ('move mouse down'): set action_type='move', direction='down', distance=100.\n"
            "   - Directions: 'up', 'down', 'left', 'right', 'up_left', 'up_right', 'down_left', 'down_right'.\n\n"
            "3. Scrolling (`action_type='scroll'`):\n"
            "   - 'scroll down': set action_type='scroll', direction='down', scroll_amount=5.\n"
            "   - 'scroll up': set action_type='scroll', direction='up', scroll_amount=5.\n"
            "   - 'scroll left' / 'scroll right': set direction='left' or 'right'.\n\n"
            "4. Get Cursor Position (`action_type='get_position'`):\n"
            "   - 'where is mouse' / 'get mouse position': returns current (X, Y) coordinates and screen size."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": [
                        "click",
                        "double_click",
                        "right_click",
                        "middle_click",
                        "move",
                        "scroll",
                        "drag",
                        "get_position"
                    ],
                    "description": "Category of mouse action: 'click', 'double_click', 'right_click', 'middle_click', 'move', 'scroll', 'drag', or 'get_position'."
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button for clicks/drags: 'left' (LMB, default), 'right' (RMB), or 'middle' (MMB)."
                },
                "preset": {
                    "type": "string",
                    "enum": [
                        "center",
                        "top_left",
                        "top_right",
                        "bottom_left",
                        "bottom_right",
                        "top_center",
                        "bottom_center",
                        "center_left",
                        "center_right"
                    ],
                    "description": "Preset screen region target for moving mouse cursor (e.g. 'center')."
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right", "up_left", "up_right", "down_left", "down_right"],
                    "description": "Direction for relative movement, scrolling, or dragging (e.g. 'up', 'down', 'left', 'right')."
                },
                "distance": {
                    "type": "integer",
                    "description": "Distance in pixels for relative cursor movement or dragging (default 100, use ~50 for 'a little')."
                },
                "x": {
                    "type": "integer",
                    "description": "Target X coordinate on screen in pixels (0 to screen width)."
                },
                "y": {
                    "type": "integer",
                    "description": "Target Y coordinate on screen in pixels (0 to screen height)."
                },
                "clicks": {
                    "type": "integer",
                    "description": "Number of clicks to perform (default 1)."
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "Number of scroll notches/units for mouse wheel scrolling (default 5)."
                }
            },
            "required": ["action_type"]
        }
    },
    {
        "type": "function",
        "name": "get_mouse_position",
        "description": "Get current mouse cursor (X, Y) coordinates and screen resolution.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "type": "function",
        "name": "move_mouse",
        "description": "Move mouse cursor to coordinates (x, y), a screen preset (e.g. 'center'), or relative direction (e.g. 'up', 'down').",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X pixel coordinate."},
                "y": {"type": "integer", "description": "Target Y pixel coordinate."},
                "preset": {"type": "string", "enum": ["center", "top_left", "top_right", "bottom_left", "bottom_right"], "description": "Screen region preset."},
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Relative direction to move."},
                "distance": {"type": "integer", "description": "Distance in pixels (default 100)."}
            }
        }
    },
    {
        "type": "function",
        "name": "mouse_click",
        "description": "Click the mouse button (left, right, middle, or double-click).",
        "parameters": {
            "type": "object",
            "properties": {
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Button to click (default: 'left')."},
                "clicks": {"type": "integer", "description": "Number of clicks: 1 for single click, 2 for double click (default: 1)."},
                "x": {"type": "integer", "description": "Optional X coordinate to click at."},
                "y": {"type": "integer", "description": "Optional Y coordinate to click at."}
            }
        }
    },
    {
        "type": "function",
        "name": "mouse_scroll",
        "description": "Scroll the mouse wheel up or down.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction (default: 'down')."},
                "scroll_amount": {"type": "integer", "description": "Number of notches to scroll (default: 5)."}
            }
        }
    }
]


# ── Dispatcher (called by registry.dispatch) ──────────────────────────────────

def execute(name: str, args: dict) -> str:
    """Route mouse tool call by name."""
    if name == "mouse_action":
        return mouse_action(
            action_type=args.get("action_type", ""),
            button=args.get("button", "left"),
            preset=args.get("preset", ""),
            direction=args.get("direction", ""),
            distance=args.get("distance", 100),
            x=args.get("x", None),
            y=args.get("y", None),
            clicks=args.get("clicks", 1),
            scroll_amount=args.get("scroll_amount", 5)
        )
    elif name in ["move_mouse", "mouse_move"]:
        return move_mouse(
            preset=args.get("preset", ""),
            direction=args.get("direction", ""),
            distance=args.get("distance", 100),
            x=args.get("x", None),
            y=args.get("y", None)
        )
    elif name in ["mouse_click", "click_mouse"]:
        return mouse_click(
            button=args.get("button", "left"),
            clicks=args.get("clicks", 1),
            x=args.get("x", None),
            y=args.get("y", None)
        )
    elif name in ["mouse_scroll", "scroll_mouse"]:
        return mouse_scroll(
            direction=args.get("direction", "down"),
            scroll_amount=args.get("scroll_amount", 5)
        )
    elif name in ["get_mouse_position", "mouse_position"]:
        return get_mouse_position()

    return f"[mouse_tools] Unknown tool: '{name}'"


# Backwards compatibility aliases
MOUSE_TOOLS = ALL_TOOLS
execute_mouse_tool = execute
