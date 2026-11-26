import pytest
import time
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage import storage
from tools.registry import dispatch
from tools.os_control_tools import list_open_windows
from tools.memory_tools import search_memory
from tools.system_tools import get_system_overview
from llm import execute_llm_query, execute_qwen_query, clean_llm_response, GROQ_API_KEY, OLLAMA_BASE_URL
import requests

def _groq_available():
    return bool(GROQ_API_KEY and GROQ_API_KEY != "no_key_set")

def _ollama_available():
    try:
        base = OLLAMA_BASE_URL.rstrip("/")
        if base.endswith("/v1"): base = base[:-3]
        return requests.get(base, timeout=2).status_code == 200
    except: return False

class TestE2EPerformance:

    def test_01_tool_dispatch_overhead(self):
        times = []
        for _ in range(10):
            start = time.perf_counter()
            # Dispatch uses the registry mapping which is fast
            dispatch('get_mouse_position', {})
            times.append(time.perf_counter() - start)
        avg_time = sum(times) / len(times)
        assert avg_time < 0.05, f"Dispatch overhead too high: {avg_time*1000:.2f}ms"

    def test_02_window_enumeration(self):
        start = time.perf_counter()
        windows_str = list_open_windows()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.2, f"Window enum too slow: {elapsed*1000:.2f}ms"
        assert isinstance(windows_str, str)

    def test_03_memory_search(self):
        start = time.perf_counter()
        mem_str = search_memory()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, f"Memory search too slow: {elapsed*1000:.2f}ms"
        assert isinstance(mem_str, str)

    def test_04_db_save_message(self, fresh_chat):
        times = []
        for i in range(50):
            start = time.perf_counter()
            storage.save_message(fresh_chat, "user", f"Perf msg {i}")
            times.append(time.perf_counter() - start)
        
        # each < 100ms
        for i, t in enumerate(times):
            assert t < 0.1, f"DB save message {i} too slow: {t*1000:.2f}ms"

    def test_05_db_get_recent_messages(self, fresh_chat):
        for i in range(50):
            storage.save_message(fresh_chat, "user", f"Perf msg {i}")
            
        start = time.perf_counter()
        msgs = storage.get_recent_messages(fresh_chat, limit=50)
        elapsed = time.perf_counter() - start
        
        assert len(msgs) == 50
        assert elapsed < 0.1, f"DB get_recent_messages too slow: {elapsed*1000:.2f}ms"

    def test_06_clean_llm_response(self):
        test_inputs = [
            "<think>Thinking...</think>Answer",
            "```json\n{\"response\": \"JSON Answer\"}\n```",
            "Thought: I should do this. Action: that. Response: Hey",
            "Here is the answer.【12†source】",
            "Just a normal reply without any tags."
        ] * 20  # 100 inputs
        
        times = []
        for text in test_inputs:
            start = time.perf_counter()
            clean_llm_response(text)
            times.append(time.perf_counter() - start)
            
        for i, t in enumerate(times):
            assert t < 0.001, f"clean_llm_response {i} too slow: {t*1000:.2f}ms"

    @pytest.mark.timeout(10)
    def test_07_system_overview(self):
        start = time.perf_counter()
        overview = get_system_overview()
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"System overview too slow: {elapsed:.2f}s"
        assert isinstance(overview, str)

    @pytest.mark.timeout(20)
    @pytest.mark.skipif(not _groq_available(), reason='Groq API not available')
    def test_08_groq_api_response(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Say 'Hello Groq'")
        start = time.perf_counter()
        reply = execute_llm_query("Say 'Hello Groq'", fresh_chat, check_cancelled=lambda: False, ai_mode="Groq")
        elapsed = time.perf_counter() - start
        assert elapsed < 15.0, f"Groq response too slow: {elapsed:.2f}s"
        assert reply != ""

    @pytest.mark.timeout(35)
    @pytest.mark.skipif(not _ollama_available(), reason='Ollama not running')
    def test_09_ollama_response(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Say 'Hello Local'")
        start = time.perf_counter()
        reply = execute_qwen_query("Say 'Hello Local'", fresh_chat, check_cancelled=lambda: False)
        elapsed = time.perf_counter() - start
        assert elapsed < 30.0, f"Ollama response too slow: {elapsed:.2f}s"
        assert reply != ""

    @pytest.mark.timeout(100)
    @pytest.mark.skipif(not _groq_available() or not _ollama_available(), reason='Both backends required')
    def test_10_sequential_queries(self, fresh_chat):
        start = time.perf_counter()
        
        storage.save_message(fresh_chat, "user", "Query 1")
        execute_llm_query("Query 1", fresh_chat, check_cancelled=lambda: False, ai_mode="Groq")
        
        storage.save_message(fresh_chat, "user", "Query 2")
        execute_qwen_query("Query 2", fresh_chat, check_cancelled=lambda: False)
        
        storage.save_message(fresh_chat, "user", "Query 3")
        execute_llm_query("Query 3", fresh_chat, check_cancelled=lambda: False, ai_mode="Multi")
        
        elapsed = time.perf_counter() - start
        assert elapsed < 90.0, f"3 sequential queries took too long: {elapsed:.2f}s"
