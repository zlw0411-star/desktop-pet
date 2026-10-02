import os
import random
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from . import win32util

IDLE_CHAT_MIN = 70
IDLE_CHAT_MAX = 140
NEGLECT_SEC = 480
SLACK_SEC = 900


class Personality(QObject):
    say = Signal(str)
    act = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.mood = int(config.get("mood", 60))
        self._last_touch = time.monotonic()
        self._next_idle = time.monotonic() + random.uniform(IDLE_CHAT_MIN, IDLE_CHAT_MAX)
        self._combo = 0
        self._combo_at = 0.0
        self._muted_until = 0.0
        self._neglect_said = False
        self._slack_said = False
        self.last_hwnd = 0
        self._skip = set()

    def remember_skip(self, hwnd):
        if hwnd:
            self._skip.add(int(hwnd))

    def note_foreground(self):
        hwnd = win32util.foreground_hwnd()
        if hwnd and hwnd not in self._skip and win32util.is_window_visible(hwnd):
            title = win32util.window_title(hwnd)
            if title:
                self.last_hwnd = hwnd

    def touch(self):
        self._last_touch = time.monotonic()
        self._neglect_said = False
        self._slack_said = False

    def bump(self, delta):
        self.mood = max(0, min(100, self.mood + int(delta)))
        self.config["mood"] = self.mood

    def mood_line(self):
        if self.mood >= 75:
            return "当前心情不错，语气可以稍微松一点。"
        if self.mood <= 35:
            return "当前心情不好，语气更冷、更短，带点不耐烦。"
        return "当前心情一般，保持平时的人设。"

    def muted(self):
        return time.monotonic() < self._muted_until

    def mute(self, seconds=300):
        self._muted_until = time.monotonic() + seconds

    def unmute(self):
        self._muted_until = 0.0

    def speak(self, text):
        if not text or self.muted():
            return
        self.say.emit(text)

    def try_command(self, text):
        raw = (text or "").strip()
        key = raw.lower().replace("！", "").replace("!", "")
        mapping = {
            "跳舞": "dance", "跳个舞": "dance", "dance": "dance",
            "过来": "come", "来": "come",
            "闭嘴": "mute", "安静": "mute",
            "坐下": "perch", "坐那": "perch", "坐上去": "perch",
            "下来": "unperch", "下来吧": "unperch",
            "心情": "mood",
        }
        action = mapping.get(key)
        if not action:
            return False
        self.touch()
        if action == "dance":
            self.act.emit("dance")
            self.speak("……看清楚了。")
        elif action == "come":
            self.act.emit("come")
            self.speak("来了。别指望我跑。")
        elif action == "mute":
            self.speak("行。")
            self.mute()
        elif action == "perch":
            self.act.emit("perch")
            self.speak("就这儿。")
        elif action == "unperch":
            self.act.emit("unperch")
            self.speak("下来了。")
        elif action == "mood":
            self.speak(self._mood_say())
        return True

    def on_pet_head(self):
        self.touch()
        self.bump(6)
        now = time.monotonic()
        if now - self._combo_at > 2.2:
            self._combo = 0
        self._combo += 1
        self._combo_at = now
        lines = {
            1: "……",
            2: "手很闲？",
            3: "再摸试试。",
            4: "够了。",
        }
        self.speak(lines.get(self._combo, "……真是。"))

    def on_pet_body(self):
        self.touch()
        self.bump(2)

    def on_chat(self):
        self.touch()
        self.unmute()
        self.bump(3)

    def on_thrown(self):
        self.touch()
        self.bump(-18)
        self.speak("……有意思。")

    def on_file(self, path):
        self.touch()
        name = os.path.basename(path or "")
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext in {".py", ".js", ".ts", ".java", ".go", ".rs"}:
            line = "又在写代码。%s，看着就累。" % name
        elif ext in {".xlsx", ".xls", ".csv"}:
            line = "表格。你还挺能忍。"
        elif ext in {".zip", ".rar", ".7z"}:
            line = "压缩包丢过来干什么。"
        elif ext in {".mp4", ".mkv", ".mp3"}:
            line = "……摸鱼证据。"
        elif ext in {".pdf", ".doc", ".docx", ".ppt", ".pptx"}:
            line = "%s。工作找上门了。" % name
        else:
            line = "这是什么，%s？" % (stem or name or "无名氏")
        self.speak(line)

    def tick(self, busy):
        self.note_foreground()
        if busy:
            return
        now = time.monotonic()
        idle = now - self._last_touch
        user_idle = win32util.idle_seconds()

        if idle >= NEGLECT_SEC and not self._neglect_said:
            self._neglect_said = True
            self.act.emit("come")
            self.speak("把我当摆件了？")
            return
        if idle >= SLACK_SEC and user_idle < 40 and not self._slack_said:
            self._slack_said = True
            self.speak("屏幕亮了半天，成果呢？")
            return
        if now >= self._next_idle:
            self._next_idle = now + random.uniform(IDLE_CHAT_MIN, IDLE_CHAT_MAX)
            self.speak(self._idle_line())

    def _mood_say(self):
        if self.mood >= 75:
            return "还行。别得意。"
        if self.mood <= 35:
            return "不怎么样。刚才那一下，记住了。"
        return "一般。过得去。"

    def _idle_line(self):
        hour = datetime.now().hour
        weekday = datetime.now().weekday()
        if self.mood <= 35:
            return random.choice(["……心情不太好。", "别来烦我。", "刚才那一下，记住了。"])
        if hour < 7:
            return random.choice(["这么早就开始了。", "……还没醒透。"])
        if hour >= 23:
            return random.choice(["还不睡？", "这个点还亮着屏幕。"])
        if weekday == 4 and 16 <= hour <= 20:
            return random.choice(["周五了，还挺能撑。", "周末快到了，别装忙。"])
        if self.mood >= 75:
            return random.choice(["还行。", "看你忙。", "……"])
        return random.choice(["……", "看你忙。", "别一副没事干的样子。", "嗯。"])
