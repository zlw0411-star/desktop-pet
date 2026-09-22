import json
import os

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from ..config import CONFIG_DIR

DEFAULT_MODELS_DIR = CONFIG_DIR / "rvc_models"


def models_dir(config):
    path = (config.get("rvc", {}) or {}).get("models_dir") or str(DEFAULT_MODELS_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def list_models(config):
    """列出模型文件夹里的 .pth，返回 [{name, index}]。"""
    directory = models_dir(config)
    result = []
    try:
        files = sorted(os.listdir(directory))
    except OSError:
        return result
    for name in files:
        if not name.lower().endswith(".pth"):
            continue
        stem = name[:-4]
        index = ""
        for ext in (".index", ".INDEX"):
            candidate = os.path.join(directory, stem + ext)
            if os.path.exists(candidate):
                index = candidate
                break
        result.append({"name": name, "index": index})
    return result


def find_index(config, model_name):
    if not model_name:
        return ""
    directory = models_dir(config)
    stem = model_name[:-4] if model_name.lower().endswith(".pth") else model_name
    for ext in (".index", ".INDEX"):
        candidate = os.path.join(directory, stem + ext)
        if os.path.exists(candidate):
            return candidate
    return ""



class RVCWorker(QObject):
    """管理常驻的 RVC 转换进程（RVCMAX Runtime 的 python）。"""

    ready = Signal(bool)
    failed = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._proc = None
        self._buffer = b""
        self._pending = None
        self._busy = False
        self._started = False

    @property
    def rvc_config(self):
        return self.config.get("rvc", {}) or {}

    def runtime_python(self):
        return os.path.join(self.rvc_config.get("root", ""), "Runtime", "python.exe")

    def worker_script(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_worker.py")

    def core_dir(self):
        return os.path.join(self.rvc_config.get("root", ""), "RVC_Core")

    def available(self):
        return (self.rvc_config.get("enabled", False)
                and os.path.exists(self.runtime_python())
                and os.path.exists(self.core_dir()))

    def start(self):
        if self._proc is not None:
            return
        self._proc = QProcess(self)
        self._proc.setProgram(self.runtime_python())
        self._proc.setArguments([self.worker_script()])
        self._proc.setWorkingDirectory(self.core_dir())
        env = QProcessEnvironment.systemEnvironment()
        env.insert("RVC_ROOT", self.rvc_config.get("root", ""))
        env.insert("weight_root", models_dir(self.config))
        self._proc.setProcessEnvironment(env)
        self._proc.setProcessChannelMode(QProcess.SeparateChannels)
        self._proc.readyReadStandardOutput.connect(self._on_stdout)
        self._proc.finished.connect(self._on_finished)
        self._proc.start()

    def _on_finished(self, code, status):
        self._proc = None
        self._busy = False
        pending = self._pending
        self._pending = None
        if pending is not None:
            pending(None, "RVC 进程已退出")

    def _on_stdout(self):
        if self._proc is None:
            return
        self._buffer += bytes(self._proc.readAllStandardOutput().data())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            self._dispatch(msg)

    def _dispatch(self, msg):
        if "ready" in msg:
            self._started = bool(msg.get("ready"))
            if not self._started:
                self.failed.emit(msg.get("error", "RVC 初始化失败"))
            self.ready.emit(self._started)
            return
        pending = self._pending
        self._pending = None
        self._busy = False
        if pending is None:
            return
        if msg.get("ok"):
            pending(msg.get("output"), None)
        else:
            pending(None, msg.get("error", "转换失败"))

    def convert(self, callback, text=None, input_path=None, output_path=None):
        if not self.available():
            callback(None, "RVC 未启用或路径无效")
            return
        if self._busy:
            callback(None, "RVC 正忙")
            return
        self.start()
        cfg = self.rvc_config
        index_path = cfg.get("index_path", "") or find_index(self.config, cfg.get("model_name", ""))
        job = {
            "cmd": "convert",
            "output": output_path,
            "model": cfg.get("model_name", ""),
            "f0up_key": int(cfg.get("f0up_key", 0)),
            "f0method": cfg.get("f0method", "harvest"),
            "index_path": index_path,
            "index_rate": float(cfg.get("index_rate", 0.66)),
            "protect": float(cfg.get("protect", 0.33)),
            "rms_mix_rate": float(cfg.get("rms_mix_rate", 1.0)),
        }
        if input_path:
            job["input"] = input_path
        else:
            job["text"] = text or ""
        self._busy = True
        self._pending = callback
        self._proc.write((json.dumps(job, ensure_ascii=False) + "\n").encode("utf-8"))

    def stop(self):
        if self._proc is not None:
            try:
                self._proc.write(b'{"cmd": "quit"}\n')
                self._proc.waitForFinished(1500)
            except Exception:
                pass
            if self._proc is not None:
                self._proc.kill()
        self._proc = None
        self._busy = False
        self._pending = None
