"""
SmartBoot — entry point.

Sets up sys.path so all ``from core.*`` and ``from utils.*`` imports
resolve correctly regardless of the working directory from which the
script is launched.
"""

import os
import sys

# Ensure the project root is first in sys.path.
_HERE = os.path.abspath(os.path.dirname(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SmartBoot")
    app.setApplicationVersion("0.1.2")
    app.setOrganizationName("SmartBoot")

    # High-DPI support
    app.setAttribute(app.AA_EnableHighDpiScaling, True)
    app.setAttribute(app.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()