from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

BUBBLE_TOP = QColor(255, 255, 255, 248)
BUBBLE_BOTTOM = QColor(238, 246, 255, 248)
BUBBLE_BORDER = QColor(196, 220, 238)
TEXT_COLOR = QColor(43, 58, 74)
SHADOW = QColor(46, 74, 110)

MAX_WIDTH = 236
PAD_X = 13
PAD_Y = 9
TAIL = 9
RADIUS = 14
MARGIN = 7
MIN_HIDE_MS = 3000
MAX_HIDE_MS = 12000


class SpeechBubble(QWidget):
    """宠物头顶的漫画式气泡，用于显示回复（支持流式追加）。"""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._text = ""
        self._anchor = None
        self._anchor_getter = None
        self._font = QFont("Microsoft YaHei UI", 9)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(220)
        self._follow_timer.timeout.connect(self._follow)

    def set_anchor_getter(self, getter):
        self._anchor_getter = getter

    def _current_anchor(self):
        if self._anchor_getter is not None:
            try:
                anchor = self._anchor_getter()
                if anchor is not None:
                    return anchor
            except Exception:
                pass
        return self._anchor

    def show_stream(self, anchor=None):
        if anchor is not None:
            self._anchor = anchor
        self._text = ""
        self._resize()
        if not self.isVisible():
            self.show()
            self.raise_()
        self._reposition()
        self._follow_timer.start()
        self._hide_timer.stop()

    def append(self, delta):
        if not self._text and not self.isVisible() and self._current_anchor() is not None:
            self.show_stream()
        self._text += delta
        self._resize()
        self._reposition()
        self.update()

    def finalize(self, text):
        if self._current_anchor() is None:
            return
        if not self.isVisible():
            self.show_stream()
        if text:
            self._text = text
        self._resize()
        self._reposition()
        self.update()
        self._hide_timer.start(self._hide_ms(self._text))

    @staticmethod
    def _hide_ms(text):
        return max(MIN_HIDE_MS, min(MAX_HIDE_MS, 2000 + len(text or "") * 80))

    def hideEvent(self, event):
        self._follow_timer.stop()
        super().hideEvent(event)

    def _follow(self):
        if self.isVisible() and self._current_anchor() is not None:
            self._reposition()

    def _resize(self):
        metrics = QFontMetrics(self._font)
        rect = metrics.boundingRect(
            QRect(0, 0, MAX_WIDTH, 10000), Qt.TextWordWrap, self._text or " ")
        width = max(64, min(MAX_WIDTH, rect.width() + 4)) + PAD_X * 2
        height = rect.height() + PAD_Y * 2
        self.setFixedSize(width + MARGIN * 2, height + MARGIN * 2 + TAIL)

    def _reposition(self):
        anchor = self._current_anchor()
        if anchor is None:
            return
        try:
            geo = anchor.frameGeometry()
            screen = anchor.screen().availableGeometry()
        except Exception:
            return
        x = geo.center().x() - self.width() // 2
        y = geo.top() - self.height() + 4
        x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
        y = max(screen.top() + 4, y)
        self.move(QPoint(int(x), int(y)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(MARGIN, MARGIN, self.width() - MARGIN * 2,
                      self.height() - MARGIN * 2 - TAIL)

        painter.setPen(Qt.NoPen)
        for i in range(6, 0, -1):
            painter.setBrush(QColor(SHADOW.red(), SHADOW.green(), SHADOW.blue(), 7))
            painter.drawRoundedRect(rect.adjusted(-i, -i + 1, i, i + 1),
                                    RADIUS + i, RADIUS + i)

        path = QPainterPath()
        path.addRoundedRect(rect, RADIUS, RADIUS)
        tail = QPainterPath()
        tail.moveTo(rect.center().x() - 8, rect.bottom() - 1)
        tail.lineTo(rect.center().x(), rect.bottom() + TAIL)
        tail.lineTo(rect.center().x() + 8, rect.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, BUBBLE_TOP)
        gradient.setColorAt(1.0, BUBBLE_BOTTOM)
        painter.setBrush(gradient)
        painter.setPen(QPen(BUBBLE_BORDER, 1.2))
        painter.drawPath(path)

        painter.setPen(TEXT_COLOR)
        painter.setFont(self._font)
        text_rect = QRect(MARGIN + PAD_X, MARGIN + PAD_Y,
                          self.width() - MARGIN * 2 - PAD_X * 2, rect.height() - PAD_Y * 2)
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                         self._text)
