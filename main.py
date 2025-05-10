import sys
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow
import os

# Add the project root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """
    Main entry point for the application.
    Initializes the GUI and starts the event loop.
    """
    app = QApplication(sys.argv)
    app.setApplicationName("SmartBoot")
    app.setApplicationVersion("0.1.0")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
