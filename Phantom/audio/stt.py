import os
import re
import shutil
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from utils.logger import log_info, log_error, log_user

# -----------------------------
# Browser State
# -----------------------------
_driver = None
_last_output = ""
_initialized = False


# -----------------------------
# Chrome Binary Finder
# -----------------------------
def find_chrome_executable() -> str | None:
    """Find the path to the Chrome executable across system standard locations."""
    for name in ["chrome", "chrome.exe", "google-chrome"]:
        found = shutil.which(name)
        if found:
            return found

    candidate_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chrome",
    ]

    for p in candidate_paths:
        if p and os.path.isfile(p):
            return p

    return None


# -----------------------------
# Noise / Hallucination Filter
# -----------------------------
HALLUCINATION_PHRASES = {
    "thank you for watching", "thanks for watching",
    "like and subscribe", "subscribe to my channel",
    "subtitles by", "translated by", "amara.org",
    "the end",
}


def is_garbage(text: str) -> bool:
    """Returns True if the transcription is likely noise/hallucination."""
    clean = text.lower().strip()
    clean = re.sub(r"[^\w\s]", "", clean).strip()

    if not clean:
        return True

    if clean in HALLUCINATION_PHRASES:
        return True

    words = clean.split()
    # Single repeating character like "a a a" or "x x"
    if len(words) >= 2 and len(set(words)) == 1 and len(words[0]) == 1:
        return True

    return False


# -----------------------------
# Normalize Wake Word
# -----------------------------
def normalize_text(text: str) -> str:
    lower = text.lower()

    replacements = {
        "fantom": "phantom",
        "phanton": "phantom",
        "phantam": "phantom",
        "phantem": "phantom",
        "fanton": "phantom",
        "fentom": "phantom",
        "fentam": "phantom",
        "phatom": "phantom",
        "phentom": "phantom",
        "phantum": "phantom",
        "fantam": "phantom",
        "phantom.": "phantom",
        "phantom,": "phantom",
        "phantom!": "phantom",
        "phantom?": "phantom",
    }

    for old, new in replacements.items():
        lower = lower.replace(old, new)

    lower = re.sub(r"[^\w\s]", "", lower)
    lower = re.sub(r"\s+", " ", lower).strip()

    return lower


def has_wake_word(text: str, wake_word: str = "phantom") -> bool:
    """Returns True if wake_word is present in the transcribed text."""
    if not text:
        return False
    normalized = normalize_text(text)
    words = normalized.split()
    wake_clean = wake_word.lower().strip()
    return wake_clean in words or wake_clean in normalized



# -----------------------------
# Chrome Web Speech API STT
# -----------------------------
def init_browser():
    """Start Chrome browser, navigate to STT page, click Start Listening."""
    global _driver, _initialized

    if _initialized and _driver:
        return

    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    options.add_argument("--use-fake-ui-for-media-stream")

    prefs = {
        "profile.default_content_setting_values.media_stream_mic": 1,
        "profile.default_content_setting_values.media_stream_camera": 1,
        "profile.default_content_setting_values.notifications": 1,
    }
    options.add_experimental_option("prefs", prefs)

    chrome_bin = find_chrome_executable()
    if chrome_bin:
        options.binary_location = chrome_bin
        log_info("STT", f"Using Chrome binary at: {chrome_bin}")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        log_info("STT", f"Built-in Selenium driver failed ({e}). Retrying with ChromeDriverManager...")
        try:
            driver = webdriver.Chrome(
                options=options,
                service=ChromeService(ChromeDriverManager().install())
            )
        except Exception as e2:
            log_error("STT", f"Failed to launch Chrome browser for STT: {e2}")
            raise e2

    _driver = driver
    _driver.get("https://allorizenproject1.netlify.app/")
    time.sleep(3)

    # Click Start Listening
    try:
        button = _driver.find_element(By.XPATH, "//button[text()='Start Listening']")
        button.click()
        time.sleep(1)
    except Exception as e:
        log_error("STT", f"Could not click 'Start Listening' button: {e}")

    try:
        _driver.minimize_window()
    except Exception:
        pass

    _initialized = True
    log_info("STT", "Chrome Web Speech API initialized.")


def listen(speech_start_timeout=None) -> str:
    """
    Polls Chrome Web Speech API output for new transcribed text.
    If speech_start_timeout is set, returns "" if no new text within that time.
    If None, waits indefinitely for new text.
    """
    global _last_output

    init_browser()

    start_time = time.time()
    stable_text = ""
    stable_since = None

    while True:
        try:
            element = _driver.find_element(By.ID, "output")
            current = element.text.strip()
        except Exception:
            time.sleep(0.2)
            continue

        # Check for new text different from what we last processed
        if current and current != _last_output:
            if current != stable_text:
                # Text changed — start stability timer
                stable_text = current
                stable_since = time.time()
            elif stable_since and (time.time() - stable_since) >= 0.5:
                # Text has been stable for 0.5s — extract raw new tail
                if _last_output and current.startswith(_last_output):
                    raw_new = current[len(_last_output):].strip()
                elif _last_output and _last_output in current:
                    raw_new = current.split(_last_output, 1)[-1].strip()
                else:
                    raw_new = current

                # Always update _last_output to current so buffer tracking stays synchronized
                _last_output = current
                text = normalize_text(raw_new)

                if is_garbage(text):
                    # Reset stability state and keep waiting
                    stable_text = ""
                    stable_since = None
                    continue

                log_user(text)
                return text

        # Timeout check
        if speech_start_timeout is not None:
            if (time.time() - start_time) > speech_start_timeout:
                return ""

        time.sleep(0.1)


def shutdown_browser():
    """Cleanly close the Chrome browser."""
    global _driver, _initialized
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
    _driver = None
    _initialized = False


if __name__ == "__main__":
    log_info("STT", "Listening...")

    while True:
        result = listen()

        if not result:
            continue

        log_info("STT", f"Transcribed: {result}")

