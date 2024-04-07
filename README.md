# smartboot
SmartBoot a python simplifies creating bootable USB drives from ISO files. Cross-platform, intuitive interface, customizable formatting, automatic bootloader installation. Effortless USB creation 

# Bootable USB Creation Scripts

These scripts facilitate the creation of bootable USB drives from ISO files on Windows and Linux systems.

## Features

- **Platform Support**: Compatible with both Windows and Linux operating systems.
- **ISO Copying**: Copies the provided ISO file to the USB drive.
- **Formatting**: Formats the USB drive with the specified file system and volume label.
- **Bootloader Installation**: Installs the appropriate bootloader (GRUB for UEFI or Syslinux for Legacy).

## Prerequisites

- **Python**: Ensure Python is installed on your system. The scripts are compatible with Python 3.
- **Dependencies**: Install the required Python packages listed in `requirements.txt` using `pip install -r requirements.txt`.

## Usage

1. Clone this repository:
git clone https://github.com/zikani/smartboot.git


2. Run the script:
- On Windows:
  ```
  python main.py
  ```
- On Linux:
  ```
  python3 main.py
  ```

3. Follow the on-screen instructions to select the ISO file, USB drive, file system, boot type, and partition scheme.

4. Once the process is complete, your bootable USB drive will be ready for use.

## Troubleshooting

- If you encounter any errors during the process, refer to the error messages provided by the scripts for troubleshooting steps.
- Ensure that you have the necessary permissions to access and modify the USB drive.

## Contributing

Contributions are welcome! If you find any issues or have suggestions for improvements, please open an issue or submit a pull request.

## License

This project is licensed under the [MIT License](LICENSE).

