import copy
import json
import math
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "DesktopPet"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "scale": 1.5,
    "fps": 30,
    "style": "girl",
    "image_path": "",
    "auto_cutout": True,
    "bottom_margin": 6,
    "always_on_top": True,
    "wander": True,
    "follow_cursor": False,
    "sleep_enabled": True,
    "proactive_chat_enabled": True,
    "focus_mode": False,
    "walk_speed": 60.0,
    "autostart": False,
    "start_position": None,
    "shown_hint": False,
    "mood": 60,
    "ai": {
        "enabled": False,
        "base_url": "",
        "model": "",
        "fallback_models": [],
        "api_key_env": "DESKTOP_PET_API_KEY",
        "system_prompt": "你是一只可爱的桌面宠物，回答简短、俏皮、口语化。",
        "max_history": 12,
        "timeout": 30,
    },
}


def _sanitize(base, user):
    """Merge persisted settings while rejecting values of the wrong shape."""
    if not isinstance(user, dict):
        return base
    for key, value in user.items():
        if key not in base:
            # Preserve forward-compatible settings.
            base[key] = value
            continue
        default = base[key]
        if isinstance(default, dict):
            if isinstance(value, dict):
                _sanitize(default, value)
        elif isinstance(default, bool):
            if isinstance(value, bool):
                base[key] = value
        elif isinstance(default, (int, float)) and not isinstance(default, bool):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ranges = {
                    "scale": (0.5, 2.0), "fps": (10, 60), "walk_speed": (10, 200),
                    "mood": (0, 100), "timeout": (1, 300), "max_history": (2, 100),
                    "bottom_margin": (0, 200),
                }
                low, high = ranges.get(key, (-1e9, 1e9))
                # Bound integers before math.isfinite, which converts to float
                # and can overflow on otherwise valid but malicious JSON ints.
                if low <= value <= high and math.isfinite(value):
                    base[key] = value
        elif isinstance(default, str):
            if isinstance(value, str):
                base[key] = value
        elif default is None:
            if (isinstance(value, (list, tuple)) and len(value) == 2
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                            and abs(v) <= 1_000_000 for v in value)):
                base[key] = [int(value[0]), int(value[1])]
        elif isinstance(default, list):
            if key == "fallback_models" and isinstance(value, str):
                base[key] = [item.strip() for item in value.split(",") if item.strip()]
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                base[key] = value
    return base


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = Path(path)
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        self.data = copy.deepcopy(DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                user = json.load(fh)
            if isinstance(user, dict):
                _sanitize(self.data, user)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError, UnicodeError):
            pass
        return self.data

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
