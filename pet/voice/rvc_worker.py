"""常驻 RVC 转换 worker。

由桌面宠物用 RVCMAX 的 Runtime\\python.exe 启动，从 stdin 读 JSON 任务、
往 stdout 写 JSON 结果（日志走 stderr）。第一次转换会加载模型，之后复用。

任务格式::

    {"cmd": "convert", "text": "你好", "model": "kikiV1.pth",
     "output": "C:/.../out.wav", "f0up_key": 0, "f0method": "harvest",
     "index_path": "", "index_rate": 0.66, "protect": 0.33, "rms_mix_rate": 0.6}

或直接给输入音频::

    {"cmd": "convert", "input": "C:/.../in.wav", "output": "C:/.../out.wav", ...}

就绪时先输出一行 ``{"ready": true}``。
"""

import json
import os
import sys
import tempfile
import traceback

REAL_OUT = sys.stdout
sys.stdout = sys.stderr

ROOT = os.environ.get("RVC_ROOT", "")
CORE = os.path.join(ROOT, "RVC_Core")
if CORE and os.path.isdir(CORE):
    os.chdir(CORE)
    sys.path.insert(0, CORE)

try:
    from dotenv import load_dotenv

    env_file = os.path.join(CORE, ".env")
    if os.path.exists(env_file):
        load_dotenv(env_file)
    else:
        load_dotenv()
    os.environ.setdefault("index_root", "logs")
    os.environ.setdefault("outside_index_root", "assets/indices")
    os.environ.setdefault("rmvpe_root", "assets/rmvpe")
    os.environ.setdefault("weight_uvr5_root", "assets/uvr5_weights")
    from configs.config import Config
    from infer.modules.vc.modules import VC
except Exception as exc:  # pragma: no cover
    REAL_OUT.write(json.dumps({"ready": False, "error": repr(exc)}) + "\n")
    REAL_OUT.flush()
    raise


def synth_sapi(text, path):
    import win32com.client

    voice = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(path, 3, False)
    voice.AudioOutputStream = stream
    voice.Speak(text)
    stream.Close()


class Converter:
    def __init__(self):
        self._config = Config()
        self._vc = VC(self._config)
        self._loaded = None

    def ensure_model(self, model):
        if model and model != self._loaded:
            self._vc.get_vc(model)
            self._loaded = model

    def convert(self, job):
        from scipy.io import wavfile

        model = job.get("model")
        self.ensure_model(model)

        src = job.get("input")
        tmp = None
        if not src:
            text = job.get("text", "")
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="pet_tts_")
            os.close(fd)
            synth_sapi(text, tmp)
            src = tmp

        try:
            _, wav = self._vc.vc_single(
                0,
                src,
                int(job.get("f0up_key", 0)),
                None,
                job.get("f0method", "harvest"),
                job.get("index_path", ""),
                None,
                float(job.get("index_rate", 0.66)),
                int(job.get("filter_radius", 3)),
                int(job.get("resample_sr", 0)),
                float(job.get("rms_mix_rate", 1.0)),
                float(job.get("protect", 0.33)),
            )
            if wav is None:
                raise RuntimeError("RVC returned no audio")
            wavfile.write(job["output"], wav[0], wav[1])
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return job["output"]


def main():
    try:
        converter = Converter()
    except Exception as exc:  # pragma: no cover
        REAL_OUT.write(json.dumps(
            {"ready": False, "error": repr(exc), "trace": traceback.format_exc()[-1500:]},
            ensure_ascii=False) + "\n")
        REAL_OUT.flush()
        return

    REAL_OUT.write(json.dumps({"ready": True}) + "\n")
    REAL_OUT.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except ValueError:
            continue
        if job.get("cmd") == "quit":
            break
        try:
            output = converter.convert(job)
            reply = {"ok": True, "output": output}
        except Exception as exc:  # noqa: BLE001
            reply = {"ok": False, "error": repr(exc),
                     "trace": traceback.format_exc()[-1500:]}
        REAL_OUT.write(json.dumps(reply, ensure_ascii=False) + "\n")
        REAL_OUT.flush()


if __name__ == "__main__":
    main()
