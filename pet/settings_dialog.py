import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QImageReader, QMovie, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QMessageBox, QPushButton, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from . import animation, autostart
from .state_machine import PetState


class SettingsDialog(QDialog):
    settings_saved = Signal()
    image_requested = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setFont(QFont("Microsoft YaHei UI", 9))
        self.setWindowTitle("桌面宠物 · 设置")
        self.setMinimumSize(520, 520)
        self._image_path = str(config.get("image_path", "") or "")
        self._candidate_image = ""
        self._preview_movie = None

        tabs = QTabWidget()
        tabs.addTab(self._appearance_tab(), "形象")
        tabs.addTab(self._behaviour_tab(), "行为")
        tabs.addTab(self._chat_tab(), "聊天")
        tabs.currentChanged.connect(lambda index: self._refresh_preview() if index == 0
                                    else self._stop_preview_movie())
        self.tabs = tabs
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self._refresh_preview()

    def _appearance_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        group = QGroupBox("形象预览")
        form = QFormLayout(group)
        self.style_combo = QComboBox()
        self.style_combo.addItem("Q版少女", "girl")
        self.style_combo.addItem("小幽灵", "ghost")
        self.style_combo.addItem("白色小人 (Doro 风)", "doro")
        self.style_combo.addItem("蓝色团子", "blob")
        self.style_combo.addItem("自定义图片", "image")
        index = self.style_combo.findData(self.config.get("style", "girl"))
        self.style_combo.setCurrentIndex(index if index >= 0 else 0)
        self.style_combo.currentIndexChanged.connect(self._refresh_preview)
        form.addRow("风格", self.style_combo)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(220, 220)
        self.preview.setStyleSheet("background:#f5f8fc;border:1px solid #dbe3ef;border-radius:14px;")
        form.addRow(self.preview)
        self.image_label = QLabel(self._image_label_text())
        self.image_label.setWordWrap(True)
        self.image_label.setStyleSheet("color:#536579")
        self.image_btn = QPushButton("选择图片…")
        self.image_btn.clicked.connect(self._pick_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_btn)
        image_row.addWidget(self.image_label, 1)
        form.addRow("图片 / GIF", image_row)
        self.cutout_cb = QCheckBox("静态图片导入时自动抠图")
        self.cutout_cb.setChecked(bool(self.config.get("auto_cutout", True)))
        form.addRow(self.cutout_cb)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.5, 2.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(float(self.config.get("scale", 1.0)))
        form.addRow("大小", self.scale_spin)
        outer.addWidget(group)
        outer.addStretch(1)
        return tab

    def _behaviour_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        group = QGroupBox("行为")
        form = QFormLayout(group)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 200)
        self.speed_spin.setSuffix(" px/s")
        self.speed_spin.setValue(int(self.config.get("walk_speed", 60)))
        form.addRow("移动速度", self.speed_spin)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(10, 60)
        self.fps_spin.setSuffix(" FPS")
        self.fps_spin.setValue(int(self.config.get("fps", 30)))
        self.fps_spin.setToolTip("调低可减少资源占用；待机和睡眠会自动使用更低帧率。")
        form.addRow("动画帧率上限", self.fps_spin)
        self.wander_cb = QCheckBox("允许自由走动")
        self.wander_cb.setChecked(bool(self.config.get("wander", True)))
        form.addRow(self.wander_cb)
        self.follow_cb = QCheckBox("跟随鼠标")
        self.follow_cb.setChecked(bool(self.config.get("follow_cursor", False)))
        form.addRow(self.follow_cb)
        self.sleep_cb = QCheckBox("会犯困睡觉")
        self.sleep_cb.setChecked(bool(self.config.get("sleep_enabled", True)))
        form.addRow(self.sleep_cb)
        self.focus_cb = QCheckBox("专注模式（减少走动和主动搭话）")
        self.focus_cb.setChecked(bool(self.config.get("focus_mode", False)))
        form.addRow(self.focus_cb)
        self.top_cb = QCheckBox("总在最前")
        self.top_cb.setChecked(bool(self.config.get("always_on_top", True)))
        form.addRow(self.top_cb)
        self.autostart_cb = QCheckBox("开机自动启动")
        self.autostart_cb.setChecked(autostart.is_enabled())
        form.addRow(self.autostart_cb)
        outer.addWidget(group)
        outer.addStretch(1)
        return tab

    def _chat_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        ai = QGroupBox("聊天与人设")
        form = QFormLayout(ai)
        ai_cfg = self.config.get("ai", {})
        self.proactive_cb = QCheckBox("允许宠物主动搭话")
        self.proactive_cb.setChecked(bool(self.config.get("proactive_chat_enabled", True)))
        form.addRow(self.proactive_cb)
        self.ai_enabled_cb = QCheckBox("启用 AI 对话")
        self.ai_enabled_cb.setChecked(bool(ai_cfg.get("enabled", False)))
        form.addRow(self.ai_enabled_cb)
        self.base_url_edit = QLineEdit(ai_cfg.get("base_url", ""))
        self.base_url_edit.setPlaceholderText("https://open.bigmodel.cn/api/paas/v4")
        form.addRow("Base URL", self.base_url_edit)
        self.model_edit = QLineEdit(ai_cfg.get("model", ""))
        self.model_edit.setPlaceholderText("glm-4-flash")
        form.addRow("模型", self.model_edit)
        self.fallback_edit = QLineEdit(", ".join(ai_cfg.get("fallback_models", [])))
        self.fallback_edit.setPlaceholderText("主模型失败时依次尝试，逗号分隔")
        form.addRow("备用模型", self.fallback_edit)
        self.key_env_edit = QLineEdit(ai_cfg.get("api_key_env", "DESKTOP_PET_API_KEY"))
        form.addRow("API Key 环境变量", self.key_env_edit)
        self.prompt_edit = QPlainTextEdit(ai_cfg.get("system_prompt", ""))
        self.prompt_edit.setPlaceholderText("你是一只可爱的桌面宠物…")
        self.prompt_edit.setFixedHeight(100)
        form.addRow("人设", self.prompt_edit)
        outer.addWidget(ai)
        outer.addStretch(1)
        return tab

    def _image_label_text(self):
        path = self._candidate_image or self._image_path
        return os.path.basename(path) if path else "未选择图片"

    def _stop_preview_movie(self):
        if self._preview_movie is not None:
            self._preview_movie.stop()
            self._preview_movie.deleteLater()
            self._preview_movie = None

    def _refresh_preview(self, *_):
        self._stop_preview_movie()
        style = self.style_combo.currentData()
        if style == "image":
            path = self._candidate_image or self._image_path
            if path and os.path.isfile(path):
                if path.lower().endswith(".gif"):
                    movie = QMovie(path)
                    if movie.isValid():
                        frame = movie.currentPixmap()
                        if frame.isNull():
                            movie.jumpToFrame(0)
                            frame = movie.currentPixmap()
                        if not frame.isNull():
                            movie.setScaledSize(frame.size().scaled(200, 200, Qt.KeepAspectRatio))
                        movie.frameChanged.connect(self._show_movie_frame)
                        self._preview_movie = movie
                        movie.start()
                        return
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    self.preview.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                         Qt.SmoothTransformation))
                    return
            self.preview.setText("请选择一张图片或 GIF")
            return
        pm = animation.render_frame(200, PetState.IDLE, 0.3, 1, style=style)
        self.preview.setPixmap(pm)

    def _show_movie_frame(self, _frame):
        if self._preview_movie is None:
            return
        pixmap = self._preview_movie.currentPixmap()
        if not pixmap.isNull():
            self.preview.setPixmap(pixmap)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择宠物形象图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if path:
            self._candidate_image = path
            self.image_label.setText(self._image_label_text())
            self.style_combo.setCurrentIndex(self.style_combo.findData("image"))
            self._refresh_preview()

    def accept(self):
        cfg = self.config
        selected_style = self.style_combo.currentData()
        candidate = self._candidate_image or self._image_path
        if selected_style == "image" and not candidate:
            QMessageBox.warning(self, "选择图片", "请先选择一张有效的图片或 GIF。")
            return
        if selected_style == "image":
            reader = QImageReader(candidate)
            if not reader.canRead() or reader.read().isNull():
                QMessageBox.warning(self, "图片无法读取", "无法读取这张图片，请换一个文件再试。")
                return
        # A newly selected image becomes active only when the shared app
        # import/cutout pipeline succeeds.
        if not self._candidate_image or selected_style != "image":
            cfg["style"] = selected_style
        cfg["auto_cutout"] = self.cutout_cb.isChecked()
        cfg["scale"] = round(float(self.scale_spin.value()), 2)
        cfg["walk_speed"] = float(self.speed_spin.value())
        cfg["fps"] = self.fps_spin.value()
        cfg["wander"] = self.wander_cb.isChecked()
        cfg["follow_cursor"] = self.follow_cb.isChecked()
        cfg["sleep_enabled"] = self.sleep_cb.isChecked()
        cfg["focus_mode"] = self.focus_cb.isChecked()
        cfg["proactive_chat_enabled"] = self.proactive_cb.isChecked()
        cfg["always_on_top"] = self.top_cb.isChecked()

        ai = cfg.get("ai", {})
        ai["enabled"] = self.ai_enabled_cb.isChecked()
        ai["base_url"] = self.base_url_edit.text().strip()
        ai["model"] = self.model_edit.text().strip()
        ai["fallback_models"] = [m.strip() for m in self.fallback_edit.text().split(",") if m.strip()]
        ai["api_key_env"] = self.key_env_edit.text().strip() or "DESKTOP_PET_API_KEY"
        prompt = self.prompt_edit.toPlainText().strip()
        if prompt:
            ai["system_prompt"] = prompt
        cfg["ai"] = ai

        desired_autostart = self.autostart_cb.isChecked()
        current_autostart = autostart.is_enabled()
        if desired_autostart != current_autostart:
            autostart.set_enabled(desired_autostart)
        actual_autostart = autostart.is_enabled()
        cfg["autostart"] = actual_autostart
        cfg.save()
        self.settings_saved.emit()
        if self._candidate_image and selected_style == "image":
            self.image_requested.emit(self._candidate_image)
        self._stop_preview_movie()
        super().accept()
        if actual_autostart != desired_autostart:
            QMessageBox.information(self.parentWidget(), "开机启动", "系统未能应用开机启动设置，请检查系统权限。")

    def hideEvent(self, event):
        self._stop_preview_movie()
        super().hideEvent(event)

    def reject(self):
        self._stop_preview_movie()
        super().reject()
