"""
workers/preloader_worker.py — Background VRAM preloader worker for Phantom AI.
"""

import os
import shutil
import subprocess
import time
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from llm import OLLAMA_BASE_URL, OLLAMA_MODEL
from utils.logger import log_info, log_success, log_warning, log_error


class ModelPreloaderWorker(QThread):
    """
    Background worker that ensures Ollama server is running (with D:\\OllamaModels)
    and preloads the local Ollama LLM into GPU VRAM at application startup,
    pinning it in VRAM indefinitely using keep_alive: -1.
    """
    preload_finished = pyqtSignal(bool, str)  # (success, message)

    def _ensure_server_running(self, base_url: str):
        try:
            r = requests.get(f"{base_url}/api/version", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass

        # Locate ollama executable
        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            default_path = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
            if os.path.exists(default_path):
                ollama_bin = default_path

        if not ollama_bin or not os.path.exists(ollama_bin):
            return False

        log_info("Preloader", "Ollama server is offline. Starting 'ollama serve' in background...")
        env = os.environ.copy()
        if "OLLAMA_MODELS" not in env or not env["OLLAMA_MODELS"]:
            env["OLLAMA_MODELS"] = r"D:\OllamaModels"

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            subprocess.Popen([ollama_bin, "serve"], env=env, creationflags=creationflags)
        except Exception as e:
            log_warning("Preloader", f"Could not launch Ollama daemon: {e}")
            return False

        for _ in range(12):
            time.sleep(0.5)
            try:
                r = requests.get(f"{base_url}/api/version", timeout=1.0)
                if r.status_code == 200:
                    log_success("Preloader", "Ollama server started successfully.")
                    return True
            except Exception:
                continue

        return False

    def run(self):
        log_info("Preloader", f"Initializing VRAM preload for local model '{OLLAMA_MODEL}'...")
        t0 = time.time()
        base = OLLAMA_BASE_URL.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]  # strip /v1

        # Auto-start Ollama if not running
        self._ensure_server_running(base)

        url = base + "/api/generate"
        try:
            resp = requests.post(
                url,
                json={
                    "model": OLLAMA_MODEL,
                    "keep_alive": -1
                },
                timeout=90
            )
            elapsed = round(time.time() - t0, 2)
            if resp.status_code == 200:
                msg = f"Model '{OLLAMA_MODEL}' fully loaded in VRAM ({elapsed}s)."
                log_success("Preloader", msg)
                self.preload_finished.emit(True, msg)
            elif resp.status_code == 404:
                msg = f"Model '{OLLAMA_MODEL}' not found in Ollama (HTTP 404). Check 'ollama list'."
                log_error("Preloader", msg)
                self.preload_finished.emit(False, msg)
            else:
                msg = f"Preload returned HTTP status {resp.status_code}: {resp.text[:100]}"
                log_error("Preloader", msg)
                self.preload_finished.emit(False, msg)
        except requests.exceptions.ConnectionError:
            elapsed = round(time.time() - t0, 2)
            msg = f"Ollama server is offline or unreachable on {base} (connection refused after {elapsed}s)."
            log_error("Preloader", msg)
            self.preload_finished.emit(False, msg)
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            msg = f"Error during model preload after {elapsed}s: {e}"
            log_error("Preloader", msg)
            self.preload_finished.emit(False, msg)

