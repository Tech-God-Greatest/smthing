import sys
import os
import re
import time
import math
import tempfile
import datetime
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer, pyqtSignal, QPoint, QSize
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                              QScrollArea, QFrame, QPushButton, QGraphicsOpacityEffect, QSizePolicy, QComboBox)
from PyQt6.QtGui import (QFont, QPainter, QBrush, QColor, QPainterPath, QPen,
                          QLinearGradient, QRadialGradient, QPolygonF, QImage, QKeySequence)

from storage import storage
from ui.sidebar import PhantomSidebar
from ui.screen_snipper import ScreenSnipper
from workers.voice_worker import VoiceWorker
from workers.query_worker import QueryWorker
from workers.title_worker import TitleGeneratorWorker, SummarizerWorker
from workers.hotkey_worker import HotkeyWorker
from workers.preloader_worker import ModelPreloaderWorker
from llm import unload_ollama_model
from audio.stt import shutdown_browser, has_wake_word, normalize_text
from audio.tts import stop as tts_stop, is_playing as tts_is_playing, speak_async
from utils.logger import log_error, log_info


class WrappingLabel(QLabel):
    """
    A QLabel that correctly reports heightForWidth so that word-wrapped text
    inside a QScrollArea expands *downward* instead of being clipped sideways.
    Required because PyQt6's QLabel doesn't implement hasHeightForWidth for
    RichText when placed inside a resizable scroll area.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        from PyQt6.QtGui import QTextDocument
        td = QTextDocument()
        td.setDefaultFont(self.font())
        td.setHtml(self.text() if self.text() else " ")
        td.setTextWidth(max(width, 1))
        return int(td.size().height()) + 6

    def sizeHint(self):
        sh = super().sizeHint()
        sh.setHeight(self.heightForWidth(sh.width()))
        return sh

    def minimumSizeHint(self):
        msh = super().minimumSizeHint()
        msh.setWidth(0)
        return msh


# ---------------------------------------------------------------------------
# Supported file types for clipboard paste
# ---------------------------------------------------------------------------
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'}
TEXT_EXTS  = {
    '.txt', '.md', '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css',
    '.json', '.yaml', '.yml', '.xml', '.csv', '.toml', '.ini', '.cfg',
    '.sh', '.bat', '.ps1', '.c', '.cpp', '.h', '.java', '.rs', '.go',
    '.rb', '.php', '.swift', '.kt', '.r', '.sql', '.log',
}
MAX_TEXT_FILE_BYTES = 64 * 1024  # 64 KB safety cap


class SmartPasteInput(QLineEdit):
    """
    A QLineEdit that intercepts Ctrl+V to detect clipboard content type:
      - QImage  → emits image_pasted(temp_png_path)
      - Image file path  → emits image_pasted(path)
      - Text file path   → emits text_file_pasted(path)
      - Plain text       → normal paste
    """
    image_pasted     = pyqtSignal(str)   # absolute path to image
    text_file_pasted = pyqtSignal(str)   # absolute path to text file

    def keyPressEvent(self, event):
        is_ctrl_v = (
            event.key() == Qt.Key.Key_V
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        )
        if is_ctrl_v:
            cb = QApplication.clipboard()
            mime = cb.mimeData()

            # ── 1. Raw image in clipboard (screenshot / copy-image from browser) ──
            if mime.hasImage():
                qimg: QImage = cb.image()
                if not qimg.isNull():
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=".png", prefix="phantom_paste_"
                    )
                    tmp.close()
                    if qimg.save(tmp.name, "PNG"):
                        self.image_pasted.emit(tmp.name)
                        return  # swallow the event — image handled

            # ── 2. File(s) dropped / copied in Explorer ──
            if mime.hasUrls():
                for url in mime.urls():
                    if url.isLocalFile():
                        path = url.toLocalFile()
                        ext  = os.path.splitext(path)[1].lower()
                        if ext in IMAGE_EXTS:
                            self.image_pasted.emit(path)
                            return
                        elif ext in TEXT_EXTS:
                            self.text_file_pasted.emit(path)
                            return

            # ── 3. Plain text that *looks like* a local file path ──
            if mime.hasText():
                raw = mime.text().strip()
                # Single-line, looks like an absolute path
                if ('\n' not in raw) and os.path.isabs(raw) and os.path.isfile(raw):
                    ext = os.path.splitext(raw)[1].lower()
                    if ext in IMAGE_EXTS:
                        self.image_pasted.emit(raw)
                        return
                    elif ext in TEXT_EXTS:
                        self.text_file_pasted.emit(raw)
                        return

            # ── 4. Fallback — normal text paste ──
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)


class ChatGroupWidget(QFrame):
    """
    Groups a User Prompt and its corresponding AI Reply into a cohesive
    sci-fi conversational card with translucent acrylic styling, glowing accent borders,
    and magnificent futuristic typography.
    """
    def __init__(self, user_text: str = None, ai_text: str = None, is_thinking: bool = False, image_path: str = None, parent=None):
        super().__init__(parent)
        self.user_text = user_text
        self.ai_text = ai_text
        self.is_thinking = is_thinking
        self.image_path = image_path

        self.setObjectName("chat_group_card")
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QFrame#chat_group_card {
                background-color: rgba(15, 22, 36, 0.65);
                border: 1px solid rgba(0, 243, 255, 0.22);
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # ---------------- USER PROMPT SECTION ----------------
        if self.user_text or self.image_path:
            user_box = QWidget(self)
            user_box.setStyleSheet("background: transparent; border: none;")
            user_layout = QVBoxLayout(user_box)
            user_layout.setContentsMargins(0, 0, 0, 0)
            user_layout.setSpacing(4)

            u_header = QHBoxLayout()
            u_header.setContentsMargins(0, 0, 0, 0)
            u_header.setSpacing(6)

            u_badge = QLabel("⚡ USER // PROMPT")
            u_badge.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            u_badge.setStyleSheet("""
                color: #00f3ff;
                background-color: rgba(0, 243, 255, 0.12);
                border: 1px solid rgba(0, 243, 255, 0.35);
                border-radius: 4px;
                padding: 2px 6px;
            """)
            u_header.addWidget(u_badge)
            u_header.addStretch()

            time_lbl = QLabel(datetime.datetime.now().strftime("%I:%M %p"))
            time_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Normal))
            time_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.40); background: transparent;")
            u_header.addWidget(time_lbl)

            user_layout.addLayout(u_header)

            display_text = self.user_text or ""
            if self.image_path:
                display_text = f"📷 <i>[Screen Snippet Attached]</i><br/>{display_text}"

            self.user_label = WrappingLabel(user_box)
            self.user_label.setText(display_text)
            self.user_label.setFont(QFont("Segoe UI", 10))
            self.user_label.setTextFormat(Qt.TextFormat.RichText)
            self.user_label.setStyleSheet("""
                color: #e0f2fe;
                background-color: rgba(255, 255, 255, 0.04);
                border-left: 3px solid #00f3ff;
                border-radius: 4px;
                padding: 6px 10px;
                line-height: 1.4;
            """)
            user_layout.addWidget(self.user_label)
            layout.addWidget(user_box)

        # ---------------- SEPARATOR LINE ----------------
        if (self.user_text or self.image_path) and (self.ai_text or self.is_thinking):
            sep = QFrame(self)
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("background-color: rgba(0, 243, 255, 0.15); max-height: 1px; border: none;")
            layout.addWidget(sep)

        # ---------------- AI REPLY SECTION ----------------
        if self.ai_text or self.is_thinking:
            ai_box = QWidget(self)
            ai_box.setStyleSheet("background: transparent; border: none;")
            ai_layout = QVBoxLayout(ai_box)
            ai_layout.setContentsMargins(0, 0, 0, 0)
            ai_layout.setSpacing(4)

            ai_header = QHBoxLayout()
            ai_header.setContentsMargins(0, 0, 0, 0)
            ai_header.setSpacing(6)

            ai_badge = QLabel("❖ PHANTOM // AI")
            ai_badge.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            ai_badge.setStyleSheet("""
                color: #00ff9d;
                background-color: rgba(0, 255, 157, 0.12);
                border: 1px solid rgba(0, 255, 157, 0.35);
                border-radius: 4px;
                padding: 2px 6px;
            """)
            ai_header.addWidget(ai_badge)
            ai_header.addStretch()

            ai_layout.addLayout(ai_header)

            self.ai_label = WrappingLabel(ai_box)
            self.ai_label.setTextFormat(Qt.TextFormat.RichText)
            self.ai_label.setFont(QFont("Segoe UI", 10))

            if self.is_thinking:
                self.ai_label.setText("<span style='color:#00f3ff; font-style:italic;'>[SYS // THINKING...] Processing quantum query stream</span>")
                self.ai_label.setStyleSheet("""
                    color: #00f3ff;
                    background-color: rgba(0, 243, 255, 0.05);
                    border-left: 3px solid #00ff9d;
                    border-radius: 4px;
                    padding: 8px 10px;
                """)
            else:
                formatted_text = self._format_ai_response(self.ai_text)
                self.ai_label.setText(formatted_text)
                self.ai_label.setStyleSheet("""
                    color: #f1f5f9;
                    background-color: rgba(0, 255, 157, 0.03);
                    border-left: 3px solid #00ff9d;
                    border-radius: 4px;
                    padding: 8px 10px;
                """)

            ai_layout.addWidget(self.ai_label)
            layout.addWidget(ai_box)

    def update_tool_status(self, tool_display: str):
        if self.is_thinking and hasattr(self, 'ai_label'):
            self.ai_label.setText(f"<span style='color:#f5a623; font-style:italic;'>[SYS // EXECUTING...] {tool_display}</span>")

    def set_ai_reply(self, reply_text: str):
        self.is_thinking = False
        if not reply_text or not str(reply_text).strip():
            reply_text = "Done."
        self.ai_text = reply_text
        formatted_text = self._format_ai_response(reply_text)
        self.ai_label.setText(formatted_text)
        self.ai_label.setStyleSheet("""
            color: #f1f5f9;
            background-color: rgba(0, 255, 157, 0.03);
            border-left: 3px solid #00ff9d;
            border-radius: 4px;
            padding: 8px 10px;
        """)

    def _format_ai_response(self, text: str) -> str:
        if not text:
            return ""

        # Extract code blocks first to protect them from regex formatting
        code_blocks = []
        def _save_code_block(match):
            lang = match.group(1) or ""
            code = match.group(2)
            code_escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            placeholder = f"___CODE_BLOCK_{len(code_blocks)}___"
            block_html = (
                f'<pre style="font-family:\'Consolas\',monospace; background:rgba(0,12,24,0.85); '
                f'color:#00f3ff; border:1px solid rgba(0,243,255,0.30); border-radius:6px; '
                f'padding:8px; margin:6px 0; overflow-x:auto; white-space:pre-wrap;">'
                f'<code>{code_escaped}</code></pre>'
            )
            code_blocks.append(block_html)
            return placeholder

        clean = re.sub(r'```(\w*)\n?(.*?)```', _save_code_block, text, flags=re.DOTALL)

        # Escape HTML special characters for the remaining text
        clean = clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Bold-italic: ***text***
        clean = re.sub(r'\*{3}(.+?)\*{3}', r'<b><i>\1</i></b>', clean, flags=re.DOTALL)
        # Bold: **text**
        clean = re.sub(r'\*{2}(.+?)\*{2}', r'<b>\1</b>', clean, flags=re.DOTALL)
        # Italic: *text*
        clean = re.sub(r'\*(.+?)\*', r'<i>\1</i>', clean, flags=re.DOTALL)
        # Bold underscores: __text__
        clean = re.sub(r'__(.+?)__', r'<b>\1</b>', clean, flags=re.DOTALL)
        # Italic underscores: _text_
        clean = re.sub(r'_(.+?)_', r'<i>\1</i>', clean, flags=re.DOTALL)

        # Inline code: `text`
        clean = re.sub(
            r'`([^`]+)`',
            r'<span style="font-family:\'Consolas\',monospace; background:rgba(0,243,255,0.10); '
            r'color:#00f3ff; border-radius:3px; padding:0 3px;">\1</span>',
            clean
        )

        # Bullet points: - item or * item
        clean = re.sub(r'^\s*[\-\*]\s+(.+)$', r'• \1', clean, flags=re.MULTILINE)

        # Convert newlines to <br/>
        clean = clean.replace("\n", "<br/>")

        # Re-insert preserved code blocks
        for idx, block in enumerate(code_blocks):
            clean = clean.replace(f"___CODE_BLOCK_{idx}___", block)

        return f"<div style='font-family: \"Segoe UI\", sans-serif; line-height: 1.45;'>{clean}</div>"

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        pen = QPen(QColor(0, 243, 255, 80), 1, Qt.PenStyle.SolidLine)
        painter.setPen(pen)

        l = 6
        painter.drawLine(rect.left(), rect.top() + l, rect.left(), rect.top())
        painter.drawLine(rect.left(), rect.top(), rect.left() + l, rect.top())
        painter.drawLine(rect.right(), rect.bottom() - l, rect.right(), rect.bottom())
        painter.drawLine(rect.right() - l, rect.bottom(), rect.right(), rect.bottom())


class PhantomNotch(QWidget):
    """
    Phantom Top Notch UI with Futuristic Sci-Fi HUD design,
    grainy rainy acrylic sheet background rendering, adaptively dynamic height elongation/shrinking,
    and grouped prompt-reply conversation architecture.
    """
    def __init__(self, sidebar_ref: PhantomSidebar):
        super().__init__()
        self.sidebar_ref = sidebar_ref
        self.sidebar = sidebar_ref
        self.current_chat_id = None
        self.is_expanded = False
        self.is_busy = False
        self.anim = None
        self.query_worker = None
        self.title_worker = None
        self.summarizer_worker = None
        self.current_request_id = 0
        self.attached_image_path = None
        self.attached_text_file_path = None
        self.snipper = None
        self.opened_by_hotkey = False
        self.hotkey_is_held = False
        self.opened_by_hover = False
        self.active_group_card = None
        self.last_active_time = 0
        self.wake_word_enabled = True

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.collapsed_height = 10
        self.min_expanded_height = 150
        self.max_expanded_height = 620
        self.current_expanded_height = 200
        self.notch_width = 440

        screen = QApplication.primaryScreen().geometry()
        self.max_expanded_height = min(640, int(screen.height() * 0.68))
        self.center_x = (screen.width() - self.notch_width) // 2
        self.setGeometry(self.center_x, 0, self.notch_width, self.collapsed_height)

        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self._auto_collapse)

        self.init_ui()

        # Connect Sidebar signals
        self.sidebar_ref.chat_selected.connect(self.load_chat_history)
        self.sidebar_ref.new_chat_requested.connect(self.start_new_chat)

        # Auto-resume the most recent active chat session on startup
        recent_chats = storage.list_chats()
        if recent_chats:
            latest_id = recent_chats[0]["id"]
            self.load_chat_history(latest_id)
            self.sidebar_ref.set_active_chat(latest_id)

        self.voice_worker = VoiceWorker()
        self.voice_worker.voice_detected_signal.connect(self.handle_voice_input)
        self.voice_worker.start()

        self.hotkey_worker = HotkeyWorker()
        self.hotkey_worker.hotkey_pressed.connect(self.handle_hotkey_pressed)
        self.hotkey_worker.hotkey_released.connect(self.handle_hotkey_released)
        self.hotkey_worker.start()

        # Preload local model into GPU VRAM on app startup in background
        self.status_dot.setText("● WARMING VRAM...")
        self.status_dot.setStyleSheet("color: #f5a623; background: transparent;")
        self.text_input.setPlaceholderText("Loading Local LLM into VRAM...")

        self.preloader_worker = ModelPreloaderWorker()
        self.preloader_worker.preload_finished.connect(self._on_model_preloaded)
        self.preloader_worker.start()

    def init_ui(self):
        self.container = QWidget(self)
        self.container.setGeometry(0, 0, self.notch_width, self.collapsed_height)
        self.container.setObjectName("notch_container")
        self.container.setStyleSheet("QWidget#notch_container { background: transparent; }")

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)

        # Sci-Fi Top Header Bar (Status & Controls)
        header_widget = QWidget(self.container)
        header_widget.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(6)

        sys_label = QLabel("❖ PHANTOM // SYS_ACTIVE", header_widget)
        sys_label.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        sys_label.setStyleSheet("color: #00f3ff; background: transparent;")
        header_layout.addWidget(sys_label)

        header_layout.addStretch()

        self.ai_combo = QComboBox(header_widget)
        self.ai_combo.addItems(["Multi", "Groq", "Local AI"])
        self.ai_combo.setToolTip("Select AI Engine: Multi (Groq + Local), Groq only, or Local AI only")
        self.ai_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(10, 16, 28, 0.75);
                color: #00f3ff;
                border: 1px solid rgba(0, 243, 255, 0.35);
                border-radius: 4px;
                padding: 1px 6px 1px 6px;
                font-family: 'Consolas';
                font-size: 10px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 1px solid rgba(0, 243, 255, 0.75);
                background-color: rgba(15, 24, 42, 0.85);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 12px;
                border-left-width: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #0a101c;
                color: #00f3ff;
                selection-background-color: rgba(0, 243, 255, 0.30);
                selection-color: #ffffff;
                border: 1px solid rgba(0, 243, 255, 0.50);
            }
        """)
        header_layout.addWidget(self.ai_combo)
        self.model_combo = self.ai_combo

        self.status_dot = QLabel("● ONLINE", header_widget)
        self.status_dot.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        self.status_dot.setStyleSheet("color: #00ff9d; background: transparent;")
        header_layout.addWidget(self.status_dot)

        layout.addWidget(header_widget)

        # Scroll Area for Chat History Cards
        self.scroll_area = QScrollArea(self.container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.20);
                width: 5px;
                border-radius: 2px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 243, 255, 0.35);
                border-radius: 2px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(0, 243, 255, 0.70);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(14)
        self.scroll_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area, 1)

        # Preview Container for Attached Screen Snippet
        self.preview_widget = QWidget(self.container)
        self.preview_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 243, 255, 0.10);
                border: 1px solid rgba(0, 243, 255, 0.40);
                border-radius: 8px;
            }
        """)
        preview_layout = QHBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(8, 4, 8, 4)
        preview_layout.setSpacing(6)

        self.preview_label = QLabel("📎 Attachment ready", self.preview_widget)
        self.preview_label.setStyleSheet("color: #00f3ff; font-family: 'Consolas'; font-size: 11px; border: none; background: transparent;")
        preview_layout.addWidget(self.preview_label, 1)

        self.remove_preview_btn = QPushButton("✕", self.preview_widget)
        self.remove_preview_btn.setFixedSize(18, 18)
        self.remove_preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_preview_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00f3ff;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #ff0055;
            }
        """)
        self.remove_preview_btn.clicked.connect(self._clear_all_attachments)
        preview_layout.addWidget(self.remove_preview_btn)

        self.preview_widget.hide()
        layout.addWidget(self.preview_widget)

        # Futuristic Input Controls Container
        input_container = QWidget(self.container)
        input_container.setStyleSheet("background: transparent; border: none;")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.text_input = SmartPasteInput(input_container)
        self.text_input.setPlaceholderText("Ask Phantom... (or hold Alt+Ctrl to speak)")
        self.text_input.setFont(QFont("Segoe UI", 10))
        self.text_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(10, 16, 28, 0.75);
                color: #ffffff;
                border: 1px solid rgba(0, 243, 255, 0.25);
                border-radius: 12px;
                padding: 8px 14px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(0, 243, 255, 0.75);
                background-color: rgba(15, 24, 42, 0.85);
            }
        """)
        self.text_input.returnPressed.connect(self.handle_text_input)
        self.text_input.textChanged.connect(self._on_text_changed)
        self.text_input.image_pasted.connect(self._on_image_pasted)
        self.text_input.text_file_pasted.connect(self._on_text_file_pasted)
        input_layout.addWidget(self.text_input, 1)

        self.circle_btn = QPushButton("📸", input_container)
        self.circle_btn.setToolTip("Circle to Search")
        self.circle_btn.setFixedSize(36, 36)
        self.circle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.circle_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 243, 255, 0.15);
                color: #ffffff;
                border: 1px solid rgba(0, 243, 255, 0.40);
                border-radius: 12px;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: rgba(0, 243, 255, 0.35);
                border: 1px solid rgba(0, 243, 255, 0.80);
            }
            QPushButton:pressed {
                background-color: rgba(0, 243, 255, 0.55);
            }
        """)
        self.circle_btn.clicked.connect(self.start_circle_search)
        input_layout.addWidget(self.circle_btn)

        layout.addWidget(input_container)

    def paintEvent(self, event):
        """
        Renders futuristic sci-fi HUD graphics with chamfered corners, neon glowing borders,
        and a translucent grainy/rainy acrylic sheet texture using custom QPainter algorithms.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        if h <= 0 or w <= 0:
            return

        chamfer = 14 if self.is_expanded else 4
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - chamfer)
        path.lineTo(w - chamfer, h)
        path.lineTo(chamfer, h)
        path.lineTo(0, h - chamfer)
        path.closeSubpath()

        acrylic_bg = QColor(10, 14, 23, 225) if self.is_expanded else QColor(8, 11, 18, 240)
        painter.fillPath(path, acrylic_bg)

        painter.save()
        painter.setClipPath(path)

        rain_pen = QPen(QColor(255, 255, 255, 8), 1, Qt.PenStyle.SolidLine)
        painter.setPen(rain_pen)
        spacing = 10
        for i in range(-h, w + h, spacing):
            painter.drawLine(i, 0, i + h // 2, h)

        grain_pen = QPen(QColor(0, 243, 255, 12), 1)
        painter.setPen(grain_pen)
        step = 16
        for y in range(4, h, step):
            for x in range(4, w, step):
                if (x + y) % 3 == 0:
                    painter.drawPoint(x, y)

        painter.restore()

        border_color = QColor(0, 243, 255, 120) if self.is_expanded else QColor(0, 243, 255, 70)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawPath(path)

        if self.is_expanded and h > 40:
            corner_pen = QPen(QColor(0, 243, 255, 220), 2)
            painter.setPen(corner_pen)
            bracket_len = 10

            painter.drawLine(0, h - chamfer - bracket_len, 0, h - chamfer)
            painter.drawLine(0, h - chamfer, chamfer, h)
            painter.drawLine(chamfer, h, chamfer + bracket_len, h)

            painter.drawLine(w, h - chamfer - bracket_len, w, h - chamfer)
            painter.drawLine(w, h - chamfer, w - chamfer, h)
            painter.drawLine(w - chamfer, h, w - chamfer - bracket_len, h)

            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor(0, 243, 255, 0))
            grad.setColorAt(0.2, QColor(0, 243, 255, 200))
            grad.setColorAt(0.5, QColor(123, 44, 191, 240))
            grad.setColorAt(0.8, QColor(0, 255, 157, 200))
            grad.setColorAt(1.0, QColor(0, 243, 255, 0))
            painter.setPen(QPen(QBrush(grad), 2))
            painter.drawLine(0, 1, w, 1)

    def _clear_chat_bubbles(self):
        self.active_group_card = None
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.scroll_layout.addStretch()

    def load_chat_history(self, chat_id: int):
        self.current_chat_id = chat_id
        self._clear_attached_image()
        self._clear_chat_bubbles()

        messages = storage.get_recent_messages(chat_id, limit=50)

        idx = 0
        while idx < len(messages):
            msg = messages[idx]
            if msg["role"] == "user":
                user_text = msg["content"]
                ai_text = None
                if idx + 1 < len(messages) and messages[idx + 1]["role"] == "assistant":
                    ai_text = messages[idx + 1]["content"]
                    idx += 1
                card = ChatGroupWidget(user_text=user_text, ai_text=ai_text)
                count = self.scroll_layout.count()
                self.scroll_layout.insertWidget(count - 1, card)
            elif msg["role"] == "assistant":
                card = ChatGroupWidget(ai_text=msg["content"])
                count = self.scroll_layout.count()
                self.scroll_layout.insertWidget(count - 1, card)
            idx += 1

        self.recalculate_and_animate_height()
        QTimer.singleShot(60, self._scroll_to_bottom)

    def start_new_chat(self):
        self.current_chat_id = None
        self._clear_attached_image()
        self._clear_chat_bubbles()
        self.recalculate_and_animate_height()

    def _calculate_target_expanded_height(self) -> int:
        self.scroll_content.adjustSize()
        content_height = self.scroll_layout.sizeHint().height()

        extra_h = 100
        if self.preview_widget.isVisible():
            extra_h += 38

        target_h = content_height + extra_h
        return max(self.min_expanded_height, min(target_h, self.max_expanded_height))

    def recalculate_and_animate_height(self):
        """
        Dynamically calculates content height requirements and smoothly animates
        the notch's expanded height (elongating for long texts and shrinking for short ones).
        """
        if not self.is_expanded:
            return

        clamped_h = self._calculate_target_expanded_height()

        if abs(self.height() - clamped_h) > 4:
            self.current_expanded_height = clamped_h
            self._animate_geometry(clamped_h)

    def _animate_geometry(self, target_height: int):
        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(140)
        self.anim.setStartValue(QRect(self.center_x, 0, self.notch_width, self.height()))
        self.anim.setEndValue(QRect(self.center_x, 0, self.notch_width, target_height))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def sync_container():
            self.container.setGeometry(0, 0, self.notch_width, self.height())
            self.update()

        self.anim.valueChanged.connect(sync_container)
        self.anim.start()

    def expand_notch(self):
        if self.is_expanded:
            return

        self.is_expanded = True
        self.collapse_timer.stop()

        target_h = self._calculate_target_expanded_height()
        self.current_expanded_height = target_h
        self._animate_geometry(target_h)

    def collapse_notch(self, force: bool = False):
        if not self.is_expanded:
            return
        if self.is_busy and not force:
            return

        self.is_expanded = False
        self.collapse_timer.stop()
        if hasattr(self, 'text_input'):
            self.text_input.clearFocus()

        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(130)
        self.anim.setStartValue(QRect(self.center_x, 0, self.notch_width, self.height()))
        self.anim.setEndValue(QRect(self.center_x, 0, self.notch_width, self.collapsed_height))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def sync_container():
            self.container.setGeometry(0, 0, self.notch_width, self.height())
            self.update()

        self.anim.valueChanged.connect(sync_container)
        self.anim.start()

    def _on_text_changed(self, text: str):
        """Reset the 5s collapse timer whenever the user types."""
        self.last_active_time = time.time()
        if not self.is_busy:
            self._start_collapse_timer()

    def _is_user_interacting(self) -> bool:
        """
        Check if user is actively interacting with the notch UI (hovering mouse over UI
        or viewing an open combo dropdown). Keyboard/text focus alone does NOT block
        auto-collapse if mouse cursor is not on the UI.
        """
        if self.underMouse():
            return True
        if hasattr(self, 'ai_combo') and self.ai_combo.view() and self.ai_combo.view().isVisible():
            return True
        return False

    def _start_collapse_timer(self):
        self.collapse_timer.start(3000)

    def enterEvent(self, event):
        """Expand notch on mouse hover; cancel any pending collapse timer."""
        self.collapse_timer.stop()
        if not self.is_expanded:
            self.expand_notch()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Collapse notch immediately when mouse leaves the notch UI."""
        if not self.is_busy and not self.hotkey_is_held:
            if not self._is_user_interacting():
                self.collapse_notch()
            else:
                self._start_collapse_timer()
        super().leaveEvent(event)

    def _auto_collapse(self):
        """Automatically collapse the notch after the 5s timer expires, unless busy or user is hovering on UI."""
        if not self.is_busy and not self.hotkey_is_held and not self._is_user_interacting():
            self.collapse_notch()
        else:
            # User is hovering on UI or combo popup is open — re-check in 5s
            self._start_collapse_timer()

    def handle_hotkey_pressed(self):
        self.hotkey_is_held = True
        self.opened_by_hotkey = True
        self.opened_by_hover = False
        self.last_active_time = time.time()
        tts_stop()
        self.expand_notch()
        self.text_input.setPlaceholderText("Listening (Alt+Ctrl held)...")

    def handle_hotkey_released(self):
        self.hotkey_is_held = False
        self.text_input.setPlaceholderText("Ask Phantom...")

    def check_and_handle_wake_word_command(self, text: str) -> bool:
        """
        Checks if text is a wake word disable or enable command.
        If matched, toggles self.wake_word_enabled, notifies user, and returns True.
        This prevents the command sentence from going to the LLM.
        """
        if not text or not text.strip():
            return False

        norm = normalize_text(text)
        clean = norm
        if clean.startswith("phantom "):
            clean = clean[8:].strip()

        if clean == "wake word disable":
            self.wake_word_enabled = False
            log_info("Voice", "Wake word disabled by user command.")
            self.status_dot.setText("● WAKE WORD DISABLED")
            self.status_dot.setStyleSheet("color: #f5a623; background: transparent;")
            tts_stop()
            speak_async("Wake word disabled.")
            def _restore_status():
                if not self.is_busy:
                    self.status_dot.setText("● ONLINE")
                    self.status_dot.setStyleSheet("color: #00ff9d; background: transparent;")
            QTimer.singleShot(2500, _restore_status)
            return True

        if clean == "wake word enable":
            self.wake_word_enabled = True
            log_info("Voice", "Wake word enabled by user command.")
            self.status_dot.setText("● WAKE WORD ENABLED")
            self.status_dot.setStyleSheet("color: #00ff9d; background: transparent;")
            tts_stop()
            speak_async("Wake word enabled.")
            def _restore_status2():
                if not self.is_busy:
                    self.status_dot.setText("● ONLINE")
                    self.status_dot.setStyleSheet("color: #00ff9d; background: transparent;")
            QTimer.singleShot(2500, _restore_status2)
            return True

        return False

    def handle_voice_input(self, text: str):
        if not text or not text.strip():
            return

        if self.check_and_handle_wake_word_command(text):
            return

        tts_was_active = tts_is_playing() or self.is_busy
        is_wake = has_wake_word(text)
        # Process during active session window, when notch is expanded, when TTS is active/busy, or wake word / hotkey activated
        in_active_window = self.is_expanded or tts_was_active or self.collapse_timer.isActive() or (time.time() - self.last_active_time < 15.0)

        should_process = not self.wake_word_enabled or is_wake or self.opened_by_hotkey or in_active_window

        if should_process:
            self.opened_by_hover = False  # active conversation turn
            self.last_active_time = time.time()
            tts_stop()
            query = text.strip()
            self.process_query(query)

    def handle_text_input(self):
        text = self.text_input.text().strip()
        if not text and not self.attached_image_path and not self.attached_text_file_path:
            return
        self.text_input.clear()
        if self.check_and_handle_wake_word_command(text):
            return
        tts_stop()
        self.process_query(text)

    def start_circle_search(self):
        self.hide()
        QApplication.processEvents()

        self.snipper = ScreenSnipper()
        self.snipper.snippet_captured.connect(self._on_snippet_captured)
        self.snipper.cancelled.connect(self._on_snippet_cancelled)
        self.snipper.show()

    def _on_snippet_captured(self, image_path: str):
        self.attached_image_path = image_path
        self.preview_label.setText("📷 Image attached")
        self.preview_widget.show()
        self.show()
        self.expand_notch()
        self.recalculate_and_animate_height()
        self.text_input.setFocus()

    def _on_snippet_cancelled(self):
        self.show()
        self.expand_notch()

    def _on_image_pasted(self, image_path: str):
        """Called when user Ctrl+V pastes an image or image file path."""
        self.attached_image_path = image_path
        self.attached_text_file_path = None
        fname = os.path.basename(image_path)
        self.preview_label.setText(f"🖼️ {fname}")
        self.preview_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 243, 255, 0.10);
                border: 1px solid rgba(0, 243, 255, 0.40);
                border-radius: 8px;
            }
        """)
        self.preview_widget.show()
        self.expand_notch()
        self.recalculate_and_animate_height()
        self.text_input.setFocus()

    def _on_text_file_pasted(self, file_path: str):
        """Called when user Ctrl+V pastes a text/code file path."""
        self.attached_text_file_path = file_path
        self.attached_image_path = None
        fname = os.path.basename(file_path)
        self.preview_label.setText(f"📄 {fname}")
        self.preview_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 255, 157, 0.08);
                border: 1px solid rgba(0, 255, 157, 0.40);
                border-radius: 8px;
            }
        """)
        self.preview_widget.show()
        self.expand_notch()
        self.recalculate_and_animate_height()
        self.text_input.setFocus()

    def _clear_all_attachments(self):
        """Remove button handler — clears whichever attachment is active."""
        self._clear_attached_image()

    def _clear_attached_image(self):
        if self.attached_image_path and "phantom_" in os.path.basename(self.attached_image_path):
            try:
                if os.path.exists(self.attached_image_path):
                    os.remove(self.attached_image_path)
            except Exception:
                pass
        self.attached_image_path = None
        self.attached_text_file_path = None
        self.preview_widget.hide()
        # Reset preview style to default
        self.preview_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 243, 255, 0.10);
                border: 1px solid rgba(0, 243, 255, 0.40);
                border-radius: 8px;
            }
        """)
        self.recalculate_and_animate_height()

    def process_query(self, query: str):
        if not self.attached_image_path and not self.attached_text_file_path:
            if self.check_and_handle_wake_word_command(query):
                self._clear_attached_image()
                return

        image_path = self.attached_image_path
        text_file_path = self.attached_text_file_path
        self._clear_attached_image()

        # ── Inject text file content into the query ──────────────────────────
        if text_file_path and os.path.isfile(text_file_path):
            try:
                fname = os.path.basename(text_file_path)
                with open(text_file_path, 'r', encoding='utf-8', errors='replace') as fh:
                    file_content = fh.read(MAX_TEXT_FILE_BYTES)
                ext = os.path.splitext(text_file_path)[1].lstrip('.')
                file_block = (
                    f"\n\n[Attached file: {fname}]\n"
                    f"```{ext}\n{file_content}\n```"
                )
                query = (query + file_block) if query else file_block.strip()
            except Exception as e:
                log_error("Notch", f"Could not read text file: {e}")

        if not query and image_path:
            query = "Analyze this image."

        if self.current_chat_id is None:
            self.current_chat_id = storage.create_chat()
            self.sidebar_ref.set_active_chat(self.current_chat_id)

        # Build a tidy display label for the chat card
        if image_path:
            display_query = f"📷 {query}" if query else "📷 Analyze this image."
        elif text_file_path:
            fname = os.path.basename(text_file_path)
            # query.split('\n')[0] = user's typed text before the injected file block
            short_q = query.split('\n')[0].strip()
            display_query = f"📄 [{fname}]" + (f" {short_q}" if short_q else "")
        else:
            display_query = query

        storage.save_message(self.current_chat_id, "user", display_query)

        self.current_request_id += 1
        req_id = self.current_request_id

        self.is_busy = True
        self.opened_by_hover = False  # processing — use timer-based collapse after done
        self.collapse_timer.stop()
        self.expand_notch()

        self.active_group_card = ChatGroupWidget(user_text=query, is_thinking=True, image_path=image_path)
        count = self.scroll_layout.count()
        self.scroll_layout.insertWidget(count - 1, self.active_group_card)
        self.recalculate_and_animate_height()
        self._scroll_to_bottom()

        if self.query_worker is not None and self.query_worker.isRunning():
            try:
                self.query_worker.thinking_signal.disconnect()
                self.query_worker.tool_called_signal.disconnect()
                self.query_worker.response_ready.disconnect()
                self.query_worker.done_signal.disconnect()
                self.query_worker.request_title_signal.disconnect()
                self.query_worker.request_summary_signal.disconnect()
            except Exception:
                pass
            try:
                self.query_worker.quit()
            except Exception:
                pass

        selected_mode = self.ai_combo.currentText()
        self.query_worker = QueryWorker(query, display_query, req_id, self.current_chat_id, self, image_path=image_path, ai_mode=selected_mode)
        self.query_worker.thinking_signal.connect(self._on_thinking)
        self.query_worker.tool_called_signal.connect(self._on_tool_called)
        self.query_worker.response_ready.connect(self._on_response)
        self.query_worker.done_signal.connect(self._on_done)
        self.query_worker.request_title_signal.connect(self._trigger_async_title)
        self.query_worker.request_summary_signal.connect(self._trigger_async_summarizer)
        self.query_worker.start()

    def _on_thinking(self, query: str, req_id: int):
        if req_id != self.current_request_id:
            return
        self.status_dot.setText("● THINKING...")
        self.status_dot.setStyleSheet("color: #00f3ff; background: transparent;")

    def _on_tool_called(self, display: str, req_id: int):
        """Flash the tool name + args in the status bar while the tool executes."""
        if req_id != self.current_request_id:
            return
        # Truncate to fit the notch width (max ~48 chars)
        label = display if len(display) <= 48 else display[:46] + "…)"
        self.status_dot.setText(f"⚙ {label}")
        self.status_dot.setStyleSheet("color: #f5a623; background: transparent;")  # amber
        if self.active_group_card and hasattr(self.active_group_card, 'update_tool_status'):
            self.active_group_card.update_tool_status(label)

        # Restore THINKING... after 1.5 s in case the tool takes a while
        QTimer.singleShot(1500, lambda: (
            self.status_dot.setText("● THINKING...")
            or self.status_dot.setStyleSheet("color: #00f3ff; background: transparent;")
        ) if self.is_busy else None)

    def _on_response(self, query: str, reply: str, req_id: int):
        if req_id != self.current_request_id:
            return
        if self.active_group_card:
            self.active_group_card.set_ai_reply(reply)

        self.status_dot.setText("● ONLINE")
        self.status_dot.setStyleSheet("color: #00ff9d; background: transparent;")
        self.recalculate_and_animate_height()
        self._scroll_to_bottom()

    def _on_done(self, req_id: int):
        if req_id != self.current_request_id:
            return
        self.is_busy = False
        self.last_active_time = time.time()
        self.sidebar_ref.refresh_chat_list()
        self._start_collapse_timer()

    def _trigger_async_title(self, chat_id: int, user_msg: str, ai_msg: str):
        self.title_worker = TitleGeneratorWorker(chat_id, user_msg, ai_msg)
        self.title_worker.title_ready.connect(self._on_title_ready)
        self.title_worker.start()

    def _on_title_ready(self, chat_id: int, title: str):
        self.sidebar_ref.refresh_chat_list()

    def _trigger_async_summarizer(self, chat_id: int):
        self.summarizer_worker = SummarizerWorker(chat_id)
        self.summarizer_worker.start()

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_model_preloaded(self, success: bool, message: str):
        self.is_busy = False
        if success:
            self.status_dot.setText("● ONLINE")
            self.status_dot.setStyleSheet("color: #00ff9d; background: transparent;")
            self.text_input.setPlaceholderText("Ask Phantom... (or hold Alt+Ctrl to speak)")
        else:
            self.status_dot.setText("● LOCAL OFFLINE")
            self.status_dot.setStyleSheet("color: #ff0055; background: transparent;")
            self.text_input.setPlaceholderText("Ask Phantom (Groq mode active)...")

    def closeEvent(self, event):
        self.hotkey_worker.running = False
        self.hotkey_worker.quit()
        self.hotkey_worker.wait(2000)
        self.voice_worker.running = False
        self.voice_worker.quit()
        self.voice_worker.wait(2000)
        if self.query_worker:
            self.query_worker.quit()
            self.query_worker.wait(3000)
        if self.title_worker:
            self.title_worker.quit()
            self.title_worker.wait(2000)
        if self.summarizer_worker:
            self.summarizer_worker.quit()
            self.summarizer_worker.wait(2000)
        if hasattr(self, 'preloader_worker') and self.preloader_worker:
            self.preloader_worker.quit()
            self.preloader_worker.wait(2000)
        unload_ollama_model()
        shutdown_browser()
        super().closeEvent(event)
