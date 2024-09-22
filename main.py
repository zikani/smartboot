from PyQt5.QtWidgets import QApplication
from smartboot import SmartBootUI


VERSION = "1.0.0"

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SmartBootUI()
    window.setWindowTitle(f"Smart Boot - Version {VERSION}")  
    window.show()
    sys.exit(app.exec_())
