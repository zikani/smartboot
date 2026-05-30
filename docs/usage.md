# User Guide

This guide explains how to use SmartBoot to create bootable USB drives.

## Quick Start

1. **Launch SmartBoot**
   - Windows: Run `smartboot` or `python main.py`
   - Linux/macOS: Run `python main.py`

2. **Select USB Device**
   - Choose your USB drive from the device dropdown
   - Click "Refresh" if your device doesn't appear

3. **Select ISO Image**
   - Click "Browse" to select your ISO file
   - SmartBoot will auto-detect the ISO type

4. **Configure Options**
   - Choose partition scheme (MBR/GPT)
   - Select boot type (BIOS/UEFI/Dual/FreeDOS)
   - Pick filesystem (FAT32/NTFS/exFAT/etc.)
   - Enable "Quick Format" for faster formatting

5. **Create Bootable USB**
   - Click "Start" to begin
   - Wait for the process to complete
   - Safely remove the USB drive

## Detailed Usage

### Device Selection

The device dropdown shows all detected USB drives with:
- Device name/model
- Capacity
- Current filesystem
- Drive letter (Windows) or mount point (Linux/macOS)

**Important**: Select the correct device - all data on the selected drive will be erased!

### ISO Selection

Supported ISO types:
- **Windows** - Windows 7/8/10/11 installation media
- **Linux** - Ubuntu, Debian, Fedora, Arch, etc.
- **FreeDOS** - FreeDOS bootable media
- **Generic** - Other bootable ISOs

SmartBoot automatically detects the ISO type based on:
- Filename patterns
- ISO contents (when possible)
- File size

### Partition Scheme

- **MBR (Master Boot Record)**
  - Legacy BIOS boot
  - Maximum 2TB partition size
  - Maximum 4 primary partitions
  - Best for older systems

- **GPT (GUID Partition Table)**
  - UEFI boot
  - Supports drives > 2TB
  - Unlimited partitions
  - Required for Secure Boot

### Boot Type

- **BIOS** - Traditional boot mode
  - Works with MBR partition scheme
  - Compatible with older systems
  - Most common option

- **UEFI** - Modern boot mode
  - Works with GPT partition scheme
  - Required for Secure Boot
  - Faster boot times
  - Best for modern systems

- **Dual (BIOS + UEFI)**
  - Creates bootable media for both modes
  - Larger file size
  - Maximum compatibility
  - Recommended for universal boot drives

- **FreeDOS** - DOS-based boot
  - For legacy DOS applications
  - BIOS boot only
  - Special use cases

### Filesystem

- **FAT32**
  - Maximum file size: 4GB
  - Best compatibility
  - Required for UEFI boot
  - Recommended for most ISOs

- **NTFS**
  - No file size limit
  - Windows-only
  - Not UEFI bootable
  - Best for large Windows ISOs

- **exFAT**
  - Large file support
  - Cross-platform
  - Limited boot support
  - Not recommended for boot media

- **ext2/3/4**
  - Linux filesystems
  - Linux boot only
  - Advanced users

### Advanced Options

#### Direct Write Mode
- Writes ISO directly to USB (dd-like)
- Faster for large ISOs
- May not work with all ISOs
- Recommended for Linux ISOs

#### ISO Type Override
- Manually specify ISO type
- Use if auto-detection fails
- Advanced users only

### Progress Indicators

SmartBoot shows progress for:
- Disk formatting
- ISO extraction/copying
- Boot sector writing
- Overall completion

## Common Use Cases

### Creating Windows Installation USB

1. Download Windows ISO from Microsoft
2. Select USB drive (8GB+ recommended)
3. Select Windows ISO
4. Configure:
   - Partition: GPT (for UEFI) or MBR (for BIOS)
   - Boot: UEFI or Dual
   - Filesystem: FAT32 (required for UEFI)
5. Start the process

### Creating Linux Live USB

1. Download Linux distribution ISO
2. Select USB drive (4GB+ recommended)
3. Select Linux ISO
4. Configure:
   - Partition: MBR or GPT
   - Boot: BIOS or Dual
   - Filesystem: FAT32
5. Start the process

### Creating Multi-Boot USB

1. Use a larger USB drive (16GB+)
2. Create first bootable ISO
3. After completion, add additional ISOs manually
4. Use a boot manager like GRUB or Syslinux

## Troubleshooting

### USB Not Detected

- Try a different USB port
- Run as Administrator/root
- Check if drive is mounted elsewhere
- Try unplugging and reconnecting

### ISO Not Recognized

- Verify ISO file is not corrupted
- Check file extension is .iso
- Try manually selecting ISO type
- Ensure ISO is bootable

### Boot Sector Write Fails

- Run as Administrator/root
- Try different boot type
- Use direct write mode
- Check USB drive for errors

### Creation Fails Mid-Process

- Ensure USB drive is not in use
- Close other applications
- Try a different USB drive
- Check available disk space

### USB Won't Boot

- Verify boot mode matches system (BIOS/UEFI)
- Check boot order in BIOS/UEFI
- Try different USB port
- Recreate with different options
- Test on another computer

## Tips and Best Practices

- Use a high-quality USB drive
- Backup important data before starting
- Use FAT32 for maximum compatibility
- Enable "Quick Format" for faster creation
- Test the bootable USB before relying on it
- Keep a copy of important ISOs locally
- Use Dual boot mode for universal compatibility

## Security Considerations

- Only download ISOs from trusted sources
- Verify ISO checksums when possible
- Don't use untrusted USB drives
- Scan ISOs for malware before use
- Keep SmartBoot updated

## Performance Tips

- Use USB 3.0+ drives for faster writes
- Close unnecessary applications during creation
- Use direct write mode for large ISOs
- Enable quick format when possible
- Use a fast USB port (USB 3.0+)

## Advanced Usage

### Command Line Interface

SmartBoot can be run from command line with parameters (future feature):

```bash
python main.py --device /dev/sdb --iso /path/to/image.iso --partition gpt --boot uefi
```

### Batch Processing

Create multiple bootable drives sequentially (future feature).

### Custom Boot Configurations

Advanced users can customize boot configurations (future feature).

## Getting Help

- Check the [FAQ](faq.md) for common questions
- Report issues on GitHub
- Join community discussions
- Check logs for error details

## Next Steps

- Read the [Installation Guide](installation.md)
- Check the [FAQ](faq.md)
- Contribute to the project (see [Contributing](contributing.md))
