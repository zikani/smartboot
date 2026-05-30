"""
ISO Manager module for SmartBoot

This module handles ISO file operations and information retrieval.
"""

import os
import subprocess
import platform
from typing import Dict, Any, Optional

from utils.logger import default_logger as logger
from .boot_sector.manager import BootSectorManager


class ISOManager:
    """
    Class for managing ISO files.
    Handles information retrieval and validation of ISO files.
    """
    
    def __init__(self):
        """Initialize the ISO Manager."""
        logger.debug("ISOManager: Initializing ISO Manager.")
        self.system = platform.system()
    
    def get_iso_info(self, iso_path: str) -> Dict[str, Any]:
        """
        Get information about an ISO file.

        Args:
            iso_path (str): Path to the ISO file
        
        Returns:
            Dict[str, Any]: Dictionary containing ISO information
        """
        logger.debug(f"ISOManager: get_iso_info called with iso_path={iso_path}")
        if not os.path.exists(iso_path):
            logger.error(f"ISOManager: ISO file not found: {iso_path}")
            raise FileNotFoundError(f"ISO file not found: {iso_path}")
        
        if not os.path.isfile(iso_path):
            logger.error(f"ISOManager: Path is not a file: {iso_path}")
            raise ValueError(f"Path is not a file: {iso_path}")
        
        size_bytes = os.path.getsize(iso_path)
        size_mb = size_bytes / (1024 * 1024)
        size_gb = size_mb / 1024
        
        if size_gb >= 1:
            size_str = f"{size_gb:.2f} GB"
        else:
            size_str = f"{size_mb:.2f} MB"
        
        iso_type = self._determine_iso_type(iso_path)
        logger.debug(f"ISOManager: Determined ISO type: {iso_type}")
        
        return {
            'path': iso_path,
            'filename': os.path.basename(iso_path),
            'size_bytes': size_bytes,
            'size': size_str,
            'type': iso_type
        }
    
    def _determine_iso_type(self, iso_path: str) -> str:
        """
        Try to determine the type of ISO (Windows, Linux, etc.)

        Args:
            iso_path (str): Path to the ISO file
        
        Returns:
            str: Type of ISO or "Unknown"
        """
        logger.debug(f"ISOManager: _determine_iso_type called for {iso_path}")
        try:
            logger.debug(f"ISOManager: Checking filename patterns for {iso_path}")
            filename = os.path.basename(iso_path).lower()
            
            if any(win_term in filename for win_term in ['windows', 'win', 'microsoft', 'server', 'enterprise', 'professional', 'home']):
                logger.debug("ISOManager: Detected Windows ISO by filename.")
                return "Windows"
            
            linux_distros = ['ubuntu', 'debian', 'fedora', 'centos', 'rhel', 'red hat', 'suse', 'opensuse', 
                            'arch', 'manjaro', 'gentoo', 'mint', 'kali', 'parrot', 'zorin', 'elementary',
                            'linux', 'slackware', 'puppy', 'tails', 'knoppix', 'bodhi', 'deepin']
            if any(distro in filename for distro in linux_distros):
                logger.debug("ISOManager: Detected Linux ISO by filename.")
                return "Linux"
            
            if any(mac_term in filename for mac_term in ['macos', 'osx', 'mac os', 'apple', 'hackintosh', 'catalina', 'mojave', 'sierra', 'monterey', 'ventura']):
                logger.debug("ISOManager: Detected macOS ISO by filename.")
                return "macOS"
            
            try:
                logger.debug(f"ISOManager: Attempting advanced detection for {iso_path}")
                if self.system == "Windows":

                    mount_cmd = [
                        "powershell",
                        "-Command",
                        f"$mountResult = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; $driveLetter = ($mountResult | Get-Volume).DriveLetter; $driveLetter"
                    ]
                    result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=10)
                    drive_letter = result.stdout.strip() + ":\\"
                    
                    try:
                        if os.path.exists(os.path.join(drive_letter, "sources", "install.wim")) or \
                           os.path.exists(os.path.join(drive_letter, "sources", "install.esd")):
                            logger.debug("ISOManager: Detected Windows ISO by content.")
                            return "Windows"
                        
                        if os.path.exists(os.path.join(drive_letter, "casper")) or \
                           os.path.exists(os.path.join(drive_letter, "isolinux")) or \
                           os.path.exists(os.path.join(drive_letter, "live")):
                            logger.debug("ISOManager: Detected Linux ISO by content.")
                            return "Linux"
                        
                        if os.path.exists(os.path.join(drive_letter, "System", "Library")) or \
                           os.path.exists(os.path.join(drive_letter, ".disk")):
                            logger.debug("ISOManager: Detected macOS ISO by content.")
                            return "macOS"
                    finally:
                        unmount_cmd = [
                            "powershell",
                            "-Command",
                            f"Dismount-DiskImage -ImagePath '{iso_path}'"
                        ]
                        subprocess.run(unmount_cmd, capture_output=True, timeout=5)
            except Exception as e:
                logger.warning(f"ISOManager: Advanced detection failed: {str(e)}")
                
            size_bytes = os.path.getsize(iso_path)
            size_gb = size_bytes / (1024 * 1024 * 1024)
            
            if size_gb > 4.5:
                if size_gb > 8.0:
                    logger.debug("ISOManager: Large ISO, likely Windows.")
                    return "Windows (likely)"
                logger.debug("ISOManager: Large ISO, unknown type.")
                return "Unknown (large ISO)"
            else:
                logger.debug("ISOManager: Small ISO, unknown type.")
                return "Unknown (small ISO)"
                
        except Exception as e:
            logger.warning(f"ISOManager: Exception in _determine_iso_type: {str(e)}")
            return "Unknown"
    
    def validate_iso(self, iso_path: str) -> bool:
        """
        Validate that the file is a proper ISO file.

        Args:
            iso_path (str): Path to the ISO file
        
        Returns:
            bool: True if valid, False otherwise
        """
        logger.debug(f"ISOManager: validate_iso called with iso_path={iso_path}")
        try:
            if not iso_path.lower().endswith('.iso'):
                logger.warning(f"ISOManager: File does not have .iso extension: {iso_path}")
                return False
            
            if not os.path.exists(iso_path):
                logger.warning(f"ISOManager: File does not exist: {iso_path}")
                return False
                
            size_bytes = os.path.getsize(iso_path)
            if size_bytes == 0:
                logger.warning(f"ISOManager: File is empty: {iso_path}")
                return False
                
            if size_bytes < 10 * 1024 * 1024:
                logger.warning(f"ISOManager: File too small to be bootable ISO: {iso_path}")
                return False
            
            try:
                if self.system in ["Linux", "Darwin"]:
                    result = subprocess.run(["file", "-b", iso_path], capture_output=True, text=True, timeout=5)
                    output = result.stdout.lower()
                    logger.debug(f"ISOManager: file command output: {output}")
                    if "iso 9660" in output or "iso image" in output or "bootable" in output:
                        logger.debug("ISOManager: Detected ISO by file command.")
                        return True
                
                elif self.system == "Windows":
                    try:
                        mount_cmd = [
                            "powershell",
                            "-Command",
                            f"$mountResult = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; $driveLetter = ($mountResult | Get-Volume).DriveLetter; $driveLetter"
                        ]
                        result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=10)
                        drive_letter = result.stdout.strip() + ":\\"
                        logger.debug(f"ISOManager: Mounted ISO at {drive_letter}")
                        valid = False
                        if os.path.exists(drive_letter):
                            if (os.path.exists(os.path.join(drive_letter, "boot")) or
                                os.path.exists(os.path.join(drive_letter, "isolinux")) or
                                os.path.exists(os.path.join(drive_letter, "sources")) or
                                os.path.exists(os.path.join(drive_letter, "casper")) or
                                os.path.exists(os.path.join(drive_letter, "EFI"))):
                                valid = True
                        return valid
                    except Exception as e:
                        logger.warning(f"ISOManager: Exception in mounting ISO: {str(e)}")
            except Exception as e:
                logger.warning(f"ISOManager: Exception in validate_iso: {str(e)}")
            
            result = size_bytes > 100 * 1024 * 1024
            logger.debug(f"ISOManager: Final validation result: {result}")
            return result
        
        except Exception as e:
            logger.error(f"ISOManager: Error validating ISO: {str(e)}")
            return False
