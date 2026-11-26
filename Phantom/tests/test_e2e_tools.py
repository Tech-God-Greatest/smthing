import pytest
import requests
from llm import execute_llm_query, GROQ_API_KEY, OLLAMA_BASE_URL
from storage import storage

SKIP_DESTRUCTIVE_TOOLS = {"shutdown_pc", "restart_pc", "logoff_user", "lock_pc", "sleep_pc", "empty_recycle_bin"}

def _groq_ok():
    return bool(GROQ_API_KEY and GROQ_API_KEY != 'no_key_set')

def _ollama_ok():
    try:
        base = OLLAMA_BASE_URL.rstrip('/')
        if base.endswith('/v1'):
            base = base[:-3]
        return requests.get(base, timeout=2).status_code == 200
    except:
        return False

def _make_tracker():
    calls = []
    def on_tool_call(name, args):
        calls.append((name, args))
    return calls, on_tool_call

pytestmark = pytest.mark.skipif(not _groq_ok() and not _ollama_ok(), reason="No LLM backend available")

def execute_and_verify(chat_id, query, expected_tool):
    if expected_tool in SKIP_DESTRUCTIVE_TOOLS:
        pytest.skip(f"Skipping destructive tool {expected_tool}")
        
    ai_modes = []
    if _groq_ok():
        ai_modes.append("Groq")
    if _ollama_ok():
        ai_modes.append("Local AI")
        
    for ai_mode in ai_modes:
        mode_chat_id = storage.create_chat(f"Test Chat {ai_mode}")
        calls, on_tool_call = _make_tracker()
        response = execute_llm_query(
            query=query,
            chat_id=mode_chat_id,
            on_tool_call=on_tool_call,
            ai_mode=ai_mode
        )
        
        called_tools = [name for name, args in calls]
        assert expected_tool in called_tools, f"[{ai_mode}] Expected tool {expected_tool} not called. Tools called: {called_tools}"
        assert response and len(response.strip()) > 0, f"[{ai_mode}] Empty response"

def test_tool_cpu_usage(fresh_chat):
    execute_and_verify(fresh_chat, "What is my CPU usage?", "get_cpu_status")

def test_tool_open_windows(fresh_chat):
    execute_and_verify(fresh_chat, "What apps are open right now?", "list_open_windows")

def test_tool_set_volume(fresh_chat):
    execute_and_verify(fresh_chat, "Set volume to 50 percent", "set_volume")

def test_tool_remember(fresh_chat):
    execute_and_verify(fresh_chat, "Remember that my favorite color is blue", "remember")

def test_tool_search_memory(fresh_chat):
    # Seed memory first
    storage.save_memory("favorite color is blue")
    execute_and_verify(fresh_chat, "What do you remember about me?", "search_memory")

def test_tool_web_search(fresh_chat):
    execute_and_verify(fresh_chat, "Search the web for latest Python release", "web_search")

def test_tool_mouse_position(fresh_chat):
    execute_and_verify(fresh_chat, "Where is my mouse cursor?", "get_mouse_position")

def test_tool_system_overview(fresh_chat):
    execute_and_verify(fresh_chat, "Give me a system overview", "get_system_overview")

def test_tool_gpu_status(fresh_chat):
    execute_and_verify(fresh_chat, "Tell me about my GPU", "get_gpu_status")

def test_tool_ram_status(fresh_chat):
    execute_and_verify(fresh_chat, "How much RAM am I using?", "get_ram_status")

def test_tool_disk_status(fresh_chat):
    execute_and_verify(fresh_chat, "What is my disk usage?", "get_disk_status")

def test_tool_network_info(fresh_chat):
    execute_and_verify(fresh_chat, "Show me network info", "get_network_info")
