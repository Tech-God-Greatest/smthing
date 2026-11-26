from PyQt6.QtCore import QThread, pyqtSignal
from llm import execute_llm_query, execute_vision_query
from storage import storage
from audio.tts import speak_async
from utils.logger import log_warning


class QueryWorker(QThread):
    """Background thread: LLM call + Async TTS + DB storage + Async Titling."""
    thinking_signal      = pyqtSignal(str, int)
    tool_called_signal   = pyqtSignal(str, int)   # (display_str, request_id)
    response_ready       = pyqtSignal(str, str, int)
    done_signal          = pyqtSignal(int)
    request_title_signal = pyqtSignal(int, str, str)
    request_summary_signal = pyqtSignal(int)

    def __init__(self, query: str, display_query: str, request_id: int, chat_id: int, notch_ref, image_path: str = None, ai_mode: str = "Multi"):
        super().__init__()
        self.query         = query          # raw query for LLM (includes full file content etc.)
        self.display_query = display_query  # UI-formatted query for signals and title generation
        self.request_id = request_id
        self.chat_id    = chat_id
        self.notch_ref  = notch_ref
        self.image_path = image_path
        self.ai_mode    = ai_mode

    def is_cancelled(self) -> bool:
        return self.notch_ref.current_request_id != self.request_id

    def _on_tool_call(self, name: str, args: dict):
        """Called by llm.py each time a tool fires. Builds a display string and emits."""
        if self.is_cancelled():
            return
        # Format: web_search("python docs") or remember(category="prefs", key="theme", ...)
        arg_parts = []
        for k, v in args.items():
            val = str(v)
            if len(val) > 40:
                val = val[:40] + "…"
            arg_parts.append(f'{k}="{val}"')
        display = f"{name}({', '.join(arg_parts)})"
        self.tool_called_signal.emit(display, self.request_id)

    def run(self):
        if self.is_cancelled():
            return

        self.thinking_signal.emit(self.display_query, self.request_id)

        try:
            recent_msgs   = storage.get_recent_messages(self.chat_id, limit=100)
            history_count = len(recent_msgs)

            if self.image_path:
                reply = execute_vision_query(
                    query=self.query,
                    image_path=self.image_path,
                    chat_id=self.chat_id,
                    check_cancelled=self.is_cancelled,
                    ai_mode=self.ai_mode
                )
            else:
                reply = execute_llm_query(
                    query=self.query,
                    chat_id=self.chat_id,
                    check_cancelled=self.is_cancelled,
                    on_tool_call=self._on_tool_call,   # ← live tool notifications
                    ai_mode=self.ai_mode
                )

            if self.is_cancelled():
                log_warning("Query", f"Request #{self.request_id} cancelled.")
                return

            if history_count <= 2:
                self.request_title_signal.emit(self.chat_id, self.display_query, reply)

            if history_count >= 50:
                self.request_summary_signal.emit(self.chat_id)

            self.response_ready.emit(self.display_query, reply, self.request_id)

            if self.is_cancelled():
                return

            try:
                speak_async(reply)
            except Exception as tts_err:
                log_warning("QueryWorker", f"TTS execution error: {tts_err}")

        except Exception as e:
            if not self.is_cancelled():
                error_msg = f"[Error]: {e}"
                # Only save if the LLM layer didn't already save a response
                recent = storage.get_recent_messages(self.chat_id, limit=1)
                if not recent or recent[-1]["role"] != "assistant":
                    storage.save_message(self.chat_id, "assistant", error_msg)
                self.response_ready.emit(self.display_query, error_msg, self.request_id)
        finally:
            if not self.is_cancelled():
                self.done_signal.emit(self.request_id)
