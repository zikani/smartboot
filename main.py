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
from PyQt5.QtCore import Qt
from gui.main_window import MainWindow


def main() -> None:
    # High-DPI support must be set before QApplication creation
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        # Qt 6 doesn't have these attributes, high-DPI is enabled by default
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("SmartBoot")
    app.setApplicationVersion("0.1.2")
    app.setOrganizationName("SmartBoot")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()