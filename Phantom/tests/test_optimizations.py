import time
import unittest
from tools.os_control_tools import list_open_windows, _get_open_windows_native
from llm import _run_tool_calls
from audio.tts import clean_markdown_for_tts


class TestOptimizations(unittest.TestCase):

    def test_native_window_performance(self):
        """Verify native Win32 window enumeration finishes in under 100ms."""
        t0 = time.time()
        windows = _get_open_windows_native()
        elapsed_ms = (time.time() - t0) * 1000
        print(f"\n[Test] Native Win32 window query: {len(windows)} windows found in {elapsed_ms:.2f} ms")
        self.assertLess(elapsed_ms, 100.0, "Native window enumeration should take under 100ms")

        result = list_open_windows()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_tool_execution_timeout_protection(self):
        """Verify _run_tool_calls wraps slow/hanging tools with safety timeouts without throwing exceptions."""
        class DummyCall:
            def __init__(self, name, args):
                self.id = "tc_test"
                self.function = self
                self.name = name
                self.arguments = args

        # Call web_search with valid query
        dummy = DummyCall("web_search", '{"query": "python"}')
        messages = []
        t0 = time.time()
        results = _run_tool_calls([dummy], messages)
        elapsed = time.time() - t0
        print(f"[Test] web_search executed in {elapsed:.2f}s")
        self.assertEqual(len(results), 1)
        self.assertLess(elapsed, 6.0, "Tool execution should complete or time out within safety window")

    def test_clean_markdown_for_tts(self):
        """Verify markdown cleanup for voice synthesis."""
        raw = "Hello **world**, *this* is `code` and\n## Heading"
        cleaned = clean_markdown_for_tts(raw)
        self.assertEqual(cleaned, "Hello world, this is code and\nHeading")

    def test_chat_context_building(self):
        """Verify _build_messages incorporates multi-turn chat history for session memory."""
        from storage import storage
        from llm import _build_messages, SYSTEM_PROMPT

        chat_id = storage.create_chat("Test Session Context")
        storage.save_message(chat_id, "user", "My favorite color is cyan.")
        storage.save_message(chat_id, "assistant", "Cyan is a great color!")

        msgs = _build_messages(SYSTEM_PROMPT, chat_id=chat_id, query="What is my favorite color?", limit=50)

        # System prompt + history (user + assistant) + current user prompt
        contents = [m["content"] for m in msgs]
        self.assertTrue(any("favorite color is cyan" in c for c in contents))
        self.assertTrue(any("Cyan is a great color" in c for c in contents))
        self.assertTrue(any("What is my favorite color" in c for c in contents))

        storage.delete_chat(chat_id)


if __name__ == "__main__":
    unittest.main()
