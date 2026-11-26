import pytest
import time
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage import storage
from llm import execute_llm_query, execute_qwen_query, execute_vision_query, clean_llm_response, GROQ_API_KEY, OLLAMA_BASE_URL
from tests.conftest import SKIP_DESTRUCTIVE_TOOLS
import requests

def _groq_available():
    return bool(GROQ_API_KEY and GROQ_API_KEY != "no_key_set")

def _ollama_available():
    try:
        base = OLLAMA_BASE_URL.rstrip("/")
        if base.endswith("/v1"): base = base[:-3]
        return requests.get(base, timeout=2).status_code == 200
    except: return False

class TestE2ESmoke:

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _groq_available(), reason='Groq API not available')
    def test_01_simple_greeting_groq(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Hello")
        reply = execute_llm_query("Hello", fresh_chat, check_cancelled=lambda: False, ai_mode="Groq")
        assert isinstance(reply, str)
        assert len(reply.strip()) > 0
        msgs = storage.get_recent_messages(fresh_chat)
        assert len(msgs) >= 2
        assert msgs[-1]["role"] == "assistant"
        assert msgs[-1]["content"] == reply

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _ollama_available(), reason='Ollama not running')
    def test_02_simple_greeting_local(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Hello")
        reply = execute_qwen_query("Hello", fresh_chat, check_cancelled=lambda: False)
        assert isinstance(reply, str)
        assert len(reply.strip()) > 0
        msgs = storage.get_recent_messages(fresh_chat)
        assert len(msgs) >= 2
        assert msgs[-1]["role"] == "assistant"
        assert msgs[-1]["content"] == reply

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _groq_available(), reason='Groq API not available')
    def test_03_multi_mode_success(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Hi there")
        reply = execute_llm_query("Hi there", fresh_chat, check_cancelled=lambda: False, ai_mode="Multi")
        assert isinstance(reply, str)
        assert len(reply.strip()) > 0

    @pytest.mark.timeout(30)
    def test_04_groq_only_mode(self, fresh_chat):
        # We can test Groq-only mode. If Groq is not available, it should error gracefully as per llm.py logic.
        storage.save_message(fresh_chat, "user", "Test")
        reply = execute_llm_query("Test", fresh_chat, check_cancelled=lambda: False, ai_mode="Groq")
        assert isinstance(reply, str)
        if not _groq_available():
            assert "[Groq API Error]" in reply or "Failed" in reply or reply == ""
        else:
            assert len(reply.strip()) > 0

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _ollama_available(), reason='Ollama not running')
    def test_05_local_only_mode(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Test")
        reply = execute_llm_query("Test", fresh_chat, check_cancelled=lambda: False, ai_mode="Local AI")
        assert isinstance(reply, str)
        assert len(reply.strip()) > 0

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _groq_available() and not _ollama_available(), reason='No LLM available')
    def test_06_empty_query_handling(self, fresh_chat):
        mode = "Groq" if _groq_available() else "Local AI"
        storage.save_message(fresh_chat, "user", "")
        reply = execute_llm_query("", fresh_chat, check_cancelled=lambda: False, ai_mode=mode)
        assert isinstance(reply, str)
        # Verify no crash

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _groq_available() and not _ollama_available(), reason='No LLM available')
    def test_07_long_query(self, fresh_chat):
        mode = "Groq" if _groq_available() else "Local AI"
        long_query = "A" * 5000
        storage.save_message(fresh_chat, "user", long_query)
        reply = execute_llm_query(long_query, fresh_chat, check_cancelled=lambda: False, ai_mode=mode)
        assert isinstance(reply, str)

    def test_08_clean_llm_response_think_tags(self):
        # clean_llm_response strips <think> tags
        text = "<think>Some internal thought</think>Actual response."
        cleaned = clean_llm_response(text)
        assert cleaned == "Actual response."

        text2 = "<think>\nMulti line\nthought\n</think>\nReal stuff"
        cleaned2 = clean_llm_response(text2)
        assert cleaned2 == "Real stuff"

    def test_09_clean_llm_response_citation_markers(self):
        text = "This is a fact【12†source】."
        cleaned = clean_llm_response(text)
        assert cleaned == "This is a fact."

    def test_10_clean_llm_response_json_pseudo_tool(self):
        # clean_llm_response handles JSON pseudo-tool response
        text = '{"thought": "I should search", "action": "web_search", "action_input": "cats"}'
        cleaned = clean_llm_response(text)
        # As per llm.py: if only pseudo tool fields remain, it returns ""
        assert cleaned == ""

        text2 = '```json\n{"response": "Here is the answer."}\n```'
        cleaned2 = clean_llm_response(text2)
        assert cleaned2 == "Here is the answer."

    @pytest.mark.timeout(30)
    @pytest.mark.skipif(not _groq_available() and not _ollama_available(), reason='No LLM available')
    def test_11_cancellation(self, fresh_chat):
        # Verify check_cancelled stops execution
        mode = "Groq" if _groq_available() else "Local AI"
        storage.save_message(fresh_chat, "user", "Hello")
        reply = execute_llm_query("Hello", fresh_chat, check_cancelled=lambda: True, ai_mode=mode)
        assert reply == ""

