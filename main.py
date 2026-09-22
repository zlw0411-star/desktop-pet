"""桌面宠物：主程序入口。"""

import sys

from PySide6.QtWidgets import QApplication

from pet.app import DesktopPetApp


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DesktopPet")
    app.setApplicationDisplayName("桌面宠物")
    app.setQuitOnLastWindowClosed(False)

    controller = DesktopPetApp(app)
    controller.start()
    app._controller = controller
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
