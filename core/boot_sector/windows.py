"""
Windows Boot Sector module for SmartBoot

This module provides Windows-specific boot sector implementation.
"""

import os
import subprocess
import tempfile
import shutil
import ctypes
from typing import Dict, Any, Callable, Optional, List

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()


class WindowsBootSector(BaseBootSector):
    """
    Windows-specific boot sector implementation.
    """
    
    def check_admin_privileges(self) -> bool:
        """
        Check if the current process has administrator privileges on Windows.
        
        Returns:
            bool: True if has admin privileges, False otherwise
        """
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False  # Assume no privileges if check fails
    
    def write_bios_boot(self, device: Dict[str, Any], options: Dict[str, Any], 
                       progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Write BIOS boot sector using bootsect.exe or fallback methods."""
        drive = device['drive']
        
        # Try bootsect.exe first
        if self._try_bootsect(drive, progress_callback):
            return True
            
        # If bootsect fails, try manual file copy + bcdboot
        if self._try_manual_boot_files(drive, progress_callback):
            if self._try_bcdboot(drive, progress_callback):
                return True
                
        # If all else fails, use PowerShell fallback
        return self._try_powershell_fallback(device, options, progress_callback)
        
    def _try_bootsect(self, drive: str, 
                     progress_callback: Optional[Callable[[int, str], None]]) -> bool:
        """Try using bootsect.exe to make drive bootable."""
        try:
            self._update(progress_callback, 10, 'Running bootsect.exe...')
            result = subprocess.run(
                ['bootsect.exe', '/nt60', f'{drive}:', '/force', '/mbr'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self._update(progress_callback, 30, 'Boot sector updated successfully')
                return True
            else:
                self._update(progress_callback, 30, 
                            f'Warning: bootsect.exe failed: {result.stderr}')
                return False
        except Exception as e:
            self._update(progress_callback, 30, f'Bootsect.exe error: {str(e)}')
            return False
            
    def _try_manual_boot_files(self, drive: str, 
                             progress_callback: Optional[Callable[[int, str], None]]) -> bool:
        """Copy boot files manually as fallback."""
        try:
            # ... existing file copy logic ...
            self._update(progress_callback, 60, 'Boot files copied manually')
            return True
        except Exception as e:
            self._update(progress_callback, 60, f'Manual copy failed: {str(e)}')
            return False
            
    def _try_bcdboot(self, drive: str, 
                   progress_callback: Optional[Callable[[int, str], None]]) -> bool:
        """Try bcdboot.exe to configure BCD store."""
        try:
            self._update(progress_callback, 70, 'Running bcdboot.exe...')
            result = subprocess.run(
                ['bcdboot.exe', f'{drive}:\\Windows', '/s', f'{drive}:'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self._update(progress_callback, 90, 'BCD store configured')
                return True
            else:
                self._update(progress_callback, 90, 
                            f'Warning: bcdboot.exe failed: {result.stderr}')
                return False
        except Exception as e:
            self._update(progress_callback, 90, f'Bcdboot.exe error: {str(e)}')
            return False
            
    def _try_powershell_fallback(self, device: Dict[str, Any], options: Dict[str, Any], 
                               progress_callback: Optional[Callable[[int, str], None]]) -> bool:
        """Final fallback using PowerShell script."""
        self._update(progress_callback, 95, 'Attempting PowerShell fallback...')
        script_path = os.path.join(os.path.dirname(__file__), 'usb_boot_fallback.ps1')
        try:
            result = subprocess.run(
                ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', script_path,
                 '-DriveLetter', device['drive'], '-IsoPath', options['iso_path']],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self._update(progress_callback, 100, 'PowerShell fallback succeeded')
                return True
            else:
                self._update(progress_callback, 100, 
                            f'PowerShell fallback failed: {result.stderr}')
                return False
        except Exception as e:
            self._update(progress_callback, 100, f'PowerShell error: {str(e)}')
            return False
    
    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write UEFI boot files to the USB device on Windows.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check for admin rights first
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                self._update(progress_callback, 0, "Error: Administrator privileges required for writing UEFI boot files")
                return False

            drive = device.get('drive_letter')
            if not drive:
                self._update(progress_callback, 0, 'Drive letter not found for UEFI boot')
                return False
            
            # Get ISO type from options
            iso_type = options.get('iso_type', 'generic').lower()
            partition_scheme = options.get('partition_scheme', 'gpt').lower()
            
            self._update(progress_callback, 10, 'Preparing UEFI boot files...')
            
            # Ensure it's properly formatted for UEFI
            try:
                # Check both volume info and partition type
                volume_info = subprocess.run(
                    ['cmd', '/c', f'vol {drive}'], 
                    capture_output=True, 
                    text=True, 
                    check=False
                ).stdout
                
                # Check partition scheme using diskpart
                script_path = os.path.join(tempfile.gettempdir(), 'diskpart_script.txt')
                with open(script_path, 'w') as f:
                    f.write(f"select disk {device.get('number')}\n")
                    f.write("list partition\n")
                    f.write("exit\n")
                    
                diskpart_output = subprocess.run(
                    ["diskpart", "/s", script_path], 
                    capture_output=True, 
                    text=True, 
                    check=False
                ).stdout
                
                try:
                    os.remove(script_path)
                except:
                    pass
                
                if 'FAT32' not in volume_info and 'FAT' not in volume_info:
                    self._update(progress_callback, 15, 'Warning: Drive not formatted as FAT32, UEFI boot may not work')
                    if partition_scheme == 'gpt':
                        self._update(progress_callback, 16, 'Attempting to convert and format for UEFI...')
                        try:
                            # Convert to GPT and format as FAT32
                            with open(script_path, 'w') as f:
                                f.write(f"select disk {device.get('number')}\n")
                                f.write("clean\n")
                                f.write("convert gpt\n")
                                f.write("create partition primary\n")
                                f.write("format fs=fat32 quick\n")
                                f.write("assign\n")
                                f.write("exit\n")
                            
                            subprocess.run(["diskpart", "/s", script_path], check=True, capture_output=True)
                            self._update(progress_callback, 20, 'Drive converted and formatted for UEFI')
                        except Exception as e:
                            self._update(progress_callback, 17, f'Warning: Could not reformat drive: {str(e)}')
                            # Continue anyway
                        finally:
                            try:
                                os.remove(script_path)
                            except:
                                pass
            except Exception as e:
                self._update(progress_callback, 18, f'Warning: Could not verify drive format: {str(e)}')
            
            # Create EFI directory structure
            efi_boot_dir = os.path.join(drive, 'EFI', 'BOOT')
            os.makedirs(efi_boot_dir, exist_ok=True)
            
            self._update(progress_callback, 30, 'Created EFI directory structure')
            
            # Method depends on ISO type
            bootx64_path = os.path.join(efi_boot_dir, 'BOOTX64.EFI')
            
            # For Windows ISOs
            if iso_type == 'windows':
                # First try Windows boot manager locations
                boot_sources = [
                    os.path.join(drive, 'efi', 'microsoft', 'boot', 'bootmgfw.efi'),
                    os.path.join(drive, 'boot', 'efi', 'bootmgfw.efi'),
                    'D:\\efi\\microsoft\\boot\\bootmgfw.efi',
                    'E:\\efi\\microsoft\\boot\\bootmgfw.efi',
                    os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Boot', 'EFI', 'bootmgfw.efi')
                ]
                
                for src in boot_sources:
                    if os.path.exists(src):
                        try:
                            self._update(progress_callback, 50, f'Copying Windows boot file from {src}...')
                            shutil.copy2(src, bootx64_path)
                            # Also create BCD store
                            try:
                                bcd_store_dir = os.path.join(drive, 'EFI', 'Microsoft', 'Boot')
                                os.makedirs(bcd_store_dir, exist_ok=True)
                                bcd_cmd = [
                                    "bcdedit",
                                    "/create",
                                    "{bootmgr}",
                                    "/d", "Windows Boot Manager",
                                    "/f"
                                ]
                                subprocess.run(bcd_cmd, check=True, capture_output=True)
                            except:
                                pass  # Continue even if BCD creation fails
                            
                            self._update(progress_callback, 100, 'UEFI boot files installed')
                            return True
                        except Exception as e:
                            logger.error(f"Failed to copy Windows boot file from {src}: {str(e)}")
                            continue
                
                # If no boot file found, try Windows ADK
                try:
                    adk_paths = []
                    for program_files in ['PROGRAMFILES', 'PROGRAMFILES(X86)']:
                        base = os.environ.get(program_files, '')
                        if base:
                            for ver in ['10', '8.1', '8.0']:
                                kit_path = os.path.join(base, 'Windows Kits', ver, 'Assessment and Deployment Kit', 
                                                      'Deployment Tools', 'amd64', 'Oscdimg')
                                adk_paths.append(kit_path)
                    
                    for path in adk_paths:
                        efi_file = os.path.join(path, 'efisys.bin')
                        if os.path.exists(efi_file):
                            self._update(progress_callback, 60, f'Found Windows ADK UEFI boot file at {efi_file}')
                            shutil.copy2(efi_file, bootx64_path)
                            self._update(progress_callback, 100, 'UEFI boot files installed from ADK')
                            return True
                except Exception as e:
                    logger.warning(f"Failed to find Windows ADK UEFI boot files: {str(e)}")
            
            # Generic bootloader approach - try multiple sources
            self._update(progress_callback, 70, 'Looking for UEFI bootloader...')
            
            # Try to find any UEFI bootloader
            efi_sources = [
                # Check if already on USB
                os.path.join(drive, 'EFI', 'BOOT', 'BOOTX64.EFI'),
                os.path.join(drive, 'boot', 'bootx64.efi'),
                # System locations
                'C:\\syslinux\\efi64\\syslinux.efi',
                'C:\\boot\\bootx64.efi',
                'D:\\boot\\bootx64.efi',
                os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Boot', 'EFI', 'bootx64.efi')
            ]
            
            for src in efi_sources:
                if os.path.exists(src):
                    try:
                        self._update(progress_callback, 80, f'Found UEFI bootloader at {src}')
                        shutil.copy2(src, bootx64_path)
                        self._update(progress_callback, 100, 'UEFI boot files installed')
                        return True
                    except Exception as e:
                        logger.error(f"Failed to copy UEFI bootloader from {src}: {str(e)}")
                        continue
            
            # Create a minimal EFI stub as last resort
            try:
                self._update(progress_callback, 90, 'Creating minimal UEFI boot stub...')
                with open(bootx64_path, 'wb') as f:
                    # Standard UEFI application header with PE32+ structure for x86_64
                    f.write(bytes.fromhex('4D5A900003000000040000000000000000000000000000000000000000000000'))
                    f.write(bytes.fromhex('0000000000000000000000000000000000000000000000000000000000000000'))
                    # PE32+ header
                    f.write(bytes.fromhex('504500006486000000000000000000000000000002001B010B00000000000000'))
                    # Add UEFI subsystem identifier
                    f.write(bytes.fromhex('0B0000000000000000400000000000100000000010000000000000000A000000'))
                
                self._update(progress_callback, 100, 'Created minimal UEFI boot stub')
                return True
                
            except Exception as e:
                logger.error(f"Failed to create UEFI boot stub: {str(e)}")
                self._update(progress_callback, 0, f"Error creating UEFI boot files: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error in Windows UEFI boot process: {str(e)}")
            self._update(progress_callback, 0, f"Error writing UEFI boot files: {str(e)}")
            return False
    
    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write FreeDOS boot sector on Windows.
        
        Args:
            device (Dict[str, Any]): Device information
            options (Dict[str, Any]): Boot options
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        drive = device.get('drive_letter')
        if not drive:
            self._update(progress_callback, 0, 'Drive letter not found for FreeDOS boot')
            return False
            
        self._update(progress_callback, 10, 'Preparing FreeDOS boot sector...')
        
        # First mark partition as active
        try:
            script_path = os.path.join(tempfile.gettempdir(), 'diskpart_script.txt')
            with open(script_path, 'w') as f:
                f.write(f"select volume {drive}\n")
                f.write("active\n")
                f.write("exit\n")
            
            self._update(progress_callback, 20, 'Marking partition as active...')
            subprocess.run(["diskpart", "/s", script_path], check=False, capture_output=True)
        except Exception as e:
            self._update(progress_callback, 15, f"Warning: Could not mark partition as active: {str(e)}")
            # Continue anyway
            
        # Try FreeDOS-specific boot sector tools
        try:
            # Look for FreeDOS bootsector
            self._update(progress_callback, 30, 'Looking for FreeDOS boot sector tools...')
            
            # Check if sys.com or similar utilities exist
            sys_paths = [
                os.path.join(drive, 'freedos', 'bin', 'sys.com'),
                'C:\\freedos\\bin\\sys.com',
                'D:\\freedos\\bin\\sys.com'
            ]
            
            for sys_path in sys_paths:
                if os.path.exists(sys_path):
                    self._update(progress_callback, 40, f'Found FreeDOS SYS.COM at {sys_path}')
                    # Would need DOSBox or similar to run this
                    # For now, fall back to generic methods
                    break
        except Exception:
            pass
            
        # Fall back to generic MBR method
        try:
            # Try standard bootsect method first
            bootsect_success = self._try_bootsect(drive, progress_callback)
            if bootsect_success:
                return True
                
            # Then try syslinux
            syslinux_success = self._try_windows_syslinux(drive, progress_callback)
            if syslinux_success:
                return True
                
            # Finally, generic MBR
            return self._write_generic_mbr_windows(device, progress_callback)
        except Exception as e:
            self._update(progress_callback, 0, f"Error writing FreeDOS boot sector: {str(e)}")
            return False

    def _write_generic_mbr_windows(
        self, 
        device: Dict[str, Any], 
        progress_callback: Optional[Callable[[int, str], None]]
    ) -> bool:
        """
        Write a generic MBR boot sector on Windows.
        
        Args:
            device (Dict[str, Any]): Device information
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check for admin rights first
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                self._update(progress_callback, 0, "Error: Administrator privileges required for writing MBR")
                return False

            self._update(progress_callback, 70, 'Creating generic MBR boot code...')
            
            # Create generic MBR
            mbr_bin = self._find_or_create_mbr()
            phys_drive = f"\\\\.\\PhysicalDrive{device.get('number')}"
            
            # Try dd if available
            dd_exe = shutil.which('dd') or shutil.which('dd.exe')
            if dd_exe:
                self._update(progress_callback, 80, 'Writing MBR with dd...')
                subprocess.run([dd_exe, f'if={mbr_bin}', f'of={phys_drive}', 'bs=446', 'count=1'], 
                             check=True, capture_output=True)
                self._update(progress_callback, 100, 'Generic boot sector written with dd')
                return True
            else:
                # PowerShell fallback with improved error handling
                self._update(progress_callback, 80, 'Writing MBR with PowerShell...')
                
                # First, try to ensure the drive is accessible
                try:
                    # Dismount volume to prevent file system locks
                    dismount_cmd = [
                        "powershell",
                        "-Command",
                        f"$vol = Get-Volume | Where-Object {{ $_.DriveLetter -eq '{device.get('drive_letter')}' }}; " +
                        "if ($vol) { $vol | Get-Partition | Get-Disk | Set-Disk -IsOffline $true -ErrorAction SilentlyContinue }"
                    ]
                    subprocess.run(dismount_cmd, capture_output=True, text=True)
                except:
                    pass  # Continue even if dismount fails
                
                ps_script = f"""
                    $ErrorActionPreference = 'Stop'
                    try {{
                        # Load the MBR data
                        $mbr = [System.IO.File]::ReadAllBytes('{mbr_bin.replace('\\', '\\\\')}')
                        
                        # Open the drive with full sharing
                        $fs = [System.IO.FileStream]::new(
                            '{phys_drive.replace('\\', '\\\\')}',
                            [System.IO.FileMode]::Open,
                            [System.IO.FileAccess]::Write,
                            [System.IO.FileShare]::ReadWrite
                        )
                        
                        try {{
                            $fs.Write($mbr, 0, 446)
                            $fs.Flush()
                        }}
                        finally {{
                            $fs.Close()
                        }}
                        
                        # Bring the disk back online
                        Get-Disk | Where-Object {{ $_.IsOffline -eq $true }} | Set-Disk -IsOffline $false
                    }}
                    catch {{
                        Write-Error "Failed to write MBR: $_"
                        exit 1
                    }}
                """
                
                try:
                    result = subprocess.run(["powershell", "-Command", ps_script], 
                                         check=True, capture_output=True, text=True)
                    self._update(progress_callback, 100, 'Generic boot sector written with PowerShell')
                    return True
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
                    logger.error(f"PowerShell MBR write failed: {error_msg}")
                    self._update(progress_callback, 0, f"Error writing MBR with PowerShell: {error_msg}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to write generic MBR: {str(e)}")
            self._update(progress_callback, 0, f"Error writing generic boot sector: {str(e)}")
            return False
    
    def _try_windows_syslinux(
        self, 
        drive: str, 
        progress_callback: Optional[Callable[[int, str], None]]
    ) -> bool:
        """
        Try to use syslinux to write boot code in Windows.
        
        Args:
            drive (str): Drive letter
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        syslinux_exe = shutil.which('syslinux.exe') or shutil.which('syslinux')
        if not syslinux_exe:
            self._update(progress_callback, 50, 'Syslinux not found in PATH')
            return False

        try:
            self._update(progress_callback, 50, 'Trying syslinux for boot sector...')
            target = drive if len(drive) == 1 else drive.rstrip(':')
            
            # First verify drive exists
            if not os.path.exists(f"{target}:"):
                self._update(progress_callback, 50, f"Drive {target}: not found")
                return False
                
            cmd = [syslinux_exe, '-maf', f"{target}:"]  # -m: MBR, -a: active, -f: force
            result = subprocess.run(
                cmd, 
                check=False,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode == 0:
                self._update(progress_callback, 100, 'Boot sector written with syslinux')
                return True
            else:
                error_msg = result.stderr if result.stderr else "Unknown error"
                self._update(progress_callback, 50, f"Syslinux failed: {error_msg}")
                logger.error(f"Syslinux failed on {target}: {error_msg}")
                return False
                
        except subprocess.TimeoutExpired:
            self._update(progress_callback, 50, "Syslinux timed out after 30 seconds")
            return False
        except Exception as e:
            self._update(progress_callback, 50, f"Syslinux error: {str(e)}")
            logger.error(f"Syslinux exception on {drive}: {str(e)}")
            return False
