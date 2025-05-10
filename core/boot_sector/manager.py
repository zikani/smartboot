"""
Boot Sector Manager module for SmartBoot

This module provides the main interface for writing boot sectors to USB devices.
It delegates platform-specific operations to specialized modules.
"""

import os
import platform
import tempfile
from typing import Dict, Any, Callable, Optional, List

from utils.logger import get_logger
from .base import BaseBootSector
from .windows import WindowsBootSector
from .linux import LinuxBootSector
from .macos import MacOSBootSector

logger = get_logger()


class BootSectorManager:
    """
    Manager class for writing boot sectors to USB devices.
    Handles platform detection and delegates to appropriate implementation.
    """
    
    def __init__(self):
        """Initialize the Boot Sector Manager."""
        self.system = platform.system()
        # Track downloaded/extracted resources
        self.resource_dir = os.path.join(tempfile.gettempdir(), "smartboot_resources")
        os.makedirs(self.resource_dir, exist_ok=True)
        
        # Create platform-specific implementation
        if self.system == 'Windows':
            self._impl = WindowsBootSector(self.resource_dir)
        elif self.system == 'Linux':
            self._impl = LinuxBootSector(self.resource_dir)
        elif self.system == 'Darwin':
            self._impl = MacOSBootSector(self.resource_dir)
        else:
            # Fallback to base implementation which will report unsupported operations
            self._impl = BaseBootSector(self.resource_dir)
            
        logger.debug(f"BootSectorManager: Initialized for {self.system}")
    
    def write_boot_sector(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write boot sector to the USB device based on selected options.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable[[int, str], None]]): Callback for progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if 'error' in device:
                self._update(progress_callback, 0, f"Error: {device['error']}")
                return False
            
            # Check for admin/root privileges first
            if not self._impl.check_admin_privileges():
                self._update(progress_callback, 0, "Error: Administrator/root privileges required. Please run SmartBoot with elevated privileges.")
                return False
            
            # Get boot type from options
            boot_type = options.get('boot_type', 'bios').lower()
            
            self._update(progress_callback, 5, f"Preparing to write {boot_type} boot sector...")
            
            # Choose the appropriate boot sector method
            if boot_type == 'freedos':
                return self._impl.write_freedos_boot(device, options, progress_callback)
            elif boot_type == 'uefi':
                return self._impl.write_uefi_boot(device, options, progress_callback)
            elif boot_type == 'dual':
                # Write both BIOS and UEFI boot sectors
                bios_success = self._impl.write_bios_boot(device, options, progress_callback)
                if not bios_success:
                    self._update(progress_callback, 50, "Warning: BIOS boot sector failed, trying UEFI...")
                uefi_success = self._impl.write_uefi_boot(device, options, progress_callback)
                if not uefi_success:
                    self._update(progress_callback, 75, "Warning: UEFI boot sector failed")
                return bios_success or uefi_success  # As long as one works, we consider it a success
            else:  # Default to BIOS
                return self._impl.write_bios_boot(device, options, progress_callback)
        except Exception as e:
            logger.error(f"Error writing boot sector: {str(e)}")
            self._update(progress_callback, 0, f"Error writing boot sector: {str(e)}")
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
