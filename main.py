import sys
import logging
from PyQt5.QtWidgets import QApplication
from smartboot import SmartBootUI


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


VERSION = "1.0.0"

def main():
    try:
        app = QApplication(sys.argv)
        window = SmartBootUI()
        window.setWindowTitle(f"Smart Boot - Version {VERSION}")  
        window.show()
        logging.info("Application started successfully.")
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
