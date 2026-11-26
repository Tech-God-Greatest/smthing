"""
tools/registry.py — The single source of truth for all Phantom AI tools.

HOW IT WORKS
============
Every tool file exports:
  - A list named  ALL_TOOLS   → OpenAI-compatible tool schema(s)
  - A callable    execute      → dispatches tool calls by name, returns str

To add a new tool:
  1. Create  tools/your_tool.py  with ALL_TOOLS + execute
  2. Import and register it below in TOOL_MODULES — that's it!

Nothing else needs to change.  llm.py reads ALL_SCHEMAS and EXECUTOR automatically.
"""

# ── Import every tool module here ─────────────────────────────────────────────
from tools import memory_tools
from tools import web_tools
from tools import app_tools
from tools import keyboard_tools
from tools import mouse_tools
from tools import system_tools
from tools import os_control_tools

# ── Registry: list every module in the order you want tools exposed ───────────
TOOL_MODULES = [
    memory_tools,
    web_tools,
    app_tools,
    keyboard_tools,
    mouse_tools,
    system_tools,
    os_control_tools,
]

# ── Auto-built from the registry — do not edit below ─────────────────────────

def _build_schemas() -> list:
    """Collect every OpenAI-formatted tool schema from all registered modules."""
    schemas = []
    for mod in TOOL_MODULES:
        for tool in mod.ALL_TOOLS:
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            })
    return schemas


def _build_executor_map() -> dict:
    """Map every tool name → the execute() callable of its module."""
    mapping = {}
    for mod in TOOL_MODULES:
        for tool in mod.ALL_TOOLS:
            mapping[tool["name"]] = mod.execute
    return mapping


# Public exports used by llm.py
ALL_SCHEMAS: list = _build_schemas()          # Pass directly to OpenAI tools=
EXECUTOR_MAP: dict = _build_executor_map()   # Dispatch table: name → execute fn


def dispatch(name: str, args: dict) -> str:
    """Route a tool call by name to the correct module's execute() function."""
    if name in EXECUTOR_MAP:
        return EXECUTOR_MAP[name](name, args)
    for mod in TOOL_MODULES:
        try:
            res = mod.execute(name, args)
            mod_prefix = f"[{mod.__name__.split('.')[-1]}] Unknown tool:"
            if not str(res).startswith(mod_prefix):
                return res
        except Exception:
            pass
    return f"[ToolRegistry] Unknown tool: '{name}'"
