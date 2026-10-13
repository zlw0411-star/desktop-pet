from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .state_machine import PetState
from . import animation


class TrayManager(QObject):
    action_triggered = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.icon = QSystemTrayIcon(self._make_icon(), parent)
        self.icon.setToolTip("桌面宠物")

        menu = QMenu()
        self.show_action = QAction("隐藏宠物", menu)
        self.show_action.triggered.connect(lambda: self.action_triggered.emit("toggle"))
        menu.addAction(self.show_action)

        chat_action = QAction("聊聊天", menu)
        chat_action.triggered.connect(lambda: self.action_triggered.emit("chat"))
        menu.addAction(chat_action)

        image_action = QAction("更换形象… (或把图片拖到宠物身上)", menu)
        image_action.triggered.connect(lambda: self.action_triggered.emit("change_image"))
        menu.addAction(image_action)

        settings_action = QAction("设置…", menu)
        settings_action.triggered.connect(lambda: self.action_triggered.emit("settings"))
        menu.addAction(settings_action)

        self.autostart_action = QAction("开机自动启动", menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(bool(config.get("autostart", False)))
        self.autostart_action.toggled.connect(
            lambda checked: self.action_triggered.emit("autostart:" + ("1" if checked else "0")))
        menu.addAction(self.autostart_action)

        self.focus_action = QAction("专注模式", menu)
        self.focus_action.setCheckable(True)
        self.focus_action.setChecked(bool(config.get("focus_mode", False)))
        self.focus_action.toggled.connect(
            lambda checked: self.action_triggered.emit("focus_mode:" + ("1" if checked else "0")))
        menu.addAction(self.focus_action)

        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(lambda: self.action_triggered.emit("quit"))
        menu.addAction(quit_action)

        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)

    def _make_icon(self):
        style = self.config.get("style", "blob")
        pm = animation.render_frame(64, PetState.IDLE, 0.0, 1, style=style)
        return QIcon(pm)

    def refresh_icon(self):
        style = self.config.get("style", "blob")
        pm = None
        if style == "image":
            from .sprite import ImageSprite

            sprite = ImageSprite(self.config.get("image_path", ""))
            if sprite.valid:
                pm = sprite.render(64, PetState.IDLE, 0.0, 1)
            sprite.stop()
        if pm is None or pm.isNull():
            pm = animation.render_frame(64, PetState.IDLE, 0.0, 1, style=style)
        self.icon.setIcon(QIcon(pm))

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.action_triggered.emit("toggle")

    def set_pet_visible(self, visible):
        self.show_action.setText("隐藏宠物" if visible else "显示宠物")

    def set_autostart(self, enabled):
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(enabled)
        self.autostart_action.blockSignals(False)

    def set_focus_mode(self, enabled):
        self.focus_action.blockSignals(True)
        self.focus_action.setChecked(bool(enabled))
        self.focus_action.blockSignals(False)

    def show(self):
        self.icon.show()

    def show_message(self, title, message):
        self.icon.showMessage(title, message, QSystemTrayIcon.Information, 2000)
