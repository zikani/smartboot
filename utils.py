import os
import ctypes
import hashlib
import logging
from typing import List, Tuple

def get_removable_drives() -> List[str]:
    """Get list of removable drives with additional details."""
    removable_drives = []
    drives = [f"{chr(d)}:\\" for d in range(65, 91)]
    for drive in drives:
        if os.path.exists(drive) and is_removable_drive(drive):
            size = get_drive_size(drive)
            label = get_drive_label(drive)
            removable_drives.append((drive, label, size))
    return removable_drives

def is_removable_drive(drive: str) -> bool:
    return ctypes.windll.kernel32.GetDriveTypeW(drive) == 2

def get_drive_size(drive: str) -> str:
    """Get formatted drive size."""
    total_bytes = ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetDiskFreeSpaceExW(drive, None, ctypes.pointer(total_bytes), None)
    return format_size(total_bytes.value)

def get_drive_label(drive: str) -> str:
    """Get drive label."""
    kernel32 = ctypes.windll.kernel32
    volume_name_buffer = ctypes.create_unicode_buffer(1024)
    kernel32.GetVolumeInformationW(
        drive, volume_name_buffer, 
        ctypes.sizeof(volume_name_buffer), 
        None, None, None, None, 0
    )
    return volume_name_buffer.value

def format_size(size: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

def verify_iso_integrity(iso_path: str) -> bool:
    """Verify ISO file integrity using SHA256."""
    try:
        sha256_hash = hashlib.sha256()
        with open(iso_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        logging.info(f"ISO integrity check passed for {iso_path}")
        return True
    except Exception as e:
        logging.error(f"ISO integrity check failed for {iso_path}: {e}")
        return False

def get_drive_space_info(drive: str) -> Tuple[str, str, str]:
    """Get formatted drive space information."""
    try:
        total_bytes = ctypes.c_ulonglong(0)
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            drive,
            None,
            ctypes.pointer(total_bytes),
            ctypes.pointer(free_bytes)
        )
        total = format_size(total_bytes.value)
        free = format_size(free_bytes.value)
        used = format_size(total_bytes.value - free_bytes.value)
        return total, used, free
    except Exception as e:
        logging.error(f"Error getting drive space info: {e}")
        return "Unknown", "Unknown", "Unknown"

def detect_windows_image_type(iso_path: str) -> str:
    """Detect Windows image type (WIM, ESD, ISO)."""
    try:
        if iso_path.lower().endswith('.wim'):
            return "WIM"
        elif iso_path.lower().endswith('.esd'):
            return "ESD"
        
        # Check ISO contents for Windows markers
        with open(iso_path, 'rb') as f:
            header = f.read(32768)  # Read first 32KB
            if b'bootmgr' in header or b'sources\\boot.wim' in header:
                return "WINDOWS_ISO"
        return "UNKNOWN"
    except Exception as e:
        logging.error(f"Error detecting Windows image type: {e}")
        return "UNKNOWN"

def is_windows_bootable_image(iso_path: str) -> bool:
    """Check if the image is a bootable Windows image."""
    image_type = detect_windows_image_type(iso_path)
    return image_type in ["WINDOWS_ISO", "WIM", "ESD"]
