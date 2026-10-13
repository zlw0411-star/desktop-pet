import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QCoreApplication, QEvent, Qt
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pet.ai.client import AIClient
from pet.chat_panel import ChatPanel
from pet.config import Config
from pet.input_bubble import InputBubble
from pet.personality import Personality
from pet.speech_bubble import SpeechBubble

APP = QApplication.instance() or QApplication([])


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.config = Config(Path(self.folder.name) / "config.json")
        self.client = AIClient(self.config)

    def tearDown(self):
        self.client.deleteLater()
        self.folder.cleanup()

    def test_sse_chunks_split_across_reads(self):
        pieces = []
        self.client.chunk.connect(pieces.append)
        raw = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n'
        self.client._reply = Mock()
        self.client._reply.readAll.side_effect = [QByteArray(raw[:19]), QByteArray(raw[19:])]
        reply = self.client._reply
        self.client._on_ready_read(reply, self.client._generation)
        self.client._on_ready_read(reply, self.client._generation)
        self.assertEqual(pieces, ["hello"])
        self.assertEqual(self.client.partial_text, "hello")

    def test_non_string_sse_content_is_ignored(self):
        self.client._consume_line(b'data: {"choices":[{"delta":{"content":["bad"]}}]}')
        self.assertEqual(self.client.partial_text, "")

    def test_non_object_error_body_is_safe(self):
        self.assertEqual(self.client._error_detail(b"[]"), "")

    def test_partial_stream_failure_retains_text_without_model_fallback(self):
        self.client._models = ["primary", "backup"]
        self.client._pending_text = "question"
        self.client._pending_in_history = True
        self.client._history.append({"role": "user", "content": "question"})
        self.client._stream_text = "partial"
        self.client._reply = Mock()
        self.client._reply.readAll.return_value = QByteArray()
        self.client._reply.error.return_value = QNetworkReply.TimeoutError
        self.client._reply.errorString.return_value = "timeout"
        client_reply = self.client._reply
        failed, status = [], []
        self.client.failed.connect(failed.append)
        self.client.status_changed.connect(status.append)
        self.client._on_finished(client_reply, self.client._generation)
        self.assertEqual(self.client.partial_text, "partial")
        self.assertEqual(failed, ["请求中断：timeout"])
        self.assertEqual(status[-1], "failed")
        self.assertEqual(self.client._model_index, 0)
        self.assertEqual(self.client._history, [])

    def test_retry_after_partial_failure_adds_user_to_history_once(self):
        self.config["ai"].update({"enabled": True, "base_url": "https://example.invalid", "model": "one"})
        self.client._models = ["one"]
        self.client._pending_text = "question"
        self.client._pending_in_history = True
        self.client._history.append({"role": "user", "content": "question"})
        self.client._stream_text = "partial"
        self.client._finish_failed("interrupted", self.client._generation)
        self.assertEqual(self.client._history, [])
        self.client._post_current = Mock()
        self.client.send("question")
        self.assertEqual(self.client._history, [{"role": "user", "content": "question"}])
        self.client._post_current.assert_called_once()

    def test_sse_http_success_error_event_fails_even_after_delta(self):
        self.client._consume_line(b'data: {"choices":[{"delta":{"content":"part"}}]}')
        self.client._consume_line(b'data: {"error":{"message":"upstream failed"}}')
        self.client._models = ["primary"]
        self.client._pending_text = "q"
        self.client._pending_in_history = False
        self.client._reply = Mock()
        self.client._reply.readAll.return_value = QByteArray()
        self.client._reply.error.return_value = QNetworkReply.NoError
        self.client._reply.errorString.return_value = ""
        reply = self.client._reply
        errors = []
        self.client.failed.connect(errors.append)
        self.client._on_finished(reply, self.client._generation)
        self.assertEqual(self.client.partial_text, "part")
        self.assertTrue(errors and "upstream failed" in errors[0])

    def test_successful_stream_requires_end_marker(self):
        self.client._require_stream_end = True
        self.client._stream_text = "partial"
        self.client._models = ["primary"]
        self.client._reply = Mock()
        self.client._reply.readAll.return_value = QByteArray()
        self.client._reply.error.return_value = QNetworkReply.NoError
        self.client._reply.errorString.return_value = ""
        errors = []
        self.client.failed.connect(errors.append)
        self.client._on_finished(self.client._reply, self.client._generation)
        self.assertEqual(errors, ["请求中断：连接结束时回复尚未完成"])

    def test_stop_returns_partial_and_cancel_is_silent(self):
        self.client._stream_text = "part"
        reply = Mock()
        self.client._reply = reply
        statuses = []
        self.client.status_changed.connect(statuses.append)
        self.assertEqual(self.client.stop(), "part")
        self.assertEqual(statuses, ["stopped"])
        self.assertTrue(reply.abort.called)
        statuses.clear()
        self.client.cancel()
        self.assertEqual(statuses, [])

    def test_stale_finished_reply_cannot_complete_replacement(self):
        stale = Mock()
        replacement = Mock()
        self.client._reply = replacement
        ready = []
        self.client.reply_ready.connect(ready.append)
        self.client._on_finished(stale, self.client._generation - 1)
        self.assertEqual(ready, [])
        self.assertIs(self.client._reply, replacement)

    def test_no_content_error_retries_once_then_timeout_reports_failed(self):
        self.client._models = ["one", "two"]
        self.client._generation = 2
        self.client._reply = Mock()
        self.client._reply.readAll.return_value = QByteArray()
        self.client._reply.error.return_value = QNetworkReply.TimeoutError
        self.client._reply.errorString.return_value = "timeout"
        old = self.client._reply
        self.client._post_current = Mock()
        self.client._on_finished(old, 2)
        self.client._post_current.assert_called_once_with(2)
        self.assertEqual(self.client._model_index, 1)


class WidgetTests(unittest.TestCase):
    def test_busy_stop_keeps_draft_and_failed_retry_is_available(self):
        bubble = InputBubble()
        bubble.input.setText("draft")
        stopped, retried = [], []
        bubble.stop_requested.connect(lambda: stopped.append(True))
        bubble.retry_requested.connect(lambda: retried.append(True))
        bubble.set_status("streaming")
        self.assertTrue(bubble.input.isEnabled())
        bubble._submit()
        self.assertEqual(stopped, [True])
        self.assertEqual(bubble.input.text(), "draft")
        bubble.set_status("failed", can_retry=True)
        bubble.input.setText("new question")
        bubble._submit()
        self.assertEqual(retried, [])
        self.assertEqual(bubble.input.text(), "")
        bubble.input.setText("retry draft")
        bubble.retry_btn.click()
        self.assertEqual(retried, [True])
        self.assertEqual(bubble.input.text(), "retry draft")
        bubble.set_mode("offline")
        bubble.set_status("waiting")
        self.assertIn("本地模式", bubble.status_label.text())
        self.assertIn("等待", bubble.status_label.text())
        bubble.adjustSize()
        self.assertGreaterEqual(bubble.status_label.geometry().left(), 17)
        self.assertGreaterEqual(bubble.status_label.geometry().top(), 8)
        self.assertLessEqual(bubble.status_label.geometry().right(), bubble.width() - 8)
        self.assertLessEqual(bubble.status_label.geometry().bottom(), bubble.height() - 8)
        bubble.set_status("failed", can_retry=True)
        self.assertGreaterEqual(bubble.input.minimumWidth(), 100)
        self.assertFalse(bubble.retry_btn.isHidden())
        bubble.close()

    def test_speech_bubble_bounds_rendered_lines_but_keeps_full_reply(self):
        bubble = SpeechBubble()
        reply = "line\n" * 20 + "https://example.invalid/" + ("verylongpathsegment" * 30)
        bubble._text = reply
        bubble._resize()
        self.assertEqual(bubble._text, reply)
        self.assertLessEqual(bubble._display_line_count, 6)
        self.assertFalse(bubble._full_button.isHidden())
        self.assertLessEqual(bubble._full_button.geometry().bottom(), bubble.height() - 1)
        bubble.close()

    def test_speech_bubble_counts_explicit_newlines_as_lines(self):
        bubble = SpeechBubble()
        for reply in ("\n".join("line%d" % i for i in range(20)),
                      "\n" + "\n".join("line%d" % i for i in range(20)) + "\n"):
            bubble._text = reply
            bubble._resize()
            self.assertEqual(bubble._text, reply)
            self.assertEqual(bubble._display_line_count, 6)
            self.assertFalse(bubble._full_button.isHidden())
        bubble.close()

    def test_chat_panel_caps_turns_and_clear_emits_signal(self):
        panel = ChatPanel()
        panel.show()
        APP.processEvents()
        cleared = []
        panel.clear_requested.connect(lambda: cleared.append(True))
        panel.begin_turn("initial")
        active_id = id(panel._active)
        reply_widget = panel._rows[active_id][1]
        panel.append_reply("stream")
        self.assertIs(panel._rows[active_id][1], reply_widget)
        self.assertIn("stream", reply_widget.toPlainText())
        self.assertTrue(reply_widget.isReadOnly())
        self.assertEqual(reply_widget.font().family(), "Microsoft YaHei UI")
        self.assertTrue(reply_widget.textInteractionFlags() & Qt.TextSelectableByMouse)
        panel.set_reply("partial", "failed")
        self.assertIn("回复失败", reply_widget.toPlainText())
        long_url = "https://example.invalid/" + ("longsegment" * 100)
        reply_widget.setPlainText(long_url)
        APP.processEvents()
        self.assertLess(reply_widget.width(), 500)
        self.assertEqual(reply_widget.horizontalScrollBar().maximum(), 0)
        for i in range(22):
            panel.begin_turn(str(i))
            panel.set_reply("reply " + str(i))
        self.assertEqual(len(panel.turns), 20)
        self.assertEqual(panel.turns[0]["user"], "2")
        panel.clear()
        self.assertEqual(panel.turns, [])
        self.assertEqual(cleared, [True])
        panel.close()

    def test_pending_scroll_is_owned_by_panel_lifecycle(self):
        panel = ChatPanel()
        panel.begin_turn("pending timer")
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()


class PersonalityTests(unittest.TestCase):
    def test_offline_greetings_and_unknown_are_friendly(self):
        p = Personality({"mood": 60})
        self.assertTrue(p.offline_reply("你好"))
        self.assertTrue(p.offline_reply("谢谢"))
        self.assertTrue(p.offline_reply("一个新问题"))

    def test_action_commands_emit_action_without_success_line(self):
        p = Personality({"mood": 60})
        actions, speech = [], []
        p.act.connect(actions.append)
        p.say.connect(speech.append)
        self.assertTrue(p.try_command("跳舞"))
        self.assertEqual(actions, ["dance"])
        self.assertEqual(speech, [])

    def test_repeated_explicit_commands_get_acknowledgments(self):
        p = Personality({"mood": 60})
        replies = []
        p.say.connect(replies.append)
        p.try_command("心情")
        p.try_command("心情")
        self.assertEqual(len(replies), 2)

    def test_consecutive_offline_greetings_choose_different_lines(self):
        p = Personality({"mood": 60})
        first = p.offline_reply("你好")
        second = p.offline_reply("你好")
        self.assertNotEqual(first, second)

    def test_pause_and_focus_do_not_emit_proactive_action(self):
        p = Personality({"mood": 60, "proactive_chat_enabled": True})
        lines = []
        p.say.connect(lines.append)
        p._next_idle = 0
        p.set_paused(True)
        p.tick(False)
        self.assertEqual(lines, [])
        p.set_paused(False)
        p.config["focus_mode"] = True
        p._next_idle = 0
        p.tick(False)
        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
