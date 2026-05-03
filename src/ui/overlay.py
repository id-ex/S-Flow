import math
import sys

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QWidget


class StatusOverlay(QWidget):
    """Floating status overlay with animated recording and processing states."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(152, 44)

        self.text = ""
        self.mode = "message"
        self.phase = 0.0
        self.audio_level = 0.0
        self.smoothed_level = 0.0
        self.wave_phase = 0.0

        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self.update_animation)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_overlay)

        self.hide()

    def show_message(
        self,
        text: str,
        duration: int | None = None,
        animate: bool = False,
        mode: str | None = None,
    ) -> None:
        """Show a status message.

        Args:
            text: Message to show.
            duration: Optional auto-hide timeout in milliseconds.
            animate: Enables animated text shimmer for processing states.
            mode: Explicit visual mode: "recording", "recognizing", "translating", or "message".
        """
        self.hide_timer.stop()
        self.text = text.rstrip(".")
        self.mode = mode or ("recognizing" if animate else "message")
        self.phase = 0.0
        if self.mode == "recording":
            self.smoothed_level = 0.0
            self.wave_phase = 0.0
        self.resize(self._preferred_width(), 44)
        self.center_on_screen()
        self.show()
        self.raise_()
        self._force_topmost()

        if self.mode in {"recording", "recognizing", "translating"}:
            if not self.anim_timer.isActive():
                self.anim_timer.start()
        else:
            self.anim_timer.stop()

        self.update()

        if duration:
            self.hide_timer.start(duration)

    def update_animation(self) -> None:
        self.phase = (self.phase + 0.0045) % 1.0

        if self.mode == "recording":
            self.smoothed_level += (self.audio_level - self.smoothed_level) * 0.2
            level = max(0.0, min(1.0, self.smoothed_level))
            self.wave_phase += 0.035 + level * 0.12

        self.update()

    @pyqtSlot(float)
    def set_audio_level(self, level: float) -> None:
        self.audio_level = max(0.0, min(1.0, level))

    def hide_overlay(self) -> None:
        self.hide_timer.stop()
        self.anim_timer.stop()
        self.hide()

    def center_on_screen(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(
            screen.x() + screen.width() // 2 - self.width() // 2,
            screen.y() + screen.height() - 100,
        )

    def _force_topmost(self) -> None:
        """Keep the toast above normal and borderless fullscreen windows on Windows."""
        if sys.platform != "win32":
            return

        try:
            import ctypes

            hwnd = int(self.winId())
            hwnd_topmost = -1
            swp_nosize = 0x0001
            swp_nomove = 0x0002
            swp_noactivate = 0x0010
            swp_showwindow = 0x0040
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                hwnd_topmost,
                0,
                0,
                0,
                0,
                swp_nomove | swp_nosize | swp_noactivate | swp_showwindow,
            )
        except Exception:
            pass

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        self._paint_capsule(painter)

        if self.mode == "recording":
            self._paint_recording_thread(painter)
        else:
            self._paint_text(painter)

    def _preferred_width(self) -> int:
        if self.mode == "recording":
            return 152

        font = QFont("Segoe UI", self._font_size(), QFont.Weight.Bold)
        text_width = QFontMetrics(font).horizontalAdvance(self.text)
        return max(130, min(286, text_width + 64))

    def _capsule_rect(self):
        return self.rect().adjusted(3, 3, -3, -3)

    def _paint_capsule(self, painter: QPainter) -> None:
        rect = self._capsule_rect()
        gradient = QLinearGradient(rect.left(), rect.center().y(), rect.right(), rect.center().y())
        gradient.setColorAt(0.0, QColor(2, 3, 7, 250))
        gradient.setColorAt(0.5, QColor(1, 2, 6, 252))
        gradient.setColorAt(1.0, QColor(2, 5, 10, 250))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

    def _paint_recording_thread(self, painter: QPainter) -> None:
        rect = self._capsule_rect()
        center_y = rect.center().y()
        line_rect = rect.adjusted(22, 0, -22, 0)
        level = max(0.0, min(1.0, self.smoothed_level))
        amplitude = 0.8 + level * 12.5
        samples = 52

        thread_specs = [
            (math.pi, 0.62, 0.0, 0.42, 1.0, False),
            (0.0, 1.0, 0.0, 1.0, 1.0, True),
        ]

        for phase_offset, amp_scale, vertical_offset, opacity, speed_scale, is_main in thread_specs:
            path = QPainterPath()
            for index in range(samples):
                t = index / (samples - 1)
                x = line_rect.left() + line_rect.width() * t
                edge_fade = math.sin(math.pi * t)
                phase = self.wave_phase * speed_scale + phase_offset
                wave = math.sin(t * math.tau * 2.1 + phase)
                overtone = math.sin(t * math.tau * 4.4 - phase * 0.72) * 0.38
                y = center_y + vertical_offset + (wave + overtone) * amplitude * amp_scale * edge_fade

                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            gradient = QLinearGradient(line_rect.left(), center_y, line_rect.right(), center_y)
            gradient.setColorAt(0.0, QColor(116, 88, 255, int(180 * opacity)))
            gradient.setColorAt(0.55, QColor(70, 225, 255, int(215 * opacity)))
            gradient.setColorAt(1.0, QColor(109, 99, 255, int(180 * opacity)))

            if is_main:
                glow_pen = QPen(QColor(70, 190, 255, 68), 5.0, Qt.PenStyle.SolidLine)
                glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(glow_pen)
                painter.drawPath(path)

            line_width = 2.0 if is_main else 0.85
            line_pen = QPen(gradient, line_width, Qt.PenStyle.SolidLine)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(line_pen)
            painter.drawPath(path)

    def _paint_text(self, painter: QPainter) -> None:
        rect = self._capsule_rect()
        font = QFont("Segoe UI", self._font_size(), QFont.Weight.Bold)
        painter.setFont(font)

        metrics = QFontMetrics(font)
        display_text = metrics.elidedText(self.text, Qt.TextElideMode.ElideRight, rect.width() - 18)
        text_rect = metrics.boundingRect(display_text)
        x = rect.center().x() - text_rect.width() / 2
        y = rect.center().y() + (metrics.ascent() - metrics.descent()) / 2

        path = QPainterPath()
        path.addText(x, y, font, display_text)

        if self.mode in {"recognizing", "translating"}:
            shimmer_width = rect.width() * 0.55
            shimmer_left = rect.left() - shimmer_width + (rect.width() + shimmer_width * 2) * self.phase
            text_gradient = QLinearGradient(shimmer_left, rect.top(), shimmer_left + shimmer_width, rect.bottom())
            text_gradient.setColorAt(0.0, QColor(128, 104, 255, 185))
            text_gradient.setColorAt(0.36, QColor(196, 173, 255, 230))
            text_gradient.setColorAt(0.62, QColor(78, 222, 255, 245))
            text_gradient.setColorAt(1.0, QColor(120, 103, 255, 185))
            painter.fillPath(path, text_gradient)
        else:
            text_gradient = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
            text_gradient.setColorAt(0.0, QColor(160, 130, 255, 230))
            text_gradient.setColorAt(0.55, QColor(91, 211, 255, 245))
            text_gradient.setColorAt(1.0, QColor(121, 103, 255, 225))
            painter.fillPath(path, text_gradient)

    def _font_size(self) -> int:
        if self.mode in {"recognizing", "translating", "ready", "done"}:
            return 13
        return 12
