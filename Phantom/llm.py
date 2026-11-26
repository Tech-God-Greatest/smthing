"""
llm.py — LLM orchestration and tool execution for Phantom AI.

Architecture
────────────
  ┌────────────────────────────────────────────────────────────────────────┐
  │                              llm.py                                    │
  │                                                                        │
  │  execute_llm_query()        execute_qwen_query()  execute_vision_query │
  │        │                            │                      │           │
  │  ┌─────▼───────────────┐     ┌──────▼─────────┐     ┌──────▼─────────┐ │
  │  │ Dynamic Tool Router │     │  Local Ollama  │     │ Vision Handler │ │
  │  │  (intent filtering) │     │  (fallback/AI) │     │  (multimodal)  │ │
  │  └─────┬───────────────┘     └────────────────┘     └────────────────┘ │
  │        │                                                               │
  │  ┌─────▼───────────────┐     ┌───────────────────────────────────────┐ │
  │  │ Groq API Execution  │───▶│ Tool Execution Engine (_run_tool_calls│ │
  │  │ (1024 token budget) │     │  (ThreadPoolExecutor, 15s timeout)    │ │
  │  └─────────────────────┘     └───────────────────┬───────────────────┘ │
  └──────────────────────────────────────────────────┼─────────────────────┘
                                                     ▼
                                          tools.dispatch (registry)

Public Functions
────────────────
  execute_llm_query(query, chat_id, check_cancelled, on_tool_call, ai_mode) -> str
  execute_qwen_query(query, chat_id, check_cancelled, on_tool_call)         -> str
  execute_vision_query(query, image_path, chat_id, check_cancelled, ai_mode) -> str
  unload_ollama_model(model_name)                                           -> None
  clear_session(chat_id)                                                    -> None
  clean_llm_response(reply)                                                 -> str
  _build_messages(...)                                                      -> list
  _run_tool_calls(tool_calls, messages, on_tool_call)                       -> list
"""

import os
import re
import json
import time
import base64
import requests
from typing import Callable, Optional, Union
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

from storage import storage
from tools import ALL_SCHEMAS, dispatch, EXECUTOR_MAP
from tools.memory_tools import search_memory
from utils.logger import log_info, log_success, log_warning, log_error


# ── Model & API Configuration ──────────────────────────────────────────────────

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "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")
GROQ_MODEL        = os.environ.get("GROQ_MODEL",        "qwen/qwen3.8-27b")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
GROQ_FALLBACK_MODELS = [GROQ_MODEL, "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
OLLAMA_MODEL      = os.environ.get("OLLAMA_MODEL",      "qwen3.5:9b")
OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL",   "http://localhost:11434/v1")

# Primary Groq client: max_retries=0 prevents long blocking sleep loops on rate limits
client = OpenAI(
    api_key=GROQ_API_KEY or "no_key_set",
    base_url="https://api.groq.com/openai/v1",
    timeout=12.0,
    max_retries=0
)

# Ollama client (local fallback)
ollama_client = OpenAI(
    api_key="ollama",
    base_url=OLLAMA_BASE_URL,
    timeout=30.0,
    max_retries=1
)


# ── System Prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """NOTHINK: Do not think. Do not reason. Do not output <think> tags or reasoning steps. Output ONLY your final response or function calls directly.

You are Phantom, an intelligent, helpful, and concise voice assistant created by Lakshit Agarwal.
You act as a personal assistant to your boss (the user).

CRITICAL RESPONSE RULES:
- Output ONLY your final conversational response or standard function calls.
- Never output reasoning steps, thinking processes, or internal analysis.
- Keep responses short, direct, natural, and conversational.
- SPEAKING STYLE (CRITICAL FOR VOICE / TTS):
  * Speak naturally like a real human speaking aloud in conversation, NOT like someone reading written text, a report, or an article.
  * NEVER use bracketed tags, parentheses, or stage directions (e.g., do NOT write [excited], (laughs), [sigh], [pause], etc.).
  * NEVER use abbreviations, acronyms, or shorthand without spelling them out phonetically or conversationally (e.g., say "for example" instead of "e.g.", "that is" instead of "i.e.", "by the way" instead of "btw", "percent" instead of "%", "dollars" instead of "$", "gigabytes" instead of "GB", "operating system" or "Windows" instead of "OS").
  * Do NOT use bullet points, numbered lists, markdown formatting, or raw links in your spoken replies—phrase information into natural, flowing spoken sentences.
  * Use natural punctuation (periods, commas, question marks, and exclamation marks) to create rhythm, pauses, and expressive tone.
- ALWAYS use standard OpenAI function calling for tools. Never output raw JSON text in your response body.
- You have NO internal memory across sessions. You CANNOT remember anything or search memory without invoking function calls. You MUST call `remember` whenever asked to remember or store facts, and MUST call `search_memory` whenever asked what you remember or about the user. NEVER pretend to remember or say you stored/checked memory in text without calling the tool!
- Whenever current info, news, or websites are needed, call web_search automatically.

TOOL USAGE DIRECTIVES:
- MEMORY TOOLS: Whenever the user introduces themselves (e.g. "My name is ..."), states personal preferences, or asks you to remember facts, call `remember`. When asked about user facts or identity (e.g. "Who am I?", "What is my name?"), call `search_memory` first before answering.
- KEYBOARD & MEDIA TOOLS: Use `keyboard_action` (or direct keyboard tools `press_key`, `shortcut`, `type_text`) for keystrokes, shortcuts, typing, or media playback (e.g. action="press", key="space" or key="playpause" to play/pause media, key="f" for fullscreen).
- APPLICATION & WEB TOOLS: Use `open_app` for local desktop programs. For web services and websites (e.g., YouTube, Netflix, GitHub, or any URL), use `open_website` or `open_app`. Whenever asked what apps, programs, or windows are open or running, always call `list_open_windows`.
- MOUSE & CURSOR TOOLS: Use `mouse_action` (or direct mouse tools `get_mouse_position`, `move_mouse`, `mouse_click`, `mouse_scroll`) whenever asked to perform mouse clicks (left click/LMB, right click/RMB, middle click/MMB, double click), scroll (up, down, left, right), move the mouse cursor (to center, screen presets, specific X,Y coordinates, or relative directions like up/down/left/right), or query mouse position.
- HARDWARE & TELEMETRY TOOLS: Use `get_system_overview`, `get_top_resource_apps`, `get_process_list`, `get_cpu_status`, `get_cpu_specs`, `get_gpu_status`, `get_display_info`, `get_ram_status`, `get_ram_hardware_specs`, `get_disk_status`, `get_storage_hardware_info`, `get_motherboard_info`, `get_network_info`, `get_battery_status`, `get_temperatures`, `get_fan_speeds`, `get_power_draw` for hardware monitoring, specs, temperatures, fan speeds, power draw, and Task Manager app resource ranking.
- OS CONTROL & WINDOW TOOLS: Use OS control & window tools (`list_open_windows`, `focus_window`, `minimize_window`, `maximize_window`, `restore_window`, `resize_window`, `lock_pc`, `sleep_pc`, `restart_pc`, `shutdown_pc`, `logoff_user`, `open_task_manager`, `kill_process`, `set_volume`, `mute_audio`, `change_brightness`, `empty_recycle_bin`) whenever asked what apps are open/running (`list_open_windows`), or to focus, minimize, maximize, restore, resize windows, lock/sleep/restart/shutdown/logoff PC, open task manager, kill processes, adjust master volume, mute/unmute audio, change screen brightness, or empty the recycle bin.

INSTRUCTIONS FOR EFFICIENT & MULTI-STEP TOOL USAGE:
- Carefully analyze the user's entire request before responding.
- Identify every task that requires tool execution.
- MULTI-STEP / SEQUENTIAL TASKS:
  - If a task requires multiple steps sequentially (e.g. searching for content and opening it, or searching then fetching a web page):
    1. FIRST step: Issue tool call `web_search` (e.g., query="[search terms]").
    2. SECOND step: When search results return a target URL, immediately issue tool call `open_website(url="[target_url]")`.
    3. THIRD step: Provide a short confirmation (e.g., "Opening [item] in browser.").
  - DO NOT STOP after `web_search` if the user asked you to play, open, or perform an action!
- PARALLEL TOOL CALLS:
  - If multiple independent tool actions are requested (e.g. "open spotify and open chrome"), call both tools simultaneously in a single turn.
- A tool may be called multiple times across iterations if the user's request requires repeated execution of the same action.
- Execute independent tool calls in parallel whenever supported. Only perform tool calls sequentially when one depends on the output of another.
- Never ignore or omit a valid portion of the user's request simply because another tool has already been called.


Whatever the USER aka MASTER asks for is your do or die command.
"""

QWEN_SYSTEM_PROMPT = "NOTHINK: Do not output reasoning or <think> tags. Output ONLY your final response or function calls directly.\n\n" + SYSTEM_PROMPT
GROQ_SYSTEM_PROMPT = SYSTEM_PROMPT


# ── Dynamic Tool Routing ───────────────────────────────────────────────────────

class ToolRouter:
    """
    Intelligently attaches only the relevant tool schemas based on the query and
    recent conversational context.

    Why this is critical:
      The 45 registered tools consume ~5,350 tokens when passed indiscriminately.
      Groq's on-demand tier enforces an 8,000 Input Tokens Per Minute (ITPM) limit.
      By dynamically selecting only the relevant tool categories (or omitting tools
      for conversational queries), prompt tokens drop to ~50–800 tokens, completely
      eliminating rate-limit freezes across rapid multi-turn chats.
    """

    _SCHEMA_MAP = {s["function"]["name"]: s for s in ALL_SCHEMAS}

    _PATTERNS = {
        "web": re.compile(r'\b(search|google|browse|website|weather|news|forecast|stocks|look\s*up|find\s*out|online|wiki|wikipedia|url|http|who\s*is|current|latest|price|score)\b', re.I),
        "apps": re.compile(r'\b(open|launch|start|close|quit|app|application|apps|chrome|spotify|notepad|calc|calculator|browser|window|windows|youtube|netflix|github)\b', re.I),
        "memory": re.compile(r'\b(remember|forget|memory|remind|favorite|preference|recall|note\s*down|keep\s*in\s*mind|who\s*am\s*i|my\s*name\s*is|what\s*is\s*my\s*name|what\'?s\s*my\s*name|i\s*like|i\s*prefer|call\s*me)\b', re.I),
        "keyboard": re.compile(r'\b(press|type|key|shortcut|hotkey|enter|space|tab|backspace|ctrl|alt|shift|esc|escape|fullscreen|pause|play|resume|copy|paste)\b', re.I),
        "mouse": re.compile(r'\b(mouse|click|double\s*click|right\s*click|middle\s*click|cursor|scroll|drag|pointer|coordinates|position)\b', re.I),
        "system": re.compile(r'\b(cpu|gpu|ram|memory|battery|temp|temperature|fan|power|watt|wattage|hardware|disk|storage|drive|specs|specification|system|vram|motherboard|mobo|process|processes|task\s*manager|network|net|wifi|ethernet|ip|bandwidth|display|monitor|screen)\b', re.I),
        "os_control": re.compile(r'\b(volume|mute|unmute|sound|audio|brightness|window|windows|minimize|maximize|restore|resize|lock\s*pc|sleep\s*pc|restart\s*pc|shutdown|recycle\s*bin|kill\s*process|end\s*task)\b', re.I),
    }

    _CATEGORY_TOOLS = {
        "web": ["web_search", "fetch_web_page", "open_website"],
        "apps": ["open_app", "close_app", "open_website", "list_open_windows", "focus_window"],
        "memory": ["remember", "forget", "update_memory", "search_memory"],
        "keyboard": ["keyboard_action", "press_key", "shortcut", "type_text"],
        "mouse": ["mouse_action", "get_mouse_position", "move_mouse", "mouse_click", "mouse_scroll"],
        "system": [
            "get_system_overview", "get_cpu_status", "get_cpu_specs", "get_gpu_status",
            "get_display_info", "get_ram_status", "get_ram_hardware_specs", "get_disk_status",
            "get_storage_hardware_info", "get_motherboard_info", "get_network_info",
            "get_battery_status", "get_temperatures", "get_fan_speeds", "get_power_draw",
            "get_top_resource_apps", "get_process_list"
        ],
        "os_control": [
            "set_volume", "mute_audio", "change_brightness", "list_open_windows",
            "focus_window", "minimize_window", "maximize_window", "restore_window",
            "resize_window", "lock_pc", "sleep_pc", "restart_pc", "shutdown_pc",
            "logoff_user", "open_task_manager", "kill_process", "empty_recycle_bin"
        ]
    }

    _CORE_FALLBACK_TOOLS = [
        "web_search", "open_website", "open_app", "close_app", "remember",
        "search_memory", "keyboard_action", "get_system_overview",
        "list_open_windows", "set_volume"
    ]

    @classmethod
    def get_tools(cls, query: str, recent_messages: Optional[list] = None) -> Optional[list]:
        """Select appropriate OpenAI tool schemas based on the query and recent messages."""
        q_lower = (query or "").lower().strip()

        # Build search corpus ONLY from user and tool turns (NEVER match inside system prompt)
        corpus_parts = [q_lower]
        if recent_messages:
            for msg in recent_messages[-4:]:
                role = msg.get("role", "")
                if role in ["user", "tool"]:
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        corpus_parts.append(content.lower())
        corpus = " ".join(corpus_parts)

        selected_tool_names = set()

        # Check regex pattern matches across each category
        for cat_name, pattern in cls._PATTERNS.items():
            if pattern.search(corpus):
                cat_tools = cls._CATEGORY_TOOLS[cat_name]
                selected_tool_names.update(cat_tools)

        # Retain tools if prior message was an active tool call or tool response
        if recent_messages and len(recent_messages) >= 1:
            last_msg = recent_messages[-1]
            if last_msg.get("role") in ["tool", "assistant"] and (last_msg.get("tool_calls") or last_msg.get("tool_call_id")):
                selected_tool_names.update(["web_search", "fetch_web_page", "open_website", "open_app"])

        if not selected_tool_names:
            # Pure conversational query — zero tools attached, saving ~4,000+ prompt tokens
            return None

        schemas = [cls._SCHEMA_MAP[name] for name in selected_tool_names if name in cls._SCHEMA_MAP]
        return schemas if schemas else None


# ── In-Process Session Memory & Message Building ───────────────────────────────

_session_messages: dict[int, list] = {}


def _serialize_tool_call(tc) -> dict:
    """Ensure a tool call object is a plain JSON-serializable dictionary."""
    if isinstance(tc, dict):
        return tc
    fn = getattr(tc, "function", None)
    return {
        "id": getattr(tc, "id", f"tc_{time.time()}"),
        "type": "function",
        "function": {
            "name": getattr(fn, "name", "") if fn else "",
            "arguments": getattr(fn, "arguments", "{}") if fn else "{}"
        }
    }


def _normalize_message(msg: Union[dict, object]) -> dict:
    """Ensure any message object (e.g. OpenAI ChatCompletionMessage or dict) is a standard dict."""
    if isinstance(msg, dict):
        res = dict(msg)
        if "tool_calls" in res and res["tool_calls"]:
            res["tool_calls"] = [_serialize_tool_call(tc) for tc in res["tool_calls"]]
        return res

    res = {"role": getattr(msg, "role", "assistant")}
    content = getattr(msg, "content", None)
    if content is not None:
        res["content"] = content
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls is not None:
        res["tool_calls"] = [_serialize_tool_call(tc) for tc in tool_calls]
    tool_call_id = getattr(msg, "tool_call_id", None)
    if tool_call_id is not None:
        res["tool_call_id"] = tool_call_id
    name = getattr(msg, "name", None)
    if name is not None:
        res["name"] = name
    return res


def _build_messages(arg1=None, arg2=None, query: Optional[str] = None, chat_id: Optional[int] = None, limit: int = 20, system_prompt: Optional[str] = None) -> list:
    """
    Build the messages list incorporating system prompt, active memory, and recent chat history.
    Maintains compatibility with tests and callers that pass arguments in different orders:
      - _build_messages(system_prompt, chat_id=1, query="...")
      - _build_messages("Final question", chat_id)
      - _build_messages(chat_id)
    """
    # 1. Resolve positional arguments
    resolved_query = query
    resolved_chat_id = chat_id
    resolved_sys_prompt = system_prompt or SYSTEM_PROMPT

    if isinstance(arg1, str) and ("You are Phantom" in arg1 or "NOTHINK" in arg1):
        resolved_sys_prompt = arg1
    elif isinstance(arg1, str) and resolved_query is None:
        resolved_query = arg1
    elif isinstance(arg1, int) and resolved_chat_id is None:
        resolved_chat_id = arg1

    if isinstance(arg2, int) and resolved_chat_id is None:
        resolved_chat_id = arg2
    elif isinstance(arg2, str) and resolved_query is None:
        resolved_query = arg2

    messages = [{"role": "system", "content": resolved_sys_prompt}]

    # 2. Inject chat summary if present
    if resolved_chat_id is not None:
        try:
            summary = storage.get_chat_summary(resolved_chat_id)
            if summary and summary.strip():
                messages.append({"role": "system", "content": f"Chat Summary: {summary.strip()}"})
        except Exception as e:
            log_warning("Summary", f"Failed to retrieve chat summary: {e}")

    # 3. Inject stored user memory dynamically
    try:
        import tools.memory_tools
        search_fn = getattr(tools.memory_tools, "search_memory", None)
        if callable(search_fn):
            try:
                current_mem = search_fn(resolved_query or "")
            except TypeError:
                current_mem = search_fn()
            if current_mem and str(current_mem).strip() and str(current_mem) != "{}":
                messages.append({"role": "system", "content": f"User Stored Memory: {current_mem}"})
    except Exception as e:
        log_warning("Memory", f"Failed to retrieve stored memory: {e}")

    # 4. Retrieve recent history from storage if chat_id is provided, respecting ~32,000 char budget
    if resolved_chat_id is not None:
        try:
            db_msgs = storage.get_recent_messages(resolved_chat_id, limit=limit)
            history_entries = []
            for m in db_msgs:
                role = m.get("role", "")
                content = m.get("content", "")
                if resolved_query and role == "user" and content == resolved_query:
                    continue
                if content:
                    history_entries.append({"role": role, "content": str(content)})

            # Cap character budget to ~32,000 characters (trim oldest messages first)
            budget = 30000
            total_history_chars = sum(len(h["content"]) for h in history_entries)
            while total_history_chars > budget and len(history_entries) > 1:
                removed = history_entries.pop(0)
                total_history_chars -= len(removed["content"])

            messages.extend(history_entries)
        except Exception as e:
            log_warning("History", f"Failed to load recent messages: {e}")

    # 5. Append current user query if provided
    if resolved_query:
        messages.append({"role": "user", "content": resolved_query})

    return messages


def _get_session(chat_id: int, system_prompt: str, mode: str = "default") -> list:
    """Return (or initialize) the running messages list for an active chat session."""
    key = (chat_id, mode)
    if key not in _session_messages:
        _session_messages[key] = _build_messages(system_prompt=system_prompt, chat_id=chat_id, limit=10)
    return _session_messages[key]


def clear_session(chat_id: int) -> None:
    """Drop in-memory history for a chat session across all modes."""
    keys_to_del = [k for k in list(_session_messages.keys()) if (k == chat_id or (isinstance(k, tuple) and k[0] == chat_id))]
    for k in keys_to_del:
        _session_messages.pop(k, None)


# ── Response Cleaning & Formatting ─────────────────────────────────────────────

def clean_llm_response(reply: Optional[str]) -> str:
    """
    Strip internal thinking blocks, ReAct JSON thoughts, and citation artifacts
    from LLM output while preserving valid response text and markdown.
    """
    if not reply:
        return ""

    # 1. Strip reasoning blocks: <think>...</think> and unclosed <think>...
    cleaned = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'</?think>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^(?:Here\'s a thinking process:|Here is a thinking process:)\s*', '', cleaned, flags=re.IGNORECASE)

    # 2. Check if wrapped in markdown code blocks e.g. ```json ... ```
    stripped_block = cleaned.strip()
    if stripped_block.startswith("```"):
        stripped_block = re.sub(r'^```(?:json)?\s*', '', stripped_block, flags=re.IGNORECASE)
        stripped_block = re.sub(r'\s*```$', '', stripped_block).strip()

    # 3. Handle JSON formatted outputs containing thought or response keys
    if stripped_block.startswith("{") and stripped_block.endswith("}"):
        try:
            data = json.loads(stripped_block)
            if isinstance(data, dict):
                for key in ["response", "answer", "output", "text", "message", "reply"]:
                    if key in data and isinstance(data[key], str) and data[key].strip():
                        return data[key].strip()

                for thought_key in ["thought", "thinking", "reasoning", "rationale", "internal_thought"]:
                    data.pop(thought_key, None)

                # If only tool action keys remain, return empty string so tool caller handles it
                remaining_keys = set(data.keys())
                if remaining_keys.issubset({"action", "actioninput", "action_input", "input", "tool", "args", "parameters"}) and len(remaining_keys) >= 2 and (remaining_keys & {"action", "tool"}):
                    return ""

                values = [str(v).strip() for v in data.values() if v]
                if values:
                    return " ".join(values)
        except Exception:
            pass

    # 4. Strip embedded "thought": "..." regex patterns
    cleaned = re.sub(r'"thought"\s*:\s*"(?:[^"\\]|\\.)*"[,\s]*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'"thinking"\s*:\s*"(?:[^"\\]|\\.)*"[,\s]*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'Thought:\s*.*?(?=(Action:|Response:|$))', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'\{\s*\}', '', cleaned)

    # 5. Remove citation and annotation markers
    cleaned = re.sub(r'【[^】]*】', '', cleaned)
    cleaned = re.sub(r'†[^ \n]+', '', cleaned)

    return cleaned.strip()


# ── Tool Execution Engine ──────────────────────────────────────────────────────

def _run_tool_calls(tool_calls, messages: list, on_tool_call: Optional[Callable[[str, dict], None]] = None) -> list:
    """
    Execute tool calls requested by the model in parallel when multiple exist.
    Appends properly formatted tool response messages and returns tool result strings.
    """
    tool_results = []

    def _exec_single(tc):
        # Extract tool details from either OpenAI object or dictionary
        if hasattr(tc, "function"):
            name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            tc_id = getattr(tc, "id", f"tc_{time.time()}")
        elif isinstance(tc, dict):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            tc_id = tc.get("id", f"tc_{time.time()}")
        else:
            return None

        # Parse arguments safely
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except Exception:
                args = {}
        else:
            args = raw_args or {}

        # Emit live UI status signal
        if on_tool_call:
            try:
                on_tool_call(name, args)
            except Exception as notify_err:
                log_warning("ToolUI", f"Notification error for tool '{name}': {notify_err}")

        # Execute tool via central dispatch table
        try:
            result = dispatch(name, args)
        except Exception as e:
            log_error("ToolExecution", f"Tool '{name}' error: {e}")
            result = f"[Tool Notice]: Execution of '{name}' failed: {e}"

        return (tc_id, name, result)

    executed_tuples = []
    max_workers = min(4, max(1, len(tool_calls)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_exec_single, tc): tc for tc in tool_calls}
        for future in futures:
            try:
                executed_tuples.append(future.result(timeout=6.0))
            except Exception as e:
                tc = futures[future]
                name = getattr(getattr(tc, "function", None), "name", str(tc))
                log_error("ToolExecution", f"Tool '{name}' timed out: {e}")
                executed_tuples.append((f"tc_timeout_{time.time()}", name, f"[Tool timed out]: {name}"))

    for item in executed_tuples:
        if not item:
            continue
        tc_id, name, result = item
        res_str = str(result)
        if len(res_str) > 1500:
            res_str = res_str[:1500] + "\n...[truncated]"
        tool_results.append(res_str)
        messages.append({
            "role": "tool",
            "tool_call_id": tc_id,
            "name": name,
            "content": res_str
        })

    return tool_results


def _parse_pseudo_tool_json(content: str) -> Optional[tuple[str, dict]]:
    """Inspect model body content for pseudo tool calls formatted as JSON text."""
    if not content:
        return None
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s*```$', '', raw).strip()

    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                action = data.get("action", data.get("tool", data.get("name", "")))
                if action and str(action).strip() in EXECUTOR_MAP:
                    action_name = str(action).strip()
                    raw_input = data.get("actioninput", data.get("action_input", data.get("query", data.get("input", data.get("args", {})))))
                    if isinstance(raw_input, dict):
                        args = raw_input
                    elif isinstance(raw_input, str):
                        if action_name in ["web_search", "fetch_web_page"]:
                            args = {"query": raw_input} if action_name == "web_search" else {"url": raw_input}
                        elif action_name in ["open_app", "close_app"]:
                            args = {"name": raw_input}
                        elif action_name == "open_website":
                            args = {"url": raw_input}
                        else:
                            args = {"input_value": raw_input}
                    else:
                        args = {}
                    return (action_name, args)
        except Exception:
            pass
    return None


def _trim_messages_for_llm(messages: list, max_turns: int = 4) -> list:
    """
    Format and trim messages for the LLM request:
    - Keep system messages intact.
    - Standardize all message entries to dictionaries.
    - Keep the latest `max_turns` conversational turns (user + assistant pairs).
    - Omit stale intermediate tool messages from prior turns, retaining active turn tools.
    """
    system_msgs = []
    conversation = []
    active_turn = []

    # Identify where the current turn begins (the latest user message)
    last_user_idx = -1
    for idx, m in enumerate(messages):
        norm = _normalize_message(m)
        if norm.get("role") == "user":
            last_user_idx = idx

    for idx, m in enumerate(messages):
        norm = _normalize_message(m)
        role = norm.get("role")
        if role == "system":
            system_msgs.append(norm)
        elif idx >= last_user_idx:
            # Active turn (user query and any subsequent tool calls/results)
            active_turn.append(norm)
        else:
            # Past turns: only retain user and assistant conversational text
            if role in ["user", "assistant"] and norm.get("content"):
                conversation.append(norm)

    # Keep last `max_turns * 2` past messages
    max_count = max_turns * 2
    trimmed_past = conversation[-max_count:] if len(conversation) > max_count else conversation

    # Sanitize long past assistant responses
    sanitized_past = []
    for msg in trimmed_past:
        if msg.get("role") == "assistant":
            content = msg.get("content") or ""
            if isinstance(content, str) and len(content) > 250:
                copy_msg = dict(msg)
                copy_msg["content"] = content[:250] + "…"
                sanitized_past.append(copy_msg)
                continue
        sanitized_past.append(msg)

    return system_msgs + sanitized_past + active_turn


# ── Primary Query Handler: Groq AI ────────────────────────────────────────────

def execute_llm_query(
    query: str,
    chat_id: int,
    check_cancelled: Optional[Callable[[], bool]] = None,
    on_tool_call: Optional[Callable[[str, dict], None]] = None,
    ai_mode: str = "Multi"
) -> str:
    """
    Primary LLM handler: Groq API with dynamic tool routing, parallel tool execution,
    and automatic local Ollama fallback.

    Modes:
      - 'Multi': Groq primary with automatic local Qwen fallback
      - 'Groq': Groq only (errors returned directly)
      - 'Local AI': Ollama only
    """
    if ai_mode == "Local AI":
        return execute_qwen_query(query, chat_id, check_cancelled=check_cancelled, on_tool_call=on_tool_call)

    if check_cancelled and check_cancelled():
        return ""

    try:
        # Retrieve or initialize running session messages
        session = _get_session(chat_id, SYSTEM_PROMPT, mode="Groq")
        if not session or session[-1].get("role") != "user" or session[-1].get("content") != query:
            session.append({"role": "user", "content": query})
            storage.save_message(chat_id, "user", query)

        reply = ""
        tool_results = []

        # Up to 4 multi-step tool execution loops
        for loop_idx in range(4):
            if check_cancelled and check_cancelled():
                return ""

            # Prepare trimmed messages for the API call
            trimmed_messages = _trim_messages_for_llm(session)

            # Dynamically select tool schemas relevant to this query and recent context
            active_tools = ToolRouter.get_tools(query, trimmed_messages)

            # Build completion request
            req_kwargs = {
                "model": GROQ_MODEL,
                "messages": trimmed_messages,
                "temperature": 0.5,
                "max_tokens": 1024,
                "timeout": 12.0
            }
            if active_tools:
                req_kwargs["tools"] = active_tools
                req_kwargs["tool_choice"] = "auto"

            response = None
            last_err = None

            for model_candidate in GROQ_FALLBACK_MODELS:
                req_kwargs["model"] = model_candidate
                try:
                    response = client.chat.completions.create(**req_kwargs)
                    break
                except Exception as api_err:
                    last_err = api_err
                    err_str = str(api_err).lower()
                    if ("rate_limit" in err_str or "429" in err_str) and loop_idx == 0:
                        wait_match = re.search(r'try again in ([\d\.]+)\s*s', err_str)
                        wait_sec = float(wait_match.group(1)) if wait_match else 2.0
                        if wait_sec <= 4.0:
                            log_warning("Groq", f"Rate limit brief pause for {model_candidate}: waiting {wait_sec + 0.3:.1f}s...")
                            time.sleep(wait_sec + 0.3)
                            try:
                                response = client.chat.completions.create(**req_kwargs)
                                break
                            except Exception as retry_err:
                                last_err = retry_err
                                log_warning("Groq", f"Retry on {model_candidate} failed: {retry_err}, trying fallback model...")
                                continue
                        else:
                            log_warning("Groq", f"Model {model_candidate} rate limited ({wait_sec:.1f}s), trying fallback model...")
                            continue
                    else:
                        log_warning("Groq", f"Model {model_candidate} error: {api_err}, trying fallback model...")
                        continue

            if response is None:
                raise last_err

            if check_cancelled and check_cancelled():
                return ""

            response_msg = response.choices[0].message
            tool_calls = getattr(response_msg, "tool_calls", None)

            # Case A: Standard function tool calls
            if tool_calls:
                # Record assistant's tool-call intent into session
                session.append(_normalize_message(response_msg))

                # Execute requested tools in parallel
                executed = _run_tool_calls(tool_calls, session, on_tool_call=on_tool_call)
                tool_results.extend(executed)

                if check_cancelled and check_cancelled():
                    return ""
                continue  # Allow the model to formulate its answer based on tool output

            # Case B: Direct conversational response or pseudo-tool JSON
            raw_content = response_msg.content or ""

            # Check for JSON pseudo-tool calls in text body
            pseudo = _parse_pseudo_tool_json(raw_content)
            if pseudo:
                action_name, args = pseudo
                if on_tool_call:
                    on_tool_call(action_name, args)
                res = dispatch(action_name, args)
                tool_results.append(str(res))

                session.append({"role": "assistant", "content": raw_content})
                session.append({
                    "role": "tool",
                    "tool_call_id": f"pseudo_{loop_idx}_{len(session)}",
                    "name": action_name,
                    "content": str(res)
                })

                if check_cancelled and check_cancelled():
                    return ""
                continue

            # Clean and sanitize conversational answer
            cleaned_reply = clean_llm_response(raw_content)
            if cleaned_reply:
                reply = cleaned_reply
                break
            elif tool_results:
                valid_res = [str(r).strip() for r in tool_results if str(r).strip()]
                reply = "; ".join(valid_res) if valid_res else "Done."
                break
            else:
                # If content was empty due to raw thinking cut-off, loop once more with core tools
                if loop_idx == 0:
                    continue
                reply = raw_content

        # Final cleanup pass
        reply = clean_llm_response(reply)
        if not reply and tool_results:
            valid_res = [str(r).strip() for r in tool_results if str(r).strip()]
            reply = "; ".join(valid_res) if valid_res else "Task completed."

        if not reply:
            reply = "I completed your request."

        # Append final reply to session and persist to storage
        session.append({"role": "assistant", "content": reply})
        storage.save_message(chat_id, "assistant", reply)
        return reply

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        if ai_mode == "Groq":
            error_reply = f"[Groq API Error]: {err_msg}"
            log_error("Groq", error_reply)
            storage.save_message(chat_id, "assistant", error_reply)
            return error_reply

        log_warning("Groq", f"API Error: {err_msg}. Falling back to local model ({OLLAMA_MODEL})...")
        return execute_qwen_query(query, chat_id, check_cancelled=check_cancelled, on_tool_call=on_tool_call)


# ── Fallback Handler: Local Ollama ─────────────────────────────────────────────

def execute_qwen_query(
    query: str,
    chat_id: int,
    check_cancelled: Optional[Callable[[], bool]] = None,
    on_tool_call: Optional[Callable[[str, dict], None]] = None
) -> str:
    """Local handler: Ollama Qwen model with local function calling and VRAM persistence."""
    if check_cancelled and check_cancelled():
        return ""

    session = _get_session(chat_id, QWEN_SYSTEM_PROMPT, mode="Local AI")
    if not session or session[-1].get("role") != "user" or session[-1].get("content") != query:
        session.append({"role": "user", "content": query})
        storage.save_message(chat_id, "user", query)

    reply = ""
    tool_results = []
    api_url = OLLAMA_BASE_URL.replace("/v1", "/api/chat")

    for loop_idx in range(4):
        if check_cancelled and check_cancelled():
            return ""

        trimmed_messages = _trim_messages_for_llm(session)
        active_tools = ToolRouter.get_tools(query, trimmed_messages)
        payload = {
            "model": OLLAMA_MODEL,
            "messages": trimmed_messages,
            "think": False,
            "stream": False,
            "keep_alive": -1,
            "options": {
                "num_ctx": 8192,
                "temperature": 0.6,
                "num_predict": 512
            }
        }
        if active_tools:
            payload["tools"] = active_tools

        try:
            resp = requests.post(api_url, json=payload, timeout=30)
            if resp.status_code != 200:
                log_warning("Ollama", f"HTTP {resp.status_code}: {resp.text}, retrying without tools")
                payload.pop("tools", None)
                resp = requests.post(api_url, json=payload, timeout=30)

            resp_data = resp.json()
            response_message = resp_data.get("message", {})
        except Exception as ex:
            error_msg = f"[Local AI Error]: {ex}"
            log_error("Ollama", error_msg)
            storage.save_message(chat_id, "assistant", error_msg)
            return error_msg

        if check_cancelled and check_cancelled():
            return ""

        tool_calls = response_message.get("tool_calls", None)
        if tool_calls:
            session.append(_normalize_message(response_message))
            executed = _run_tool_calls(tool_calls, session, on_tool_call=on_tool_call)
            tool_results.extend(executed)
            if check_cancelled and check_cancelled():
                return ""
            continue

        raw_content = (response_message.get("content", "") or "").strip()
        pseudo = _parse_pseudo_tool_json(raw_content)
        if pseudo:
            action_name, args = pseudo
            if on_tool_call:
                on_tool_call(action_name, args)
            res = dispatch(action_name, args)
            tool_results.append(str(res))

            session.append({"role": "assistant", "content": raw_content})
            session.append({
                "role": "tool",
                "tool_call_id": f"qwen_pseudo_{loop_idx}_{len(session)}",
                "name": action_name,
                "content": str(res)
            })
            if check_cancelled and check_cancelled():
                return ""
            continue

        cleaned = clean_llm_response(raw_content)
        if cleaned:
            reply = cleaned
        elif tool_results:
            valid_res = [str(r).strip() for r in tool_results if str(r).strip()]
            reply = "; ".join(valid_res) if valid_res else "Done."
        else:
            reply = raw_content
        break

    reply = clean_llm_response(reply)
    if not reply and tool_results:
        valid_res = [str(r).strip() for r in tool_results if str(r).strip()]
        reply = "; ".join(valid_res) if valid_res else "Done."

    if not reply:
        reply = "I processed your request."

    session.append({"role": "assistant", "content": reply})
    storage.save_message(chat_id, "assistant", reply)
    return reply


# ── Vision Handler ─────────────────────────────────────────────────────────────

def execute_vision_query(
    query: str,
    image_path: str,
    chat_id: int,
    check_cancelled: Optional[Callable[[], bool]] = None,
    ai_mode: str = "Multi"
) -> str:
    """Multimodal vision handler: analyzes images with Groq vision or local Ollama."""
    if not query or not query.strip():
        query = "Analyze this image snippet and explain what you see in detail."

    try:
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        error_msg = f"[Error reading image file]: {e}"
        storage.save_message(chat_id, "assistant", error_msg)
        return error_msg

    image_data_url = f"data:image/png;base64,{b64_image}"
    multimodal_user_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": query},
            {"type": "image_url", "image_url": {"url": image_data_url}}
        ]
    }

    if ai_mode != "Local AI":
        session = _get_session(chat_id, SYSTEM_PROMPT)
        session.append(multimodal_user_msg)
        try:
            log_info("Vision", f"Attempting Groq Vision API ({GROQ_VISION_MODEL})...")
            trimmed = _trim_messages_for_llm(session)
            response = client.chat.completions.create(
                model=GROQ_VISION_MODEL,
                messages=trimmed,
                max_tokens=1024,
                timeout=15.0
            )

            if check_cancelled and check_cancelled():
                return ""

            reply = clean_llm_response(response.choices[0].message.content or "")
            if reply:
                session.append({"role": "assistant", "content": reply})
            storage.save_message(chat_id, "assistant", reply)
            log_success("Vision", "Groq Vision response received.")
            return reply

        except Exception as e:
            if ai_mode == "Groq":
                error_msg = f"[Groq Vision API Error]: {e}"
                log_error("Vision", error_msg)
                storage.save_message(chat_id, "assistant", error_msg)
                return error_msg

            if session and session[-1] == multimodal_user_msg:
                session.pop()
            log_warning("Vision", f"Groq Vision error: {e}. Falling back to Ollama...")

    # Local Ollama vision fallback
    try:
        ollama_session = _get_session(chat_id, QWEN_SYSTEM_PROMPT)
        ollama_session.append(multimodal_user_msg)
        trimmed_ollama = _trim_messages_for_llm(ollama_session)

        response = ollama_client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=trimmed_ollama,
            extra_body={
                "think": False,
                "keep_alive": -1,
                "options": {"num_ctx": 8192, "temperature": 0.6}
            }
        )

        if check_cancelled and check_cancelled():
            return ""

        reply = clean_llm_response(response.choices[0].message.content or "")
        if reply:
            ollama_session.append({"role": "assistant", "content": reply})
        storage.save_message(chat_id, "assistant", reply)
        return reply

    except Exception as e:
        error_msg = f"[Local Vision Error]: {e}"
        log_error("Vision", error_msg)
        storage.save_message(chat_id, "assistant", error_msg)
        return error_msg


# ── Model Unload ───────────────────────────────────────────────────────────────

def unload_ollama_model(model_name: str = OLLAMA_MODEL) -> None:
    """Send an explicit unload request to Ollama to free GPU VRAM on exit."""
    try:
        url = OLLAMA_BASE_URL.replace("/v1", "/api/generate")
        requests.post(url, json={"model": model_name, "keep_alive": 0}, timeout=3.0)
        log_info("Ollama", f"Unloaded model '{model_name}' from VRAM.")
    except Exception as e:
        log_error("Ollama", f"Failed to unload '{model_name}': {e}")
