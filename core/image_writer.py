"""
Image Writer module for SmartBoot

This module handles writing ISO images and disk images to USB devices.
Supports various ISO types (Windows, Linux, etc.) and raw disk images.
"""
import os
import platform
import subprocess
import shutil
import tempfile
import time
from typing import Dict, Any, Callable, Optional, List, Tuple
from utils.logger import default_logger as logger


class ImageWriter:
    """
    Class for writing ISO and disk images to USB devices.
    Handles extraction, copying, and direct writing operations.
    """
    
    def __init__(self):
        """Initialize the Image Writer."""
        logger.debug("ImageWriter: Initializing Image Writer.")
        self.system = platform.system()
        logger.debug(f"ImageWriter: Detected platform system: {self.system}")
        self._temp_dirs = []  # Track temp dirs for cleanup
    
    def __del__(self):
        """Clean up temporary directories on deletion."""
        for temp_dir in self._temp_dirs:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    def write_iso(
        self,
        iso_path: str,
        target_drive: str,
        iso_type: str = "auto",
        extract_files: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write an ISO image to a USB drive.

        Args:
            iso_path (str): Path to the ISO file
            target_drive (str): Drive letter (Windows) or mount point (Linux/macOS)
            iso_type (str): Type of ISO (auto, windows, linux, freedos, etc.)
            extract_files (bool): Extract files instead of direct write
            progress_callback (Optional[Callable]): For progress updates
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.debug(f"ImageWriter: write_iso called with iso_path={iso_path}, target_drive={target_drive}, iso_type={iso_type}, extract_files={extract_files}")
        try:
            if not os.path.exists(iso_path):
                logger.error(f"ImageWriter: ISO file not found: {iso_path}")
                self._update_progress(progress_callback, 0, f"Error: ISO file not found: {iso_path}")
                return False
            
            # Auto-detect ISO type if not specified
            if iso_type == "auto":
                logger.debug("ImageWriter: Auto-detecting ISO type.")
                iso_type = self._detect_iso_type(iso_path, progress_callback)
                self._update_progress(progress_callback, 10, f"Detected ISO type: {iso_type}")
            
            # Format target drive path for the current OS
            if self.system == "Windows":
                if len(target_drive) == 1:
                    target_drive = f"{target_drive}:\\"
                elif not target_drive.endswith(":\\"):
                    target_drive = f"{target_drive}:\\"
            else:
                if not os.path.exists(target_drive):
                    logger.error(f"ImageWriter: Target drive not found: {target_drive}")
                    self._update_progress(progress_callback, 0, f"Error: Target drive not found: {target_drive}")
                    return False
            
            # Choose the appropriate method based on ISO type and extraction preference
            if not extract_files:
                logger.debug("ImageWriter: Performing direct image write (dd-like mode).")
                return self._write_image_direct(iso_path, target_drive, progress_callback)
            elif iso_type.lower() == "windows":
                logger.debug("ImageWriter: Writing Windows ISO.")
                return self._write_windows_iso(iso_path, target_drive, progress_callback)
            elif iso_type.lower() in ["linux", "ubuntu", "debian", "fedora"]:
                logger.debug(f"ImageWriter: Writing Linux ISO: {iso_type}")
                return self._write_linux_iso(iso_path, target_drive, progress_callback)
            elif iso_type.lower() in ["freedos", "msdos", "dos"]:
                logger.debug("ImageWriter: Writing DOS/FreeDOS ISO.")
                return self._write_dos_iso(iso_path, target_drive, progress_callback)
            else:
                logger.debug(f"ImageWriter: Writing generic ISO: {iso_type}")
                return self._write_generic_iso(iso_path, target_drive, progress_callback)
        except Exception as e:
            logger.exception(f"ImageWriter: Exception in write_iso: {str(e)}")
            self._update_progress(progress_callback, 0, f"Error writing ISO: {str(e)}")
            return False
    
    def write_disk_image(
        self,
        image_path: str,
        target_device: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write a raw disk image directly to a device.

        Args:
            image_path (str): Path to the disk image file
            target_device (str): Device path (/dev/sdX or PhysicalDriveN)
            progress_callback (Optional[Callable]): For progress updates
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not os.path.exists(image_path):
                self._update_progress(progress_callback, 0, f"Error: Image file not found: {image_path}")
                return False
            
            # Determine if the image is compressed
            is_compressed = any(image_path.lower().endswith(ext) for ext in ['.gz', '.xz', '.bz2', '.zip'])
            
            # Direct write based on platform
            if self.system == "Windows":
                return self._write_image_windows(image_path, target_device, is_compressed, progress_callback)
            else:  # Linux/macOS
                return self._write_image_unix(image_path, target_device, is_compressed, progress_callback)
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error writing disk image: {str(e)}")
            return False
    
    def _detect_iso_type(
        self, 
        iso_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> str:
        """
        Detect the type of ISO image.

        Args:
            iso_path (str): Path to the ISO file
            progress_callback (Optional[Callable]): For progress updates
        
        Returns:
            str: Detected ISO type (windows, linux, freedos, generic)
        """
        self._update_progress(progress_callback, 5, "Detecting ISO type...")
        
        # First check the filename for common patterns
        filename = os.path.basename(iso_path).lower()
        
        # Windows detection
        if any(win_term in filename for win_term in ['windows', 'win', 'microsoft', 'server']):
            return "windows"
        
        # Linux distribution detection
        linux_distros = ['ubuntu', 'debian', 'fedora', 'centos', 'rhel', 'suse', 'arch', 'manjaro', 'linux', 'mint']
        if any(distro in filename for distro in linux_distros):
            return "linux"
        
        # DOS detection
        if any(dos_term in filename for dos_term in ['freedos', 'msdos', 'dos']):
            return "freedos"
        
        # Try to mount and check content (Windows only)
        if self.system == "Windows":
            try:
                # Use PowerShell to mount and check ISO contents
                mount_cmd = [
                    "powershell",
                    "-Command",
                    f"$mountResult = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; $driveLetter = ($mountResult | Get-Volume).DriveLetter; $driveLetter"
                ]
                result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=10)
                drive_letter = result.stdout.strip() + ":\\"
                
                try:
                    # Check for Windows markers
                    if os.path.exists(os.path.join(drive_letter, "sources", "install.wim")) or \
                       os.path.exists(os.path.join(drive_letter, "sources", "install.esd")):
                        return "windows"
                    
                    # Check for Linux markers
                    if os.path.exists(os.path.join(drive_letter, "casper")) or \
                       os.path.exists(os.path.join(drive_letter, "isolinux")) or \
                       os.path.exists(os.path.join(drive_letter, "live")):
                        return "linux"
                    
                    # Check for DOS markers
                    if os.path.exists(os.path.join(drive_letter, "kernel.sys")) or \
                       os.path.exists(os.path.join(drive_letter, "command.com")):
                        return "freedos"
                finally:
                    # Always unmount the ISO
                    unmount_cmd = [
                        "powershell",
                        "-Command",
                        f"Dismount-DiskImage -ImagePath '{iso_path}'"
                    ]
                    subprocess.run(unmount_cmd, capture_output=True, timeout=5)
            except Exception:
                # If mounting fails, continue with other detection methods
                pass
        
        # Fallback to generic
        return "generic"
    
    def _write_windows_iso(
        self,
        iso_path: str,
        target_drive: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write a Windows ISO to a USB drive.
        
        Args:
            iso_path (str): Path to the Windows ISO
            target_drive (str): Drive letter with trailing backslash
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 15, "Preparing to write Windows ISO...")
        
        # Mount the ISO
        try:
            mount_cmd = [
                "powershell",
                "-Command",
                f"$mountResult = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; $driveLetter = ($mountResult | Get-Volume).DriveLetter; $driveLetter"
            ]
            result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=10)
            iso_drive = result.stdout.strip() + ":\\"
            
            if not os.path.exists(iso_drive):
                self._update_progress(progress_callback, 0, f"Error: Could not mount ISO at {iso_drive}")
                return False
            
            self._update_progress(progress_callback, 20, f"ISO mounted at {iso_drive}")
            
            try:
                # Copy all files from ISO to USB
                self._update_progress(progress_callback, 25, "Copying Windows files to USB...")
                
                # Use robocopy for efficient copying
                robocopy_cmd = [
                    "robocopy",
                    iso_drive,
                    target_drive,
                    "/E",     # Copy subdirectories, including empty ones
                    "/NFL",   # No file list - don't log file names
                    "/NDL",   # No directory list - don't log directory names
                    "/NJH",   # No job header
                    "/NJS",   # No job summary
                    "/NC",    # No class - don't log file classes
                    "/NS",    # No size - don't log file sizes
                    "/MT:4"   # Multi-threaded, 4 threads
                ]
                
                # Robocopy returns non-zero exit codes even on success
                subprocess.run(robocopy_cmd, capture_output=True)
                
                self._update_progress(progress_callback, 80, "Files copied successfully")
                
                # Make the USB bootable using bootsect.exe
                self._update_progress(progress_callback, 85, "Making USB bootable...")
                
                # Try to find bootsect.exe in the ISO
                bootsect_paths = [
                    os.path.join(iso_drive, "boot", "bootsect.exe"),
                    os.path.join(iso_drive, "sources", "bootsect.exe")
                ]
                # Fallbacks: environment variable and hardcoded path
                env_bootsect = os.environ.get("BOOTSECT_PATH")
                if env_bootsect:
                    bootsect_paths.append(env_bootsect)
                bootsect_paths.append(r"C:\\tools\\bootsect.exe")
                
                bootsect_exe = None
                for path in bootsect_paths:
                    if os.path.exists(path):
                        bootsect_exe = path
                        break
                
                if bootsect_exe:
                    # Run bootsect.exe to make the USB bootable
                    bootsect_cmd = [
                        bootsect_exe,
                        "/nt60",
                        target_drive,
                        "/force",
                        "/mbr"
                    ]
                    try:
                        subprocess.run(bootsect_cmd, check=True, capture_output=True)
                        self._update_progress(progress_callback, 95, "Made USB bootable with bootsect.exe")
                    except subprocess.CalledProcessError as e:
                        self._update_progress(progress_callback, 90, "Warning: bootsect.exe failed, USB may not be bootable. Try running as administrator. Error: {}".format(getattr(e, 'stderr', b'').decode(errors='ignore')))
                else:
                    self._update_progress(progress_callback, 90, "Warning: bootsect.exe not found in ISO, BOOTSECT_PATH, or C:\\tools\\bootsect.exe. USB may not be bootable.")
                
                self._update_progress(progress_callback, 100, "Windows ISO written successfully")
                return True
            finally:
                # Always unmount the ISO
                unmount_cmd = [
                    "powershell",
                    "-Command",
                    f"Dismount-DiskImage -ImagePath '{iso_path}'"
                ]
                subprocess.run(unmount_cmd, capture_output=True, timeout=5)
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error writing Windows ISO: {str(e)}")
            return False
    
    def _write_linux_iso(
        self,
        iso_path: str,
        target_drive: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write a Linux ISO to a USB drive.
        
        Args:
            iso_path (str): Path to the Linux ISO
            target_drive (str): Drive letter or mount point
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 15, "Preparing to write Linux ISO...")
        
        if self.system == "Windows":
            # On Windows, we can either extract the ISO or use a direct write
            # Direct write is more reliable for Linux ISOs
            return self._write_image_direct(iso_path, target_drive, progress_callback)
        else:
            # On Linux/macOS, use dd for direct write
            device_path = target_drive
            if os.path.isdir(target_drive):
                # If it's a mount point, we need to find the device
                try:
                    mount_info = subprocess.run(["mount"], capture_output=True, text=True)
                    for line in mount_info.stdout.splitlines():
                        if target_drive in line:
                            parts = line.split()
                            device_path = parts[0]
                            break
                except Exception:
                    pass
            
            return self._write_image_unix(iso_path, device_path, False, progress_callback)
    
    def _write_dos_iso(
        self,
        iso_path: str,
        target_drive: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write a DOS ISO to a USB drive.
        
        Args:
            iso_path (str): Path to the DOS ISO
            target_drive (str): Drive letter or mount point
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 15, "Preparing to write DOS ISO...")
        
        # Extract the ISO
        temp_dir = tempfile.mkdtemp(prefix="smartboot_dos_")
        self._temp_dirs.append(temp_dir)
        
        try:
            # Extract ISO to temp directory
            self._update_progress(progress_callback, 20, "Extracting DOS ISO...")
            
            if self.system == "Windows":
                # Use 7-Zip or PowerShell to extract
                if shutil.which("7z"):
                    extract_cmd = ["7z", "x", f"-o{temp_dir}", iso_path]
                    subprocess.run(extract_cmd, check=True, capture_output=True)
                else:
                    # Mount and copy
                    mount_cmd = [
                        "powershell",
                        "-Command",
                        f"$mountResult = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; $driveLetter = ($mountResult | Get-Volume).DriveLetter; $driveLetter"
                    ]
                    result = subprocess.run(mount_cmd, capture_output=True, text=True)
                    iso_drive = result.stdout.strip() + ":\\"
                    
                    try:
                        # Copy files
                        copy_cmd = ["xcopy", f"{iso_drive}*", temp_dir, "/E", "/H", "/I"]
                        subprocess.run(copy_cmd, check=True, capture_output=True)
                    finally:
                        # Unmount
                        unmount_cmd = ["powershell", "-Command", f"Dismount-DiskImage -ImagePath '{iso_path}'"]
                        subprocess.run(unmount_cmd, capture_output=True)
            else:
                # Use 7z or mount and copy
                if shutil.which("7z"):
                    extract_cmd = ["7z", "x", f"-o{temp_dir}", iso_path]
                    subprocess.run(extract_cmd, check=True, capture_output=True)
                else:
                    # Create a mount point
                    mount_point = os.path.join(temp_dir, "iso_mount")
                    os.makedirs(mount_point, exist_ok=True)
                    
                    try:
                        # Mount the ISO
                        mount_cmd = ["sudo", "mount", "-o", "loop", iso_path, mount_point]
                        subprocess.run(mount_cmd, check=True, capture_output=True)
                        
                        # Copy files
                        copy_cmd = ["cp", "-r", f"{mount_point}/.", temp_dir]
                        subprocess.run(copy_cmd, check=True, capture_output=True)
                    finally:
                        # Unmount
                        unmount_cmd = ["sudo", "umount", mount_point]
                        subprocess.run(unmount_cmd, capture_output=True)
            
            self._update_progress(progress_callback, 50, "DOS files extracted")
            
            # Copy files to USB
            self._update_progress(progress_callback, 60, "Copying DOS files to USB...")
            
            if self.system == "Windows":
                # Use xcopy for Windows
                copy_cmd = ["xcopy", f"{temp_dir}\\*", target_drive, "/E", "/H", "/I"]
                subprocess.run(copy_cmd, check=True, capture_output=True)
            else:
                # Use cp for Linux/macOS
                copy_cmd = ["cp", "-r", f"{temp_dir}/.", target_drive]
                subprocess.run(copy_cmd, check=True, capture_output=True)
            
            self._update_progress(progress_callback, 90, "DOS files copied to USB")
            
            # Make the USB bootable
            self._update_progress(progress_callback, 95, "Making USB bootable...")
            
            # Look for sys.com or equivalent
            sys_file = None
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.lower() == "sys.com":
                        sys_file = os.path.join(root, file)
                        break
                if sys_file:
                    break
            
            if sys_file and self.system == "Windows":
                # Run sys.com to make the USB bootable
                sys_cmd = [sys_file, target_drive[0] + ":"]
                try:
                    subprocess.run(sys_cmd, check=True, capture_output=True)
                    self._update_progress(progress_callback, 98, "Made USB bootable with sys.com")
                except subprocess.CalledProcessError:
                    self._update_progress(progress_callback, 95, "Warning: sys.com failed, USB may not be bootable")
            else:
                self._update_progress(progress_callback, 95, "Warning: sys.com not found, USB may not be bootable")
            
            self._update_progress(progress_callback, 100, "DOS ISO written successfully")
            return True
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error writing DOS ISO: {str(e)}")
            return False
        finally:
            # Clean up
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                self._temp_dirs.remove(temp_dir)
            except:
                pass
    
    def _write_generic_iso(
        self,
        iso_path: str,
        target_drive: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write a generic ISO to a USB drive by extracting files.
        
        Args:
            iso_path (str): Path to the ISO
            target_drive (str): Drive letter or mount point
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 15, "Preparing to write generic ISO...")
        
        # Extract the ISO
        temp_dir = tempfile.mkdtemp(prefix="smartboot_iso_")
        self._temp_dirs.append(temp_dir)
        
        try:
            # Extract ISO to temp directory
            self._update_progress(progress_callback, 20, "Extracting ISO...")
            
            if self.system == "Windows":
                # Use 7-Zip or PowerShell to extract
                if shutil.which("7z"):
                    extract_cmd = ["7z", "x", f"-o{temp_dir}", iso_path]
                    subprocess.run(extract_cmd, check=True, capture_output=True)
                else:
                    # Mount and copy
                    mount_cmd = [
                        "powershell",
                        "-Command",
                        f"$mountResult = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; $driveLetter = ($mountResult | Get-Volume).DriveLetter; $driveLetter"
                    ]
                    result = subprocess.run(mount_cmd, capture_output=True, text=True)
                    iso_drive = result.stdout.strip() + ":\\"
                    
                    try:
                        # Copy files
                        copy_cmd = ["xcopy", f"{iso_drive}*", temp_dir, "/E", "/H", "/I"]
                        subprocess.run(copy_cmd, check=True, capture_output=True)
                    finally:
                        # Unmount
                        unmount_cmd = ["powershell", "-Command", f"Dismount-DiskImage -ImagePath '{iso_path}'"]
                        subprocess.run(unmount_cmd, capture_output=True)
            else:
                # Use 7z or mount and copy
                if shutil.which("7z"):
                    extract_cmd = ["7z", "x", f"-o{temp_dir}", iso_path]
                    subprocess.run(extract_cmd, check=True, capture_output=True)
                else:
                    # Create a mount point
                    mount_point = os.path.join(temp_dir, "iso_mount")
                    os.makedirs(mount_point, exist_ok=True)
                    
                    try:
                        # Mount the ISO
                        mount_cmd = ["sudo", "mount", "-o", "loop", iso_path, mount_point]
                        subprocess.run(mount_cmd, check=True, capture_output=True)
                        
                        # Copy files
                        copy_cmd = ["cp", "-r", f"{mount_point}/.", temp_dir]
                        subprocess.run(copy_cmd, check=True, capture_output=True)
                    finally:
                        # Unmount
                        unmount_cmd = ["sudo", "umount", mount_point]
                        subprocess.run(unmount_cmd, capture_output=True)
            
            self._update_progress(progress_callback, 50, "ISO files extracted")
            
            # Copy files to USB
            self._update_progress(progress_callback, 60, "Copying files to USB...")
            
            if self.system == "Windows":
                # Use xcopy for Windows
                copy_cmd = ["xcopy", f"{temp_dir}\\*", target_drive, "/E", "/H", "/I"]
                subprocess.run(copy_cmd, check=True, capture_output=True)
            else:
                # Use cp for Linux/macOS
                copy_cmd = ["cp", "-r", f"{temp_dir}/.", target_drive]
                subprocess.run(copy_cmd, check=True, capture_output=True)
            
            self._update_progress(progress_callback, 100, "ISO written successfully")
            return True
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error writing generic ISO: {str(e)}")
            return False
        finally:
            # Clean up
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                self._temp_dirs.remove(temp_dir)
            except:
                pass
    
    def _write_image_direct(self, 
        image_path: str,
        target_drive: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write an image directly to a drive (dd-like operation).
        
        Args:
            image_path (str): Path to the image file
            target_drive (str): Drive letter or device path
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 15, "Preparing for direct image write...")
        
        # Convert target_drive to device path
        device_path = target_drive
        if self.system == "Windows":
            # If it's a drive letter, convert to physical drive
            if len(target_drive) == 1 or (len(target_drive) == 2 and target_drive[1] == ':'):
                drive_letter = target_drive[0]
                try:
                    # Get physical drive number
                    cmd = [
                        "powershell",
                        "-Command",
                        f"Get-Partition | Where-Object {{ $_.DriveLetter -eq '{drive_letter}' }} | Select-Object -ExpandProperty DiskNumber"
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    disk_number = result.stdout.strip()
                    
                    if disk_number and disk_number.isdigit():
                        device_path = f"\\\\.\\PhysicalDrive{disk_number}"
                    else:
                        self._update_progress(progress_callback, 0, f"Error: Could not find physical drive for {drive_letter}:")
                        return False
                except Exception as e:
                    self._update_progress(progress_callback, 0, f"Error finding physical drive: {str(e)}")
                    return False
            elif target_drive.endswith(':\\'):
                drive_letter = target_drive[0]
                try:
                    # Get physical drive number
                    cmd = [
                        "powershell",
                        "-Command",
                        f"Get-Partition | Where-Object {{ $_.DriveLetter -eq '{drive_letter}' }} | Select-Object -ExpandProperty DiskNumber"
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    disk_number = result.stdout.strip()
                    
                    if disk_number and disk_number.isdigit():
                        device_path = f"\\\\.\\PhysicalDrive{disk_number}"
                    else:
                        self._update_progress(progress_callback, 0, f"Error: Could not find physical drive for {drive_letter}:")
                        return False
                except Exception as e:
                    self._update_progress(progress_callback, 0, f"Error finding physical drive: {str(e)}")
                    return False
        
        # Perform the write based on platform
        if self.system == "Windows":
            return self._write_image_windows(image_path, device_path, False, progress_callback)
        else:  # Linux/macOS
            return self._write_image_unix(image_path, device_path, False, progress_callback)
    
    def _write_image_windows(self,
        image_path: str,
        device_path: str,
        is_compressed: bool,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write an image to a device on Windows.
        
        Args:
            image_path (str): Path to the image file
            device_path (str): Physical drive path
            is_compressed (bool): Whether the image is compressed
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 20, "Writing image to device...")
        
        # Check if we have dd for Windows or similar tools
        dd_path = shutil.which("dd") or shutil.which("dd.exe")
        if dd_path:
            # Use dd for direct write
            try:
                if is_compressed:
                    # For compressed images, use a pipe
                    if image_path.lower().endswith('.gz'):
                        # Use gzip
                        cmd = f"gzip -dc \"{image_path}\" | {dd_path} of=\"{device_path}\" bs=4M"
                        subprocess.run(cmd, shell=True, check=True)
                    elif image_path.lower().endswith('.xz'):
                        # Use xz
                        cmd = f"xz -dc \"{image_path}\" | {dd_path} of=\"{device_path}\" bs=4M"
                        subprocess.run(cmd, shell=True, check=True)
                    elif image_path.lower().endswith('.bz2'):
                        # Use bzip2
                        cmd = f"bzip2 -dc \"{image_path}\" | {dd_path} of=\"{device_path}\" bs=4M"
                        subprocess.run(cmd, shell=True, check=True)
                    else:
                        # Unsupported compression
                        self._update_progress(progress_callback, 0, f"Error: Unsupported compression format: {image_path}")
                        return False
                else:
                    # Direct write
                    cmd = [dd_path, f"if={image_path}", f"of={device_path}", "bs=4M"]
                    subprocess.run(cmd, check=True, capture_output=True)
                
                self._update_progress(progress_callback, 100, "Image written successfully")
                return True
            except subprocess.CalledProcessError as e:
                self._update_progress(progress_callback, 0, f"Error writing image: {e.stderr if hasattr(e, 'stderr') else str(e)}")
                return False
            except Exception as e:
                self._update_progress(progress_callback, 0, f"Error writing image: {str(e)}")
                return False
        else:
            # Fallback to PowerShell for direct write
            import ctypes
            import textwrap
            try:
                # Check for admin rights
                try:
                    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
                except Exception:
                    is_admin = False
                if not is_admin:
                    self._update_progress(progress_callback, 0, "Error: This operation requires Administrator privileges. Please run SmartBoot as Administrator.")
                    return False
                # PowerShell direct write using streaming approach with chunks
                # This avoids loading the entire file into memory at once
                ps_script = textwrap.dedent(f"""
                    $ErrorActionPreference = 'Stop'
                    try {{
                        $source = [System.IO.File]::OpenRead('{image_path}')
                        try {{
                            # Use CreateFile API with direct access to physical drive
                            $GENERIC_WRITE = 0x40000000
                            $FILE_SHARE_WRITE = 0x2
                            $OPEN_EXISTING = 3
                            $FILE_FLAG_NO_BUFFERING = 0x20000000
                            $FILE_FLAG_WRITE_THROUGH = 0x80000000
                            
                            # Load necessary API
                            Add-Type -TypeDefinition @"
                            using System;
                            using System.IO;
                            using System.Runtime.InteropServices;
                            
                            public class NativeMethods {{
                                [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
                                public static extern IntPtr CreateFile(
                                    string lpFileName, uint dwDesiredAccess, uint dwShareMode,
                                    IntPtr lpSecurityAttributes, uint dwCreationDisposition,
                                    uint dwFlagsAndAttributes, IntPtr hTemplateFile);
                                    
                                [DllImport("kernel32.dll", SetLastError=true)]
                                public static extern bool WriteFile(
                                    IntPtr hFile, byte[] lpBuffer, uint nNumberOfBytesToWrite,
                                    out uint lpNumberOfBytesWritten, IntPtr lpOverlapped);
                                    
                                [DllImport("kernel32.dll", SetLastError=true)]
                                public static extern bool CloseHandle(IntPtr hObject);
                            }}
"@
                            
                            $handle = [NativeMethods]::CreateFile(
                                '{device_path}',
                                $GENERIC_WRITE,
                                $FILE_SHARE_WRITE,
                                [IntPtr]::Zero,
                                $OPEN_EXISTING,
                                $FILE_FLAG_WRITE_THROUGH -bor $FILE_FLAG_NO_BUFFERING,
                                [IntPtr]::Zero
                            )
                            
                            if ($handle -eq -1) {{
                                throw "Failed to open device: $([System.Runtime.InteropServices.Marshal]::GetLastWin32Error())"
                            }}
                            
                            try {{
                                # Use 1MB chunks to avoid memory issues
                                $buffer = New-Object byte[] (1MB)
                                $bytesRead = 0
                                $totalWritten = 0
                                $bytesWritten = 0
                                
                                # Read and write in chunks
                                while (($bytesRead = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {{
                                    [NativeMethods]::WriteFile($handle, $buffer, $bytesRead, [ref]$bytesWritten, [IntPtr]::Zero) | Out-Null
                                    $totalWritten += $bytesWritten
                                    Write-Host "Written $totalWritten bytes"
                                }}
                            }}
                            finally {{
                                # Always close the handle
                                [NativeMethods]::CloseHandle($handle) | Out-Null
                            }}
                        }}
                        finally {{
                            # Always close the source file
                            $source.Close()
                        }}
                    }} catch {{
                        Write-Error "Error: $($_.Exception.Message)"
                        exit 1
                    }}
                """)
                cmd = ["powershell", "-Command", ps_script]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                self._update_progress(progress_callback, 100, "Image written successfully")
                return True
            except subprocess.CalledProcessError as e:
                error_output = ''
                if hasattr(e, 'stderr') and e.stderr:
                    error_output += f"\n[stderr]\n{e.stderr.strip()}"
                if hasattr(e, 'stdout') and e.stdout:
                    error_output += f"\n[stdout]\n{e.stdout.strip()}"
                # Print error output to console for debugging
                print("[PowerShell Write Error]", error_output)
                # Optionally, log to file if logger is available
                try:
                    import logging
                    logging.error("PowerShell Write Error:%s", error_output)
                except Exception:
                    pass
                self._update_progress(progress_callback, 0, f"Error writing image (PowerShell): {str(e)}{error_output}\nEnsure you are running as Administrator and the device is not in use.")
                return False
            except Exception as e:
                self._update_progress(progress_callback, 0, f"Error writing image: {str(e)}")
                return False
    
    def _write_image_unix(self,
        image_path: str,
        device_path: str,
        is_compressed: bool,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Write an image to a device on Linux/macOS.
        
        Args:
            image_path (str): Path to the image file
            device_path (str): Device path (/dev/sdX)
            is_compressed (bool): Whether the image is compressed
            progress_callback (Optional[Callable]): For progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        self._update_progress(progress_callback, 20, "Writing image to device...")
        
        try:
            if is_compressed:
                # For compressed images, use a pipe
                if image_path.lower().endswith('.gz'):
                    # Use gzip
                    cmd = f"gzip -dc \"{image_path}\" | sudo dd of=\"{device_path}\" bs=4M status=progress"
                    subprocess.run(cmd, shell=True, check=True)
                elif image_path.lower().endswith('.xz'):
                    # Use xz
                    cmd = f"xz -dc \"{image_path}\" | sudo dd of=\"{device_path}\" bs=4M status=progress"
                    subprocess.run(cmd, shell=True, check=True)
                elif image_path.lower().endswith('.bz2'):
                    # Use bzip2
                    cmd = f"bzip2 -dc \"{image_path}\" | sudo dd of=\"{device_path}\" bs=4M status=progress"
                    subprocess.run(cmd, shell=True, check=True)
                else:
                    # Unsupported compression
                    self._update_progress(progress_callback, 0, f"Error: Unsupported compression format: {image_path}")
                    return False
            else:
                # Direct write
                cmd = ["sudo", "dd", f"if={image_path}", f"of={device_path}", "bs=4M", "status=progress"]
                subprocess.run(cmd, check=True, capture_output=True)
            
            # Sync to ensure all writes are complete
            subprocess.run(["sync"], check=True)
            
            self._update_progress(progress_callback, 100, "Image written successfully")
            return True
        except subprocess.CalledProcessError as e:
            self._update_progress(progress_callback, 0, f"Error writing image: {e.stderr if hasattr(e, 'stderr') else str(e)}")
            return False
        except Exception as e:
            self._update_progress(progress_callback, 0, f"Error writing image: {str(e)}")
            return False
    
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
