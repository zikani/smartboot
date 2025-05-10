"""
Disk Formatter module for SmartBoot

This module handles formatting USB devices with various filesystems.
Supports FAT/FAT32/NTFS/exFAT/UDF/ReFS on Windows and ext2/ext3/ext4 on Linux.
"""
import os
import platform
import subprocess
import time
import shutil
from typing import Dict, Any, Callable, Optional, List, Tuple
from ..utils.logger import default_logger as logger


class DiskFormatter:
    """
    Class for formatting disks with various filesystems.
    Handles formatting, partitioning, and filesystem creation.
    """
    
    # Supported filesystems by platform
    SUPPORTED_FS = {
        'Windows': ['FAT', 'FAT32', 'NTFS', 'exFAT', 'UDF', 'ReFS'],
        'Linux': ['fat', 'fat32', 'ntfs', 'exfat', 'ext2', 'ext3', 'ext4', 'udf'],
        'Darwin': ['FAT32', 'ExFAT', 'NTFS', 'APFS', 'HFS+']
    }
    
    def __init__(self):
        """Initialize the Disk Formatter."""
        logger.debug("DiskFormatter: Initializing Disk Formatter.")
        self.system = platform.system()
        logger.debug(f"DiskFormatter: Detected platform system: {self.system}")
    
    def get_supported_filesystems(self) -> List[str]:
        """
        Get list of supported filesystems for the current OS.
        
        Returns:
            List[str]: List of supported filesystem names
        """
        logger.debug(f"DiskFormatter: Getting supported filesystems for {self.system}")
        fs = self.SUPPORTED_FS.get(self.system, [])
        logger.debug(f"DiskFormatter: Supported filesystems: {fs}")
        return fs
    
    def format_disk(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str = "BOOTABLE",
        partition_scheme: str = "MBR",
        quick_format: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[bool, str]:
        """
        Format a disk with the specified filesystem.
        """
        logger.debug(f"DiskFormatter: format_disk called with device={device}, filesystem={filesystem}, label={label}, partition_scheme={partition_scheme}, quick_format={quick_format}")
        try:
            if 'error' in device:
                logger.error(f"DiskFormatter: Device error: {device['error']}")
                self._update_progress(progress_callback, 0, f"Error: {device['error']}")
                return False, ""
                
            if self.system == 'Windows':
                logger.debug("DiskFormatter: Using Windows format routine.")
                return self._format_windows(device, filesystem, label, partition_scheme, quick_format, progress_callback)
            elif self.system == 'Linux':
                logger.debug("DiskFormatter: Using Linux format routine.")
                return self._format_linux(device, filesystem, label, partition_scheme, quick_format, progress_callback)
            elif self.system == 'Darwin':  # macOS
                logger.debug("DiskFormatter: Using macOS format routine.")
                return self._format_macos(device, filesystem, label, partition_scheme, quick_format, progress_callback)
            else:
                logger.error(f"DiskFormatter: Unsupported OS: {self.system}")
                self._update_progress(progress_callback, 0, f"Unsupported OS: {self.system}")
                return False, ""
        except Exception as e:
            logger.exception(f"DiskFormatter: Exception in format_disk: {str(e)}")
            self._update_progress(progress_callback, 0, f"Error formatting disk: {str(e)}")
            return False, ""
    
    def _format_windows(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str,
        partition_scheme: str,
        quick_format: bool,
        progress_callback: Optional[Callable[[int, str], None]]
    ) -> Tuple[bool, str]:
        """Format a disk on Windows."""
        disk_number = device.get('number')
        if disk_number is None or disk_number < 0:
            self._update_progress(progress_callback, 0, "Error: Invalid device number")
            return False, ""

        # Check for admin rights
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                self._update_progress(progress_callback, 0, "Error: Administrator privileges required")
                return False, ""
        except Exception:
            pass

        # Step 1: Clean the disk
        try:
            clean_cmd = [
                "powershell",
                "-Command",
                f"Clear-Disk -Number {disk_number} -RemoveData -Confirm:$false"
            ]
            
            result = subprocess.run(clean_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # Try diskpart fallback for cleaning
                try:
                    script_path = os.path.join(os.environ.get('TEMP', '.'), 'diskpart_script.txt')
                    with open(script_path, 'w') as f:
                        f.write(f"select disk {disk_number}\n")
                        f.write("clean\n")
                        f.write("exit\n")
                    
                    diskpart_cmd = ["diskpart", "/s", script_path]
                    subprocess.run(diskpart_cmd, capture_output=True, text=True, check=True)
                    
                    try:
                        os.remove(script_path)
                    except:
                        pass
                except Exception as e:
                    self._update_progress(progress_callback, 0, f"Error cleaning disk: {str(e)}")
                    return False, ""
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error cleaning disk: {str(e)}")
            return False, ""
            
        self._update_progress(progress_callback, 15, "Disk cleaned successfully")

        # Step 2: Initialize disk with correct partition scheme
        try:
            if partition_scheme.lower() == "mbr":
                init_cmd = [
                    "powershell",
                    "-Command",
                    f"Initialize-Disk -Number {disk_number} -PartitionStyle MBR"
                ]
            else:  # GPT
                init_cmd = [
                    "powershell",
                    "-Command",
                    f"Initialize-Disk -Number {disk_number} -PartitionStyle GPT"
                ]
            
            result = subprocess.run(init_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # Try diskpart fallback for initialization
                try:
                    script_path = os.path.join(os.environ.get('TEMP', '.'), 'diskpart_script.txt')
                    with open(script_path, 'w') as f:
                        f.write(f"select disk {disk_number}\n")
                        f.write(f"convert {partition_scheme.lower()}\n")
                        f.write("exit\n")
                    
                    diskpart_cmd = ["diskpart", "/s", script_path]
                    subprocess.run(diskpart_cmd, capture_output=True, text=True, check=True)
                    
                    try:
                        os.remove(script_path)
                    except:
                        pass
                except Exception as e:
                    self._update_progress(progress_callback, 0, f"Error initializing disk: {str(e)}")
                    return False, ""
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error initializing disk: {str(e)}")
            return False, ""
            
        self._update_progress(progress_callback, 25, f"Disk initialized with {partition_scheme} partition scheme")
        
        # Step 3: Create and format primary partition
        try:
            if filesystem.upper() == "FAT32":
                # Use diskpart for FAT32 to avoid PowerShell's 32GB limit
                script_path = os.path.join(os.environ.get('TEMP', '.'), 'diskpart_script.txt')
                with open(script_path, 'w') as f:
                    f.write(f"select disk {disk_number}\n")
                    f.write("create partition primary\n")
                    f.write("select partition 1\n")
                    f.write("active\n")  # Mark as active for booting
                    f.write(f"format fs=fat32 label=\"{label}\" quick\n")
                    f.write("assign\n")
                    f.write("exit\n")
                
                diskpart_cmd = ["diskpart", "/s", script_path]
                subprocess.run(diskpart_cmd, capture_output=True, text=True, check=True)
                
                try:
                    os.remove(script_path)
                except:
                    pass
            else:
                # Use PowerShell for other filesystems
                format_option = "-Full" if not quick_format else ""
                
                create_partition_cmd = [
                    "powershell",
                    "-Command",
                    f"New-Partition -DiskNumber {disk_number} -UseMaximumSize -IsActive | "
                    f"Format-Volume -FileSystem {filesystem} {format_option} -NewFileSystemLabel '{label}' -Force | "
                    f"Add-PartitionAccessPath -AssignDriveLetter"
                ]
                
                result = subprocess.run(create_partition_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    # Fallback to diskpart
                    script_path = os.path.join(os.environ.get('TEMP', '.'), 'diskpart_script.txt')
                    with open(script_path, 'w') as f:
                        f.write(f"select disk {disk_number}\n")
                        f.write("create partition primary\n")
                        f.write("select partition 1\n")
                        f.write("active\n")
                        f.write(f"format fs={filesystem} label=\"{label}\" quick\n")
                        f.write("assign\n")
                        f.write("exit\n")
                    
                    diskpart_cmd = ["diskpart", "/s", script_path]
                    subprocess.run(diskpart_cmd, capture_output=True, text=True, check=True)
                    
                    try:
                        os.remove(script_path)
                    except:
                        pass
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error creating/formatting partition: {str(e)}")
            return False, ""
            
        self._update_progress(progress_callback, 75, "Partition created and formatted")
        
        # Step 4: Get the assigned drive letter
        try:
            get_drive_letter_cmd = [
                "powershell",
                "-Command",
                f"Get-Partition -DiskNumber {disk_number} | Get-Volume | Select-Object -ExpandProperty DriveLetter"
            ]
            
            result = subprocess.run(get_drive_letter_cmd, capture_output=True, text=True)
            drive_letter = result.stdout.strip()
            
            if not drive_letter:
                # Fallback methods to get drive letter
                try:
                    # Try using wmic
                    wmic_cmd = [
                        "wmic", "logicaldisk", "where", "drivetype=2", "get", "deviceid", "/value"
                    ]
                    result = subprocess.run(wmic_cmd, capture_output=True, text=True)
                    for line in result.stdout.splitlines():
                        if line.startswith("DeviceID="):
                            drive_letter = line.split("=")[1].strip()
                            break
                except:
                    pass
                
                # If still no drive letter, try scanning common removable drive letters
                if not drive_letter:
                    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                        try:
                            if os.path.exists(f"{letter}:\\"):
                                # Verify it's a removable drive
                                drive_type_cmd = [
                                    "powershell",
                                    "-Command",
                                    f"(Get-WmiObject -Class Win32_LogicalDisk | Where-Object {{ $_.DeviceID -eq '{letter}:' }}).DriveType"
                                ]
                                result = subprocess.run(drive_type_cmd, capture_output=True, text=True)
                                if result.stdout.strip() == "2":  # 2 = Removable drive
                                    drive_letter = letter
                                    break
                        except:
                            continue
            
            if drive_letter:
                self._update_progress(progress_callback, 100, f"Disk formatted successfully, assigned to {drive_letter}:")
                return True, drive_letter
            else:
                self._update_progress(progress_callback, 0, "Error: Could not determine drive letter")
                return False, ""
                
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error getting drive letter: {str(e)}")
            return False, ""
    
    def _format_linux(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str,
        partition_scheme: str,
        quick_format: bool,
        progress_callback: Optional[Callable[[int, str], None]]
    ) -> Tuple[bool, str]:
        """Format a disk on Linux."""
        device_path = device.get('name')
        if not device_path:
            self._update_progress(progress_callback, 0, "Error: Invalid device path")
            return False, ""
        
        if not device_path.startswith('/dev/'):
            device_path = f"/dev/{device_path}"
        
        # Step 1: Update progress
        self._update_progress(progress_callback, 5, "Preparing to format device...")
        
        # Step 2: Unmount the device if it's mounted
        try:
            # Check if mounted
            mount_check = subprocess.run(["mount"], capture_output=True, text=True)
            if device_path in mount_check.stdout:
                # Unmount all partitions
                subprocess.run(["sudo", "umount", device_path + "*"], capture_output=True)
        except Exception:
            # Continue even if unmount fails
            pass
        
        # Step 3: Create a new partition table
        try:
            if partition_scheme.upper() == "MBR":
                # Create MBR partition table
                subprocess.run(["sudo", "parted", "-s", device_path, "mklabel", "msdos"], check=True, capture_output=True)
            else:
                # Create GPT partition table
                subprocess.run(["sudo", "parted", "-s", device_path, "mklabel", "gpt"], check=True, capture_output=True)
            
            self._update_progress(progress_callback, 20, f"Created {partition_scheme} partition table")
        except subprocess.CalledProcessError as e:
            self._update_progress(progress_callback, 0, f"Error creating partition table: {e.stderr}")
            return False, ""
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error creating partition table: {str(e)}")
            return False, ""
        
        # Step 4: Create a new partition
        try:
            # Create a primary partition using the entire disk
            subprocess.run(
                ["sudo", "parted", "-s", device_path, "mkpart", "primary", "0%", "100%"],
                check=True, capture_output=True
            )
            self._update_progress(progress_callback, 40, "Created partition")
            
            # Wait for the partition to be recognized by the system
            time.sleep(1)
            
            # Get the partition name
            partition = f"{device_path}1"  # Assuming the first partition
            
            # Make sure the partition exists
            for _ in range(5):  # Try a few times
                if os.path.exists(partition):
                    break
                time.sleep(1)
            
            if not os.path.exists(partition):
                # Try alternative partition naming schemes
                if os.path.exists(f"{device_path}p1"):
                    partition = f"{device_path}p1"
                else:
                    self._update_progress(progress_callback, 0, f"Error: Partition {partition} not found")
                    return False, ""
        except subprocess.CalledProcessError as e:
            self._update_progress(progress_callback, 0, f"Error creating partition: {e.stderr}")
            return False, ""
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error creating partition: {str(e)}")
            return False, ""
        
        # Step 5: Format the partition with the selected filesystem
        try:
            # Format based on filesystem type
            if filesystem.lower() in ["fat", "fat32", "vfat"]:
                # Format as FAT32
                cmd = ["sudo", "mkfs.vfat", "-F", "32"]
                if label:
                    cmd.extend(["-n", label])
                cmd.append(partition)
                subprocess.run(cmd, check=True, capture_output=True)
            elif filesystem.lower() == "ntfs":
                # Format as NTFS
                cmd = ["sudo", "mkfs.ntfs"]
                if quick_format:
                    cmd.append("-f")  # Quick format
                if label:
                    cmd.extend(["-L", label])
                cmd.append(partition)
                subprocess.run(cmd, check=True, capture_output=True)
            elif filesystem.lower() == "exfat":
                # Format as exFAT
                cmd = ["sudo", "mkfs.exfat"]
                if label:
                    cmd.extend(["-n", label])
                cmd.append(partition)
                subprocess.run(cmd, check=True, capture_output=True)
            elif filesystem.lower().startswith("ext"):
                # Format as ext2/3/4
                cmd = [f"sudo", f"mkfs.{filesystem.lower()}"]
                if label:
                    cmd.extend(["-L", label])
                cmd.append(partition)
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                self._update_progress(progress_callback, 0, f"Unsupported filesystem: {filesystem}")
                return False, ""
            
            self._update_progress(progress_callback, 60, f"Formatted partition with {filesystem}")
        except subprocess.CalledProcessError as e:
            self._update_progress(progress_callback, 0, f"Error formatting partition: {e.stderr}")
            return False, ""
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error formatting partition: {str(e)}")
            return False, ""
        
        # Step 6: Mount the partition
        mount_point = ""
        try:
            # Create a mount point
            mount_dir = f"/tmp/smartboot_mount_{int(time.time())}"
            os.makedirs(mount_dir, exist_ok=True)
            
            # Mount the partition
            mount_cmd = ["sudo", "mount"]
            if filesystem.lower() in ["ntfs", "exfat"]:
                # For NTFS and exFAT, we might need specific mount options
                mount_cmd.extend(["-t", filesystem.lower()])
            mount_cmd.extend([partition, mount_dir])
            
            subprocess.run(mount_cmd, check=True, capture_output=True)
            mount_point = mount_dir
            
            self._update_progress(progress_callback, 80, f"Mounted partition at {mount_point}")
        except subprocess.CalledProcessError as e:
            self._update_progress(progress_callback, 70, f"Warning: Could not mount partition: {e.stderr}")
            # Continue without mounting
        except Exception as e:
            self._update_progress(progress_callback, 70, f"Warning: Could not mount partition: {str(e)}")
            # Continue without mounting
        
        self._update_progress(progress_callback, 100, f"Disk formatted successfully with {filesystem}")
        return True, mount_point or partition
    
    def _format_macos(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str,
        partition_scheme: str,
        quick_format: bool,
        progress_callback: Optional[Callable[[int, str], None]]
    ) -> Tuple[bool, str]:
        """Format a disk on macOS."""
        device_path = device.get('name')
        if not device_path:
            self._update_progress(progress_callback, 0, "Error: Invalid device path")
            return False, ""
        
        if not device_path.startswith('/dev/'):
            device_path = f"/dev/{device_path}"
        
        # Step 1: Update progress
        self._update_progress(progress_callback, 5, "Preparing to format device...")
        
        # Step 2: Unmount the device if it's mounted
        try:
            subprocess.run(["diskutil", "unmountDisk", device_path], capture_output=True)
        except Exception:
            # Continue even if unmount fails
            pass
        
        # Step 3: Create a new partition scheme and format
        try:
            # Map filesystem names to diskutil format names
            format_map = {
                "FAT32": "MS-DOS FAT32",
                "ExFAT": "ExFAT",
                "NTFS": "NTFS",
                "HFS+": "HFS+",
                "APFS": "APFS"
            }
            
            diskutil_format = format_map.get(filesystem, "MS-DOS FAT32")  # Default to FAT32
            
            # Map partition scheme
            scheme = "MBR" if partition_scheme.upper() == "MBR" else "GPT"
            
            # Format the entire disk
            cmd = [
                "diskutil", "eraseDisk", 
                diskutil_format,  # Format
                label or "BOOTABLE",  # Volume name
                scheme,  # Partition scheme
                device_path  # Device
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self._update_progress(progress_callback, 0, f"Error formatting disk: {result.stderr}")
                return False, ""
            
            # Extract the mount point from the output
            mount_point = ""
            for line in result.stdout.splitlines():
                if "Volume name" in line and "mounted at" in line:
                    mount_point = line.split("mounted at")[-1].strip()
                    break
            
            self._update_progress(progress_callback, 100, f"Disk formatted successfully with {filesystem}")
            return True, mount_point or f"/Volumes/{label}"
        except subprocess.CalledProcessError as e:
            self._update_progress(progress_callback, 0, f"Error formatting disk: {e.stderr}")
            return False, ""
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error formatting disk: {str(e)}")
            return False, ""
    
    def _update_progress(
        self,
        callback: Optional[Callable[[int, str], None]],
        percent: int,
        message: str
    ):
        """
        Update progress through the callback if provided.
        
        Args:
            callback (Optional[Callable[[int, str], None]]): Progress callback
            percent (int): Progress percentage (0-100)
            message (str): Progress message
        """
        if callback:
            callback(percent, message)
        print(f"Progress: {percent}% - {message}")
