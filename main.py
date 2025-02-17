import sys
import logging
from PyQt5.QtWidgets import QApplication
from smartboot import SmartBootUI

VERSION = "1.0.0"

def configure_logging() -> None:
    """Configure logging settings."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def handle_shutdown():
    """Handle application shutdown."""
    logging.info("Application is shutting down.")

def main() -> None:
    """Main entry point for the application."""
    configure_logging()
    try:
        app = QApplication(sys.argv)
        window = SmartBootUI()
        window.setWindowTitle(f"Smart Boot - Version {VERSION}")
        window.show()
        logging.info("Application started successfully.")
        app.aboutToQuit.connect(handle_shutdown)
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
    
