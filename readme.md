# SmartBoot

<div align="center">

![SmartBoot Logo](https://via.placeholder.com/128x128?text=SB)

**A reliable USB bootable media creator**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/zikani/smartboot)

[Features](#features) • [Downloads](#downloads) • [Installation](#installation) • [Usage](#usage) • [Documentation](#documentation) • [Contributing](#contributing)

</div>

---

SmartBoot is a cross-platform utility that helps you create bootable USB drives from ISO images. It provides a simple, reliable interface for creating bootable media for Windows, Linux, and other operating systems.

## Features

- **Cross-Platform Support** - Works on Windows, Linux, and macOS
- **Multiple ISO Types** - Supports Windows, Linux, FreeDOS, and generic bootable ISOs
- **Flexible Partitioning** - MBR and GPT partition schemes
- **Multiple Boot Modes** - BIOS, UEFI, Dual (BIOS+UEFI), and FreeDOS boot support
- **Various Filesystems** - FAT32, NTFS, exFAT, UDF, ReFS, ext2/3/4, APFS, HFS+
- **Direct Write Mode** - Fast dd-like writing for large ISOs
- **Automatic Detection** - Auto-detects ISO type and USB devices
- **Progress Tracking** - Real-time progress updates during creation
- **Logging** - Comprehensive logging for troubleshooting

## Downloads

### Source Code
```bash
git clone https://github.com/zikani/smartboot.git
```

### Requirements
- Python 3.7 or higher
- PyQt5 >= 5.15.0

See [Installation Guide](docs/installation.md) for detailed installation instructions.

## Installation

### Quick Install

```bash
# Clone the repository
git clone https://github.com/zikani/smartboot.git
cd smartboot

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Platform-Specific Installation

For detailed installation instructions for your platform, see:
- [Windows Installation](docs/installation.md#windows)
- [Linux Installation](docs/installation.md#linux)
- [macOS Installation](docs/installation.md#macos)

## Usage

### Quick Start

1. **Launch SmartBoot**
   ```bash
   python main.py
   ```

2. **Select USB Device**
   - Choose your USB drive from the device dropdown
   - Click "Refresh" if your device doesn't appear

3. **Select ISO Image**
   - Click "Browse" to select your ISO file
   - SmartBoot will auto-detect the ISO type

4. **Configure Options**
   - Partition scheme: MBR or GPT
   - Boot type: BIOS, UEFI, Dual, or FreeDOS
   - Filesystem: FAT32, NTFS, exFAT, etc.
   - Enable "Quick Format" for faster formatting

5. **Create Bootable USB**
   - Click "Start" to begin
   - Wait for the process to complete
   - Safely remove the USB drive

### Supported ISO Types

| Type | Examples | Notes |
|------|----------|-------|
| Windows | Windows 7/8/10/11, Server | Supports both BIOS and UEFI |
| Linux | Ubuntu, Debian, Fedora, Arch | Most distributions supported |
| FreeDOS | FreeDOS ISOs | BIOS boot only |
| Generic | Other bootable ISOs | May require manual configuration |

For detailed usage instructions, see the [User Guide](docs/usage.md).

## Documentation

- [Installation Guide](docs/installation.md) - Detailed installation instructions
- [User Guide](docs/usage.md) - Complete usage documentation
- [FAQ](docs/faq.md) - Frequently asked questions
- [Architecture](docs/architecture.md) - System architecture and design
- [Changelog](docs/changelog.md) - Version history and changes
- [Contributing](docs/contributing.md) - How to contribute to SmartBoot

## Screenshots

*Screenshots coming soon*

## System Requirements

### Minimum Requirements
- **OS**: Windows 7+, Linux (Ubuntu 18.04+), macOS 10.14+
- **RAM**: 512 MB
- **Disk Space**: 100 MB for application
- **USB Drive**: At least 4 GB (8 GB recommended for Windows ISOs)

### Recommended Requirements
- **OS**: Windows 10+, Linux (Ubuntu 20.04+), macOS 11+
- **RAM**: 1 GB
- **USB Drive**: USB 3.0+ for faster writes

## Comparison

| Feature | SmartBoot | Rufus | Etcher |
|---------|-----------|-------|--------|
| Cross-Platform | ✅ Windows, Linux, macOS | ❌ Windows only | ✅ Windows, Linux, macOS |
| GUI | ✅ PyQt5 | ✅ Native | ✅ Electron |
| ISO Type Detection | ✅ Auto | ✅ Auto | ❌ Manual |
| Multiple Boot Modes | ✅ BIOS/UEFI/Dual | ✅ BIOS/UEFI | ❌ None |
| Direct Write Mode | ✅ Yes | ✅ Yes | ❌ No |
| Verification | ❌ Planned | ✅ Yes | ✅ Yes |
| Open Source | ✅ MIT | ✅ GPL | ✅ Apache 2.0 |

## Known Issues

See [GitHub Issues](https://github.com/zikani/smartboot/issues) for current known issues and to report new ones.

## Contributing

Contributions are welcome! Please see the [Contributing Guide](docs/contributing.md) for details on:
- Code contributions
- Bug reports
- Feature requests
- Documentation improvements

## Roadmap

### Version 0.2.0 (Planned)
- Command-line interface
- Multi-boot USB support
- ISO verification (checksums)
- Written data verification
- Configuration profiles

### Version 0.3.0 (Planned)
- Persistent storage for Linux live USBs
- Windows To Go support
- Plugin system
- Internationalization (i18n)
- Standalone executable builds

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/intro) for the excellent GUI framework
- [Python](https://www.python.org/) for the programming language
- [Rufus](https://rufus.ie/) for inspiration and reference
- The open-source community for various tools and libraries

## Support

- [Documentation](docs/)
- [Report Issues](https://github.com/zikani/smartboot/issues)
- [Discussions](https://github.com/zikani/smartboot/discussions)
- Email: support@smartboot.dev

## Donate

If you find SmartBoot useful, consider supporting the project:
- [GitHub Sponsors](https://github.com/sponsors/zikani)
- [PayPal](https://paypal.me/smartboot)

---

<div align="center">

**[⬆ Back to Top](#smartboot)**

Made with ❤️ by the SmartBoot team

</div>
