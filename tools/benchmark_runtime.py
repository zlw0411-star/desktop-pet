"""Repeatable offscreen rendering and hidden-window benchmark."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.pet_window import PetWindow
from pet.state_machine import PetState


def benchmark():
    app = QApplication.instance() or QApplication([])
    results = {}
    with tempfile.TemporaryDirectory() as folder:
        image = QPixmap(600, 600)
        image.fill(QColor("#83b6e5"))
        image_path = str(Path(folder) / "pet.png")
        image.save(image_path)
        for style in ("girl", "image"):
            cfg = Config(Path(folder) / "config.json")
            cfg["style"] = style
            cfg["image_path"] = image_path
            pet = PetWindow(cfg)
            masks = [0]
            update_mask = pet._update_mask

            def count_mask():
                masks[0] += 1
                update_mask()

            pet._update_mask = count_mask
            pet.sm.force(PetState.TALK)
            for i in range(20):
                pet.sm.t = pet._clock = i / 30
                pet._render()
            masks[0] = 0
            begin = time.perf_counter()
            for i in range(300):
                pet.sm.t = pet._clock = i / 30
                pet._render()
            results[style] = {
                "render_ms_per_frame": round((time.perf_counter() - begin) * 1000 / 300, 3),
                "mask_updates_300_frames": masks[0],
            }
            pet.start()
            pet.hide()
            ticks = [0]
            pet._timer.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
            loop = QEventLoop()
            QTimer.singleShot(400, loop.quit)
            loop.exec()
            results[style]["hidden_ticks_400ms"] = ticks[0]
            pet.stop()
            pet.close()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    benchmark()
