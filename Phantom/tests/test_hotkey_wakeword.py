import unittest
from audio.stt import has_wake_word, normalize_text
from workers.hotkey_worker import HotkeyWorker


class TestHotkeyAndWakeWord(unittest.TestCase):
    def test_has_wake_word(self):
        # Sentences with phantom wake word
        self.assertTrue(has_wake_word("Phantom"))
        self.assertTrue(has_wake_word("phantom"))
        self.assertTrue(has_wake_word("Fantom"))
        self.assertTrue(has_wake_word("Hey Phantom, what's the weather?"))
        self.assertTrue(has_wake_word("Can you help me, phantom?"))
        self.assertTrue(has_wake_word("PHANTOM tell me a joke"))
        self.assertTrue(has_wake_word("fantom please search for news"))

        # Sentences without phantom wake word
        self.assertFalse(has_wake_word("What is quantum computing?"))
        self.assertFalse(has_wake_word("Hello how are you doing today"))
        self.assertFalse(has_wake_word("Open chrome browser"))
        self.assertFalse(has_wake_word(""))
        self.assertFalse(has_wake_word(None))

    def test_normalize_text_wake_word(self):
        self.assertIn("phantom", normalize_text("fantom"))
        self.assertIn("phantom", normalize_text("phanton"))
        self.assertIn("phantom", normalize_text("phantam"))

    def test_hotkey_worker_init(self):
        worker = HotkeyWorker(poll_interval_ms=50)
        self.assertTrue(worker.running)
        self.assertFalse(worker.is_held)


if __name__ == "__main__":
    unittest.main()
