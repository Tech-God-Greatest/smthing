import os
import tempfile
import uuid
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QCursor, QKeySequence, QFont


class ScreenSnipper(QWidget):
    """Full-screen translucent overlay for circling/selecting screen areas with Sci-Fi HUD aesthetics."""
    snippet_captured = pyqtSignal(str)  # Emits image file path
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.start_pos = None
        self.current_pos = None
        self.is_selecting = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        else:
            self.setGeometry(0, 0, 1920, 1080)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            self.close()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.current_pos = event.pos()

            if self.start_pos and self.current_pos:
                rect = QRect(self.start_pos, self.current_pos).normalized()
                if rect.width() > 10 and rect.height() > 10:
                    self.hide()
                    QApplication.processEvents()

                    screen = QApplication.primaryScreen()
                    if screen:
                        pixmap = screen.grabWindow(
                            0,
                            rect.x(),
                            rect.y(),
                            rect.width(),
                            rect.height()
                        )
                        temp_dir = tempfile.gettempdir()
                        temp_path = os.path.join(temp_dir, f"phantom_snippet_{uuid.uuid4().hex[:8]}.png")
                        pixmap.save(temp_path, "PNG")
                        self.snippet_captured.emit(temp_path)
                    else:
                        self.cancelled.emit()
                else:
                    self.cancelled.emit()
            else:
                self.cancelled.emit()

            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        screen_rect = self.rect()
        overlay_color = QColor(6, 10, 18, 175)

        if self.start_pos and self.current_pos and self.is_selecting:
            select_rect = QRect(self.start_pos, self.current_pos).normalized()

            path = QPainterPath()
            path.addRect(screen_rect.x(), screen_rect.y(), screen_rect.width(), screen_rect.height())

            sub_path = QPainterPath()
            sub_path.addRoundedRect(
                select_rect.x(),
                select_rect.y(),
                select_rect.width(),
                select_rect.height(),
                6, 6
            )

            path = path.subtracted(sub_path)
            painter.fillPath(path, overlay_color)

            # Highlight selection region
            painter.fillPath(sub_path, QColor(0, 243, 255, 20))

            # Glowing neon outline
            pen = QPen(QColor(0, 243, 255, 220), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRoundedRect(select_rect, 6, 6)

            # Sci-Fi Corner reticles & dimensions tag
            accent_pen = QPen(QColor(0, 255, 157, 255), 2.5, Qt.PenStyle.SolidLine)
            painter.setPen(accent_pen)
            r = select_rect
            length = min(16, min(r.width(), r.height()) // 4)

            # Top-left
            painter.drawLine(r.left(), r.top(), r.left() + length, r.top())
            painter.drawLine(r.left(), r.top(), r.left(), r.top() + length)
            # Top-right
            painter.drawLine(r.right(), r.top(), r.right() - length, r.top())
            painter.drawLine(r.right(), r.top(), r.right(), r.top() + length)
            # Bottom-left
            painter.drawLine(r.left(), r.bottom(), r.left() + length, r.bottom())
            painter.drawLine(r.left(), r.bottom(), r.left(), r.bottom() - length)
            # Bottom-right
            painter.drawLine(r.right(), r.bottom(), r.right() - length, r.bottom())
            painter.drawLine(r.right(), r.bottom(), r.right(), r.bottom() - length)

            # Draw resolution tag HUD text
            dim_text = f"TARGET // {r.width()}x{r.height()} PX"
            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            painter.setPen(QColor(0, 243, 255, 220))
            painter.drawText(r.left() + 4, r.top() - 6, dim_text)
        else:
            painter.fillRect(screen_rect, overlay_color)
