"""
tools/keyboard_tools.py — Single combined keyboard action tool for Phantom AI.

Enables pressing single keys (e.g. 'p', 'space', 'enter'), keyboard shortcuts (e.g. 'ctrl+t', 'ctrl+w'),
and typing out text phrases into active application windows.

TOOL CONTRACT
=============
  ALL_TOOLS   list   -> OpenAI tool schemas
  execute     func   -> execute(name: str, args: dict) -> str
"""

import time
import pyautogui

# Disable fail-safe popup when moving cursor to screen corners during keyboard automation
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

KEY_ALIASES = {
    "esc": "escape",
    "return": "enter",
    "cmd": "win",
    "super": "win",
    "windows": "win",
    "control": "ctrl",
    "spacebar": "space",
}


def _normalize_key(k: str) -> str:
    k_clean = str(k).lower().strip()
    return KEY_ALIASES.get(k_clean, k_clean)


def keyboard_action(action_type: str, input_value: str, repeat: int = 1) -> str:
    """Execute keyboard action: press single key, shortcut combination, or type text phrase."""
    if not input_value:
        return "Error: No input_value provided for keyboard_action."

    action_type = str(action_type or "").lower().strip()
    count = max(1, min(int(repeat or 1), 20))

    try:
        if action_type == "press_key":
            key = _normalize_key(input_value)
            for _ in range(count):
                pyautogui.press(key)
                if count > 1:
                    time.sleep(0.05)
            return f"Pressed key '{key}'" + (f" {count} times." if count > 1 else ".")

        elif action_type == "shortcut":
            # e.g. "ctrl+t" -> ["ctrl", "t"], "ctrl+shift+t" -> ["ctrl", "shift", "t"]
            parts = [_normalize_key(p) for p in str(input_value).split("+") if p.strip()]
            if not parts:
                return "Error: Invalid shortcut key string."

            for _ in range(count):
                pyautogui.hotkey(*parts)
                if count > 1:
                    time.sleep(0.05)
            return f"Triggered shortcut '{'+'.join(parts)}'."

        elif action_type == "type_text":
            pyautogui.write(str(input_value), interval=0.01)
            return f"Typed phrase: '{input_value}'."

        else:
            return f"Error: Unknown action_type '{action_type}'. Must be 'press_key', 'shortcut', or 'type_text'."

    except Exception as e:
        return f"Error performing keyboard action: {e}"


# ── Tool schema (OpenAI function-calling format) ─────────────────────────────

ALL_TOOLS = [
    {
        "type": "function",
        "name": "keyboard_action",
        "description": (
            "Perform keyboard interactions on the computer: press individual keys, trigger keyboard shortcut combinations, or type text phrases into active windows.\n\n"
            "WHEN AND HOW TO USE THIS TOOL:\n\n"
            "1. Press Single Keys (`action_type='press_key'`):\n"
            "   - Use this tool to perform any task the user asks, even if not a direct  request to press any keys or shortcuts. Think about it and deciede what would be the best key or shortcut for the function. \n"
            "   - 'pause video' / 'play video' / 'pause' / 'resume': set input_value='p' (or 'space' / 'k').\n"
            "   - 'mute' / 'unmute': set input_value='m'.\n"
            "   - 'fullscreen' / 'exit fullscreen': set input_value='f'.\n"
            "   - 'press enter' / 'submit': set input_value='enter'.\n"
            "   - 'press tab' / 'next field': set input_value='tab'.\n"
            "   - 'press escape' / 'close popup': set input_value='escape'.\n"
            "   - Standard key names: 'p', 'k', 'f', 'm', 'space', 'enter', 'tab', 'escape', 'backspace', 'delete', 'up', 'down', 'left', 'right'.\n\n"
            "2. Trigger Keyboard Shortcuts (`action_type='shortcut'`):\n"
            "   - Use this tool to perform any task the user asks, even if not a direct  request to press any keys or shortcuts. Think about it and deciede what would be the best key or shortcut for the function. \n"
            "   - 'open new tab' / 'new tab': set input_value='ctrl+t'.\n"
            "   - 'close tab' / 'close current tab': set input_value='ctrl+w'.\n"
            "   - 'open new window' / 'new window': set input_value='ctrl+n'.\n"
            "   - 'reopen closed tab' / 'undo close tab': set input_value='ctrl+shift+t'.\n"
            "   - 'copy': set input_value='ctrl+c'.\n"
            "   - 'paste': set input_value='ctrl+v'.\n"
            "   - 'select all': set input_value='ctrl+a'.\n"
            "   - 'close app' / 'close window': set input_value='alt+f4'.\n"
            "   - 'show desktop' / 'minimize all': set input_value='win+d'.\n"
            "   - Join modifier keys with '+': e.g. 'ctrl+t', 'ctrl+w', 'ctrl+shift+t', 'alt+tab', 'win+d'.\n\n"
            "3. Type Text Phrases (`action_type='type_text'`):\n"
            "   - 'type [phrase]' or 'write [phrase]': set input_value='[phrase]'.\n"
            "   - Types out the exact string into whichever text box or app is currently focused."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["press_key", "shortcut", "type_text"],
                    "description": "The category of keyboard action: 'press_key' for single keys, 'shortcut' for key combinations (e.g. 'ctrl+t'), or 'type_text' to type out phrases."
                },
                "input_value": {
                    "type": "string",
                    "description": "The specific key name (e.g. 'p', 'space', 'enter'), shortcut string (e.g. 'ctrl+t', 'ctrl+w'), or text phrase to type (e.g. 'hello world')."
                },
                "repeat": {
                    "type": "integer",
                    "description": "Optional number of times to repeat the key action (default 1)."
                }
            },
        }
    },
    {
        "type": "function",
        "name": "press_key",
        "description": "Press a single keyboard key (e.g. 'space' for pause/resume, 'f' for fullscreen, 'm' for mute, 'enter', 'tab', 'escape').",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name (e.g. 'space', 'enter', 'esc', 'tab', 'p', 'f', 'm')."},
                "repeat": {"type": "integer", "description": "Number of times to press the key (default 1)."}
            },
            "required": ["key"]
        }
    },
    {
        "type": "function",
        "name": "shortcut",
        "description": "Trigger a keyboard shortcut combination (e.g. 'ctrl+t' for new tab, 'ctrl+w' to close tab, 'ctrl+c', 'ctrl+v', 'alt+f4', 'win+d').",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "Shortcut combination joined with '+' (e.g. 'ctrl+t', 'ctrl+w', 'win+d', 'alt+tab')."},
                "repeat": {"type": "integer", "description": "Repeat count (default 1)."}
            },
            "required": ["keys"]
        }
    },
    {
        "type": "function",
        "name": "type_text",
        "description": "Type a text phrase into whichever application or text field is currently focused.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type out."}
            },
            "required": ["text"]
        }
    }
]


# ── Dispatcher (called by registry.dispatch) ──────────────────────────────────

def execute(name: str, args: dict) -> str:
    """Route keyboard tool call by name."""
    if name == "keyboard_action":
        return keyboard_action(
            action_type=args.get("action_type", ""),
            input_value=args.get("input_value", ""),
            repeat=args.get("repeat", 1)
        )
    elif name == "press_key":
        key = args.get("key", args.get("input_value", ""))
        repeat = args.get("repeat", 1)
        return keyboard_action("press_key", key, repeat)
    elif name == "shortcut":
        keys = args.get("keys", args.get("shortcut", args.get("input_value", "")))
        repeat = args.get("repeat", 1)
        return keyboard_action("shortcut", keys, repeat)
    elif name == "type_text":
        text = args.get("text", args.get("input_value", ""))
        return keyboard_action("type_text", text)
    return f"[keyboard_tools] Unknown tool: '{name}'"


# Backwards compatibility aliases
KEYBOARD_TOOLS = ALL_TOOLS
execute_keyboard_tool = execute
