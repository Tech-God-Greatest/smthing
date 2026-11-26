import asyncio
import os
import re
import tempfile
import threading
import warnings

# Suppress known noisy third-party warnings
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = "1"
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import pygame
from utils.logger import log_assistant, log_error, log_info

# Initialize pygame mixer once
pygame.mixer.init()

# Voice configuration
# Kokoro expressive voices:
# Female: 'af_heart' (default, warm & emotional), 'af_bella', 'af_sarah', 'af_nicole', 'af_sky', 'bf_emma', 'bf_isabella'
# Male:   'am_adam', 'am_michael', 'am_echo', 'bm_george', 'bm_fable'
KOKORO_VOICE = "af_heart"
EDGE_FALLBACK_VOICE = "en-US-AvaNeural"
VOICE = KOKORO_VOICE  # Backward compatibility alias

_current_id = 0
_id_lock = threading.Lock()

_pipeline = None
_pipeline_lock = threading.Lock()


def get_pipeline():
    """Lazily loads and caches the Kokoro TTS pipeline with CUDA acceleration."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            try:
                import torch
                from kokoro import KPipeline
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                _pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', device=device)
                log_info("TTS", f"Kokoro-82M AI TTS engine initialized on device: {device.upper()}")
            except Exception as e:
                log_error("TTS", f"Failed to initialize Kokoro pipeline: {e}")
                _pipeline = False
        return _pipeline if _pipeline is not False else None


def set_voice(voice_name: str):
    """Sets the active voice for Kokoro TTS."""
    global KOKORO_VOICE, VOICE
    KOKORO_VOICE = voice_name
    VOICE = voice_name


def clean_markdown_for_tts(text: str) -> str:
    """Strips markdown formatting symbols so TTS never reads 'asterisk' aloud."""
    if not text:
        return text
    # Remove bracketed stage directions or emotion tags: [excited], [sad], [laughter], etc.
    text = re.sub(r'\[[a-zA-Z\s_-]+\]', '', text)
    # Remove bold: ***text*** or **text**
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text, flags=re.DOTALL)
    # Remove italic underscores: _text_ or __text__
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text, flags=re.DOTALL)
    # Remove inline code backticks: `text`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove heading markers anywhere in text (e.g. ## Heading)
    text = re.sub(r'#{1,6}\s*', '', text)
    # Remove remaining bare asterisks/underscores that weren't part of a pair
    text = re.sub(r'[\*_]', '', text)
    return text.strip()


async def _generate_edge_speech(text: str, output_path: str):
    """Generates audio using Edge TTS as a reliable fallback."""
    import edge_tts
    communicate = edge_tts.Communicate(text, EDGE_FALLBACK_VOICE)
    await asyncio.wait_for(communicate.save(output_path), timeout=8.0)


def _generate_kokoro_speech(text: str, output_path: str, voice: str = None) -> bool:
    """
    Synthesizes speech using local Kokoro-82M neural model.
    Returns True on success, False on failure.
    """
    pipeline = get_pipeline()
    if pipeline is None:
        return False

    try:
        import torch
        import soundfile as sf

        target_voice = voice or KOKORO_VOICE
        generator = pipeline(text, voice=target_voice, speed=1.0)
        chunks = []
        for _, _, audio in generator:
            if audio is not None and len(audio) > 0:
                chunks.append(audio)

        if not chunks:
            return False

        full_audio = torch.cat(chunks) if len(chunks) > 1 else chunks[0]
        # full_audio is 24kHz float tensor
        audio_np = full_audio.detach().cpu().numpy()
        sf.write(output_path, audio_np, 24000)
        return True
    except Exception as e:
        log_error("TTS", f"Kokoro generation failed ({e}), falling back to Edge TTS")
        return False


def stop():
    """Stop any currently playing or pending TTS immediately."""
    global _current_id
    with _id_lock:
        _current_id += 1
    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
    except Exception:
        pass


def is_playing() -> bool:
    """Returns True if TTS audio is currently playing."""
    try:
        return pygame.mixer.music.get_busy()
    except Exception:
        return False


def speak(text: str, voice: str = None):
    """
    Synthesizes text to speech using expressive Kokoro AI TTS (with Edge TTS fallback)
    and plays it synchronously.
    Markdown formatting (*bold*, **bold**, _italic_, etc.) is stripped
    before synthesis.
    Can be interrupted at any time by calling stop().
    """
    global _current_id

    if not text or not text.strip():
        return

    with _id_lock:
        _current_id += 1
        my_id = _current_id

    # Strip markdown so voice engine never reads asterisks / underscores
    tts_text = clean_markdown_for_tts(text)

    log_assistant(text)

    # Use .wav for Kokoro, .mp3 for Edge TTS
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_filename = temp_file.name

    try:
        if _current_id != my_id:
            return

        success = _generate_kokoro_speech(tts_text, temp_filename, voice=voice)

        if not success:
            if _current_id != my_id:
                return
            # Fallback to Edge TTS
            fallback_mp3 = temp_filename.replace(".wav", ".mp3")
            asyncio.run(_generate_edge_speech(tts_text, fallback_mp3))
            temp_filename = fallback_mp3

        if _current_id != my_id:
            return

        pygame.mixer.music.load(temp_filename)
        pygame.mixer.music.play()

        # Wait for playback to finish or be interrupted
        while pygame.mixer.music.get_busy() and _current_id == my_id:
            pygame.time.Clock().tick(20)

    except Exception as e:
        log_error("TTS", f"Playback error: {e}")
    finally:
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass

        if os.path.exists(temp_filename):
            for _ in range(5):
                try:
                    os.remove(temp_filename)
                    break
                except Exception:
                    import time
                    time.sleep(0.1)


def speak_async(text: str, voice: str = None):
    """Non-blocking background helper for speech synthesis."""
    if not text or not text.strip():
        return
    t = threading.Thread(target=speak, args=(text, voice), daemon=True)
    t.start()


if __name__ == "__main__":
    speak("Hello! I am Phantom. Your upgraded voice assistant with expressive, natural AI speech.")
