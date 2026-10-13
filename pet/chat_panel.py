"""A small, session-only chat transcript window."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QTextOption
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QPushButton, QScrollArea,
                               QTextEdit, QVBoxLayout, QWidget)


class _TranscriptText(QTextEdit):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setFont(QFont("Microsoft YaHei UI", 9))
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAnywhere)
        self.document().setDefaultTextOption(option)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setMinimumWidth(0)
        self.setFrameStyle(0)
        self.setPlainText(text)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_height)
        self.textChanged.connect(self._schedule_fit)
        self._schedule_fit()

    def _schedule_fit(self):
        self._fit_timer.start(0)

    def _fit_height(self):
        width = max(1, self.viewport().width())
        self.document().setTextWidth(width)
        height = self.document().documentLayout().documentSize().height()
        self.setFixedHeight(max(24, int(height + 10)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_fit()


class ChatPanel(QDialog):
    clear_requested = Signal()
    MAX_TURNS = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("聊天记录")
        self.resize(390, 480)
        self.turns = []
        self._active = None
        self._rows = {}
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._do_scroll)
        self._root = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._messages = QVBoxLayout(self._content)
        self._messages.addStretch(1)
        self._scroll.setWidget(self._content)
        self._root.addWidget(self._scroll, 1)
        controls = QHBoxLayout()
        self.copy_button = QPushButton("复制")
        self.clear_button = QPushButton("清空")
        controls.addStretch(1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.clear_button)
        self._root.addLayout(controls)
        self.copy_button.clicked.connect(self.copy_transcript)
        self.clear_button.clicked.connect(self.clear)

    def begin_turn(self, text):
        turn = {"user": str(text or ""), "reply": "", "status": "waiting"}
        self.turns.append(turn)
        self._active = turn
        self._add_row(turn)
        while len(self.turns) > self.MAX_TURNS:
            old = self.turns.pop(0)
            self._remove_row(old)
        self._scroll_to_bottom()

    def append_reply(self, delta):
        if self._active is None:
            return
        self._active["reply"] += str(delta or "")
        self._active["status"] = "streaming"
        self._update_reply(self._active)

    def set_reply(self, text, status="complete"):
        if self._active is None:
            return
        self._active["reply"] = str(text or "")
        self._active["status"] = status
        self._update_reply(self._active)

    def clear(self):
        self._scroll_timer.stop()
        self.turns.clear()
        self._active = None
        while self._messages.count() > 1:
            item = self._messages.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._rows.clear()
        self.clear_requested.emit()

    def _new_label(self, text=""):
        return _TranscriptText(text)

    def _add_row(self, turn):
        user = self._new_label("你：" + turn["user"])
        reply = self._new_label()
        self._messages.insertWidget(self._messages.count() - 1, user)
        self._messages.insertWidget(self._messages.count() - 1, reply)
        self._rows[id(turn)] = (user, reply)
        self._update_reply(turn)

    def _remove_row(self, turn):
        for widget in self._rows.pop(id(turn), ()):
            self._messages.removeWidget(widget)
            widget.deleteLater()

    def _update_reply(self, turn):
        row = self._rows.get(id(turn))
        if not row:
            return
        label = row[1]
        statuses = {"waiting": "（等待回复）", "streaming": "（回复中）",
                    "stopped": "（已停止）", "interrupted": "（已中断）",
                    "failed": "（回复失败）"}
        status = statuses.get(turn["status"], "")
        if turn["reply"] or status:
            label.setPlainText("宠物%s：%s" % (status, turn["reply"]))
            label.show()
        else:
            label.hide()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self._scroll_timer.start(0)

    def _do_scroll(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def closeEvent(self, event):
        self._scroll_timer.stop()
        super().closeEvent(event)

    def copy_transcript(self):
        from PySide6.QtWidgets import QApplication
        lines = []
        for turn in self.turns:
            lines.append("你：" + turn["user"])
            if turn["reply"]:
                status = {"stopped": "（已停止）", "interrupted": "（已中断）",
                          "failed": "（回复失败）"}.get(turn["status"], "")
                lines.append("宠物%s：%s" % (status, turn["reply"]))
        QApplication.clipboard().setText("\n".join(lines))
