import os
import datetime
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QTimer, QPoint
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                              QScrollArea, QFrame, QPushButton, QMenu, QFileDialog, QInputDialog, QMessageBox)
from PyQt6.QtGui import QFont, QPainter, QBrush, QColor, QPainterPath, QPen, QAction, QIcon, QCursor, QLinearGradient
from storage import storage


class ChatItemWidget(QWidget):
    chat_selected = pyqtSignal(int)
    chat_action = pyqtSignal(str, int)  # action_name, chat_id

    def __init__(self, chat_data: dict, is_active: bool = False):
        super().__init__()
        self.chat_id = chat_data["id"]
        self.title = chat_data["title"]
        self.updated_at = chat_data["updated_at"]
        self.is_active = is_active

        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(10)

        # Sci-Fi Globe / Cyber Icon
        icon_label = QLabel("🌐")
        icon_label.setFont(QFont("Segoe UI Emoji", 11))
        icon_label.setStyleSheet("""
            background: rgba(0, 243, 255, 0.10);
            border: 1px solid rgba(0, 243, 255, 0.25);
            border-radius: 6px;
            padding: 2px 4px;
        """)
        layout.addWidget(icon_label)

        # Title and Timestamp vertical layout
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.title_label.setStyleSheet("color: #e2e8f0; background: transparent; border: none;")
        text_layout.addWidget(self.title_label)

        time_str = self._format_timestamp(self.updated_at)
        if time_str:
            time_label = QLabel(time_str)
            time_label.setFont(QFont("Consolas", 7))
            time_label.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
            text_layout.addWidget(time_label)

        layout.addLayout(text_layout, 1)

        # Context Menu Button (⋮)
        self.menu_btn = QPushButton("⋮")
        self.menu_btn.setFixedSize(24, 24)
        self.menu_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(0, 243, 255, 0.20);
                color: #00f3ff;
            }
        """)
        self.menu_btn.clicked.connect(self.show_context_menu)
        layout.addWidget(self.menu_btn)

        self.update_style()

    def _format_timestamp(self, ts_str: str) -> str:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                dt = datetime.datetime.strptime(ts_str, fmt)
                return dt.strftime("%I:%M %p").lstrip('0')
            except ValueError:
                continue
        return ""

    def update_style(self):
        if self.is_active:
            bg_style = "background-color: rgba(0, 243, 255, 0.15); border-left: 3px solid #00f3ff; border-radius: 8px;"
        else:
            bg_style = "background-color: transparent; border-left: 3px solid transparent; border-radius: 8px;"

        self.setStyleSheet(f"""
            QWidget {{
                {bg_style}
            }}
            QWidget:hover {{
                background-color: rgba(0, 243, 255, 0.08);
                border-left: 3px solid rgba(0, 243, 255, 0.60);
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.chat_selected.emit(self.chat_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self.show_context_menu()

    def show_context_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0d1322;
                color: #e2e8f0;
                border: 1px solid rgba(0, 243, 255, 0.35);
                border-radius: 8px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 16px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 243, 255, 0.25);
                color: #00f3ff;
            }
        """)

        rename_action = QAction("✏️ Rename", menu)
        rename_action.triggered.connect(lambda: self.chat_action.emit("rename", self.chat_id))

        export_json_action = QAction("📄 Export JSON", menu)
        export_json_action.triggered.connect(lambda: self.chat_action.emit("export_json", self.chat_id))

        export_md_action = QAction("📝 Export Markdown", menu)
        export_md_action.triggered.connect(lambda: self.chat_action.emit("export_md", self.chat_id))

        archive_action = QAction("📦 Archive", menu)
        archive_action.triggered.connect(lambda: self.chat_action.emit("archive", self.chat_id))

        delete_action = QAction("🗑️ Delete", menu)
        delete_action.triggered.connect(lambda: self.chat_action.emit("delete", self.chat_id))

        menu.addAction(rename_action)
        menu.addAction(export_json_action)
        menu.addAction(export_md_action)
        menu.addAction(archive_action)
        menu.addSeparator()
        menu.addAction(delete_action)

        menu.exec(QCursor.pos())


class PhantomSidebar(QWidget):
    """
    Phantom Left Sidebar Notch UI with sleek sci-fi HUD styling,
    grainy rainy acrylic sheet texturing, and dynamic conversation management.
    """
    chat_selected = pyqtSignal(int)
    new_chat_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_expanded = False
        self.anim = None
        self.current_active_chat_id = None
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self._auto_collapse)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self.collapsed_width = 22
        self.expanded_width = 340
        self.sidebar_height = 620

        screen = QApplication.primaryScreen().geometry()
        self.center_y = (screen.height() - self.sidebar_height) // 2
        self.setGeometry(0, self.center_y, self.collapsed_width, self.sidebar_height)

        self.init_ui()
        self.refresh_chat_list()

    def init_ui(self):
        self.container = QWidget(self)
        self.container.setGeometry(0, 0, self.expanded_width, self.sidebar_height)
        self.container.setObjectName("sidebar_container")
        self.container.setStyleSheet("QWidget#sidebar_container { background: transparent; }")

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(14, 16, 14, 16)
        main_layout.setSpacing(12)

        # Header Row: Sci-Fi System Badge + + New Chat Button & Close Button (✕)
        sys_header = QLabel("❖ PHANTOM // ARCHIVES")
        sys_header.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        sys_header.setStyleSheet("color: #00f3ff; background: transparent;")
        main_layout.addWidget(sys_header)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.new_chat_btn = QPushButton("+ New Chat Session")
        self.new_chat_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 243, 255, 0.12);
                color: #ffffff;
                border: 1px solid rgba(0, 243, 255, 0.35);
                border-radius: 10px;
                padding: 8px 14px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(0, 243, 255, 0.28);
                border-color: rgba(0, 243, 255, 0.70);
            }
        """)
        self.new_chat_btn.clicked.connect(self._on_new_chat_clicked)
        header_layout.addWidget(self.new_chat_btn, 1)

        # Close Sidebar Button (✕)
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close Sidebar")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 85, 0.30);
                color: #ffffff;
                border-color: rgba(255, 0, 85, 0.60);
            }
        """)
        self.close_btn.clicked.connect(self.collapse_sidebar)
        header_layout.addWidget(self.close_btn)

        main_layout.addLayout(header_layout)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search conversations...")
        self.search_input.setFont(QFont("Segoe UI", 9))
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(10, 16, 28, 0.70);
                color: #ffffff;
                border: 1px solid rgba(0, 243, 255, 0.22);
                border-radius: 14px;
                padding: 6px 14px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(0, 243, 255, 0.65);
                background-color: rgba(15, 24, 42, 0.85);
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        main_layout.addWidget(self.search_input)

        # Scroll Area for Chat List
        self.scroll_area = QScrollArea()
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
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(6)

        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, 1)

    def paintEvent(self, event):
        """
        Renders sleek sci-fi HUD dock graphics with chamfered edges, translucent
        rainy/grainy acrylic sheet background, and neon border accents.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        if h <= 0 or w <= 0:
            return

        chamfer = 16 if self.is_expanded else 6
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w - chamfer, 0)
        path.lineTo(w, chamfer)
        path.lineTo(w, h - chamfer)
        path.lineTo(w - chamfer, h)
        path.lineTo(0, h)
        path.closeSubpath()

        # 1. Translucent Acrylic Glass Fill
        acrylic_bg = QColor(10, 14, 23, 230) if self.is_expanded else QColor(8, 11, 18, 245)
        painter.fillPath(path, acrylic_bg)

        # 2. Procedural Rainy/Grainy Acrylic Texture
        painter.save()
        painter.setClipPath(path)

        rain_pen = QPen(QColor(255, 255, 255, 7), 1, Qt.PenStyle.SolidLine)
        painter.setPen(rain_pen)
        spacing = 12
        for i in range(-h, w + h, spacing):
            painter.drawLine(i, 0, i + h // 2, h)

        grain_pen = QPen(QColor(0, 243, 255, 10), 1)
        painter.setPen(grain_pen)
        step = 18
        for y in range(4, h, step):
            for x in range(4, w, step):
                if (x + y) % 3 == 0:
                    painter.drawPoint(x, y)

        painter.restore()

        # 3. Glowing Border & Cyber Accent Line
        border_color = QColor(0, 243, 255, 110) if self.is_expanded else QColor(0, 243, 255, 60)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawPath(path)

        # Glowing Vertical Accent along right edge
        if self.is_expanded:
            grad = QLinearGradient(w - 1, 0, w - 1, h)
            grad.setColorAt(0.0, QColor(0, 243, 255, 0))
            grad.setColorAt(0.2, QColor(0, 243, 255, 220))
            grad.setColorAt(0.5, QColor(123, 44, 191, 240))
            grad.setColorAt(0.8, QColor(0, 255, 157, 220))
            grad.setColorAt(1.0, QColor(0, 243, 255, 0))
            painter.setPen(QPen(QBrush(grad), 2))
            painter.drawLine(w - 1, 0, w - 1, h)

    def expand_sidebar(self):
        if self.is_expanded:
            return
        self.is_expanded = True

        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(160)
        self.anim.setStartValue(QRect(0, self.center_y, self.width(), self.sidebar_height))
        self.anim.setEndValue(QRect(0, self.center_y, self.expanded_width, self.sidebar_height))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def sync_container():
            self.container.setGeometry(0, 0, self.width(), self.sidebar_height)
            self.update()

        self.anim.valueChanged.connect(sync_container)
        self.anim.start()

    def collapse_sidebar(self):
        if not self.is_expanded:
            return
        self.is_expanded = False

        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(150)
        self.anim.setStartValue(QRect(0, self.center_y, self.width(), self.sidebar_height))
        self.anim.setEndValue(QRect(0, self.center_y, self.collapsed_width, self.sidebar_height))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def sync_container():
            self.container.setGeometry(0, 0, self.width(), self.sidebar_height)
            self.update()

        self.anim.valueChanged.connect(sync_container)
        self.anim.start()

    def toggle_sidebar(self):
        if self.is_expanded:
            self.collapse_sidebar()
        else:
            self.expand_sidebar()

    def enterEvent(self, event):
        """Expand sidebar on mouse hover and cancel pending collapse timer."""
        self.collapse_timer.stop()
        if not self.is_expanded:
            self.expand_sidebar()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Start 3-second auto-collapse timer when mouse leaves the sidebar."""
        if self.is_expanded:
            self.collapse_timer.start(3000)
        super().leaveEvent(event)

    def _auto_collapse(self):
        """Automatically collapse the sidebar after the 3-second inactivity timer fires."""
        if self.is_expanded and not self.underMouse():
            self.collapse_sidebar()

    def _on_search_changed(self, text: str):
        self.refresh_chat_list(search_query=text)

    def _on_new_chat_clicked(self):
        self.current_active_chat_id = None
        self.refresh_chat_list()
        self.new_chat_requested.emit()

    def set_active_chat(self, chat_id: int):
        self.current_active_chat_id = chat_id
        self.refresh_chat_list()

    def refresh_chat_list(self, search_query: str = ""):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        chats = storage.list_chats(search_query=search_query)

        if not chats:
            no_chat_lbl = QLabel("No active sessions found")
            no_chat_lbl.setFont(QFont("Consolas", 9))
            no_chat_lbl.setStyleSheet("color: #64748b; padding: 20px 10px;")
            no_chat_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.scroll_layout.addWidget(no_chat_lbl)
            self.scroll_layout.addStretch()
            return

        grouped = self._group_chats_by_date(chats)

        for group_title, group_chats in grouped.items():
            if not group_chats:
                continue

            header_label = QLabel(f"// {group_title.upper()}")
            header_label.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            header_label.setStyleSheet("color: #00f3ff; padding: 8px 4px 4px 4px; background: transparent;")
            self.scroll_layout.addWidget(header_label)

            for c in group_chats:
                is_active = (c["id"] == self.current_active_chat_id)
                item_widget = ChatItemWidget(c, is_active=is_active)
                item_widget.chat_selected.connect(self._on_chat_selected)
                item_widget.chat_action.connect(self._on_chat_action)
                self.scroll_layout.addWidget(item_widget)

        self.scroll_layout.addStretch()

    def _group_chats_by_date(self, chats: list) -> dict:
        today_date = datetime.date.today()
        yesterday_date = today_date - datetime.timedelta(days=1)
        seven_days_ago = today_date - datetime.timedelta(days=7)

        groups = {
            "Today": [],
            "Yesterday": [],
            "Previous 7 days": [],
            "Older": []
        }

        for c in chats:
            ts_str = c.get("updated_at", "")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
                try:
                    dt = datetime.datetime.strptime(ts_str, fmt).date()
                    if dt == today_date:
                        groups["Today"].append(c)
                    elif dt == yesterday_date:
                        groups["Yesterday"].append(c)
                    elif dt >= seven_days_ago:
                        groups["Previous 7 days"].append(c)
                    else:
                        groups["Older"].append(c)
                    break
                except ValueError:
                    continue
            else:
                groups["Older"].append(c)

        return groups

    def _on_chat_selected(self, chat_id: int):
        self.current_active_chat_id = chat_id
        self.refresh_chat_list(search_query=self.search_input.text())
        self.chat_selected.emit(chat_id)

    def _on_chat_action(self, action: str, chat_id: int):
        if action == "delete":
            storage.delete_chat(chat_id)
            if self.current_active_chat_id == chat_id:
                self.current_active_chat_id = None
                self.new_chat_requested.emit()
            self.refresh_chat_list(search_query=self.search_input.text())

        elif action == "rename":
            text, ok = QInputDialog.getText(self, "Rename Chat Session", "Enter new session title:")
            if ok and text.strip():
                storage.update_chat_title(chat_id, text.strip())
                self.refresh_chat_list(search_query=self.search_input.text())

        elif action == "archive":
            storage.archive_chat(chat_id, is_archived=True)
            if self.current_active_chat_id == chat_id:
                self.current_active_chat_id = None
                self.new_chat_requested.emit()
            self.refresh_chat_list(search_query=self.search_input.text())

        elif action in ("export_json", "export_md", "export_txt"):
            fmt = action.replace("export_", "")
            content = storage.export_chat(chat_id, export_format=fmt)
            if content:
                file_filter = "JSON Files (*.json)" if fmt == "json" else ("Markdown Files (*.md)" if fmt == "md" else "Text Files (*.txt)")
                file_path, _ = QFileDialog.getSaveFileName(self, f"Export Chat ({fmt.upper()})", f"chat_{chat_id}.{fmt}", file_filter)
                if file_path:
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        QMessageBox.information(self, "Export Successful", f"Chat saved to {file_path}")
                    except Exception as e:
                        QMessageBox.critical(self, "Export Error", f"Failed to save file: {e}")

    load_chat_history = refresh_chat_list
