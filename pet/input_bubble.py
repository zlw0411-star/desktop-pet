from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

TOP = QColor(255, 255, 255, 250)
BOTTOM = QColor(238, 246, 255, 250)
BORDER = QColor(196, 220, 238)
SHADOW = QColor(46, 74, 110)
ACCENT = QColor(93, 178, 232)
ACCENT_HOVER = QColor(74, 163, 221)

MARGIN = 8
TAIL = 9
RADIUS = 15


class InputBubble(QWidget):
    """宠物旁的迷你输入气泡（只有输入框 + 发送）。"""

    submitted = Signal(str)
    closed = Signal()
    stop_requested = Signal()
    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(272)
        self._anchor = None
        self._side = "right"
        self._busy = False
        self._mode = "send"
        self._can_retry = False
        self._mode_label_text = "AI"

        self.input = QLineEdit()
        self.input.setPlaceholderText("和我说点什么…")
        self.input.setFont(QFont("Microsoft YaHei UI", 9))
        self.input.setMinimumWidth(100)
        self.input.setMinimumHeight(30)
        self.input.setStyleSheet(
            "QLineEdit{border:1px solid #cfe3f2;border-radius:15px;padding:4px 12px;"
            "background:#f7fbff;color:#2b3a4a;}"
            "QLineEdit:focus{border:1px solid #8ec7ea;background:#ffffff;}")
        self.input.returnPressed.connect(self._submit)

        self.send_btn = QPushButton("发送")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setMinimumHeight(30)
        self.send_btn.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        self.send_btn.setStyleSheet(
            "QPushButton{border:none;border-radius:15px;padding:4px 14px;"
            "background:%s;color:white;}"
            "QPushButton:hover{background:%s;}" % (ACCENT.name(), ACCENT_HOVER.name()))
        self.send_btn.clicked.connect(self._submit)

        self.retry_btn = QPushButton("重试")
        self.retry_btn.setCursor(Qt.PointingHandCursor)
        self.retry_btn.setMinimumHeight(30)
        self.retry_btn.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        self.retry_btn.setStyleSheet("QPushButton{border:1px solid #b9d9ed;border-radius:15px;padding:4px 8px;background:#f7fbff;color:#438ab5;} QPushButton:hover{background:#eaf6ff;}")
        self.retry_btn.clicked.connect(self.retry_requested)
        self.retry_btn.hide()
        self.status_label = QLabel("AI · 就绪")
        self.status_label.setFont(QFont("Microsoft YaHei UI", 8))
        self.status_label.setStyleSheet("color:#648198;padding-left:4px;")

        outer = QVBoxLayout(self)
        self._outer = outer
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._row = QHBoxLayout()
        self._row.setSpacing(6)
        self._row.addWidget(self.input, 1)
        self._row.addWidget(self.send_btn)
        self._row.addWidget(self.retry_btn)
        self._row.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.status_label, 0)
        outer.addLayout(self._row)
        self._apply_margins()

        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(220)
        self._follow_timer.timeout.connect(self._follow)

    def _apply_margins(self):
        pad = MARGIN + 6
        extra = MARGIN + TAIL + 4
        if self._side == "left":
            self._outer.setContentsMargins(pad, pad, extra, pad)
        elif self._side == "bottom":
            self._outer.setContentsMargins(pad, pad, pad, extra + 2)
        else:
            self._outer.setContentsMargins(extra, pad, pad, pad)

    def _submit(self):
        if self._busy:
            self.stop_requested.emit()
            return
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)
        self.input.setFocus()

    def set_busy(self, busy):
        self._busy = bool(busy)
        self.send_btn.setText("停止" if self._busy else "发送")
        self.input.setEnabled(True)

    def set_mode(self, mode):
        self._mode = str(mode or "send")
        self._mode_label_text = {"offline": "本地模式", "ai": "AI 模式"}.get(self._mode, self._mode)
        self.status_label.setText("%s · %s" % (self._mode_label_text, "正在回复…" if self._busy else "就绪"))
        self.send_btn.setText("停止" if self._busy else "发送")

    def set_status(self, status, can_retry=False):
        self._can_retry = bool(can_retry)
        if status == "failed" and self._can_retry:
            self._mode = "retry"
        elif status in ("complete", "stopped", "waiting", "streaming"):
            self._mode = "send"
        self.set_busy(status in ("waiting", "streaming"))
        label = {
            "waiting": "等待回复…", "streaming": "正在回复…",
            "complete": "就绪", "stopped": "已停止", "failed": "回复失败",
        }.get(status, str(status))
        if status == "failed" and self._can_retry:
            label += " · 可重试"
        self.status_label.setText("%s · %s" % (self._mode_label_text, label))
        self.retry_btn.setVisible(status == "failed" and self._can_retry)
        self.adjustSize()

    def popup_beside(self, anchor):
        self._anchor = anchor
        self._place()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self._follow_timer.start()

    def _follow(self):
        if self.isVisible() and self._anchor is not None:
            self._place()

    def _place(self):
        if self._anchor is None:
            return
        try:
            geo = self._anchor.frameGeometry()
            screen = self._anchor.screen().availableGeometry()
        except Exception:
            return

        prev = self._side
        gap = 4
        y = geo.center().y() - 24
        right_x = geo.right() - 6
        left_space = geo.left() - screen.left()
        right_space = screen.right() - geo.right()
        below_space = screen.bottom() - geo.bottom()

        if right_space >= self.width() + gap:
            self._side = "right"
        elif left_space >= self.width() + gap:
            self._side = "left"
        elif below_space >= 56:
            self._side = "bottom"
        else:
            self._side = "right"

        if self._side != prev:
            self._apply_margins()
        self.adjustSize()

        w, h = self.width(), self.height()
        if self._side == "right":
            x = right_x
            y = geo.center().y() - h // 2
        elif self._side == "left":
            x = geo.left() - w + 6
            y = geo.center().y() - h // 2
        else:
            x = geo.center().x() - w // 2
            y = geo.bottom() - 8

        x = max(screen.left() + 4, min(x, screen.right() - w - 4))
        y = max(screen.top() + 4, min(y, screen.bottom() - h - 4))
        self.move(QPoint(int(x), int(y)))
        self.update()

    def hideEvent(self, event):
        self._follow_timer.stop()
        self.closed.emit()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._side == "left":
            rect = QRectF(MARGIN, MARGIN, self.width() - MARGIN * 2 - TAIL,
                          self.height() - MARGIN * 2)
        elif self._side == "bottom":
            rect = QRectF(MARGIN, MARGIN, self.width() - MARGIN * 2,
                          self.height() - MARGIN * 2 - TAIL)
        else:
            rect = QRectF(MARGIN + TAIL, MARGIN, self.width() - MARGIN * 2 - TAIL,
                          self.height() - MARGIN * 2)

        painter.setPen(Qt.NoPen)
        for i in range(6, 0, -1):
            painter.setBrush(QColor(SHADOW.red(), SHADOW.green(), SHADOW.blue(), 7))
            painter.drawRoundedRect(rect.adjusted(-i, -i + 1, i, i + 1),
                                    RADIUS + i, RADIUS + i)

        path = QPainterPath()
        path.addRoundedRect(rect, RADIUS, RADIUS)
        tail = QPainterPath()
        cy = rect.center().y()
        if self._side == "left":
            tail.moveTo(rect.right() - 1, cy - 8)
            tail.lineTo(rect.right() + TAIL, cy)
            tail.lineTo(rect.right() - 1, cy + 8)
        elif self._side == "bottom":
            tail.moveTo(rect.center().x() - 8, rect.bottom() - 1)
            tail.lineTo(rect.center().x(), rect.bottom() + TAIL)
            tail.lineTo(rect.center().x() + 8, rect.bottom() - 1)
        else:
            tail.moveTo(rect.left() + 1, cy - 8)
            tail.lineTo(rect.left() - TAIL, cy)
            tail.lineTo(rect.left() + 1, cy + 8)
        tail.closeSubpath()
        path = path.united(tail)

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, TOP)
        gradient.setColorAt(1.0, BOTTOM)
        painter.setBrush(gradient)
        painter.setPen(QPen(BORDER, 1.2))
        painter.drawPath(path)
