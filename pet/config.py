import copy
import json
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
    "walk_speed": 60.0,
    "autostart": False,
    "start_position": None,
    "voice": {
        "enabled": True,
        "engine": None,
        "voice_name": None,
        "volume": 1.0,
        "rate": 0.0,
    },
    "rvc": {
        "enabled": False,
        "root": r"E:\rvc\RVCMAX_Nvidia_xiaoyuan\RVCMAX_Nvidia_xiaoyuan",
        "models_dir": "",
        "model_name": "kikiV1.pth",
        "index_path": "",
        "f0method": "rmvpe",
        "f0up_key": 0,
        "index_rate": 0.66,
        "protect": 0.33,
        "rms_mix_rate": 0.6,
    },
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


def _deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = Path(path)
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                user = json.load(fh)
            if isinstance(user, dict):
                _deep_merge(self.data, user)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
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
