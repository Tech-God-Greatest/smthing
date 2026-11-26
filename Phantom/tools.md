# Phantom AI — Tool System Guide

Adding a new tool to Phantom is like clicking a block into place.
**Three steps. One file to edit. Zero changes to the AI engine.**

---

## How the Tool System Works

```
tools/
├── registry.py        <- THE ONLY FILE YOU EDIT to register a new tool
├── memory_tools.py    <- Memory (remember / forget / search)
├── web_tools.py       <- Web search + web page fetching
└── your_new_tool.py   <- Drop your new file here
```

Every tool file exports exactly **two things**:

| Export     | Type       | Purpose                                          |
|------------|------------|--------------------------------------------------|
| `ALL_TOOLS`| `list`     | OpenAI function-calling schema(s) for this file  |
| `execute`  | `function` | `execute(name: str, args: dict) -> str`          |

`llm.py` imports only `ALL_SCHEMAS` and `dispatch` from `tools/registry.py`.
It never needs to know which tools exist — the registry handles everything automatically.

---

## How to Add a New Tool (3 Steps)

### Step 1 — Drop the tool file into `tools/`

Create `tools/your_tool.py` following the contract template below.

### Step 2 — Register it in `tools/registry.py`

```python
# At the top — add your import
from tools import your_tool

# In TOOL_MODULES list — add your module
TOOL_MODULES = [
    memory_tools,
    web_tools,
    your_tool,   # <- add here
]
```

### Step 3 — Done

Restart Phantom. The AI now has your new tool on both Groq and Ollama paths.

---

## Tool File Template

```python
"""
tools/your_tool.py — Short description of what this tool does.

TOOL CONTRACT
=============
  ALL_TOOLS   list   -> OpenAI tool schemas for the tools in this file
  execute     func   -> execute(name: str, args: dict) -> str
"""

# Imports
# import whatever you need here


# Tool implementations

def my_function(param_one: str, param_two: str = "default") -> str:
    """What this function actually does."""
    # your logic here
    return "result string"


# Tool schemas (OpenAI function-calling format)

ALL_TOOLS = [
    {
        "type": "function",
        "name": "my_function",
        "description": (
            "Clear description for the AI: explain WHEN to use this tool "
            "and what it returns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "param_one": {
                    "type": "string",
                    "description": "What param_one is for."
                },
                "param_two": {
                    "type": "string",
                    "description": "What param_two is for. Optional."
                }
            },
            "required": ["param_one"]
        }
    }
    # Add more entries if this file has multiple tools
]


# Dispatcher (called by registry.dispatch)

def execute(name: str, args: dict) -> str:
    """Route tool calls by name. registry.py calls this automatically."""
    if name == "my_function":
        return my_function(
            args.get("param_one", ""),
            args.get("param_two", "default")
        )
    else:
        return f"[your_tool] Unknown tool: '{name}'"
```

---

## ChatGPT Prompt — Generate a Drag-and-Drop Tool Package

**Usage:** Replace the [CAPS] placeholders, paste into ChatGPT, send.
The reply will be a complete, ready-to-drop tool file + exact registry edit lines.

---

```
You are an expert Python developer helping me build a tool plugin for my AI voice
assistant called Phantom.

Phantom uses an OpenAI-compatible tool-calling system.
Every tool lives in its own file inside a `tools/` folder.
Each file must export:
  - ALL_TOOLS : list of OpenAI function-calling schema dicts
  - execute(name: str, args: dict) -> str : a dispatcher function

===========================================
TOOL REQUEST
===========================================
Tool name    : [TOOL_NAME]
File name    : tools/[FILE_NAME].py
What it does : [SHORT_DESCRIPTION]
               [LONGER_DESCRIPTION_IF_NEEDED]

Functions to expose to the AI:
  1. [FUNCTION_NAME_1]([PARAMS]) -> [RETURN_DESCRIPTION]
  2. [FUNCTION_NAME_2]([PARAMS]) -> [RETURN_DESCRIPTION]
  (add or remove lines as needed)

External libraries it may use : [e.g. "requests, google-api-python-client, none"]
Environment variables / secrets: [e.g. "GOOGLE_API_KEY or none"]
===========================================

Generate:

1. The complete `tools/[FILE_NAME].py` file using this exact template structure:

"""
tools/[FILE_NAME].py — [SHORT_DESCRIPTION]

TOOL CONTRACT
=============
  ALL_TOOLS   list   -> OpenAI tool schemas for the tools in this file
  execute     func   -> execute(name: str, args: dict) -> str
"""

# imports

# tool implementation functions

ALL_TOOLS = [...]   # one entry per exposed function

def execute(name: str, args: dict) -> str:
    # route by name, return str


2. The exact two lines to add in `tools/registry.py`:
   - The import line at the top of the file
   - The module name inside the TOOL_MODULES list

3. A one-sentence addition to the AI SYSTEM_PROMPT in `llm.py` so the AI
   knows when to use the new tool.

4. Any pip install commands needed.

Make the code clean, well-commented, and production-ready.
Return everything in clearly labelled code blocks with file paths as headers.
```

---

## Existing Tools Reference

| File                 | Tool names                                             | Description                                          |
|----------------------|--------------------------------------------------------|------------------------------------------------------|
| `memory_tools.py`    | `remember`, `forget`, `update_memory`, `search_memory` | Persistent user memory stored in `memory.json`       |
| `web_tools.py`       | `web_search`, `fetch_web_page`                         | DuckDuckGo search + web page scraping                |
| `app_tools.py`       | `open_app`, `close_app`, `open_website`                | Launch/kill desktop apps and open websites           |
| `keyboard_tools.py`  | `keyboard_action`                                      | Press keys (P, enter), shortcuts (ctrl+t), & type text|
| `mouse_tools.py`     | `mouse_action`                                         | Clicks (LMB, RMB, MMB), move (x,y, presets, relative), scroll, & drag|

---

## Quick-Reference Checklist

When adding a tool, verify every item:

- [ ] `tools/your_tool.py` exists and exports `ALL_TOOLS` and `execute`
- [ ] `tools/registry.py` has the import line at the top
- [ ] `tools/registry.py` has the module name inside `TOOL_MODULES`
- [ ] All `"name"` strings in `ALL_TOOLS` match the strings routed in `execute()`
- [ ] `execute()` always returns a `str` (never `None`)
- [ ] The AI SYSTEM_PROMPT in `llm.py` mentions when to use the new tool
- [ ] Any required packages are installed (`pip install ...`)
- [ ] Phantom restarted to pick up the new tool
