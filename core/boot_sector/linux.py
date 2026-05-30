"""
Linux Boot Sector module for SmartBoot

This module provides Linux-specific boot sector implementation.
"""

import os
import subprocess
import tempfile
import shutil
import time
from typing import Dict, Any, Callable, Optional, List

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()


class LinuxBootSector(BaseBootSector):
    """
    Linux-specific boot sector implementation.
    """
    
    def __init__(self, resource_dir: str):
        """
        Initialize the Linux boot sector implementation.
        
        Args:
            resource_dir (str): Directory for storing resources
        """
        super().__init__(resource_dir)
        self._mounted_paths = []
    
    def __del__(self):
        """Clean up resources on deletion."""
        self._cleanup_mounts()
    
    def _cleanup_mounts(self):
        """Clean up any mounted partitions."""
        if self._mounted_paths:
            for mount_point in self._mounted_paths:
                try:
                    if os.path.ismount(mount_point):
                        subprocess.run(['sudo', 'umount', mount_point], check=False, capture_output=True)
                except Exception as e:
                    logger.warning(f"Failed to unmount {mount_point}: {e}")
                
                try:
                    if os.path.exists(mount_point) and os.path.isdir(mount_point):
                        os.rmdir(mount_point)
                except Exception:
                    pass
    
    def check_admin_privileges(self) -> bool:
        """
        Check if the current process has root privileges on Linux.
        
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
            
        partition = f"{dev}{number}"
        if os.path.exists(partition):
            return partition
        
        if os.path.exists(f"{dev}p{number}"):
            return f"{dev}p{number}"
        
        return None
    
    def _mount_partition(self, partition_path: str) -> Optional[str]:
        """
        Mount a partition and return the mount point.
        
        Args:
            partition_path (str): Path to the partition
            
        Returns:
            Optional[str]: Mount point or None if failed
        """
        if not partition_path or not os.path.exists(partition_path):
            return None
        
        mount_point = f"/tmp/smartboot_mount_{int(time.time())}"
        os.makedirs(mount_point, exist_ok=True)
        
        try:
            subprocess.run(['sudo', 'mount', partition_path, mount_point], check=True, capture_output=True)
            self._mounted_paths.append(mount_point)
            return mount_point
        except Exception as e:
            logger.error(f"Error mounting partition {partition_path}: {str(e)}")
            try:
                os.rmdir(mount_point)
            except:
                pass
            return None
    
    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write BIOS boot sector on Linux using syslinux/extlinux or fallback.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        path = device.get('name')
        if not path:
            self._update(progress_callback, 0, 'Device name not found for boot sector')
            return False
        
        if not path.startswith('/dev/'):
            dev = f"/dev/{path}"
        else:
            dev = path
        
        self._update(progress_callback, 10, 'Writing BIOS boot sector...')
        
        iso_type = options.get('iso_type', 'generic').lower()
        partition_scheme = options.get('partition_scheme', 'mbr').lower()
        
        partition = self._get_device_partition(device)
        if partition:
            self._update(progress_callback, 20, f'Found partition {partition}')
            
            if shutil.which('parted'):
                try:
                    self._update(progress_callback, 30, 'Marking partition as bootable...')
                    subprocess.run(['sudo', 'parted', '-s', dev, 'set', '1', 'boot', 'on'], check=True, capture_output=True)
                    self._update(progress_callback, 40, 'Partition marked as bootable')
                except subprocess.CalledProcessError as e:
                    self._update(progress_callback, 35, f"Warning: Could not mark partition as bootable: {e.stderr if hasattr(e, 'stderr') else str(e)}")
        else:
            self._update(progress_callback, 20, f"Warning: Could not find first partition for {dev}")
        
        
        if iso_type in ['linux', 'ubuntu', 'debian', 'fedora'] or iso_type == 'generic':
            if shutil.which('syslinux'):
                try:
                    self._update(progress_callback, 50, 'Installing syslinux boot code...')
                    if partition:
                        subprocess.run(['sudo', 'syslinux', '--install', partition], check=True, capture_output=True)
                        
                        if partition_scheme == 'mbr':
                            mbr_paths = [
                                '/usr/lib/syslinux/mbr.bin',
                                '/usr/lib/syslinux/mbr/mbr.bin',
                                '/usr/share/syslinux/mbr.bin'
                            ]
                            for mbr_path in mbr_paths:
                                if os.path.exists(mbr_path):
                                    self._update(progress_callback, 70, f'Installing MBR from {mbr_path}...')
                                    subprocess.run(['sudo', 'dd', f'if={mbr_path}', f'of={dev}', 'bs=440', 'count=1'], 
                                                 check=True, capture_output=True)
                                    break
                        
                        self._update(progress_callback, 100, 'Boot sector written with syslinux')
                        return True
                except subprocess.CalledProcessError as e:
                    self._update(progress_callback, 55, f"syslinux failed: {e.stderr if hasattr(e, 'stderr') else str(e)}")
        
        if shutil.which('extlinux'):
            try:
                self._update(progress_callback, 60, 'Trying extlinux...')
                
                mount_point = device.get('drive_letter')
                is_custom_mount = False
                
                if not mount_point or not os.path.exists(mount_point):
                    mount_point = self._mount_partition(partition)
                    is_custom_mount = True
                
                if mount_point and os.path.exists(mount_point):
                    subprocess.run(['sudo', 'extlinux', '--install', mount_point], check=True, capture_output=True)
                    
                    if partition_scheme == 'mbr':
                        mbr_paths = [
                            '/usr/lib/syslinux/mbr.bin',
                            '/usr/lib/syslinux/mbr/mbr.bin',
                            '/usr/share/syslinux/mbr.bin',
                            '/usr/lib/EXTLINUX/mbr.bin'
                        ]
                        for mbr_path in mbr_paths:
                            if os.path.exists(mbr_path):
                                subprocess.run(['sudo', 'dd', f'if={mbr_path}', f'of={dev}', 'bs=440', 'count=1'], 
                                             check=True, capture_output=True)
                                break
                    
                    self._update(progress_callback, 100, 'Boot sector written with extlinux')
                    return True
            except subprocess.CalledProcessError as e:
                self._update(progress_callback, 65, f"extlinux failed: {e.stderr if hasattr(e, 'stderr') else str(e)}")
            except Exception as e:
                self._update(progress_callback, 65, f"extlinux failed: {str(e)}")
        
        if shutil.which('ms-sys'):
            try:
                self._update(progress_callback, 70, 'Trying ms-sys for MBR...')
                subprocess.run(['sudo', 'ms-sys', '-m', dev], check=True, capture_output=True)
                self._update(progress_callback, 100, 'Boot sector written with ms-sys')
                return True
            except subprocess.CalledProcessError:
                pass
        
        try:
            self._update(progress_callback, 80, 'Trying direct MBR writing...')
            
            mbr_bin = self._find_or_create_mbr()
            
            if mbr_bin and os.path.exists(mbr_bin):
                subprocess.run(['sudo', 'dd', f'if={mbr_bin}', f'of={dev}', 'bs=446', 'count=1', 'conv=notrunc'], 
                             check=True, capture_output=True)
                self._update(progress_callback, 100, 'Boot sector written with dd')
                return True
        except Exception as e:
            self._update(progress_callback, 90, f"dd fallback failed: {str(e)}")
            try:
                fdisk_cmd = f"echo -e 'a\n1\nw\n' | sudo fdisk {dev}"
                subprocess.run(fdisk_cmd, shell=True, check=False)
                self._update(progress_callback, 95, 'Attempted partition flag with fdisk')
                return True
            except:
                pass

        self._update(progress_callback, 0, 'Failed to write BIOS boot sector using any available method')
        return False
    
    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write UEFI boot files to the USB device on Linux.
        
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
                
            partition = self._get_device_partition(device)
            if not partition:
                self._update(progress_callback, 0, f"Could not find first partition on {dev}")
                return False
                
            iso_type = options.get('iso_type', 'generic').lower()
            partition_scheme = options.get('partition_scheme', 'gpt').lower()
            
            self._update(progress_callback, 10, 'Preparing UEFI boot files...')
            
            try:
                blkid_output = subprocess.run(['sudo', 'blkid', partition], 
                                           capture_output=True, text=True, check=True).stdout
                
                if 'TYPE="vfat"' not in blkid_output and partition_scheme == 'gpt':
                    self._update(progress_callback, 15, 'Warning: Partition not FAT32, attempting to reformat...')
                    try:
                        subprocess.run(['sudo', 'umount', partition], check=False, capture_output=True)
                        
                        parted_cmd = ['sudo', 'parted', '-s', dev]
                        if 'gpt' in subprocess.run([*parted_cmd, 'print'], 
                                                capture_output=True, text=True).stdout.lower():
                            subprocess.run([*parted_cmd, 'mklabel', 'gpt'], check=True, capture_output=True)
                            
                        subprocess.run([*parted_cmd, 'mkpart', 'EFI', 'fat32', '1MiB', '100%'],
                                    check=True, capture_output=True)
                        subprocess.run([*parted_cmd, 'set', '1', 'esp', 'on'],
                                    check=True, capture_output=True)
                        
                        subprocess.run(['sudo', 'mkfs.vfat', '-F', '32', partition],
                                    check=True, capture_output=True)
                        
                        self._update(progress_callback, 20, 'Partition reformatted for UEFI')
                    except Exception as e:
                        self._update(progress_callback, 16, f'Warning: Could not reformat partition: {str(e)}')
            except Exception as e:
                self._update(progress_callback, 17, f'Warning: Could not verify partition format: {str(e)}')
            
            mount_point = device.get('drive_letter')
            is_custom_mount = False
            
            if not mount_point or not os.path.exists(mount_point):
                try:
                    diskutil_output = subprocess.run(
                        ['diskutil', 'info', partition], 
                        capture_output=True, 
                        text=True, 
                        check=True
                    ).stdout
                    
                    for line in diskutil_output.splitlines():
                        if 'Mount Point:' in line:
                            mount_point = line.split(':', 1)[1].strip()
                            break
                except Exception:
                    pass
                    
                if not mount_point or not os.path.exists(mount_point):
                    mount_point = self._mount_partition(partition)
                    is_custom_mount = True
                
            if not mount_point or not os.path.exists(mount_point):
                self._update(progress_callback, 0, f"Could not mount partition {partition}")
                return False
                
            efi_boot_dir = os.path.join(mount_point, 'EFI', 'BOOT')
            os.makedirs(efi_boot_dir, exist_ok=True)
            
            self._update(progress_callback, 30, 'Created EFI directory structure')
            bootx64_path = os.path.join(efi_boot_dir, 'BOOTX64.EFI')
            
            if iso_type in ['linux', 'ubuntu', 'debian', 'fedora']:
                if shutil.which('grub-install'):
                    try:
                        self._update(progress_callback, 40, 'Installing GRUB EFI bootloader...')
                        
                        grub_dir = os.path.join(mount_point, 'boot', 'grub')
                        os.makedirs(grub_dir, exist_ok=True)
                        
                        subprocess.run([
                            'sudo', 'grub-install',
                            '--target=x86_64-efi',
                            '--efi-directory=' + mount_point,
                            '--boot-directory=' + os.path.join(mount_point, 'boot'),
                            '--removable',
                            '--no-nvram',
                            '--no-floppy'
                        ], check=True, capture_output=True)
                        
                        config_path = os.path.join(grub_dir, 'grub.cfg')
                        with open(config_path, 'w') as f:
                            f.write('search --file --set=root /boot/grub/grub.cfg\n')
                            f.write('set prefix=($root)/boot/grub\n')
                            f.write('configfile ($root)/boot/grub/grub.cfg\n')
                        
                        if os.path.exists(bootx64_path):
                            self._update(progress_callback, 100, 'UEFI boot files installed with GRUB')
                            return True
                    except Exception as e:
                        logger.error(f"GRUB installation failed: {str(e)}")
                
                efi_sources = [
                    '/usr/lib/systemd/boot/efi/systemd-bootx64.efi',
                    '/usr/share/efi/systemd-boot/systemd-bootx64.efi',
                    '/usr/lib/gummiboot/gummibootx64.efi',
                    '/usr/share/efi-x86_64/grub/grubx64.efi',
                    '/usr/lib/grub/x86_64-efi/grubx64.efi',
                    '/boot/efi/EFI/BOOT/BOOTX64.EFI',
                    '/usr/lib/syslinux/efi64/syslinux.efi',
                    '/usr/lib/refind/refind_x64.efi'
                ]
                
                for src in efi_sources:
                    if os.path.exists(src):
                        try:
                            self._update(progress_callback, 60, f'Copying UEFI bootloader from {src}...')
                            subprocess.run(['sudo', 'cp', src, bootx64_path], check=True)
                            
                            src_dir = os.path.dirname(src)
                            if 'systemd-boot' in src or 'gummiboot' in src:
                                config_dir = os.path.join(mount_point, 'loader', 'entries')
                                os.makedirs(config_dir, exist_ok=True)
                            elif 'grub' in src:
                                grub_dir = os.path.join(mount_point, 'boot', 'grub', 'x86_64-efi')
                                os.makedirs(grub_dir, exist_ok=True)
                                if os.path.exists(os.path.join(src_dir, 'grub.cfg')):
                                    subprocess.run(['sudo', 'cp', '-r', 
                                                os.path.join(src_dir, '*'),
                                                grub_dir], check=True)
                            elif 'refind' in src:
                                refind_dir = os.path.join(mount_point, 'EFI', 'BOOT')
                                if os.path.exists(os.path.join(src_dir, 'refind')):
                                    subprocess.run(['sudo', 'cp', '-r',
                                                os.path.join(src_dir, 'refind'),
                                                refind_dir], check=True)
                            
                            self._update(progress_callback, 100, 'UEFI boot files installed')
                            return True
                        except Exception as e:
                            logger.error(f"Failed to copy bootloader from {src}: {str(e)}")
                            continue
            
            self._update(progress_callback, 70, 'Looking for UEFI bootloader...')
            
            if os.path.exists(bootx64_path):
                self._update(progress_callback, 100, 'UEFI boot files already present')
                return True
                
            system_efi_dirs = [
                '/boot/efi',
                '/usr/share/efi',
                '/usr/lib/efi'
            ]
            
            for efi_dir in system_efi_dirs:
                if os.path.exists(efi_dir):
                    for root, _, files in os.walk(efi_dir):
                        for file in files:
                            if file.lower().endswith('.efi'):
                                try:
                                    src = os.path.join(root, file)
                                    self._update(progress_callback, 80, f'Found bootloader at {src}')
                                    subprocess.run(['sudo', 'cp', src, bootx64_path], check=True)
                                    self._update(progress_callback, 100, 'UEFI boot files installed')
                                    return True
                                except Exception:
                                    continue
            
            self._update(progress_callback, 90, 'Could not find UEFI bootloader locally')
            
            self._update(progress_callback, 0, 'No suitable UEFI bootloader found. Please install grub-efi package.')
            return False
            
        except Exception as e:
            logger.error(f"Error in Linux UEFI boot process: {str(e)}")
            self._update(progress_callback, 0, f"Error writing UEFI boot files: {str(e)}")
            return False
    
    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write FreeDOS boot sector on Linux.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        
        path = device.get('name')
        if not path:
            self._update(progress_callback, 0, 'Device name not found for FreeDOS boot')
            return False
        
        if not path.startswith('/dev/'):
            dev = f"/dev/{path}"
        else:
            dev = path
            
        self._update(progress_callback, 10, 'Preparing FreeDOS boot sector...')
        
        partition = self._get_device_partition(device)
        if partition:
            if shutil.which('parted'):
                try:
                    self._update(progress_callback, 20, 'Marking partition as bootable...')
                    subprocess.run(['sudo', 'parted', '-s', dev, 'set', '1', 'boot', 'on'], check=True, capture_output=True)
                except Exception:
                    pass
                    
            try:
                fdisk_cmd = f"echo -e 'a\n1\nw\n' | sudo fdisk {dev}"
                subprocess.run(fdisk_cmd, shell=True, check=False)
            except Exception:
                pass
                
        sys_paths = [
            '/usr/bin/dosemu',
            '/usr/bin/dosbox'
        ]
        
        for sys_path in sys_paths:
            if shutil.which(sys_path):
                self._update(progress_callback, 30, f'Found DOS emulator {sys_path}, could be used for FreeDOS')
                break
                
        try:
            return self.write_bios_boot(device, options, progress_callback)
        except Exception as e:
            self._update(progress_callback, 0, f"Error writing FreeDOS boot sector: {str(e)}")
            return False
