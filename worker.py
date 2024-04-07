import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
import platform



class Worker(QThread):
    progress_update = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    usb_creation_completed = pyqtSignal()

    

    def __init__(self):
        super().__init__()

    def set_arguments(self, iso_path, drive_path, file_system, volume_label, selected_device, selected_boot_type,
                     selected_partition_scheme):
        self.iso_path = iso_path
        self.drive_path = drive_path
        self.file_system = file_system
        self.volume_label = volume_label
        self.selected_device = selected_device
        self.selected_boot_type = selected_boot_type
        self.selected_partition_scheme = selected_partition_scheme

    def run(self):
        try:
            self.create_bootable_usb()
            self.usb_creation_completed.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def create_bootable_usb(self):
        self.format_usb_drive()
        self.copy_iso_to_usb()
        self.install_bootloader()

    def format_usb_drive(drive_number, file_system, volume_label, quick_format=True, log_file_path="formatting_log.txt"):
        try:
            if not drive_number or not file_system or not volume_label:
                raise ValueError("Drive number, file system, and volume label must be provided.")

            if platform.system() == "Windows":
                import wmi

                c = wmi.WMI()

                disks = c.Win32_DiskDrive()

                selected_disk = None
                for disk in disks:
                    if str(disk.Index) == drive_number:
                        selected_disk = disk
                        break

                if not selected_disk:
                    raise ValueError("Disk not found.")

                print(f"Formatting disk {selected_disk.Caption}...")
                disk = c.Win32_DiskDrive(Index=int(drive_number))
                for part in disk.Partitions():
                    part.Delete()

                disk.FormatFileSystem(Format=file_system, QuickFormat=quick_format, VolumeName=volume_label)
                print(f"Disk {selected_disk.Caption} formatted successfully.")
            else:
                supported_filesystems = ["vfat", "ntfs", "ext2", "ext3", "ext4"]
                if file_system.lower() not in supported_filesystems:
                    raise ValueError(f"Unsupported file system: {file_system}")

                subprocess.run(["mkfs." + file_system, "-n", volume_label, drive_number], check=True)
                print(f"USB drive formatted with {file_system} file system and label '{volume_label}'.")
        except Exception as e:
            print("Failed to format the disk:", e)
            

    
                

    def copy_iso_to_usb(self):
        try:
            subprocess.run(["dd", "if=" + self.iso_path, "of=" + self.drive_path, "bs=4M"], check=True)

            iso_hash = self.get_iso_hash(self.iso_path)
            drive_hash = self.get_drive_hash(self.drive_path)

            if iso_hash != drive_hash:
                raise ValueError("MD5 checksums don't match. Copy operation might have failed.")
            print("ISO copied successfully and verified!")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to copy ISO to USB: {e}")
        
    

    


    def get_iso_hash(self, iso_path):
        # Placeholder for actual MD5 checksum calculation
        return "placeholder_iso_hash"

    def get_drive_hash(self, drive_path):
        # Placeholder for actual MD5 checksum calculation
        return "placeholder_drive_hash"

    def install_bootloader(self):
        if self.selected_boot_type == "UEFI":
            if self.selected_partition_scheme == "GPT":
                try:
                    subprocess.run([
                        "grub-install",
                        "--target=x86_64-efi",
                        "--efi-directory=/boot/efi",
                        "--bootloader-id=grub",
                        "--removable",
                        self.drive_path
                    ], check=True)
                except subprocess.CalledProcessError as e:
                    raise ValueError(f"Failed to install GRUB bootloader for UEFI (GPT): {e}")
            elif self.selected_partition_scheme == "MBR":
                try:
                    subprocess.run([
                        "grub-install",
                        "--target=i386-efi",
                        "--efi-directory=/boot/efi",
                        "--bootloader-id=grub",
                        "--removable",
                        self.drive_path
                    ], check=True)
                except subprocess.CalledProcessError as e:
                    raise ValueError(f"Failed to install GRUB bootloader for UEFI (MBR): {e}")
        elif self.selected_boot_type == "Legacy":
            try:
                subprocess.run(["syslinux", "--install", self.drive_path], check=True)
            except subprocess.CalledProcessError as e:
                raise ValueError(f"Failed to install Syslinux bootloader for Legacy: {e}")
