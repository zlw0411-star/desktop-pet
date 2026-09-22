from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

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

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(272)

        self.input = QLineEdit()
        self.input.setPlaceholderText("和我说点什么…")
        self.input.setFont(QFont("Microsoft YaHei UI", 9))
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

        row = QHBoxLayout(self)
        row.setContentsMargins(MARGIN + 6, MARGIN + 6, MARGIN + 6, MARGIN + TAIL + 4)
        row.setSpacing(6)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)

    def _submit(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)

    def popup_above(self, anchor):
        self.adjustSize()
        geo = anchor.frameGeometry()
        screen = anchor.screen().availableGeometry()
        x = geo.center().x() - self.width() // 2
        y = geo.top() - self.height() + 6
        x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
        y = max(screen.top() + 4, y)
        self.move(QPoint(int(x), int(y)))
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

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
        gradient.setColorAt(0.0, TOP)
        gradient.setColorAt(1.0, BOTTOM)
        painter.setBrush(gradient)
        painter.setPen(QPen(BORDER, 1.2))
        painter.drawPath(path)
