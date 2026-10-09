import json
import os

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkReply, QNetworkRequest)


class AIClient(QObject):
    """OpenAI 兼容接口客户端：流式输出 + 主/备模型自动降级。"""

    chunk = Signal(str)          # 增量文本
    reply_ready = Signal(str)    # 完整回复
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._manager = QNetworkAccessManager(self)
        self._history = []
        self._reply = None
        self._pending_text = ""
        self._models = []
        self._model_index = 0
        self._stream_buffer = b""
        self._stream_text = ""
        self._replied = False
        self._placeholder_timer = QTimer(self)
        self._placeholder_timer.setSingleShot(True)
        self._placeholder_timer.timeout.connect(lambda: self._placeholder(""))

    def is_configured(self):
        cfg = self.config["ai"]
        return bool(cfg.get("enabled") and cfg.get("base_url") and cfg.get("model"))

    def reset_history(self):
        self._history.clear()

    def _model_list(self):
        cfg = self.config["ai"]
        models = [cfg.get("model")]
        fallbacks = cfg.get("fallback_models") or []
        if isinstance(fallbacks, str):
            fallbacks = [m.strip() for m in fallbacks.split(",")]
        for name in fallbacks:
            if name and name not in models:
                models.append(name)
        return [m for m in models if m]

    def send(self, text, mood_line=""):
        text = (text or "").strip()
        if not text:
            return
        self._mood_line = mood_line or ""
        self.cancel()
        if not self.is_configured():
            self.busy_changed.emit(True)
            self._placeholder_timer.start(250)
            return
        self._pending_text = text
        self._history.append({"role": "user", "content": text})
        self._models = self._model_list()
        self._model_index = 0
        self._post_current()

    def _placeholder(self, text):
        self.busy_changed.emit(False)
        self.reply_ready.emit("我还没接入大脑呢，去设置里填上模型配置就能聊天啦～")

    def _current_model(self):
        if not self._models:
            self._models = self._model_list()
        if not self._models:
            return self.config["ai"].get("model", "")
        return self._models[min(self._model_index, len(self._models) - 1)]

    def _post_current(self):
        cfg = self.config["ai"]
        api_key = os.environ.get(cfg.get("api_key_env") or "", "").strip()
        if not api_key:
            self._discard_pending()
            self.busy_changed.emit(False)
            self.failed.emit("缺少 API Key：请设置环境变量 %s。" % cfg.get("api_key_env"))
            return

        self._stream_buffer = b""
        self._stream_text = ""
        self._replied = False
        self._mood_line = getattr(self, "_mood_line", "")

        prompt = cfg.get("system_prompt", "")
        if self._mood_line:
            prompt = (prompt + "\n" + self._mood_line).strip()
        messages = [{"role": "system", "content": prompt}]
        messages.extend(self._history[-int(cfg.get("max_history", 12)):])

        payload = {
            "model": self._current_model(),
            "messages": messages,
            "stream": True,
        }
        url = cfg.get("base_url").rstrip("/") + "/chat/completions"
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Authorization", ("Bearer " + api_key).encode("utf-8"))
        request.setRawHeader(b"Accept", b"text/event-stream")
        request.setTransferTimeout(int(cfg.get("timeout", 30)) * 1000)

        self.busy_changed.emit(True)
        self._reply = self._manager.post(request, json.dumps(payload).encode("utf-8"))
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.finished.connect(self._on_finished)

    def _on_ready_read(self):
        if self._reply is None:
            return
        self._stream_buffer += bytes(self._reply.readAll().data())
        while b"\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split(b"\n", 1)
            self._consume_line(line)

    def _consume_line(self, raw_line):
        line = raw_line.decode("utf-8", "replace").strip()
        if not line or not line.startswith("data:"):
            return
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            obj = json.loads(data)
        except ValueError:
            return
        choices = obj.get("choices") or []
        if not choices:
            return
        delta = choices[0].get("delta") or {}
        piece = delta.get("content")
        if piece:
            self._stream_text += piece
            self._replied = True
            self.chunk.emit(piece)

    def _on_finished(self):
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        self._stream_buffer += bytes(reply.readAll().data())
        for line in self._stream_buffer.split(b"\n"):
            self._consume_line(line)
        raw = self._stream_buffer
        error = reply.error()
        reply.deleteLater()

        if self._stream_text:
            self.busy_changed.emit(False)
            self._history.append({"role": "assistant", "content": self._stream_text})
            self._pending_text = ""
            limit = max(2, int(self.config["ai"].get("max_history", 12)))
            self._history = self._history[-limit:]
            self.reply_ready.emit(self._stream_text.strip())
            return

        if error != QNetworkReply.NoError or self._looks_like_error(raw):
            detail = self._error_detail(raw) or reply.errorString()
            if self._retry_next():
                return
            self.busy_changed.emit(False)
            self._discard_pending()
            self.failed.emit("请求失败：%s" % detail)
            return

        if self._retry_next():
            return
        self.busy_changed.emit(False)
        self._discard_pending()
        self.failed.emit("模型没有返回内容")

    def _retry_next(self):
        if self._model_index + 1 < len(self._models):
            self._model_index += 1
            self._post_current()
            return True
        return False

    @staticmethod
    def _looks_like_error(raw):
        text = raw.decode("utf-8", "replace").strip()
        return text.startswith("{") and '"error"' in text

    @staticmethod
    def _error_detail(raw):
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
            error = data.get("error")
            if isinstance(error, dict):
                return error.get("message") or str(error)
            if error:
                return str(error)
        except (ValueError, TypeError):
            pass
        return ""

    def _discard_pending(self):
        if self._pending_text and self._history and self._history[-1]["role"] == "user":
            self._history.pop()
        self._pending_text = ""

    def cancel(self):
        self._placeholder_timer.stop()
        self._discard_pending()
        reply = self._reply
        self._reply = None
        if reply is not None:
            try:
                reply.readyRead.disconnect(self._on_ready_read)
            except (TypeError, RuntimeError):
                pass
            try:
                reply.finished.disconnect(self._on_finished)
            except (TypeError, RuntimeError):
                pass
            reply.abort()
            reply.deleteLater()
        self.busy_changed.emit(False)
