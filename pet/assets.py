import hashlib
import shutil
from pathlib import Path

from .config import CONFIG_DIR

ASSET_DIR = CONFIG_DIR / "assets"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def is_image(path):
    return Path(path).suffix.lower() in IMAGE_EXTS


def import_image(path):
    src = Path(path)
    if not src.exists() or not src.is_file() or not is_image(src):
        return None
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    stat = src.stat()
    digest = hashlib.md5(
        ("%s|%s|%s" % (src.resolve(), stat.st_size, stat.st_mtime)).encode("utf-8")
    ).hexdigest()[:10]
    dst = ASSET_DIR / ("pet_%s%s" % (digest, src.suffix.lower()))
    try:
        shutil.copy2(src, dst)
    except OSError:
        return None
    for old in ASSET_DIR.glob("pet_*"):
        if old != dst:
            try:
                old.unlink()
            except OSError:
                pass
    return str(dst)


def latest_image():
    if not ASSET_DIR.exists():
        return None
    files = sorted(ASSET_DIR.glob("pet_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None
