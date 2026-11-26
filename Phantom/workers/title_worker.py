import re
import traceback
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from storage import storage
from llm import OLLAMA_MODEL, OLLAMA_BASE_URL
from utils.logger import log_error

OLLAMA_URL = OLLAMA_BASE_URL.replace("/v1", "/api/chat")


class TitleGeneratorWorker(QThread):
    """Background thread to generate a concise title for a new chat instantly."""
    title_ready = pyqtSignal(int, str)

    def __init__(self, chat_id: int, user_msg: str, ai_msg: str):
        super().__init__()
        self.chat_id = chat_id
        self.user_msg = user_msg
        self.ai_msg = ai_msg

    def run(self):
        try:
            clean_text = re.sub(r'[^\w\s]', '', self.user_msg).strip()
            words = clean_text.split()
            title = ' '.join(words[:6]).title() if words else 'New Chat'
            if len(words) > 6:
                title += '...'

            storage.update_chat_title(self.chat_id, title)
            self.title_ready.emit(self.chat_id, title)
        except Exception as e:
            log_error("TitleWorker", f"Title generation error: {e}")


class SummarizerWorker(QThread):
    """Background thread to summarize long conversations using Ollama."""
    summary_ready = pyqtSignal(int, str)

    def __init__(self, chat_id: int):
        super().__init__()
        self.chat_id = chat_id

    def run(self):
        try:
            messages = storage.get_recent_messages(self.chat_id, limit=50)

            if not messages:
                return

            transcript = []

            for m in messages:
                role = "User" if m["role"] == "user" else "Assistant"
                transcript.append(f"{role}: {m['content']}")

            full_transcript = "\n".join(transcript)

            prompt = (
                "Summarize the following conversation.\n\n"
                "Include:\n"
                "- Main topics\n"
                "- Important user information\n"
                "- Key decisions\n\n"
                "Keep it to 2-3 concise sentences.\n\n"
                f"{full_transcript[:3000]}"
            )

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert conversation summarizer. Do not think."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "stream": False,
                    "think": False,
                    "keep_alive": -1,
                    "options": {
                        "num_ctx": 4096,
                        "num_predict": 100
                    }
                },
                timeout=30
            )

            response.raise_for_status()

            data = response.json()

            if "message" not in data:
                raise RuntimeError("No 'message' field in Ollama response.")

            summary = data["message"]["content"].strip()

            if summary:
                storage.update_chat_summary(self.chat_id, summary)
                self.summary_ready.emit(self.chat_id, summary)

        except Exception as e:
            log_error("TitleWorker", f"Summarizer error: {e}")