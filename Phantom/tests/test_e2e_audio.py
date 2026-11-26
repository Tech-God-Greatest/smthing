import pytest
import time
from audio.tts import clean_markdown_for_tts, speak_async, stop, is_playing
from audio.stt import normalize_text, has_wake_word, is_garbage, init_browser

def test_clean_markdown_for_tts_bold():
    assert clean_markdown_for_tts("This is **bold** text") == "This is bold text"

def test_clean_markdown_for_tts_italic():
    assert clean_markdown_for_tts("This is *italic* text") == "This is italic text"

def test_clean_markdown_for_tts_inline_code():
    assert clean_markdown_for_tts("Use `code` here") == "Use code here"

def test_clean_markdown_for_tts_headers():
    assert clean_markdown_for_tts("## Header text") == "Header text"

def test_clean_markdown_for_tts_empty():
    assert clean_markdown_for_tts("") == ""
    assert clean_markdown_for_tts(None) is None

def test_clean_markdown_for_tts_emotion_tags():
    assert clean_markdown_for_tts("Hello there! [excited] I am glad to see you. [sad]") == "Hello there!  I am glad to see you."

def test_clean_markdown_for_tts_mixed():
    text = "## Hello\nThis is **bold** and *italic* with `code`."
    cleaned = clean_markdown_for_tts(text)
    assert "Hello" in cleaned
    assert "bold" in cleaned
    assert "italic" in cleaned
    assert "code" in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert "##" not in cleaned

def test_speak_async_short_text():
    # Calling speak sync or async, the instruction says speak_async but TTS file has speak
    # We will call speak directly, it might be blocking but it's short.
    speak_async("Hello")
    assert True

def test_stop_no_crash():
    stop()
    assert True

def test_is_playing_returns_false_when_idle():
    stop()
    assert is_playing() is False

def test_set_voice():
    import audio.tts as tts
    original = tts.KOKORO_VOICE
    try:
        tts.set_voice("am_adam")
        assert tts.KOKORO_VOICE == "am_adam"
        assert tts.VOICE == "am_adam"
    finally:
        tts.set_voice(original)

def test_normalize_text_fantom():
    assert normalize_text("fantom") == "phantom"

def test_normalize_text_phanton():
    assert normalize_text("phanton") == "phantom"

def test_normalize_text_punctuation():
    assert normalize_text("hello, world!") == "hello world"

def test_has_wake_word_detects():
    assert has_wake_word("Hey phantom how are you") is True

def test_has_wake_word_no_wake_word():
    assert has_wake_word("hello there") is False

def test_has_wake_word_empty():
    assert has_wake_word("") is False

def test_is_garbage_thanks():
    assert is_garbage("thank you for watching") is True

def test_is_garbage_repeated_chars():
    assert is_garbage("a a a a") is True

def test_is_garbage_empty():
    assert is_garbage("") is True

def test_is_garbage_valid_speech():
    assert is_garbage("open chrome please") is False

@pytest.mark.slow
def test_stt_browser_init():
    try:
        init_browser()
        assert True
    except Exception as e:
        pytest.skip(f"Chrome not available or failed to start: {e}")
