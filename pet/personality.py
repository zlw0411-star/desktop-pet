import os
import random
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from . import win32util

PROACTIVE_MIN = 300
PROACTIVE_MAX = 600


class Personality(QObject):
    say = Signal(str)
    act = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.mood = int(config.get("mood", 60))
        self._last_touch = time.monotonic()
        self._next_idle = time.monotonic() + random.uniform(PROACTIVE_MIN, PROACTIVE_MAX)
        self._paused = False
        self._pause_started = None
        self._combo = 0
        self._combo_at = 0.0
        self._muted_until = 0.0
        self.last_hwnd = 0
        self._skip = set()
        self._last_line = ""
        self._last_offline_reply = ""

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

    def bump(self, delta):
        self.mood = max(0, min(100, self.mood + int(delta)))
        self.config["mood"] = self.mood

    def mood_line(self):
        if self.mood >= 75:
            return "当前心情不错，语气可以更亲近、活泼一点。"
        if self.mood <= 35:
            return "当前心情有些低落，语气安静简短，但依然友善。"
        return "当前心情平常，保持轻松友好的口吻。"

    def muted(self):
        return time.monotonic() < self._muted_until

    def mute(self, seconds=300):
        self._muted_until = time.monotonic() + seconds

    def unmute(self):
        self._muted_until = 0.0

    def speak(self, text, allow_repeat=False):
        if not text or (self.muted() and not allow_repeat):
            return
        if text == self._last_line and not allow_repeat:
            return
        self._last_line = text
        self.say.emit(text)

    def set_paused(self, paused):
        paused = bool(paused)
        if paused == self._paused:
            return
        now = time.monotonic()
        self._paused = paused
        if paused:
            self._pause_started = now
        else:
            # Start a fresh interval after resuming; never replay missed chatter.
            self._next_idle = now + random.uniform(PROACTIVE_MIN, PROACTIVE_MAX)
            self._pause_started = None

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
        if action in {"dance", "come", "perch", "unperch"}:
            self.act.emit(action)
        elif action == "mute":
            self.speak("好，我安静一会儿。", allow_repeat=True)
            self.mute()
        elif action == "mood":
            self.speak(self._mood_say(), allow_repeat=True)
        return True

    def offline_reply(self, text):
        """Friendly local response for simple chat when no model is configured."""
        self.touch()
        self.unmute()
        self.bump(1)
        raw = (text or "").strip()
        key = raw.lower()
        if any(word in key for word in ("你好", "嗨", "hello", "hi", "早上好", "晚上好")):
            choices = ["嗨！我在这儿陪你。", "你好呀，今天想聊点什么？", "嘿，见到你真好。"]
        elif any(word in key for word in ("谢谢", "谢啦", "thanks", "thank you")):
            choices = ["不客气，我很乐意陪你。", "嘿嘿，小事一桩。", "能帮上忙就好！"]
        elif any(word in key for word in ("心情", "开心吗", "怎么样", "还好吗")):
            choices = [self._mood_say()]
        elif any(word in key for word in ("陪", "无聊", "孤单", "在吗")):
            choices = ["我在呀，想聊会儿天还是让我跳支舞？", "当然陪你。你今天过得怎么样？", "我就在旁边，随时可以找我聊聊。"]
        else:
            choices = ["我现在还在学习聊天，不过很愿意陪你。你可以试试“跳舞”“过来”“坐下”或“心情”。",
                       "我还在慢慢学习，不过可以陪你聊聊。也可以试试“跳舞”“过来”“坐下”或“心情”。",
                       "这个问题我暂时答不上来，但我愿意听你多说一点。你也可以叫我跳舞或过来。"]
        available = [reply for reply in choices if reply != self._last_offline_reply]
        reply = random.choice(available or choices)
        self._last_offline_reply = reply
        return reply

    def on_pet_head(self):
        self.touch()
        self.bump(6)
        now = time.monotonic()
        if now - self._combo_at > 2.2:
            self._combo = 0
        self._combo += 1
        self._combo_at = now
        lines = {1: "嘿，摸摸收到！", 2: "还想再摸一下吗？", 3: "好啦，我也很喜欢你。", 4: "哈哈，痒痒的！"}
        self.speak(lines.get(self._combo, "嘿嘿，今天很黏人呀。"))

    def on_pet_body(self):
        self.touch()
        self.bump(2)

    def on_chat(self):
        self.touch()
        self.unmute()
        self.bump(3)

    def on_thrown(self):
        self.touch()
        self.bump(-5)
        self.speak("哇，起飞了！下次先打个招呼嘛。")

    def on_file(self, path):
        self.touch()
        name = os.path.basename(path or "")
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext in {".py", ".js", ".ts", ".java", ".go", ".rs"}:
            line = "又在写代码啦，%s。需要我陪你想想吗？" % name
        elif ext in {".xlsx", ".xls", ".csv"}:
            line = "表格时间！记得偶尔活动一下。"
        elif ext in {".zip", ".rar", ".7z"}:
            line = "收到一个压缩包：%s。" % name
        elif ext in {".mp4", ".mkv", ".mp3"}:
            line = "这个看起来很有趣：%s。" % name
        elif ext in {".pdf", ".doc", ".docx", ".ppt", ".pptx"}:
            line = "%s，辛苦啦，我陪你一起看。" % name
        else:
            line = "这是什么文件呀，%s？" % (stem or name or "")
        self.speak(line)

    def tick(self, busy=False):
        if self._paused or self.config.get("focus_mode", False):
            return
        self.note_foreground()
        if busy or not self.config.get("proactive_chat_enabled", True):
            return
        now = time.monotonic()
        if now >= self._next_idle:
            self._next_idle = now + random.uniform(PROACTIVE_MIN, PROACTIVE_MAX)
            self.speak(self._idle_line())

    def _mood_say(self):
        if self.mood >= 75:
            return "心情挺好呀，有你陪着更开心。"
        if self.mood <= 35:
            return "有一点点低落，不过和你聊聊会好起来。"
        return "还不错，平平静静的。你呢？"

    def _idle_line(self):
        hour = datetime.now().hour
        weekday = datetime.now().weekday()
        options = ["我在旁边陪你，想聊点什么吗？", "记得喝口水，忙完我们再聊。", "今天有什么开心的小事吗？", "我刚想到一个有趣的话题，要听听吗？"]
        if hour < 7:
            options = ["这么早呀，先喝点水醒醒神吧。", "我陪你开始新的一天。"]
        elif hour >= 23:
            options = ["夜深啦，忙完也记得休息。", "我陪你一会儿，困了就去睡吧。"]
        elif weekday == 4 and 16 <= hour <= 20:
            options.append("快到周末啦，有什么计划吗？")
        if self.mood >= 75:
            options += ["看到你在忙，我也觉得很安心。", "嘿，我在这里给你加油！"]
        if self.mood <= 35:
            options = ["我安静陪着你，想说话时叫我。", "要不要聊点轻松的？"]
        choices = [line for line in options if line != self._last_line]
        return random.choice(choices or options)
