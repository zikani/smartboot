# Changelog

All notable changes to SmartBoot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of SmartBoot
- USB device detection for Windows, Linux, and macOS
- ISO file validation and type detection
- Support for Windows, Linux, FreeDOS, and generic ISOs
- Disk formatting with multiple filesystems (FAT32, NTFS, exFAT, UDF, ReFS, ext2/3/4, APFS, HFS+)
- Partition scheme support (MBR and GPT)
- Boot type options (BIOS, UEFI, Dual, FreeDOS)
- Boot sector writing for all platforms
- Direct write mode (dd-like)
- Progress tracking and logging
- PyQt5-based GUI

### Known Issues
- Import error in usb_manager.py and iso_manager.py (BootSectorManager import path)
- Wrong device key access in boot_sector/windows.py (uses 'drive' instead of 'drive_letter')
- Missing device number validation in disk_formatter.py
- Linux device path inconsistency
- Missing error handling for missing device keys

## [0.1.0] - TBD

### Planned Features
- Command-line interface
- Multi-boot USB support
- Persistent storage for Linux live USBs
- ISO verification (checksums)
- Written data verification
- Configuration profiles
- Batch processing
- Plugin system for additional filesystems/bootloaders
- Internationalization (i18n)
- Standalone executable builds
- Performance optimizations
- Caching mechanisms

### Planned Improvements
- Better error handling and user feedback
- Asynchronous operations for non-blocking UI
- Enhanced device detection
- More robust boot sector writing
- Additional bootloader support (GRUB2, Syslinux, etc.)
- Windows To Go support
- Secure Boot compatibility improvements
- Better fallback mechanisms

## Version History

### Version 0.1.0 (Upcoming)
- Initial public release
- Core functionality for creating bootable USB drives
- Cross-platform support (Windows, Linux, macOS)
- Basic GUI with essential features

---

## Categories

### Added
- New features
- New capabilities

### Changed
- Changes in existing functionality
- Feature modifications

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes
- Issue resolutions

### Security
- Security vulnerability fixes

---

## Release Notes Format

Each release will include:
- Version number
- Release date
- Summary of changes
- Known issues
- Upgrade instructions (if applicable)
- Download links

---

## Reporting Issues

Found a bug? Have a suggestion? Please report it on the [GitHub Issues](https://github.com/zikani/smartboot/issues) page.

---

## Contributing

Want to contribute? See the [Contributing Guide](contributing.md) for details.
