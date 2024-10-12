from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, 
                             QVBoxLayout, QFileDialog, QMessageBox, 
                             QProgressBar, QComboBox, QSystemTrayIcon, 
                             QAction, QMenu, QStyle, QGroupBox, 
                             QRadioButton, QCheckBox)
from PyQt5.QtCore import Qt
from worker import USBWorker
import os
import ctypes
import logging

class SmartBootUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Boot")
        self.resize(480, 400)

        # Logging setup
        logging.basicConfig(filename="smartboot.log", level=logging.INFO, 
                            format="%(asctime)s - %(levelname)s - %(message)s")

        self.worker = USBWorker()
        self.worker.progress_update.connect(self.update_progress_bar)
        self.worker.usb_creation_completed.connect(self.handle_worker_finished)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.tray_icon.setToolTip("Smart Boot")
        self.create_tray_menu()

        self.iso_list = []
        self.initUI()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.show()

    def create_tray_menu(self):
        tray_menu = QMenu(self)
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.show)
        tray_menu.addAction(restore_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)

    def initUI(self):
        layout = QVBoxLayout()

        # Drag and Drop Area
        self.drag_drop_label = QLabel("Drag and drop ISO file(s) here")
        self.drag_drop_label.setAlignment(Qt.AlignCenter)
        self.drag_drop_label.setAcceptDrops(True)
        self.drag_drop_label.setStyleSheet("border: 2px dashed #aaa; padding: 20px;")
        layout.addWidget(self.drag_drop_label)

        self.drag_drop_label.dropEvent = self.dropEvent
        self.drag_drop_label.dragEnterEvent = self.dragEnterEvent

        # Select Drive ComboBox
        self.create_drive_combobox(layout)

        # Checkbox for Auto Determine Settings
        self.auto_determine_checkbox = QCheckBox("Auto Determine Settings")
        self.auto_determine_checkbox.stateChanged.connect(self.toggle_advanced_options)
        layout.addWidget(self.auto_determine_checkbox)

        # Add a group box for Partition Scheme and Bootloader Type
        self.create_options_group(layout)

        # OS Type Selection
        self.create_os_type_selection(layout)

        # Browse ISO Button
        self.create_button(layout, "Browse ISO", self.add_iso_to_usb)

        # Create Bootable USB Button
        self.create_button(layout, "Create Bootable USB", self.confirm_create_bootable)

        # Progress Bar
        self.progress_bar = self.create_progress_bar(layout)

        # Status Label
        self.status_label = self.create_label(layout)

        self.setLayout(layout)

    def toggle_advanced_options(self):
        """Enable or disable the advanced options based on the checkbox state."""
        is_checked = self.auto_determine_checkbox.isChecked()
        # Enable/disable the partition and bootloader combo boxes
        self.partition_combo.setEnabled(not is_checked)
        self.bootloader_combo.setEnabled(not is_checked)

    def create_os_type_selection(self, layout):
        """Create radio buttons for OS type selection."""
        self.os_type_group = QGroupBox("Select OS Type")
        os_layout = QVBoxLayout()

        self.windows_radio = QRadioButton("Windows")
        self.linux_radio = QRadioButton("Linux")
        self.linux_radio.setChecked(True)  # Default to Linux

        os_layout.addWidget(self.windows_radio)
        os_layout.addWidget(self.linux_radio)
        self.os_type_group.setLayout(os_layout)

        layout.addWidget(self.os_type_group)

    def create_drive_combobox(self, layout):
        self.drive_combo = QComboBox()
        self.drive_combo.addItems(self.get_removable_drives())
        layout.addWidget(QLabel("Select USB Drive:"))
        layout.addWidget(self.drive_combo)

    def create_options_group(self, layout):
        """Create a group box for advanced options like Partition Scheme and Bootloader."""
        options_group = QGroupBox("Advanced Options")
        options_layout = QVBoxLayout()

        # Partition Scheme
        self.partition_combo = QComboBox()
        self.partition_combo.addItems(["MBR", "GPT"])
        options_layout.addWidget(QLabel("Partition Scheme:"))
        options_layout.addWidget(self.partition_combo)

        # Bootloader Type
        self.bootloader_combo = QComboBox()
        self.bootloader_combo.addItems(["UEFI", "Legacy"])
        options_layout.addWidget(QLabel("Bootloader Type:"))
        options_layout.addWidget(self.bootloader_combo)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

    def get_removable_drives(self):
        """Get a list of removable drives (USB drives) on the system."""
        removable_drives = []
        drives = [f"{chr(d)}:\\" for d in range(65, 91)]  # Drive letters from A to Z
        for drive in drives:
            if os.path.exists(drive) and self.is_removable_drive(drive):
                removable_drives.append(drive)
        return removable_drives

    def is_removable_drive(self, drive):
        """Check if the drive is removable."""
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
        return drive_type == 2  # DRIVE_REMOVABLE

    def handle_worker_finished(self):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Bootable USB creation completed.")
        self.show_notification("USB Creation Completed", "The bootable USB creation process has finished.")
        logging.info("Bootable USB creation completed successfully.")

    def show_notification(self, title, message):
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 5000)

    def create_progress_bar(self, layout):
        progress_bar = QProgressBar()  # Create progress bar
        progress_bar.setVisible(False)  # Initially hidden
        layout.addWidget(progress_bar)
        return progress_bar  # Return the created progress bar

    def create_button(self, layout, button_text, on_click_function):
        button = QPushButton(button_text)
        button.clicked.connect(on_click_function)
        layout.addWidget(button)

    def create_label(self, layout):
        label = QLabel()  # Create a new label
        layout.addWidget(label)
        return label  # Return the created label

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path) and path.endswith('.iso'):
                    self.add_iso_file(path)
                    break
            else:
                QMessageBox.warning(self, "Invalid File", "Please drop an ISO file.")
        else:
            QMessageBox.warning(self, "Invalid File", "Please drop an ISO file.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def add_iso_file(self, path):
        self.drag_drop_label.setText("ISO file(s): " + ", ".join(self.iso_list + [path]))  # Update the label with the ISO path
        self.iso_list.append(path)  # Add to list of ISOs

    def add_iso_to_usb(self):
        options = QFileDialog.Options()
        iso_file, _ = QFileDialog.getOpenFileName(self, "Select ISO File", "", 
                                                   "ISO Files (*.iso);;All Files (*)", 
                                                   options=options)
        if iso_file:
            self.add_iso_file(iso_file)  # Call the method to add the ISO file

    def confirm_create_bootable(self):
        drive_path = self.drive_combo.currentText()  # Get selected drive from ComboBox
        
        if not drive_path:
            QMessageBox.warning(self, "Error", "Please select a USB drive.")
            return
        
        if not self.iso_list:
            QMessageBox.warning(self, "Error", "Please add at least one ISO file.")
            return

        # Automatically determine settings
        self.auto_determine_settings()

        # Proceed with confirmation and bootable creation
        preview_message = self.create_preview_message()
        confirmation = QMessageBox.question(self, "Confirmation", 
                                            f"Are you sure you want to create a bootable USB drive?\n\n{preview_message}",
                                            QMessageBox.Yes | QMessageBox.No)
        if confirmation == QMessageBox.Yes:
            self.create_bootable()

    def auto_determine_settings(self):
        """Automatically determine bootloader, filesystem, and cluster size based on the ISO."""
        if self.windows_radio.isChecked():
            # Windows settings
            self.selected_boot_type = self.bootloader_combo.currentText()  # Get selected bootloader type
            self.file_system = "NTFS"  # Generally, Windows uses NTFS
            self.selected_partition_scheme = self.partition_combo.currentText()  # Use user-selected partition scheme
        elif self.linux_radio.isChecked():
            # Linux settings
            self.selected_boot_type = self.bootloader_combo.currentText()  # Use user-selected bootloader type
            if "iso9660" in self.iso_list[0].lower():  # Check if it's a common Linux format
                self.file_system = "ext4"  # Set a common filesystem for Linux
            else:
                self.file_system = "FAT32"  # Use FAT32 for compatibility with older systems
            self.selected_partition_scheme = self.partition_combo.currentText()  # Use user-selected partition scheme


    def create_preview_message(self):
        """Create a preview message for the confirmation dialog."""
        return (f"ISO Files: {', '.join(self.iso_list)}\n"
                f"Selected Drive: {self.drive_combo.currentText()}\n"
                f"Bootloader Type: {self.selected_boot_type}\n"
                f"Filesystem: {self.file_system}\n"
                f"Partition Scheme: {self.selected_partition_scheme}")

    def create_bootable(self):
        # Check if auto determine is enabled
        if self.auto_determine_checkbox.isChecked():
            self.auto_determine_settings()  # Set the necessary arguments automatically
        else:
            # If not auto determining, ensure to use user-selected values
            self.selected_boot_type = self.bootloader_combo.currentText()
            self.selected_partition_scheme = self.partition_combo.currentText()

        # Check if selected_boot_type and selected_partition_scheme have been assigned
        if not self.selected_boot_type or not self.selected_partition_scheme:
            QMessageBox.warning(self, "Error", "Boot type or partition scheme is not set.")
            return

        # Proceed with setting arguments for the USBWorker
        self.worker.set_arguments(
            self.iso_list,
            self.drive_combo.currentText(),
            self.file_system,
            "BOOTABLE",  # Example volume label
            "sdb",        # Example selected device; consider making this dynamic
            self.selected_boot_type,
            self.selected_partition_scheme
        )
                
        self.worker.start()
        self.progress_bar.setVisible(True)  # Show progress bar

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

# Main block to run the application
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SmartBootUI()
    window.show()
    sys.exit(app.exec_())
