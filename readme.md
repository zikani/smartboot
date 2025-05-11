# SmartBoot

SmartBoot is a USB boot media creator application that allows users to create bootable USB drives from ISO images. It provides a user-friendly interface built with PyQt5.

## Features

- **USB Device Management**: Detect and select USB devices.
- **ISO Image Selection**: Browse and select ISO files to create bootable media.
- **Cross-Platform Support**: Works on Windows, Linux, and macOS.
- **Logging**: Provides logging functionality to track application events.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/zikani/smartboot.git
   cd smartboot
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```

2. Select a USB device from the dropdown menu.
3. Click the "Refresh" button to update the list of available devices.
4. Browse and select an ISO file using the file dialog.
5. Follow the on-screen instructions to create the bootable USB drive.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/intro) for the GUI framework.
- [Python](https://www.python.org/) for the programming language.
