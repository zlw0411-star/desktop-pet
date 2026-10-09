import os
from importlib.util import find_spec
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .config import CONFIG_DIR

MODEL_DIR = CONFIG_DIR / "models"
MODEL_NAME = "u2net.onnx"
MODEL_URL = ("https://github.com/danielgatis/rembg/releases/"
             "download/v0.0.0/u2net.onnx")
MODEL_MD5 = "60024c5c889badc19c04ad937298a77b"

_session = None


def model_path():
    configured = Path(os.environ.get("U2NET_HOME") or MODEL_DIR) / MODEL_NAME
    if configured.is_file():
        return configured
    bundled = Path(__file__).resolve().parents[1] / "models" / MODEL_NAME
    return bundled if bundled.is_file() else configured


def model_available():
    return model_path().exists()


def rembg_available():
    # Importing rembg loads the inference stack; keep that off the UI thread.
    return all(find_spec(name) is not None for name in ("rembg", "PIL", "onnxruntime"))


def available():
    return rembg_available() and model_available()


def _get_session():
    global _session
    if _session is None:
        os.environ["U2NET_HOME"] = str(model_path().parent)
        from rembg import new_session

        _session = new_session("u2net")
    return _session


def _clean_edges(result):
    from PIL import ImageFilter

    alpha = result.getchannel("A")
    low, high = 24, 205
    alpha = alpha.point(
        lambda v: 0 if v < low else (255 if v > high else int((v - low) * 255 / (high - low)))
    )
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    result.putalpha(alpha)
    return result


def cutout(src_path, dst_path=None):
    from rembg import remove
    from PIL import Image

    with Image.open(src_path) as source:
        image = source.convert("RGBA")
    result = remove(image, session=_get_session())
    result = _clean_edges(result)
    bbox = result.getbbox()
    if bbox:
        pad = max(4, int(max(result.size) * 0.01))
        left = max(0, bbox[0] - pad)
        top = max(0, bbox[1] - pad)
        right = min(result.width, bbox[2] + pad)
        bottom = min(result.height, bbox[3] + pad)
        result = result.crop((left, top, right, bottom))
    if dst_path is None:
        dst_path = str(Path(src_path).with_name(Path(src_path).stem + "_cut.png"))
    result.save(dst_path)
    return dst_path


class CutoutWorker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, src_path, dst_path=None, parent=None):
        super().__init__(parent)
        self.src_path = src_path
        self.dst_path = dst_path

    def run(self):
        global _session
        try:
            self.done.emit(cutout(self.src_path, self.dst_path))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            # The model is only needed during image import, not all day.
            _session = None
