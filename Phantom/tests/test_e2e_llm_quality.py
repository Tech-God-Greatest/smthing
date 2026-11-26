import pytest
from llm import execute_llm_query, clean_llm_response, _build_messages
from storage import storage

def test_simple_factual_question(fresh_chat, groq_available):
    if not groq_available:
        pytest.skip("Groq not available")
    response = execute_llm_query("What is 2+2?", fresh_chat, lambda: False)
    assert "4" in response

def test_follow_up_question(fresh_chat, groq_available):
    if not groq_available:
        pytest.skip("Groq not available")
    execute_llm_query("My name is PhantomTestUser", fresh_chat, lambda: False)
    response = execute_llm_query("What is my name?", fresh_chat, lambda: False)
    assert "PhantomTestUser" in response

def test_previous_prompt(fresh_chat, groq_available):
    if not groq_available:
        pytest.skip("Groq not available")
    execute_llm_query("Hello there", fresh_chat, lambda: False)
    response = execute_llm_query("What was my previous prompt?", fresh_chat, lambda: False)
    assert "Hello there" in response

def test_multi_turn_conversation(fresh_chat, groq_available):
    if not groq_available:
        pytest.skip("Groq not available")
    execute_llm_query("I have 3 apples", fresh_chat, lambda: False)
    execute_llm_query("I get 2 more apples", fresh_chat, lambda: False)
    response = execute_llm_query("How many apples do I have now?", fresh_chat, lambda: False)
    assert "5" in response or "five" in response.lower()

def test_clean_llm_response_markdown():
    text = "This is **bold** text"
    assert clean_llm_response(text) == text

def test_clean_llm_response_think_tags():
    text = "Here is an answer.<think>thinking here</think> End."
    cleaned = clean_llm_response(text)
    assert "<think>" not in cleaned
    assert "thinking here" not in cleaned
    assert "Here is an answer." in cleaned
    assert "End." in cleaned

def test_clean_llm_response_unclosed_think():
    text = "Hello<think>thinking forever"
    cleaned = clean_llm_response(text)
    assert "<think>" not in cleaned
    assert "thinking forever" not in cleaned
    assert "Hello" in cleaned

def test_clean_llm_response_empty():
    assert clean_llm_response("") == ""
    assert clean_llm_response(None) == ""

def test_clean_llm_response_citations():
    text = "Here is a fact.【1†source】"
    cleaned = clean_llm_response(text)
    assert "【1†source】" not in cleaned
    assert "fact." in cleaned

def test_build_messages_character_budget(fresh_chat):
    long_text = "A" * 5000
    for _ in range(10):
        storage.add_message(fresh_chat, "user", long_text)
        storage.add_message(fresh_chat, "assistant", long_text)
    
    messages = _build_messages("Final question", fresh_chat)
    total_len = sum(len(m.get('content', '')) for m in messages if isinstance(m.get('content'), str))
    assert total_len <= 35000  # Budget is ~32000

def test_build_messages_memory(fresh_chat, monkeypatch):
    import tools.memory_tools
    monkeypatch.setattr(tools.memory_tools, "search_memory", lambda q: "User likes blue.")
    messages = _build_messages("What color do I like?", fresh_chat)
    contents = " ".join(m.get('content', '') for m in messages if isinstance(m.get('content'), str))
    assert "User likes blue" in contents

def test_build_messages_summary(fresh_chat):
    storage.update_chat_summary(fresh_chat, "This is a summary of the chat.")
    messages = _build_messages("Hello", fresh_chat)
    contents = " ".join(m.get('content', '') for m in messages if isinstance(m.get('content'), str))
    assert "This is a summary of the chat" in contents
