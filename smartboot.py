import json
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, 
                             QVBoxLayout, QFileDialog, QMessageBox, 
                             QProgressBar, QComboBox, QSystemTrayIcon, 
                             QAction, QMenu, QStyle, QGroupBox, 
                             QRadioButton, QCheckBox, QHBoxLayout)
from PyQt5.QtCore import Qt, QTimer
from worker import USBWorker
import os
import ctypes
import logging
from config import UI_CONFIG, SUPPORTED_FILESYSTEMS, SUPPORTED_BOOTLOADERS, SUPPORTED_PARTITION_SCHEMES
from utils import get_removable_drives, verify_iso_integrity, get_drive_space_info, is_windows_bootable_image
from update_checker import UpdateChecker  # Fixed import path
from backup_manager import BackupManager
import asyncio

class SmartBootUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(UI_CONFIG['window_title'])
        self.resize(UI_CONFIG['window_width'], UI_CONFIG['window_height'])

        # Logging setup
        logging.basicConfig(filename="smartboot.log", level=logging.INFO, 
                            format="%(asctime)s - %(levelname)s - %(message)s")

        self.worker = USBWorker()
        self.setup_worker_connections()
        self.setup_tray_icon()

        self.iso_list = []
        self.cancel_requested = False
        self.update_checker = UpdateChecker()
        self.backup_manager = BackupManager()
        
        # Replace direct call with async handler
        QTimer.singleShot(0, self.init_async)
        
        self.setup_ui()

    def init_async(self):
        """Initialize async operations."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.check_for_updates())

    def setup_worker_connections(self):
        """Setup worker signal connections with error handling."""
        self.worker.progress_update.connect(self.update_progress_bar)
        self.worker.usb_creation_completed.connect(self.handle_worker_finished)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.status_update.connect(self.handle_worker_status)

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def handle_worker_error(self, error_message):
        """Handle worker errors."""
        QMessageBox.critical(self, "Error", f"An error occurred: {error_message}")
        self.status_label.setText(f"Error: {error_message}")
        logging.error(f"Worker error: {error_message}")
        self.progress_bar.setVisible(False)
        self.finish_operation()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.show()

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.tray_icon.setToolTip("Smart Boot")
        self.create_tray_menu()

    def create_tray_menu(self):
        tray_menu = QMenu(self)
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.show)
        tray_menu.addAction(restore_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)

    def setup_ui(self):
        layout = QVBoxLayout()

        # Status Message
        self.status_message = QLabel("Ready")
        self.status_message.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_message)

        # Drag and Drop Area
        self.drag_drop_label = QLabel("Drag and drop ISO file(s) here")
        self.drag_drop_label.setAlignment(Qt.AlignCenter)
        self.drag_drop_label.setAcceptDrops(True)
        self.drag_drop_label.setStyleSheet("border: 2px dashed #aaa; padding: 20px;")
        layout.addWidget(self.drag_drop_label)

        self.drag_drop_label.dropEvent = self.dropEvent
        self.drag_drop_label.dragEnterEvent = self.dragEnterEvent

        # Drive Selection with Details
        self.create_drive_selection_group(layout)

        # Checkbox for Auto Determine Settings
        self.auto_determine_checkbox = QCheckBox("Auto Determine Settings")
        self.auto_determine_checkbox.stateChanged.connect(self.toggle_advanced_options)
        layout.addWidget(self.auto_determine_checkbox)

        # Checkbox for Bad Blocks Check
        self.bad_blocks_checkbox = QCheckBox("Perform Bad Blocks Check")
        layout.addWidget(self.bad_blocks_checkbox)

        # Add a group box for Partition Scheme and Bootloader Type
        self.create_options_group(layout)

        # OS Type Selection
        self.create_os_type_selection(layout)

        # Button Group
        button_layout = QHBoxLayout()
        self.create_button(button_layout, "Browse ISO", self.add_iso_to_usb)
        self.create_button(button_layout, "Create Bootable USB", self.confirm_create_bootable)
        self.cancel_button = self.create_button(button_layout, "Cancel", self.cancel_operation)
        self.cancel_button.setEnabled(False)
        layout.addLayout(button_layout)

        # Progress Section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel()
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Add backup/restore buttons
        backup_layout = QHBoxLayout()
        self.create_button(backup_layout, "Backup Configuration", self.backup_config)
        self.create_button(backup_layout, "Restore Configuration", self.restore_config)
        layout.addLayout(backup_layout)

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

    def create_drive_selection_group(self, layout):
        drive_group = QGroupBox("USB Drive Selection")
        drive_layout = QVBoxLayout()
        
        # Create the drive details label first
        self.drive_details = QLabel()
        self.drive_details.setStyleSheet("color: #666;")
        
        # Create and setup combo box
        self.drive_combo = QComboBox()
        self.drive_combo.currentIndexChanged.connect(self.update_drive_details)
        
        # Create refresh button
        refresh_button = QPushButton("Refresh Drives")
        refresh_button.clicked.connect(self.refresh_drive_list)
        
        # Add widgets to layout in desired order
        drive_layout.addWidget(self.drive_combo)
        drive_layout.addWidget(refresh_button)
        drive_layout.addWidget(self.drive_details)
        
        drive_group.setLayout(drive_layout)
        layout.addWidget(drive_group)
        
        # Populate the drive list after all UI elements are created
        self.refresh_drive_list()

    def refresh_drive_list(self):
        """Refresh the list of available USB drives."""
        if hasattr(self, 'drive_combo'):  # Check if combo box exists
            self.drive_combo.clear()
            drives = get_removable_drives()
            for drive, label, size in drives:
                self.drive_combo.addItem(f"{drive} ({label}) - {size}")
            self.update_drive_details()

    def update_drive_details(self):
        """Update the drive details label based on selected drive."""
        if not hasattr(self, 'drive_details'):  # Check if label exists
            return
            
        if self.drive_combo.currentText():
            drive = self.drive_combo.currentText().split()[0]
            total, used, free = get_drive_space_info(drive)
            self.drive_details.setText(
                f"Total: {total}\nUsed: {used}\nFree: {free}"
            )
        else:
            self.drive_details.setText("No drive selected")

    def create_options_group(self, layout):
        """Create a group box for advanced options like Partition Scheme and Bootloader."""
        options_group = QGroupBox("Advanced Options")
        options_layout = QVBoxLayout()

        # Partition Scheme
        self.partition_combo = QComboBox()
        self.partition_combo.addItems(SUPPORTED_PARTITION_SCHEMES)
        options_layout.addWidget(QLabel("Partition Scheme:"))
        options_layout.addWidget(self.partition_combo)

        # Bootloader Type
        self.bootloader_combo = QComboBox()
        self.bootloader_combo.addItems(SUPPORTED_BOOTLOADERS)
        options_layout.addWidget(QLabel("Bootloader Type:"))
        options_layout.addWidget(self.bootloader_combo)

        # File System Type
        self.filesystem_combo = QComboBox()
        self.filesystem_combo.addItems(SUPPORTED_FILESYSTEMS)
        options_layout.addWidget(QLabel("File System:"))
        options_layout.addWidget(self.filesystem_combo)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

    def handle_worker_finished(self):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Bootable USB creation completed.")
        self.show_notification("USB Creation Completed", "The bootable USB creation process has finished.")
        logging.info("Bootable USB creation completed successfully.")
        self.finish_operation()

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
        return button

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
        if (event.mimeData().hasUrls()):
            event.accept()
        else:
            event.ignore()

    def add_iso_file(self, path):
        # Verify Windows image compatibility
        if path.lower().endswith(('.iso', '.wim', '.esd')):
            if path.lower().endswith('.iso') and not verify_iso_integrity(path):
                QMessageBox.warning(self, "Invalid File", "ISO file verification failed.")
                return
            self.iso_list.append(path)
            self.drag_drop_label.setText("Image file(s): " + ", ".join(self.iso_list))
            # Auto-select Windows if Windows image detected
            if is_windows_bootable_image(path):
                self.windows_radio.setChecked(True)
                self.auto_determine_settings()
        else:
            QMessageBox.warning(self, "Invalid File", "Please select a valid ISO, WIM, or ESD file.")

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
        """Automatically determine settings based on image type."""
        if self.windows_radio.isChecked() or any(is_windows_bootable_image(iso) for iso in self.iso_list):
            self.selected_boot_type = "UEFI"
            self.file_system = "NTFS"
            self.selected_partition_scheme = "GPT"
            # Update UI to reflect Windows settings
            self.bootloader_combo.setCurrentText("UEFI")
            self.partition_combo.setCurrentText("GPT")
            self.filesystem_combo.setCurrentText("NTFS")
        else:
            # ...existing Linux settings...
            self.selected_boot_type = self.bootloader_combo.currentText()  # Use user-selected bootloader type
            if "iso9660" in self.iso_list[0].lower():  # Check if it's a common Linux format
                self.file_system = "ext4"  # Set a common filesystem for Linux
            else:
                self.file_system = "FAT32"  # Use FAT32 for compatibility with older systems
            self.selected_partition_scheme = self.partition_combo.currentText()  # Use user-selected partition scheme
            self.filesystem_combo.setCurrentText(self.file_system)

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
            self.file_system = self.filesystem_combo.currentText()

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
            self.selected_partition_scheme,
            check_bad_blocks=self.bad_blocks_checkbox.isChecked()
        )
                
        self.worker.start()
        self.start_operation()

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def cancel_operation(self):
        """Cancel the current USB creation operation."""
        if self.worker and self.worker.isRunning():
            self.cancel_requested = True
            self.worker.cancel()
            self.status_message.setText("Cancelling operation...")
            self.cancel_button.setEnabled(False)

    def handle_worker_status(self, status):
        """Handle status updates from worker."""
        self.status_message.setText(status)

    def start_operation(self):
        """Start USB creation operation."""
        self.cancel_requested = False
        self.cancel_button.setEnabled(True)
        self.create_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def finish_operation(self):
        """Clean up after operation completes."""
        self.cancel_button.setEnabled(False)
        self.create_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.cancel_requested = False
        self.refresh_drive_list()

    async def check_for_updates(self):
        """Check for application updates."""
        try:
            has_update, version, url = await self.update_checker.check_for_updates()
            if has_update:
                # Use QTimer to safely update UI from async context
                QTimer.singleShot(0, lambda: self.show_update_notification(version, url))
        except Exception as e:
            logging.error(f"Update check failed: {e}")

    def show_update_notification(self, version, url):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(f"New version {version} available!")
        msg.setInformativeText(f"Download from: {url}")
        msg.setWindowTitle("Update Available")
        msg.exec_()

    def backup_config(self):
        """Backup current configuration."""
        try:
            config = self.get_current_config()
            backup_path = self.backup_manager.create_backup(
                self.drive_combo.currentText(),
                config
            )
            self.show_notification("Backup Created", f"Backup saved to {backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Error", str(e))

    def restore_config(self):
        """Restore configuration from backup."""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Backup File", 
                self.backup_manager.backup_dir,
                "Backup Files (*.gz)"
            )
            if file_path:
                config = self.backup_manager.restore_backup(file_path)
                self.apply_config(config)
        except Exception as e:
            QMessageBox.critical(self, "Restore Error", str(e))

    def apply_config(self, config):
        """Apply configuration settings from backup."""
        # Apply the configuration settings to the UI and other components
        pass

    def get_current_config(self):
        """Get current configuration settings."""
        # Retrieve current settings from the UI and other components
        return {}

    def load_settings(self):
        """Load application settings."""
        try:
            with open('settings.json', 'r') as f:
                settings = json.load(f)
                # Apply settings to the application
                self.apply_settings(settings)
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")

    def save_settings(self):
        """Save application settings."""
        try:
            settings = self.get_current_settings()
            with open('settings.json', 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

    def apply_settings(self, settings):
        """Apply settings to the application."""
        # Apply settings to the UI and other components
        pass

    def get_current_settings(self):
        """Get current application settings."""
        # Retrieve current settings from the UI and other components
        return {}


