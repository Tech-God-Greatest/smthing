import pytest
import requests
from llm import execute_llm_query, GROQ_API_KEY, OLLAMA_BASE_URL
from storage import storage

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

def execute_sequential_test(chat_id, query, min_calls, expected_tools=None):
    ai_modes = []
    if _groq_ok():
        ai_modes.append("Groq")
    if _ollama_ok():
        ai_modes.append("Local AI")
        
    for ai_mode in ai_modes:
        mode_chat_id = storage.create_chat(f"Sequential Test Chat {ai_mode}")
        calls, on_tool_call = _make_tracker()
        response = execute_llm_query(
            query=query,
            chat_id=mode_chat_id,
            on_tool_call=on_tool_call,
            ai_mode=ai_mode
        )
        
        called_tools = [name for name, args in calls]
        assert len(calls) >= min_calls, f"[{ai_mode}] Expected at least {min_calls} tool calls, got {len(calls)}. Tools: {called_tools}"
        
        if expected_tools:
            for et in expected_tools:
                assert et in called_tools, f"[{ai_mode}] Expected tool {et} not called. Tools called: {called_tools}"
                
        assert response and len(response.strip()) > 0, f"[{ai_mode}] Empty response"
        
        # Verify chat history saved
        history = storage.get_recent_messages(mode_chat_id)
        assert len(history) > 0, "Chat history not saved correctly"

def test_sequential_remember_search(fresh_chat):
    execute_sequential_test(
        fresh_chat, 
        "Remember my name is TestUser, then tell me what you remember about me",
        min_calls=2,
        expected_tools=["remember", "search_memory"]
    )

def test_sequential_web_search_summary(fresh_chat):
    execute_sequential_test(
        fresh_chat,
        "Search the web for Python 3.13 features and give me a summary",
        min_calls=1,
        expected_tools=["web_search"]
    )

def test_sequential_cpu_gpu(fresh_chat):
    execute_sequential_test(
        fresh_chat,
        "Get my CPU status and my GPU status",
        min_calls=2,
        expected_tools=["get_cpu_status", "get_gpu_status"]
    )

def test_sequential_system_apps(fresh_chat):
    execute_sequential_test(
        fresh_chat,
        "What is my system overview and what apps are running?",
        min_calls=2,
        expected_tools=["get_system_overview", "list_open_windows"]
    )
