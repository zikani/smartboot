import sys
import os
import subprocess
import logging
from PyQt5.QtWidgets import (QApplication, QLabel, QMainWindow, QPushButton, 
                             QVBoxLayout, QWidget, QFileDialog, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal
import platform
import ctypes

# USBWorker thread for handling USB creation
class USBWorker(QThread):
    # PyQt5 signals to notify progress, errors, and completion
    progress_update = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
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

    # Set arguments for USB creation process
    def set_arguments(self, iso_list, drive_path, file_system, volume_label, 
                      selected_device, selected_boot_type, selected_partition_scheme):
        self.iso_list = iso_list
        self.drive_path = drive_path
        self.file_system = file_system
        self.volume_label = volume_label
        self.selected_device = selected_device
        self.selected_boot_type = selected_boot_type
        self.selected_partition_scheme = selected_partition_scheme

    def run(self):
        try:
            self.check_system_requirements()
            self.create_bootable_usb()
            self.usb_creation_completed.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
            logging.error(f"Error during USB creation: {e}")

    # Check system requirements
    def check_system_requirements(self):
        if not self.is_user_admin():
            raise PermissionError("Administrative privileges are required.")

        required_tools = ["dd", "mkfs.ext4", "mkfs.ntfs", "grub-install", "syslinux"]
        missing_tools = [tool for tool in required_tools if not self.is_tool_installed(tool)]

        if missing_tools:
            raise EnvironmentError(f"Required tools are missing: {', '.join(missing_tools)}")

        drive_space = self.get_free_space(self.drive_path)
        required_space = self.estimate_iso_size(self.iso_list)

        if drive_space < required_space:
            raise ValueError(f"Insufficient space: Required {required_space} bytes, Available {drive_space} bytes.")

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

    # Manage the overall process of creating the bootable USB
    def create_bootable_usb(self):
        self.format_usb_drive()
        self.copy_iso_to_usb()
        self.install_bootloader()

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
        selected_disk.FormatFileSystem(Format=self.file_system, QuickFormat=True, VolumeName=self.volume_label)

    def format_on_linux(self):
        supported_filesystems = ["vfat", "ntfs", "ext2", "ext3", "ext4"]
        if self.file_system.lower() not in supported_filesystems:
            raise ValueError(f"Unsupported file system: {self.file_system}")
        subprocess.run(["mkfs." + self.file_system, "-n", self.volume_label, self.drive_path], check=True)

    # Copy ISO files to the USB drive
    def copy_iso_to_usb(self):
        for iso in self.iso_list:
            subprocess.run(["dd", f"if={iso}", f"of={self.drive_path}", "bs=4M", "conv=fdatasync"], check=True)

    def install_bootloader(self):
        if self.selected_boot_type == "UEFI":
            self.install_grub()
        elif self.selected_boot_type == "Legacy":
            self.install_syslinux()

    def install_grub(self):
        subprocess.run(["grub-install", "--target=x86_64-efi", "--removable", self.drive_path], check=True)

    def install_syslinux(self):
        subprocess.run(["syslinux", "--install", self.drive_path], check=True)


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
