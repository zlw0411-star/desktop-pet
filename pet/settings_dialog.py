from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSpinBox, QVBoxLayout)
from PySide6.QtCore import Signal

from . import autostart
from .assets import import_image


class SettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("桌面宠物 · 设置")
        self.setMinimumWidth(360)

        behaviour = QGroupBox("行为")
        b_form = QFormLayout(behaviour)

        self.style_combo = QComboBox()
        self.style_combo.addItem("Q版少女", "girl")
        self.style_combo.addItem("小幽灵", "ghost")
        self.style_combo.addItem("白色小人 (Doro 风)", "doro")
        self.style_combo.addItem("蓝色团子", "blob")
        self.style_combo.addItem("自定义图片", "image")
        current_style = config.get("style", "girl")
        index = self.style_combo.findData(current_style)
        self.style_combo.setCurrentIndex(index if index >= 0 else 0)
        b_form.addRow("形象", self.style_combo)

        self._image_path = config.get("image_path", "")
        image_row = QHBoxLayout()
        self.image_label = QLabel(self._image_label_text())
        self.image_label.setStyleSheet("color:#5a6b7a;font-size:11px;")
        self.image_btn = QPushButton("选择图片…")
        self.image_btn.clicked.connect(self._pick_image)
        image_row.addWidget(self.image_btn)
        image_row.addWidget(self.image_label, 1)
        b_form.addRow("图片", image_row)

        self.cutout_cb = QCheckBox("导入图片时自动抠图（去背景）")
        self.cutout_cb.setChecked(bool(config.get("auto_cutout", True)))
        b_form.addRow(self.cutout_cb)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.5, 2.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(float(config.get("scale", 1.0)))
        b_form.addRow("大小", self.scale_spin)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 200)
        self.speed_spin.setSuffix(" px/s")
        self.speed_spin.setValue(int(config.get("walk_speed", 60)))
        b_form.addRow("移动速度", self.speed_spin)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(10, 60)
        self.fps_spin.setSuffix(" FPS")
        self.fps_spin.setValue(int(config.get("fps", 30)))
        self.fps_spin.setToolTip("调低可减少资源占用；待机和睡眠会自动使用更低帧率。")
        b_form.addRow("动画帧率上限", self.fps_spin)

        self.wander_cb = QCheckBox("允许自由走动")
        self.wander_cb.setChecked(bool(config.get("wander", True)))
        b_form.addRow(self.wander_cb)

        self.follow_cb = QCheckBox("跟随鼠标")
        self.follow_cb.setChecked(bool(config.get("follow_cursor", False)))
        b_form.addRow(self.follow_cb)

        self.sleep_cb = QCheckBox("会犯困睡觉")
        self.sleep_cb.setChecked(bool(config.get("sleep_enabled", True)))
        b_form.addRow(self.sleep_cb)

        self.top_cb = QCheckBox("总在最前")
        self.top_cb.setChecked(bool(config.get("always_on_top", True)))
        b_form.addRow(self.top_cb)

        self.autostart_cb = QCheckBox("开机自动启动")
        self.autostart_cb.setChecked(autostart.is_enabled())
        b_form.addRow(self.autostart_cb)

        ai = QGroupBox("AI 对话")
        a_form = QFormLayout(ai)
        ai_cfg = config.get("ai", {}) or {}
        self.ai_enabled_cb = QCheckBox("启用 AI 对话")
        self.ai_enabled_cb.setChecked(bool(ai_cfg.get("enabled", False)))
        a_form.addRow(self.ai_enabled_cb)

        self.base_url_edit = QLineEdit(ai_cfg.get("base_url", ""))
        self.base_url_edit.setPlaceholderText("https://open.bigmodel.cn/api/paas/v4")
        a_form.addRow("Base URL", self.base_url_edit)

        self.model_edit = QLineEdit(ai_cfg.get("model", ""))
        self.model_edit.setPlaceholderText("glm-4-flash")
        a_form.addRow("模型", self.model_edit)

        self.fallback_edit = QLineEdit(", ".join(ai_cfg.get("fallback_models", []) or []))
        self.fallback_edit.setPlaceholderText("主模型失败时依次尝试，逗号分隔")
        a_form.addRow("备用模型", self.fallback_edit)

        self.key_env_edit = QLineEdit(ai_cfg.get("api_key_env", "DESKTOP_PET_API_KEY"))
        a_form.addRow("API Key 环境变量", self.key_env_edit)

        self.prompt_edit = QPlainTextEdit(ai_cfg.get("system_prompt", ""))
        self.prompt_edit.setPlaceholderText("你是一只可爱的桌面宠物…")
        self.prompt_edit.setFixedHeight(80)
        a_form.addRow("人设", self.prompt_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(behaviour)
        layout.addWidget(ai)
        layout.addWidget(buttons)

    def _image_label_text(self):
        if self._image_path:
            import os
            return os.path.basename(self._image_path)
        return "（未选择）"

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择宠物形象图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if not path:
            return
        stored = import_image(path)
        if stored:
            self._image_path = stored
            self.image_label.setText(self._image_label_text())
            index = self.style_combo.findData("image")
            if index >= 0:
                self.style_combo.setCurrentIndex(index)

    def accept(self):
        cfg = self.config
        cfg["style"] = self.style_combo.currentData()
        cfg["image_path"] = self._image_path
        cfg["auto_cutout"] = self.cutout_cb.isChecked()
        cfg["scale"] = round(float(self.scale_spin.value()), 2)
        cfg["walk_speed"] = float(self.speed_spin.value())
        cfg["fps"] = self.fps_spin.value()
        cfg["wander"] = self.wander_cb.isChecked()
        cfg["follow_cursor"] = self.follow_cb.isChecked()
        cfg["sleep_enabled"] = self.sleep_cb.isChecked()
        cfg["always_on_top"] = self.top_cb.isChecked()
        cfg["autostart"] = self.autostart_cb.isChecked()

        ai = cfg.get("ai", {}) or {}
        ai["enabled"] = self.ai_enabled_cb.isChecked()
        ai["base_url"] = self.base_url_edit.text().strip()
        ai["model"] = self.model_edit.text().strip()
        ai["fallback_models"] = [m.strip() for m in self.fallback_edit.text().split(",")
                                 if m.strip()]
        ai["api_key_env"] = self.key_env_edit.text().strip() or "DESKTOP_PET_API_KEY"
        prompt = self.prompt_edit.toPlainText().strip()
        if prompt:
            ai["system_prompt"] = prompt
        cfg["ai"] = ai

        cfg.save()
        autostart.set_enabled(cfg["autostart"])
        self.settings_saved.emit()
        super().accept()
