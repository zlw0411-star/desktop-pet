from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                               QVBoxLayout)

from . import autostart
from .assets import import_image
from .voice import rvc as rvc_mod


class SettingsDialog(QDialog):
    settings_saved = Signal()
    voice_test_requested = Signal()

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

        voice = QGroupBox("语音")
        v_form = QFormLayout(voice)
        self.voice_cb = QCheckBox("让宠物说话 (TTS)")
        self.voice_cb.setChecked(bool((config.get("voice") or {}).get("enabled", True)))
        v_form.addRow(self.voice_cb)

        rcfg = config.get("rvc", {}) or {}
        rvc = QGroupBox("RVC 音色（用 RVCMAX 的模型说话）")
        r_form = QFormLayout(rvc)
        self.rvc_cb = QCheckBox("启用 RVC 音色")
        self.rvc_cb.setChecked(bool(rcfg.get("enabled", False)))
        r_form.addRow(self.rvc_cb)

        self.rvc_root_edit = QLineEdit(rcfg.get("root", ""))
        r_form.addRow("RVCMAX 目录", self.rvc_root_edit)

        self.rvc_model_combo = QComboBox()
        self.rvc_model_combo.setEditable(True)
        self.rvc_model_combo.setInsertPolicy(QComboBox.NoInsert)
        self._reload_models(rcfg.get("model_name", ""))
        model_row = QHBoxLayout()
        model_row.addWidget(self.rvc_model_combo, 1)
        self.rvc_open_btn = QPushButton("打开文件夹")
        self.rvc_open_btn.clicked.connect(self._open_models_dir)
        model_row.addWidget(self.rvc_open_btn)
        r_form.addRow("模型文件", model_row)

        self.rvc_index_edit = QLineEdit(rcfg.get("index_path", ""))
        self.rvc_index_edit.setPlaceholderText("可留空")
        r_form.addRow("索引文件", self.rvc_index_edit)
        self.rvc_model_combo.currentTextChanged.connect(self._sync_index)

        self.rvc_pitch_spin = QSpinBox()
        self.rvc_pitch_spin.setRange(-24, 24)
        self.rvc_pitch_spin.setValue(int(rcfg.get("f0up_key", 0)))
        r_form.addRow("变调 (半音)", self.rvc_pitch_spin)

        self.rvc_method_combo = QComboBox()
        for label, value in (("rmvpe (推荐)", "rmvpe"), ("harvest", "harvest"),
                             ("crepe", "crepe"), ("pm", "pm")):
            self.rvc_method_combo.addItem(label, value)
        mi = self.rvc_method_combo.findData(rcfg.get("f0method", "rmvpe"))
        self.rvc_method_combo.setCurrentIndex(mi if mi >= 0 else 0)
        r_form.addRow("音高算法", self.rvc_method_combo)

        self.rvc_test_btn = QPushButton("测试语音")
        self.rvc_test_btn.clicked.connect(self.voice_test_requested.emit)
        r_form.addRow(self.rvc_test_btn)

        ai = QGroupBox("AI 对话（留空则使用占位回复）")
        a_form = QFormLayout(ai)
        ai_cfg = config.get("ai", {}) or {}
        self.ai_enabled_cb = QCheckBox("启用 AI 对话")
        self.ai_enabled_cb.setChecked(bool(ai_cfg.get("enabled", False)))
        a_form.addRow(self.ai_enabled_cb)

        self.base_url_edit = QLineEdit(ai_cfg.get("base_url", ""))
        self.base_url_edit.setPlaceholderText("https://api.deepseek.com/v1")
        a_form.addRow("Base URL", self.base_url_edit)

        self.model_edit = QLineEdit(ai_cfg.get("model", ""))
        self.model_edit.setPlaceholderText("deepseek-chat")
        a_form.addRow("模型", self.model_edit)

        self.fallback_edit = QLineEdit(", ".join(ai_cfg.get("fallback_models", []) or []))
        self.fallback_edit.setPlaceholderText("主模型失败时依次尝试，逗号分隔")
        a_form.addRow("备用模型", self.fallback_edit)

        self.key_env_edit = QLineEdit(ai_cfg.get("api_key_env", "DESKTOP_PET_API_KEY"))
        a_form.addRow("API Key 环境变量", self.key_env_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(behaviour)
        layout.addWidget(voice)
        layout.addWidget(rvc)
        layout.addWidget(ai)
        layout.addWidget(buttons)

    def _image_label_text(self):
        if self._image_path:
            import os
            return os.path.basename(self._image_path)
        return "（未选择）"

    def _reload_models(self, current):
        self.rvc_model_combo.clear()
        names = [m["name"] for m in rvc_mod.list_models(self.config)]
        self.rvc_model_combo.addItems(names)
        if current:
            index = self.rvc_model_combo.findText(current)
            if index >= 0:
                self.rvc_model_combo.setCurrentIndex(index)
            else:
                self.rvc_model_combo.setEditText(current)

    def _open_models_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(rvc_mod.models_dir(self.config)))

    def _sync_index(self, name):
        path = rvc_mod.find_index(self.config, name)
        if path:
            self.rvc_index_edit.setText(path)

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
        cfg["wander"] = self.wander_cb.isChecked()
        cfg["follow_cursor"] = self.follow_cb.isChecked()
        cfg["sleep_enabled"] = self.sleep_cb.isChecked()
        cfg["always_on_top"] = self.top_cb.isChecked()
        cfg["autostart"] = self.autostart_cb.isChecked()

        voice = cfg.get("voice", {}) or {}
        voice["enabled"] = self.voice_cb.isChecked()
        cfg["voice"] = voice

        rvc = cfg.get("rvc", {}) or {}
        rvc["enabled"] = self.rvc_cb.isChecked()
        rvc["root"] = self.rvc_root_edit.text().strip()
        rvc["model_name"] = self.rvc_model_combo.currentText().strip()
        rvc["index_path"] = self.rvc_index_edit.text().strip()
        rvc["f0up_key"] = int(self.rvc_pitch_spin.value())
        rvc["f0method"] = self.rvc_method_combo.currentData()
        cfg["rvc"] = rvc

        ai = cfg.get("ai", {}) or {}
        ai["enabled"] = self.ai_enabled_cb.isChecked()
        ai["base_url"] = self.base_url_edit.text().strip()
        ai["model"] = self.model_edit.text().strip()
        ai["fallback_models"] = [m.strip() for m in self.fallback_edit.text().split(",")
                                 if m.strip()]
        ai["api_key_env"] = self.key_env_edit.text().strip() or "DESKTOP_PET_API_KEY"
        cfg["ai"] = ai

        cfg.save()
        autostart.set_enabled(cfg["autostart"])
        self.settings_saved.emit()
        super().accept()
