"""
tools/memory_tools.py — Persistent user memory (remember / forget / update / search).

TOOL CONTRACT (every tool file must follow this)
================================================
  ALL_TOOLS   list   → OpenAI tool schemas for the tools in this file
  execute     func   → execute(name: str, args: dict) -> str
"""

import os
import json
import threading

# ── File path ─────────────────────────────────────────────────────────────────
ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(ROOT_DIR, "memory.json")


# ── Internal helpers ──────────────────────────────────────────────────────────

_memory_lock = threading.RLock()

def _load_memory() -> dict:
    with _memory_lock:
        if not os.path.exists(MEMORY_FILE):
            return {}
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}


def _save_memory(mem: dict):
    with _memory_lock:
        with open(MEMORY_FILE, "w") as f:
            json.dump(mem, f, indent=4)


# Loaded once at import; mutated in-place by the functions below.
_memory: dict = _load_memory()


# ── Tool implementations ──────────────────────────────────────────────────────

def remember(category: str, key: str, value: str) -> str:
    with _memory_lock:
        if category not in _memory:
            _memory[category] = {}
        _memory[category][key] = value
        _save_memory(_memory)
        return f"Remembered {category}.{key}"


def forget(category: str, key: str) -> str:
    with _memory_lock:
        if category in _memory and key in _memory[category]:
            del _memory[category][key]
            if not _memory[category]:
                del _memory[category]
            _save_memory(_memory)
            return f"Forgot {category}.{key}"
        return "Memory not found"


def update_memory(category: str, key: str, value: str) -> str:
    with _memory_lock:
        if category not in _memory:
            _memory[category] = {}
        _memory[category][key] = value
        _save_memory(_memory)
        return f"Updated {category}.{key}"


def search_memory() -> str:
    """Return the entire memory store as a JSON string."""
    return json.dumps(_memory, indent=4)


# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

ALL_TOOLS = [
    {
        "type": "function",
        "name": "remember",
        "description": "Save useful long-term user information, preferences, habits, or facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Memory category, e.g. preferences, personal, technical"
                },
                "key": {
                    "type": "string",
                    "description": "Name / label of the memory entry"
                },
                "value": {
                    "type": "string",
                    "description": "The information to remember"
                }
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "type": "function",
        "name": "forget",
        "description": "Remove a specific memory entry.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "key":      {"type": "string"}
            },
            "required": ["category", "key"]
        }
    },
    {
        "type": "function",
        "name": "update_memory",
        "description": "Update an existing memory entry with a new value.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "key":      {"type": "string"},
                "value":    {"type": "string"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "type": "function",
        "name": "search_memory",
        "description": "Read all stored user memories.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]


# ── Dispatcher (called by registry.dispatch) ──────────────────────────────────

def execute(name: str, args: dict) -> str:
    """Route a memory tool call by name."""
    if name == "remember":
        return remember(
            args.get("category", "general"),
            args.get("key", ""),
            args.get("value", "")
        )
    elif name == "forget":
        return forget(
            args.get("category", "general"),
            args.get("key", "")
        )
    elif name == "update_memory":
        return update_memory(
            args.get("category", "general"),
            args.get("key", ""),
            args.get("value", "")
        )
    elif name == "search_memory":
        return search_memory()
    else:
        return f"[memory_tools] Unknown tool: '{name}'"


# ── Backwards-compat aliases (used in llm.py pre-refactor) ───────────────────
# These stay so nothing breaks if any file still imports them directly.
MEMORY_TOOLS        = ALL_TOOLS
execute_memory_tool = execute
