# Frequently Asked Questions

## General Questions

### What is SmartBoot?

SmartBoot is a cross-platform application for creating bootable USB drives from ISO images. It supports Windows, Linux, and macOS, and can create bootable media for various operating systems.

### Is SmartBoot free?

Yes, SmartBoot is open-source software released under the MIT License. It is free to use, modify, and distribute.

### What operating systems does SmartBoot support?

SmartBoot runs on:
- Windows 7/8/10/11
- Linux (Ubuntu, Debian, Fedora, Arch, etc.)
- macOS 10.14 (Mojave) or later

### What types of ISOs can I use?

SmartBoot supports:
- Windows installation ISOs (7, 8, 10, 11, Server)
- Linux distribution ISOs (Ubuntu, Debian, Fedora, Arch, etc.)
- FreeDOS ISOs
- Generic bootable ISOs

## Installation

### Do I need administrator privileges?

Yes, creating bootable USB drives requires administrator/root privileges to:
- Access USB devices
- Format disks
- Write boot sectors
- Mount/unmount filesystems

### Can I run SmartBoot without installing Python?

Currently, SmartBoot requires Python 3.7 or higher. A standalone executable version may be available in the future.

### Why does SmartBoot need PyQt5?

PyQt5 is used for the graphical user interface. It provides a native look and feel on each platform.

## Usage

### Why is my USB drive not detected?

Possible reasons:
- USB drive not properly connected
- Insufficient permissions (run as Administrator/root)
- Drive is mounted elsewhere
- Driver issues (Windows)
- Try a different USB port

### Can I use a USB drive smaller than 4GB?

Technically yes, but most ISOs require at least 4GB. Windows ISOs typically require 8GB or more.

### What's the difference between MBR and GPT?

- **MBR**: Legacy BIOS boot, max 2TB, max 4 partitions
- **GPT**: UEFI boot, unlimited size, unlimited partitions
- Choose based on your system's boot mode

### Should I use BIOS or UEFI boot?

- **BIOS**: For older systems or legacy boot
- **UEFI**: For modern systems with UEFI firmware
- **Dual**: For maximum compatibility (both modes)

### What filesystem should I use?

- **FAT32**: Best compatibility, required for UEFI, 4GB file limit
- **NTFS**: Windows-only, no file size limit, not UEFI bootable
- **exFAT**: Large files, cross-platform, limited boot support
- **ext2/3/4**: Linux-only, advanced users

### What is "Direct Write" mode?

Direct write mode writes the ISO directly to the USB drive (like dd command). It's faster but may not work with all ISOs. Recommended for Linux ISOs.

### Can I create a multi-boot USB?

Currently, SmartBoot creates single-boot USBs. Multi-boot support may be added in the future. For now, you can manually add additional ISOs after creation.

## Troubleshooting

### Why did the creation process fail?

Common causes:
- USB drive in use by another application
- Insufficient permissions
- Corrupted ISO file
- USB drive errors
- Insufficient disk space

### Why won't my USB boot?

Possible reasons:
- Wrong boot mode selected (BIOS vs UEFI)
- Boot sector not written correctly
- USB drive not in boot order
- Corrupted ISO
- USB port issues
- System doesn't support the boot mode

### How do I fix a "Boot sector write failed" error?

- Run SmartBoot as Administrator/root
- Try different boot type
- Use direct write mode
- Check USB drive for errors
- Try a different USB drive

### Can I recover data from a USB after using SmartBoot?

No, SmartBoot formats the USB drive, erasing all data. Always backup important data before creating bootable media.

### Why is the process so slow?

Possible reasons:
- USB 2.0 drive (use USB 3.0+)
- Large ISO file
- Slow write speed of USB drive
- System resources
- Antivirus scanning

## Technical

### How does SmartBoot detect ISO type?

SmartBoot uses multiple methods:
- Filename pattern matching
- ISO content examination (mounting when possible)
- File size heuristics
- Manual override option

### What happens during the creation process?

1. USB device detection and validation
2. Disk formatting (clean, partition, format)
3. ISO extraction or direct write
4. Boot sector writing
5. Verification

### Does SmartBoot verify the written data?

Currently, SmartBoot doesn't perform full verification. This may be added in a future release. You can verify by testing the bootable USB.

### Can I use SmartBoot from command line?

Currently, SmartBoot is GUI-only. Command-line support may be added in the future.

### Where are logs stored?

Logs are stored in platform-specific locations:
- Windows: `%APPDATA%\smartboot\logs\`
- Linux: `~/.local/share/smartboot/logs/`
- macOS: `~/Library/Logs/smartboot/`

## Compatibility

### Does SmartBoot work with Secure Boot?

SmartBoot can create UEFI bootable media, but Secure Boot support depends on the ISO and system configuration. Some ISOs may require disabling Secure Boot.

### Can I create Windows To Go drives?

Not currently supported. This feature may be added in the future.

### Does SmartBoot support persistent storage?

Not currently. Linux live USBs with persistence may be supported in the future.

### Can I use SmartBoot on ARM systems?

SmartBoot should work on ARM systems running Linux or macOS (Apple Silicon), but Windows ARM support is limited.

## Security

### Is SmartBoot safe to use?

SmartBoot is open-source, meaning the code can be audited. Always download from official sources and verify ISO checksums.

### Can SmartBoot damage my computer?

SmartBoot only writes to the selected USB drive. However, selecting the wrong drive could result in data loss. Always verify the selected device.

### Does SmartBoot collect data?

No, SmartBoot does not collect or transmit any data. All operations are performed locally.

## Development

### How can I contribute?

See the [Contributing Guide](contributing.md) for details on:
- Code contributions
- Bug reports
- Feature requests
- Documentation improvements

### What programming language is SmartBoot written in?

SmartBoot is written in Python 3 with PyQt5 for the GUI.

### Can I build a standalone executable?

Yes, using tools like PyInstaller or PyOX. See the [Building Guide](building.md) for details.

## Support

### Where can I get help?

- Check this FAQ
- Read the [User Guide](usage.md)
- Search existing GitHub issues
- Open a new issue on GitHub
- Join community discussions

### How do I report a bug?

When reporting bugs, include:
- Operating system and version
- Python version
- SmartBoot version
- Steps to reproduce
- Error messages or logs
- ISO type and size

### How do I request a feature?

Open a GitHub issue with:
- Feature description
- Use case
- Possible implementation approach
- Priority level

## License

### Can I use SmartBoot commercially?

Yes, SmartBoot is licensed under the MIT License, which allows commercial use.

### Can I modify and redistribute SmartBoot?

Yes, the MIT License allows modification and redistribution, as long as the license and copyright notice are included.

## Other

### How does SmartBoot compare to Rufus/Etcher?

SmartBoot is similar to Rufus and Etcher but with cross-platform support (Windows, Linux, macOS). Each tool has its strengths:
- Rufus: Windows-only, very fast, highly configurable
- Etcher: Cross-platform, simple interface, verification
- SmartBoot: Cross-platform, Python-based, extensible

### Will SmartBoot remain free?

Yes, SmartBoot will remain free and open-source under the MIT License.

### How can I stay updated?

- Watch the GitHub repository
- Follow release notes
- Join community discussions
- Check the documentation regularly
