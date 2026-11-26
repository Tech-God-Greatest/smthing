import pytest
import requests
import time
from llm import execute_llm_query, GROQ_API_KEY, OLLAMA_BASE_URL

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

def execute_parallel_test(chat_id, query, expected_tools):
    ai_modes = []
    if _groq_ok():
        ai_modes.append("Groq")
    if _ollama_ok():
        ai_modes.append("Local AI")
        
    from storage import storage

    for ai_mode in ai_modes:
        mode_chat_id = storage.create_chat(f"Parallel Test Chat {ai_mode}")
        calls, on_tool_call = _make_tracker()
        
        start_time = time.time()
        response = execute_llm_query(
            query=query,
            chat_id=mode_chat_id,
            on_tool_call=on_tool_call,
            ai_mode=ai_mode
        )
        end_time = time.time()
        
        called_tools = [name for name, args in calls]
        for et in expected_tools:
            assert et in called_tools, f"[{ai_mode}] Expected tool {et} not called. Tools called: {called_tools}"
            
        assert response and len(response.strip()) > 0, f"[{ai_mode}] Empty response"
        
        # Parallel execution shouldn't take extremely long (assuming API is responsive)
        max_duration = 45 if ai_mode == "Local AI" else 30
        assert end_time - start_time < max_duration, f"[{ai_mode}] Execution took too long: {end_time - start_time}s"

def test_parallel_cpu_gpu(fresh_chat):
    execute_parallel_test(
        fresh_chat,
        "What is my CPU and GPU status?",
        expected_tools=["get_cpu_status", "get_gpu_status"]
    )

def test_parallel_ram_disk(fresh_chat):
    execute_parallel_test(
        fresh_chat,
        "Check RAM usage and disk status at the same time",
        expected_tools=["get_ram_status", "get_disk_status"]
    )

def test_parallel_system_network(fresh_chat):
    execute_parallel_test(
        fresh_chat,
        "Get system overview and network info",
        expected_tools=["get_system_overview", "get_network_info"]
    )
