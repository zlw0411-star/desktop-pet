from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import QPushButton, QWidget

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

    full_reply_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._text = ""
        self._display_text = ""
        self._display_layout = None
        self._display_line_count = 0
        self._anchor = None
        self._anchor_getter = None
        self._font = QFont("Microsoft YaHei UI", 9)
        self._full_button = QPushButton("查看完整回复", self)
        self._full_button.setCursor(Qt.PointingHandCursor)
        self._full_button.setStyleSheet("QPushButton{border:0;background:transparent;color:#438ab5;font-size:9pt;text-align:right;} QPushButton:hover{text-decoration:underline;}")
        self._full_button.clicked.connect(self.full_reply_requested)
        self._full_button.hide()
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
        self._display_text = ""
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
        width = MAX_WIDTH
        text_width = width - PAD_X * 2 - 4

        def make_layout(text):
            layout = QTextLayout(text or " ", self._font)
            option = QTextOption()
            option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            layout.setTextOption(option)
            layout.beginLayout()
            lines = []
            y = 0.0
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(text_width)
                line.setPosition(QPointF(0, y))
                y += line.height()
                lines.append(line)
            layout.endLayout()
            return layout, lines

        layout_text = (self._text or " ").replace("\r\n", "\u2028").replace("\r", "\u2028").replace("\n", "\u2028")
        full_layout, full_lines = make_layout(layout_text)
        overflow = len(full_lines) > 6
        if overflow and full_lines:
            end = full_lines[5].textStart() + full_lines[5].textLength()
            prefix = layout_text[:end].rstrip(" \u2028")
            self._display_text = prefix + "…"
            self._display_layout, shown = make_layout(self._display_text)
            while len(shown) > 6 and prefix:
                prefix = prefix[:-1].rstrip()
                self._display_text = prefix + "…"
                self._display_layout, shown = make_layout(self._display_text)
        else:
            self._display_text = self._text
            self._display_layout, shown = full_layout, full_lines
        self._display_line_count = min(6, len(shown))
        self._full_button.setVisible(overflow)
        line_height = max([line.height() for line in shown] or [metrics.height()])
        height = max(metrics.height(), line_height * self._display_line_count) + PAD_Y * 2
        if overflow:
            height += 20
        width = max(64, min(MAX_WIDTH, width)) + PAD_X * 2
        self.setFixedSize(width + MARGIN * 2, height + MARGIN * 2 + TAIL)
        self._full_button.setGeometry(self.width() - 132, self.height() - TAIL - 24, 124, 18)

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
        y = max(screen.top() + 4, min(y, screen.bottom() - self.height() - 4))
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
        painter.save()
        painter.setClipRect(QRect(MARGIN + PAD_X, MARGIN + PAD_Y,
                                  self.width() - MARGIN * 2 - PAD_X * 2,
                                  max(0, int(rect.height()) - PAD_Y * 2 - (20 if self._full_button.isVisible() else 0))))
        if self._display_layout is not None:
            self._display_layout.draw(painter, QPointF(MARGIN + PAD_X, MARGIN + PAD_Y))
        painter.restore()
