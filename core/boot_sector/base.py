"""
Base Boot Sector module for SmartBoot

This module provides the base class for platform-specific boot sector implementations.
"""

import os
import tempfile
from typing import Dict, Any, Callable, Optional, List

from utils.logger import get_logger

logger = get_logger()


class BaseBootSector:
    """
    Base class for boot sector implementations.
    Defines the interface that all platform-specific implementations must follow.
    """
    
    def __init__(self, resource_dir: str):
        """
        Initialize the base boot sector implementation.
        
        Args:
            resource_dir (str): Directory for storing resources
        """
        self.resource_dir = resource_dir
        self._mounted_paths = []
    
    def __del__(self):
        """Clean up resources on deletion."""
        self._cleanup_mounts()
    
    def _cleanup_mounts(self):
        """Clean up any mounted partitions."""
        pass
    
    def _get_device_drive(self, device: Dict[str, Any]) -> Optional[str]:
        """
        Get the drive letter from device dictionary with backward compatibility.
        
        Args:
            device (Dict[str, Any]): Device information dictionary
            
        Returns:
            Optional[str]: Drive letter or None if not found
        """
        return device.get('drive_letter') or device.get('drive')
    
    def _normalize_device_path(self, device_name: str) -> str:
        """
        Normalize device path by ensuring it starts with /dev/ for Linux/macOS.
        
        Args:
            device_name (str): Device name or path
            
        Returns:
            str: Normalized device path
        """
        if not device_name.startswith('/dev/'):
            return f"/dev/{device_name}"
        return device_name
    
    def _validate_device_dict(self, device: Dict[str, Any], required_keys: list = None) -> bool:
        """
        Validate device dictionary has required keys.
        
        Args:
            device (Dict[str, Any]): Device information dictionary
            required_keys (list): List of required keys (default: ['name'])
            
        Returns:
            bool: True if valid, False otherwise
        """
        if required_keys is None:
            required_keys = ['name']
        
        for key in required_keys:
            if key not in device:
                return False
        return True
    
    def check_admin_privileges(self) -> bool:
        """
        Check if the current process has administrator/root privileges.
        
        Returns:
            bool: True if has admin privileges, False otherwise
        """
        return False
    
    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write BIOS boot sector using appropriate method for the OS.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable[[int, str], None]]): Callback for progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update(progress_callback, 0, "BIOS boot sector writing not supported on this platform")
        return False
    
    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write UEFI boot files to the USB device.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable[[int, str], None]]): Callback for progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update(progress_callback, 0, "UEFI boot sector writing not supported on this platform")
        return False
    
    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write FreeDOS boot sector to the USB device.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable[[int, str], None]]): Callback for progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update(progress_callback, 0, "FreeDOS boot sector writing not supported on this platform")
        return False
    
    def _update(
        self, 
        progress_callback: Optional[Callable[[int, str], None]], 
        progress: int, 
        message: str
    ) -> None:
        """
        Update progress and log messages.
        
        Args:
            progress_callback: Function to call with progress updates
            progress: Progress percentage (0-100)
            message: Progress message
        """
        logger.debug(f"Boot sector progress: {progress}% - {message}")
        if progress_callback:
            progress_callback(progress, message)
    
    def _find_or_create_mbr(self) -> str:
        """
        Find or create a generic MBR file.
        
        Returns:
            str: Path to the MBR file
        """
        mbr_bin = os.path.join(self.resource_dir, 'mbr.bin')
        if not os.path.exists(mbr_bin):
            with open(mbr_bin, 'wb') as f:
                f.write(bytes.fromhex('33C08ED0BC007C8BF4507C50068C067C681E0001066'))
                f.write(bytes.fromhex('8B1E5C7C66FF065A7CB8C07CEB4E0752E280F2B280'))
                f.write(bytes.fromhex('F6F372CD13731F8BF5EA007C0000B041BBAA55CD13'))
                f.write(bytes.fromhex('720C817FFE7D55AA740B33C0CD13EB5E8A5640668B'))
                f.write(bytes.fromhex('1E5C7C668B1E5C7C66FF065A7CB8C07C'))
        
        return mbr_bin
