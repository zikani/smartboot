"""
macOS Boot Sector module for SmartBoot

This module provides macOS-specific boot sector implementation.
"""

import os
import subprocess
import tempfile
import shutil
from typing import Dict, Any, Callable, Optional, List

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()


class MacOSBootSector(BaseBootSector):
    """
    macOS-specific boot sector implementation.
    """
    
    def check_admin_privileges(self) -> bool:
        """
        Check if the current process has root privileges on macOS.
        
        Returns:
            bool: True if has root privileges, False otherwise
        """
        try:
            return subprocess.run(['sudo', '-n', 'true'], check=False, capture_output=True).returncode == 0
        except Exception:
            return False
    
    def _get_device_partition(self, device: Dict[str, Any], number: int = 1) -> Optional[str]:
        """
        Get the path to a specific partition on a device.
        
        Args:
            device (Dict[str, Any]): Device information
            number (int): Partition number (1-based)
            
        Returns:
            Optional[str]: Partition path or None if not found
        """
        path = device.get('name')
        if not path:
            return None
        
        if not path.startswith('/dev/'):
            dev = f"/dev/{path}"
        else:
            dev = path
            
        partition_formats = [
            f"{dev}s{number}",
            f"{dev}{number}"
        ]
        
        for partition in partition_formats:
            if os.path.exists(partition):
                return partition
                
        return None
    
    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write BIOS boot sector on macOS (limited functionality).
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update(progress_callback, 10, 'Writing BIOS boot sector on macOS...')
        
        path = device.get('name')
        if not path:
            self._update(progress_callback, 0, 'Device name not found for boot sector')
            return False
        
        if not path.startswith('/dev/'):
            dev = f"/dev/{path}"
        else:
            dev = path
        
        partition = self._get_device_partition(device)
        if not partition:
            if os.path.exists(f"{dev}s1"):
                partition = f"{dev}s1"
        
        try:
            self._update(progress_callback, 50, 'Writing generic MBR with dd...')
            
            mbr_bin = self._find_or_create_mbr()
            
            if mbr_bin and os.path.exists(mbr_bin):
                subprocess.run(['sudo', 'diskutil', 'unmountDisk', dev], check=False, capture_output=True)
                
                subprocess.run(['sudo', 'dd', f'if={mbr_bin}', f'of={dev}', 'bs=446', 'count=1', 'conv=notrunc'], 
                             check=True, capture_output=True)
                
                self._update(progress_callback, 100, 'Generic boot sector written with dd')
                return True
        except Exception as e:
            self._update(progress_callback, 0, f"Error writing boot sector: {str(e)}")
            return False
    
    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write UEFI boot files to the USB device on macOS.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.check_admin_privileges():
                self._update(progress_callback, 0, "Error: Root privileges required for writing UEFI boot files")
                return False

            path = device.get('name')
            if not path:
                self._update(progress_callback, 0, 'Device name not found for UEFI boot')
                return False
            
            if not path.startswith('/dev/'):
                dev = f"/dev/{path}"
            else:
                dev = path
            
            self._update(progress_callback, 10, 'Preparing UEFI boot files...')
            
            partition = self._get_device_partition(device)
            if not partition:
                self._update(progress_callback, 0, f"Could not find partition on {dev}")
                return False
            
            mount_info = subprocess.run(['diskutil', 'info', partition], 
                                     capture_output=True, text=True, check=False).stdout
            
            mount_point = None
            for line in mount_info.splitlines():
                if 'Mount Point:' in line:
                    mount_point = line.split(':', 1)[1].strip()
                    break
            
            if not mount_point or not os.path.exists(mount_point):
                try:
                    self._update(progress_callback, 20, f'Mounting {partition}...')
                    mount_result = subprocess.run(['diskutil', 'mount', partition], 
                                               capture_output=True, text=True, check=True).stdout
                    
                    for line in mount_result.splitlines():
                        if 'on' in line and partition in line:
                            parts = line.split('on')
                            if len(parts) > 1:
                                mount_point = parts[1].strip()
                                break
                except Exception as e:
                    self._update(progress_callback, 0, f"Error mounting partition: {str(e)}")
                    return False
            
            if not mount_point or not os.path.exists(mount_point):
                self._update(progress_callback, 0, f"Could not find or create mount point for {partition}")
                return False
            
            efi_boot_dir = os.path.join(mount_point, 'EFI', 'BOOT')
            os.makedirs(efi_boot_dir, exist_ok=True)
            
            self._update(progress_callback, 30, 'Created EFI directory structure')
            
            bootx64_path = os.path.join(efi_boot_dir, 'BOOTX64.EFI')
            
            efi_sources = [
                '/usr/standalone/i386/apfs.efi',
                '/usr/standalone/i386/EfiLoginUI.efi',
                '/System/Library/CoreServices/boot.efi',
                '/usr/share/syslinux/efi64/syslinux.efi'
            ]
            
            for src in efi_sources:
                if os.path.exists(src):
                    try:
                        self._update(progress_callback, 40, f'Copying bootloader from {src}...')
                        shutil.copy2(src, bootx64_path)
                        self._update(progress_callback, 100, 'UEFI boot files installed')
                        return True
                    except Exception as e:
                        logger.error(f"Failed to copy bootloader from {src}: {str(e)}")
                        continue
            
            self._update(progress_callback, 0, "Could not find suitable UEFI bootloader on macOS")
            return False
            
        except Exception as e:
            logger.error(f"Error in macOS UEFI boot process: {str(e)}")
            self._update(progress_callback, 0, f"Error writing UEFI boot files: {str(e)}")
            return False
    
    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write FreeDOS boot sector on macOS.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        
        return self.write_bios_boot(device, options, progress_callback)
