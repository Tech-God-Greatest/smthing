import unittest
from audio.stt import has_wake_word, normalize_text


class TestNotchVoiceFilterLogic(unittest.TestCase):
    def check_should_process(self, text: str, opened_by_hotkey: bool, tts_was_active: bool = False, wake_word_enabled: bool = True) -> bool:
        is_wake = has_wake_word(text)
        in_active_window = tts_was_active
        return not wake_word_enabled or is_wake or opened_by_hotkey or in_active_window

    def is_wake_word_command(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        norm = normalize_text(text)
        clean = norm
        if clean.startswith("phantom "):
            clean = clean[8:].strip()
        return clean in ("wake word disable", "wake word enable")

    def test_voice_filtering_matrix(self):
        # Case 1: Wake word spoken, NOT opened by hotkey, wake word enabled -> SHOULD process
        self.assertTrue(self.check_should_process("Phantom what is the weather", opened_by_hotkey=False, wake_word_enabled=True))

        # Case 2: Wake word NOT spoken, NOT opened by hotkey, NO TTS, wake word enabled -> SHOULD IGNORE
        self.assertFalse(self.check_should_process("what is the weather", opened_by_hotkey=False, wake_word_enabled=True))

        # Case 3: Wake word NOT spoken, NOT opened by hotkey, NO TTS, wake word DISABLED -> SHOULD process
        self.assertTrue(self.check_should_process("what is the weather", opened_by_hotkey=False, wake_word_enabled=False))

        # Case 4: Wake word NOT spoken, WAS opened by hotkey -> SHOULD process
        self.assertTrue(self.check_should_process("what is the weather", opened_by_hotkey=True, wake_word_enabled=True))

        # Case 5: TTS active / interrupted, no wake word -> SHOULD process
        self.assertTrue(self.check_should_process("stop and tell me the weather", opened_by_hotkey=False, tts_was_active=True, wake_word_enabled=True))

    def test_wake_word_command_detection(self):
        self.assertTrue(self.is_wake_word_command("wake word disable"))
        self.assertTrue(self.is_wake_word_command("Wake word disable."))
        self.assertTrue(self.is_wake_word_command("phantom wake word disable"))
        self.assertTrue(self.is_wake_word_command("Phantom, wake word disable!"))

        self.assertTrue(self.is_wake_word_command("wake word enable"))
        self.assertTrue(self.is_wake_word_command("Wake word enable."))
        self.assertTrue(self.is_wake_word_command("phantom wake word enable"))

        self.assertFalse(self.is_wake_word_command("what is the wake word"))
        self.assertFalse(self.is_wake_word_command("disable wake word"))


if __name__ == "__main__":
    unittest.main()

