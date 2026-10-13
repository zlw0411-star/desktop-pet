import json
import os

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class AIClient(QObject):
    """OpenAI-compatible streaming client with bounded in-memory history."""

    chunk = Signal(str)
    reply_ready = Signal(str)
    failed = Signal(str)
    busy_changed = Signal(bool)
    status_changed = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._manager = QNetworkAccessManager(self)
        self._history = []
        self._reply = None
        self._generation = 0
        self._stream_buffer = b""
        self._stream_text = ""
        self.partial_text = ""
        self._pending_text = ""
        self._pending_in_history = False
        self._models = []
        self._model_index = 0
        self._mood_line = ""
        self._require_stream_end = False
        self._saw_stream_end = False
        self._stream_error = ""
        self._placeholder_timer = QTimer(self)
        self._placeholder_timer.setSingleShot(True)
        self._placeholder_timer.timeout.connect(self._placeholder)

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
        if self._reply is not None or self._placeholder_timer.isActive():
            self.cancel()
        self._generation += 1
        self.partial_text = ""
        self._stream_text = ""
        self._stream_buffer = b""
        self._saw_stream_end = False
        self._stream_error = ""
        self._pending_text = text
        self._pending_in_history = False
        self._mood_line = mood_line or ""
        self._models = self._model_list()
        self._model_index = 0
        if not self.is_configured():
            self.busy_changed.emit(True)
            self.status_changed.emit("waiting")
            self._placeholder_timer.start(250)
            return
        self._history.append({"role": "user", "content": text})
        self._pending_in_history = True
        self._post_current(self._generation)

    def _placeholder(self):
        self._pending_text = ""
        self.busy_changed.emit(False)
        self.status_changed.emit("complete")
        self.reply_ready.emit("我还没接入大脑呢，去设置里填上模型配置就能聊天啦～")

    def _current_model(self):
        if not self._models:
            self._models = self._model_list()
        return self._models[min(self._model_index, len(self._models) - 1)] if self._models else ""

    def _post_current(self, generation=None):
        generation = self._generation if generation is None else generation
        if generation != self._generation:
            return
        cfg = self.config["ai"]
        api_key = os.environ.get(cfg.get("api_key_env") or "", "").strip()
        if not api_key:
            self._finish_failed("缺少 API Key：请设置环境变量 %s。" % cfg.get("api_key_env"), generation)
            return
        self._stream_buffer = b""
        self._stream_text = ""
        self.partial_text = ""
        self._saw_stream_end = False
        self._stream_error = ""
        self._require_stream_end = True
        prompt = cfg.get("system_prompt", "")
        if self._mood_line:
            prompt = (prompt + "\n" + self._mood_line).strip()
        messages = [{"role": "system", "content": prompt}]
        messages.extend(self._history[-int(cfg.get("max_history", 12)):])
        payload = {"model": self._current_model(), "messages": messages, "stream": True}
        request = QNetworkRequest(QUrl(cfg.get("base_url").rstrip("/") + "/chat/completions"))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Authorization", ("Bearer " + api_key).encode("utf-8"))
        request.setRawHeader(b"Accept", b"text/event-stream")
        request.setTransferTimeout(int(cfg.get("timeout", 30)) * 1000)
        self.busy_changed.emit(True)
        self.status_changed.emit("waiting")
        reply = self._manager.post(request, json.dumps(payload).encode("utf-8"))
        self._reply = reply
        reply.readyRead.connect(lambda r=reply, g=generation: self._on_ready_read(r, g))
        reply.finished.connect(lambda r=reply, g=generation: self._on_finished(r, g))

    def _on_ready_read(self, reply=None, generation=None):
        reply = reply or self._reply
        generation = self._generation if generation is None else generation
        if reply is None or generation != self._generation or reply is not self._reply:
            return
        self._stream_buffer += bytes(reply.readAll().data())
        while b"\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split(b"\n", 1)
            self._consume_line(line, generation)

    def _consume_line(self, raw_line, generation=None):
        generation = self._generation if generation is None else generation
        if generation != self._generation:
            return
        line = raw_line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            return
        data = line[5:].strip()
        if not data or data == "[DONE]":
            if data == "[DONE]":
                self._saw_stream_end = True
            return
        try:
            obj = json.loads(data)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        if obj.get("error"):
            err = obj["error"]
            self._stream_error = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            return
        choices = obj.get("choices") or []
        if not isinstance(choices, list) or (choices and not isinstance(choices[0], dict)):
            return
        choice = choices[0] if choices else {}
        if choice.get("finish_reason") is not None:
            self._saw_stream_end = True
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            return
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            self._stream_text += piece
            self.partial_text = self._stream_text
            self.status_changed.emit("streaming")
            self.chunk.emit(piece)

    def _on_finished(self, reply=None, generation=None):
        reply = reply or self._reply
        generation = self._generation if generation is None else generation
        if reply is None or generation != self._generation or reply is not self._reply:
            return
        self._stream_buffer += bytes(reply.readAll().data())
        for line in self._stream_buffer.split(b"\n"):
            self._consume_line(line, generation)
        raw = self._stream_buffer
        error = reply.error()
        error_string = reply.errorString()
        reply.deleteLater()
        self._reply = None
        if error != QNetworkReply.NoError or self._looks_like_error(raw) or self._stream_error:
            detail = self._stream_error or self._error_detail(raw) or error_string
            if self._stream_text:
                self._finish_failed("请求中断：%s" % detail, generation)
            elif self._retry_next(generation):
                return
            else:
                self._finish_failed("请求失败：%s" % detail, generation)
            return
        if self._stream_text:
            if self._require_stream_end and not self._saw_stream_end:
                self._finish_failed("请求中断：连接结束时回复尚未完成", generation)
                return
            self._complete(generation)
        elif self._retry_next(generation):
            return
        else:
            self._finish_failed("模型没有返回内容", generation)

    def _complete(self, generation):
        if generation != self._generation:
            return
        self.busy_changed.emit(False)
        self.status_changed.emit("complete")
        self._history.append({"role": "assistant", "content": self._stream_text})
        self._trim_history()
        self._pending_text = ""
        self._pending_in_history = False
        self.partial_text = self._stream_text
        self.reply_ready.emit(self._stream_text.strip())

    def _finish_failed(self, message, generation):
        if generation != self._generation:
            return
        self.busy_changed.emit(False)
        self.status_changed.emit("failed")
        self.partial_text = self._stream_text
        self._discard_pending()
        self.failed.emit(message)

    def _retry_next(self, generation=None):
        generation = self._generation if generation is None else generation
        if generation != self._generation or self._stream_text or self._model_index + 1 >= len(self._models):
            return False
        self._model_index += 1
        self._post_current(generation)
        return True

    @staticmethod
    def _looks_like_error(raw):
        text = raw.decode("utf-8", "replace").strip()
        return text.startswith("{") and '"error"' in text

    @staticmethod
    def _error_detail(raw):
        try:
            body = json.loads(raw.decode("utf-8", "replace"))
            if not isinstance(body, dict):
                return ""
            error = body.get("error")
            if isinstance(error, dict):
                return error.get("message") or str(error)
            if error:
                return str(error)
        except (ValueError, TypeError):
            pass
        return ""

    def _trim_history(self):
        limit = max(2, int(self.config["ai"].get("max_history", 12)))
        self._history = self._history[-limit:]

    def _discard_pending(self):
        if self._pending_in_history and self._pending_text:
            for i in range(len(self._history) - 1, -1, -1):
                entry = self._history[i]
                if entry.get("role") == "user" and entry.get("content") == self._pending_text:
                    self._history.pop(i)
                    break
        self._pending_text = ""
        self._pending_in_history = False

    def stop(self):
        """Stop the active request and return any streamed text."""
        partial = self._stream_text
        self._generation += 1
        self._placeholder_timer.stop()
        self._discard_pending()
        reply, self._reply = self._reply, None
        if reply is not None:
            for signal, slot in ((reply.readyRead, self._on_ready_read), (reply.finished, self._on_finished)):
                try:
                    signal.disconnect()
                except (TypeError, RuntimeError):
                    pass
            reply.abort()
            reply.deleteLater()
        self.partial_text = partial
        self.busy_changed.emit(False)
        self.status_changed.emit("stopped")
        return partial

    def cancel(self):
        """Silently cancel as a lifecycle operation."""
        self._generation += 1
        self._placeholder_timer.stop()
        self._discard_pending()
        reply, self._reply = self._reply, None
        if reply is not None:
            try:
                reply.abort()
                reply.deleteLater()
            except RuntimeError:
                pass
        self.busy_changed.emit(False)
