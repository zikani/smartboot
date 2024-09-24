# SmartBoot – Simplified Bootable USB Drive Creation from ISO Files

**SmartBoot** is a powerful and user-friendly Python tool that simplifies creating bootable USB drives from ISO files. Whether you need a bootable USB for Windows or Linux, SmartBoot makes the process fast and efficient. This cross-platform utility provides customizable formatting options and automatically installs the appropriate bootloader for UEFI and Legacy systems. With SmartBoot, creating a bootable USB drive has never been easier.

## Key Features of SmartBoot

- **Cross-Platform Compatibility**: SmartBoot supports both Windows and Linux systems, making it a versatile solution for bootable USB drive creation.
- **ISO File Copying**: Easily copy ISO files to your USB drive with just a few steps.
- **Custom USB Drive Formatting**: Format your USB drive with your preferred file system (FAT32, NTFS, etc.) and set a custom volume label.
- **Automatic Bootloader Installation**: SmartBoot automatically installs the correct bootloader (GRUB for UEFI or Syslinux for Legacy BIOS), ensuring that your USB drive boots properly.
- **Simple, Intuitive Interface**: The script guides you through the process, making it accessible even for non-technical users.

## Prerequisites for SmartBoot

Before you can use SmartBoot to create bootable USB drives, ensure you have the following:

- **Python 3**: SmartBoot requires Python 3 installed on your system.
- **Required Python Packages**: Install the necessary Python dependencies using the following command:
  ```bash
  pip install -r requirements.txt

## Usage

1. Clone this repository:
https://github.com/zikani/smartboot.git


2. Run the script:
- On Windows:
  ```
  python main.py
  ```
- On Linux:
  ```
  python3 main.py
  ```

3. **Follow the Interactive Instructions**:

  -  Select your ISO file.
  -  Choose the USB drive you want to format.
  -  Specify the file system, boot type (UEFI or Legacy BIOS), and partition scheme.

4. **Finish the Process**: Once completed, your bootable USB drive will be ready to use for installing operating systems or running live environments.

## Troubleshooting

- **Permission Errors**: Make sure you have the necessary permissions (administrator on Windows or root on Linux) to modify and access the USB drive.
- **Error Messages**: If any errors occur during the process, SmartBoot will provide guidance on how to resolve them.

## Why Use SmartBoot for Bootable USB Drive Creation?
-  **Ease of Use**: The intuitive interface makes SmartBoot ideal for users at any technical level.
-  **Cross-Platform Functionality**: Whether you're on Windows or Linux, SmartBoot ensures seamless USB drive creation.
-  **Customizability**: You can customize the file system, partitioning, and bootloader for full control over your bootable USB.

## Contributing

Contributions are welcome! If you find any issues or have suggestions for improvements, please open an issue or submit a pull request.

## License

This project is licensed under the [MIT License](LICENSE).

