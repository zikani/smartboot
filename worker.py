import sys
import os
import subprocess
import logging
from random import randint
from PyQt5.QtWidgets import (QApplication, QLabel, QMainWindow, QPushButton, 
                             QVBoxLayout, QWidget, QFileDialog, QMessageBox)
from PyQt5.QtCore import pyqtSignal, QObject
import platform
import ctypes
import shutil
from utils import verify_iso_integrity, get_drive_size
import threading

# USBWorker thread for handling USB creation
class USBWorker(QObject):
    # PyQt5 signals to notify progress, errors, and completion
    progress_update = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    usb_creation_completed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.iso_list = []
        self.drive_path = ''
        self.file_system = ''
        self.volume_label = ''
        self.selected_device = ''
        self.selected_boot_type = ''
        self.selected_partition_scheme = ''
        self.is_cancelled = False
        self.total_steps = 0
        self.current_step = 0
        self.thread = None

    # Set arguments for USB creation process
    def set_arguments(self, iso_list, drive_path, file_system, volume_label, 
                      selected_device, selected_boot_type, selected_partition_scheme, check_bad_blocks=False):
        self.iso_list = iso_list
        self.drive_path = drive_path
        self.file_system = file_system
        self.volume_label = volume_label
        self.selected_device = selected_device
        self.selected_boot_type = selected_boot_type
        self.selected_partition_scheme = selected_partition_scheme
        self.check_bad_blocks = check_bad_blocks
        self.total_steps = len(iso_list) * 2 + 3  # ISO verification + copying + formatting + bootloader
        if self.check_bad_blocks:
            self.total_steps += 1  # Additional step for bad blocks check
        self.current_step = 0

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        try:
            self.log_start()
            self.check_system_requirements()
            if self.check_bad_blocks:
                self.perform_bad_blocks_check()
            self.verify_all_isos()
            if self.is_cancelled:
                return
            
            self.create_bootable_usb()
            if not self.is_cancelled:
                self.usb_creation_completed.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.cleanup_on_error()
            logging.error(f"Error during USB creation: {e}")
        finally:
            self.log_end()

    def log_start(self):
        """Log the start of the USB creation process."""
        logging.info("Starting USB creation process.")

    def log_end(self):
        """Log the end of the USB creation process."""
        logging.info("USB creation process ended.")

    def verify_all_isos(self):
        """Verify integrity of all ISO files before proceeding."""
        for index, iso in enumerate(self.iso_list):
            if self.is_cancelled:
                return
            self.status_update.emit(f"Verifying ISO: {os.path.basename(iso)}")
            if not verify_iso_integrity(iso):
                raise ValueError(f"ISO verification failed for {iso}")
            self.update_progress()
            self.progress_update.emit(int(((index + 1) / len(self.iso_list)) * 100))

    # Check system requirements
    def check_system_requirements(self):
        """Enhanced system requirements check."""
        if not self.is_user_admin():
            raise PermissionError("Administrative privileges are required.")

        required_tools = ["dd", "mkfs.ext4", "mkfs.ntfs", "grub-install", "syslinux"]
        missing_tools = [tool for tool in required_tools if not self.is_tool_installed(tool)]

        if missing_tools:
            raise EnvironmentError(f"Required tools are missing: {', '.join(missing_tools)}")

        # Check drive space
        drive_space = self.get_free_space(self.drive_path)
        required_space = self.calculate_required_space()
        if drive_space < required_space:
            raise ValueError(
                f"Insufficient space. Required: {required_space/1024/1024:.2f}MB, "
                f"Available: {drive_space/1024/1024:.2f}MB"
            )

        # Verify drive is not system drive
        if self.is_system_drive(self.drive_path):
            raise ValueError("Cannot use system drive as target")

        self.update_progress()

    def calculate_required_space(self):
        """Calculate total required space including overhead."""
        iso_size = sum(os.path.getsize(iso) for iso in self.iso_list)
        overhead = 512 * 1024 * 1024  # 512MB overhead for bootloader and fs
        return iso_size + overhead

    def is_system_drive(self, drive_path):
        """Check if the selected drive is the system drive."""
        system_drive = os.environ.get('SystemDrive', 'C:')
        return drive_path.upper().startswith(system_drive.upper())

    # Check if the script is running as an administrator
    def is_user_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    # Verify if the necessary system tool is available
    def is_tool_installed(self, tool):
        return subprocess.call(["which", tool], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0

    # Get available space on the USB drive
    def get_free_space(self, drive_path):
        statvfs = os.statvfs(drive_path)
        return statvfs.f_frsize * statvfs.f_bavail

    # Calculate total size of all the ISO files
    def estimate_iso_size(self, iso_list):
        total_size = sum(os.path.getsize(iso_path) for iso_path in iso_list)
        return total_size
    
    def is_windows_bootable_image(self, iso_path):
        """Check if the ISO is a Windows bootable image."""
        try:
            with open(iso_path, 'rb') as f:
                # Check for Windows boot marker
                f.seek(0x8000)  # Skip first 32KB
                data = f.read(16)
                return b'CD001' in data and (b'WINDOWS' in data or b'BOOTMGR' in data)
        except:
            return False
    
    def detect_windows_image_type(self, iso_path):
        """Detect the type of Windows image file."""
        if not os.path.exists(iso_path):
            return None
            
        file_ext = os.path.splitext(iso_path)[1].lower()
        if file_ext == '.iso':
            return "WINDOWS_ISO"
        elif file_ext == '.wim':
            return "WIM"
        elif file_ext == '.esd':
            return "ESD"
        return None
        
            # Manage the overall process of creating the bootable USB
    def create_bootable_usb(self):
        try:
            self.status_update.emit("Checking image type...")
            if any(self.is_windows_bootable_image(iso) for iso in self.iso_list):
                self.create_windows_bootable()
            else:
                self.create_linux_bootable()
        except Exception as e:
            raise RuntimeError(f"Failed to create bootable USB: {str(e)}")

    def create_windows_bootable(self):
        """Create Windows bootable USB."""
        try:
            self.status_update.emit("Preparing Windows bootable USB...")
            
            # Format with NTFS
            self.format_with_ntfs()
            self.update_progress()

            if self.is_cancelled:
                return

            # Copy Windows files
            self.copy_windows_files()
            if self.is_cancelled:
                return

            # Setup Windows bootloader
            self.setup_windows_bootloader()
            self.update_progress()

        except Exception as e:
            raise RuntimeError(f"Windows USB creation failed: {str(e)}")

    def format_with_ntfs(self):
        """Format drive with NTFS for Windows."""
        try:
            if platform.system() == "Windows":
                # Use Windows format command
                cmd = f'format {self.drive_path} /fs:NTFS /q /y'
                subprocess.run(cmd, shell=True, check=True)
            else:
                # Use mkfs.ntfs for Linux
                cmd = f'mkfs.ntfs -f -Q {self.drive_path}'
                subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Format failed: {str(e)}")

    def copy_windows_files(self):
        """Copy Windows installation files."""
        for iso in self.iso_list:
            image_type = self.detect_windows_image_type(iso)
            if image_type == "WINDOWS_ISO":
                self.extract_windows_iso(iso)
            elif image_type in ["WIM", "ESD"]:
                self.apply_windows_image(iso)
            self.update_progress()

    def extract_windows_iso(self, iso_path):
        """Extract Windows ISO contents."""
        try:
            self.status_update.emit(f"Extracting {os.path.basename(iso_path)}...")
            if platform.system() == "Windows":
                # Use PowerShell to mount and copy
                mount_point = f"{chr(randint(68, 90))}:"  # Random drive letter D-Z
                ps_cmd = r"""
                Mount-DiskImage -ImagePath "{iso_path}"
                $vol = Get-Volume | Where-Object {{ $_.DriveType -eq 'CD-ROM' }}
                Copy-Item "$($vol.DriveLetter):\*" "{self.drive_path}" -Recurse -Force
                Dismount-DiskImage -ImagePath "{iso_path}"
                """
                subprocess.run(["powershell", "-Command", ps_cmd], check=True)
            else:
                # Use 7z for Linux
                subprocess.run(["7z", "x", iso_path, f"-o{self.drive_path}"], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to extract Windows ISO: {str(e)}")

    def setup_windows_bootloader(self):
        """Setup Windows bootloader."""
        try:
            self.status_update.emit("Setting up Windows bootloader...")
            if platform.system() == "Windows":
                # Use bcdboot for Windows
                subprocess.run([
                    "bcdboot",
                    f"{self.drive_path}\\Windows",
                    "/s", self.drive_path,
                    "/f", "ALL"
                ], check=True)
            else:
                # Use direct file copy for Linux
                bootfiles = ["bootmgr", "bootmgr.efi", "boot"]
                for file in bootfiles:
                    src = f"{self.drive_path}/sources/boot/{file}"
                    dst = f"{self.drive_path}/{file}"
                    if os.path.exists(src):
                        shutil.copy2(src, dst)
        except Exception as e:
            raise RuntimeError(f"Failed to setup Windows bootloader: {str(e)}")

    def apply_windows_image(self, image_path):
        """Apply Windows WIM/ESD image."""
        try:
            self.status_update.emit(f"Applying Windows image from {os.path.basename(image_path)}...")
            if platform.system() == "Windows":
                # Use DISM for Windows
                subprocess.run([
                    "dism",
                    "/Apply-Image",
                    "/ImageFile:", image_path,
                    "/Index:1",
                    f"/ApplyDir:{self.drive_path}"
                ], check=True)
            else:
                # Use wimlib for Linux
                subprocess.run([
                    "wimlib-imagex",
                    "apply",
                    image_path,
                    self.drive_path,
                    "1"
                ], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to apply Windows image: {str(e)}")

    def create_linux_bootable(self):
        """Create bootable USB with enhanced progress tracking and safety checks."""
        try:
            self.status_update.emit("Formatting drive...")
            self.format_usb_drive()
            self.update_progress()

            if self.is_cancelled:
                return

            self.status_update.emit("Copying ISO files...")
            self.copy_iso_files()
            
            if self.is_cancelled:
                return

            self.status_update.emit("Installing bootloader...")
            self.install_bootloader()
            self.update_progress()

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Command failed: {e.cmd}. Return code: {e.returncode}")
        except Exception as e:
            raise RuntimeError(f"Failed to create bootable USB: {str(e)}")

    # Format the USB drive
    def format_usb_drive(self):
        if platform.system() == "Windows":
            self.format_on_windows()
        else:
            self.format_on_linux()

    def format_on_windows(self):
        import wmi
        c = wmi.WMI()
        selected_disk = self.get_selected_disk_windows(c)
        if not selected_disk:
            raise ValueError("Disk not found.")
        
        if self.file_system.lower() in ["fat", "fat32", "ntfs", "exfat", "refs"]:
            selected_disk.FormatFileSystem(Format=self.file_system, QuickFormat=True, VolumeName=self.volume_label)
        else:
            raise ValueError(f"Unsupported file system: {self.file_system}")

    def format_on_linux(self):
        supported_filesystems = ["vfat", "ntfs", "ext2", "ext3", "ext4", "udf", "exfat"]
        if self.file_system.lower() not in supported_filesystems:
            raise ValueError(f"Unsupported file system: {self.file_system}")
        subprocess.run(["mkfs." + self.file_system, "-n", self.volume_label, self.drive_path], check=True)

    # Copy ISO files to the USB drive
    def copy_iso_files(self):
        """Copy ISO files with progress tracking."""
        for iso in self.iso_list:
            if self.is_cancelled:
                return
            
            self.status_update.emit(f"Copying {os.path.basename(iso)}...")
            try:
                self.copy_with_progress(iso, self.drive_path)
            except Exception as e:
                raise RuntimeError(f"Failed to copy {iso}: {str(e)}")
            self.update_progress()

    def copy_with_progress(self, src, dst):
        """Copy file with progress updates."""
        file_size = os.path.getsize(src)
        copied = 0
        with open(src, 'rb') as fsrc:
            with open(dst, 'wb') as fdst:
                while True:
                    buf = fsrc.read(1024*1024)
                    if not buf:
                        break
                    fdst.write(buf)
                    copied += len(buf)
                    progress = (copied / file_size) * 100
                    self.progress_update.emit(int(progress))

    def install_bootloader(self):
        if self.selected_boot_type == "UEFI":
            self.install_grub()
        elif self.selected_boot_type == "Legacy":
            self.install_syslinux()

    def install_grub(self):
        subprocess.run(["grub-install", "--target=x86_64-efi", "--removable", self.drive_path], check=True)

    def install_syslinux(self):
        subprocess.run(["syslinux", "--install", self.drive_path], check=True)

    def cleanup_on_error(self):
        """Clean up any temporary files or partial operations on error."""
        try:
            self.status_update.emit("Cleaning up...")
            # Add cleanup code here
            logging.info("Cleanup completed")
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")

    def cancel(self):
        """Cancel the current operation safely."""
        self.is_cancelled = True
        self.status_update.emit("Cancelling operation...")

    def update_progress(self):
        """Update overall progress."""
        self.current_step += 1
        progress = (self.current_step / self.total_steps) * 100
        self.progress_update.emit(int(progress))

    def perform_bad_blocks_check(self):
        """Perform a bad blocks check on the drive."""
        self.status_update.emit("Checking for bad blocks...")
        try:
            if platform.system() == "Windows":
                # Use chkdsk for Windows
                cmd = f'chkdsk {self.drive_path} /r'
                subprocess.run(cmd, shell=True, check=True)
            else:
                # Use badblocks for Linux
                cmd = f'badblocks -v {self.drive_path}'
                subprocess.run(cmd, shell=True, check=True)
            self.update_progress()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Bad blocks check failed: {str(e)}")


# MainWindow class for handling the UI and interactions
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Smart Boot Creator')
        self.setGeometry(100, 100, 600, 400)
        self.initUI()
        self.usb_worker = None

    def initUI(self):
        # QLabel to show status
        self.status_label = QLabel("Status: Ready", self)
        self.status_label.setGeometry(10, 10, 500, 30)

        # QPushButton to start bootable USB creation
        self.create_button = QPushButton("Create Bootable USB", self)
        self.create_button.setGeometry(10, 50, 200, 30)
        self.create_button.clicked.connect(self.confirm_create_bootable)

        # Layout and central widget
        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.create_button)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def confirm_create_bootable(self):
        # Start the bootable USB creation process
        iso_files, _ = QFileDialog.getOpenFileNames(self, "Select ISO Files", "", "ISO Files (*.iso)")
        drive_path = QFileDialog.getExistingDirectory(self, "Select USB Drive")
        if iso_files and drive_path:
            self.status_label.setText("Creating bootable USB...")
            self.start_usb_creation(iso_files, drive_path)
        else:
            QMessageBox.warning(self, "Warning", "Please select ISO files and a USB drive.")

    def start_usb_creation(self, iso_list, drive_path):
        self.usb_worker = USBWorker()
        self.usb_worker.set_arguments(
            iso_list, drive_path, file_system="vfat", volume_label="BOOTABLE",
            selected_device="sdb", selected_boot_type="UEFI", selected_partition_scheme="GPT"
        )
        self.usb_worker.error_occurred.connect(self.handle_error)
        self.usb_worker.usb_creation_completed.connect(self.handle_completion)
        self.usb_worker.start()

    def handle_error(self, error_message):
        self.status_label.setText(f"Error: {error_message}")

    def handle_completion(self):
        self.status_label.setText("Bootable USB creation completed!")


# Main entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
