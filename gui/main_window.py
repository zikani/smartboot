"""
Main window for SmartBoot application
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QComboBox, QProgressBar,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout,
    QCheckBox, QRadioButton, QButtonGroup, QSpacerItem,
    QSizePolicy, QGridLayout
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon
from PyQt5.Qt import QApplication

from core.usb_manager import USBManager
from core.iso_manager import ISOManager
from core.image_writer import ImageWriter
from core.boot_sector.manager import BootSectorManager
import os
import tempfile


class MainWindow(QMainWindow):
    """
    Main window for the SmartBoot application.
    """
    
    def __init__(self):
        super().__init__()
        
        # Initialize resources directory
        self.resource_dir = os.path.join(tempfile.gettempdir(), "smartboot_resources")
        os.makedirs(self.resource_dir, exist_ok=True)
        
        self.usb_manager = USBManager()
        self.iso_manager = ISOManager()
        self.usb_writer = ImageWriter()
        self.boot_manager = BootSectorManager()
        
        self.selected_device = None
        self.selected_iso = None
        self.detected_iso_type = None  # Track detected ISO type
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("SmartBoot - USB Boot Media Creator")
        self.setMinimumSize(600, 500)
        
        # Create central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Create header with logo and title
        header_layout = QHBoxLayout()
        logo_label = QLabel("🚀")  # Placeholder for logo
        logo_label.setStyleSheet("font-size: 24px;")
        title_label = QLabel("SmartBoot")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        # Device selection section
        device_group = QGroupBox("Step 1: Select USB Device")
        device_layout = QVBoxLayout(device_group)
        
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.on_device_selected)
        self.device_combo.setMinimumWidth(400)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_devices)
        
        device_select_layout = QHBoxLayout()
        device_select_layout.addWidget(self.device_combo)
        device_select_layout.addWidget(self.refresh_button)
        
        device_layout.addLayout(device_select_layout)
        
        # Device info
        self.device_info_label = QLabel("No device selected")
        device_layout.addWidget(self.device_info_label)
        
        main_layout.addWidget(device_group)
        
        # ISO selection section
        iso_group = QGroupBox("Step 2: Select ISO Image")
        iso_layout = QVBoxLayout(iso_group)
        
        self.iso_path_label = QLabel("No ISO selected")
        self.iso_path_label.setWordWrap(True)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_iso)
        
        iso_select_layout = QHBoxLayout()
        iso_select_layout.addWidget(self.iso_path_label)
        iso_select_layout.addWidget(self.browse_button)
        
        iso_layout.addLayout(iso_select_layout)
        
        # ISO info
        self.iso_info_label = QLabel("")
        iso_layout.addWidget(self.iso_info_label)
        
        main_layout.addWidget(iso_group)
        
        # Options section
        options_group = QGroupBox("Step 3: Options")
        options_layout = QFormLayout(options_group)
        
        # Partition scheme
        self.partition_scheme_group = QButtonGroup(self)
        mbr_radio = QRadioButton("MBR (Legacy BIOS)")
        gpt_radio = QRadioButton("GPT (UEFI)")
        self.partition_scheme_group.addButton(mbr_radio, 0)
        self.partition_scheme_group.addButton(gpt_radio, 1)
        mbr_radio.setChecked(True)
        
        partition_layout = QHBoxLayout()
        partition_layout.addWidget(mbr_radio)
        partition_layout.addWidget(gpt_radio)
        options_layout.addRow("Partition Scheme:", partition_layout)
        
        # Boot type
        self.boot_type_group = QButtonGroup(self)
        bios_radio = QRadioButton("BIOS")
        uefi_radio = QRadioButton("UEFI")
        dual_radio = QRadioButton("Dual (BIOS+UEFI)")
        freedos_radio = QRadioButton("FreeDOS")
        self.boot_type_group.addButton(bios_radio, 0)
        self.boot_type_group.addButton(uefi_radio, 1)
        self.boot_type_group.addButton(dual_radio, 2)
        self.boot_type_group.addButton(freedos_radio, 3)
        bios_radio.setChecked(True)
        
        # Connect signals to update UI based on selections
        bios_radio.toggled.connect(self.update_boot_options)
        uefi_radio.toggled.connect(self.update_boot_options)
        dual_radio.toggled.connect(self.update_boot_options)
        freedos_radio.toggled.connect(self.update_boot_options)
        mbr_radio.toggled.connect(self.update_boot_options)
        gpt_radio.toggled.connect(self.update_boot_options)
        
        boot_layout = QGridLayout()
        boot_layout.addWidget(bios_radio, 0, 0)
        boot_layout.addWidget(uefi_radio, 0, 1)
        boot_layout.addWidget(dual_radio, 1, 0)
        boot_layout.addWidget(freedos_radio, 1, 1)
        options_layout.addRow("Boot Type:", boot_layout)
        
        # Filesystem
        self.filesystem_combo = QComboBox()
        self.update_filesystem_options()
        options_layout.addRow("Filesystem:", self.filesystem_combo)
        
        # Quick format
        self.format_checkbox = QCheckBox("Quick Format")
        self.format_checkbox.setChecked(True)
        options_layout.addRow("", self.format_checkbox)
        
        # Advanced options
        self.advanced_group = QGroupBox("Advanced Options")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        advanced_layout = QFormLayout(self.advanced_group)
        
        # Direct write option
        self.direct_write_checkbox = QCheckBox("Direct Write (dd mode)")
        self.direct_write_checkbox.setToolTip("Write ISO directly to USB without extracting files")
        advanced_layout.addRow("", self.direct_write_checkbox)
        
        # ISO type detection
        self.iso_type_combo = QComboBox()
        self.iso_type_combo.addItems(["Auto-detect", "Windows", "Linux", "FreeDOS", "Generic"])
        advanced_layout.addRow("ISO Type:", self.iso_type_combo)
        
        options_layout.addRow("", self.advanced_group)
        
        main_layout.addWidget(options_group)
        
        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Ready")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        main_layout.addWidget(progress_group)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.start_button = QPushButton("START")
        self.start_button.setMinimumSize(100, 40)
        self.start_button.clicked.connect(self.start_process)
        self.start_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        main_layout.addLayout(button_layout)
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Initialize device list
        self.refresh_devices()
    
    def refresh_devices(self):
        """Refresh the list of USB devices."""
        self.device_combo.clear()
        try:
            self.devices = self.usb_manager.get_devices()
            if not self.devices:
                self.device_combo.addItem("No USB devices found")
                self.device_info_label.setText("No devices found")
                self.selected_device = None
                self.update_start_button()
                return
            for device in self.devices:
                self.device_combo.addItem(f"{device['name']} ({device['size']})")
            self.device_combo.setCurrentIndex(0)
            self.selected_device = self.devices[0]
            self.update_device_info()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error refreshing devices: {str(e)}")
            self.device_info_label.setText("Error loading devices")
    
    def update_device_info(self):
        """Update the device information display."""
        if self.selected_device:
            info = (
                f"Device: {self.selected_device['name']}\n"
                f"Size: {self.selected_device['size']}\n"
                f"File System: {self.selected_device.get('filesystem', 'Unknown')}"
            )
            self.device_info_label.setText(info)
        else:
            self.device_info_label.setText("No device selected")
        self.update_start_button()

    def on_device_selected(self, index):
        if hasattr(self, 'devices') and self.devices and 0 <= index < len(self.devices):
            self.selected_device = self.devices[index]
        else:
            self.selected_device = None
        self.update_device_info()
    
    def browse_iso(self):
        """Open file dialog to select an ISO file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO File", "", "ISO Files (*.iso);;All Files (*)"
        )
        
        if file_path:
            self.selected_iso = file_path
            self.iso_path_label.setText(file_path)
            try:
                iso_info = self.iso_manager.get_iso_info(file_path)
                self.iso_info_label.setText(
                    f"Size: {iso_info['size']}\n"
                    f"Type: {iso_info.get('type', 'Unknown')}"
                )
            except Exception as e:
                QMessageBox.warning(self, "Warning", f"Could not read ISO details: {str(e)}")
                self.iso_info_label.setText(f"Size: Unknown\nType: Unknown")
        
        self.update_start_button()
    
    def update_filesystem_options(self):
        """Update filesystem options based on selected boot type and partition scheme."""
        current_fs = self.filesystem_combo.currentText() if self.filesystem_combo.count() > 0 else "FAT32"
        self.filesystem_combo.clear()
        
        # Get boot type and partition scheme
        boot_type_id = self.boot_type_group.checkedId() if hasattr(self, 'boot_type_group') else 0
        partition_scheme_id = self.partition_scheme_group.checkedId()
        
        # Set filesystem options based on boot type and partition scheme
        if boot_type_id == 3:  # FreeDOS
            self.filesystem_combo.addItems(["FAT32", "FAT"])
        elif boot_type_id == 1 or boot_type_id == 2:  # UEFI or Dual
            if partition_scheme_id == 1:  # GPT
                self.filesystem_combo.addItems(["FAT32", "NTFS", "exFAT"])
            else:  # MBR
                self.filesystem_combo.addItems(["FAT32", "NTFS", "exFAT"])
        else:  # BIOS
            self.filesystem_combo.addItems(["FAT32", "NTFS", "exFAT", "UDF"])
        
        # Try to restore previous selection if it's still available
        index = self.filesystem_combo.findText(current_fs)
        if index >= 0:
            self.filesystem_combo.setCurrentIndex(index)
    
    def update_boot_options(self):
        """Update UI based on boot type and partition scheme selections."""
        # Get current selections
        boot_type_id = self.boot_type_group.checkedId()
        partition_scheme_id = self.partition_scheme_group.checkedId()
        
        # Enforce compatibility between boot type and partition scheme
        if boot_type_id == 1:  # UEFI
            # UEFI requires GPT
            if partition_scheme_id == 0:  # MBR
                self.partition_scheme_group.button(1).setChecked(True)  # Switch to GPT
        elif boot_type_id == 3:  # FreeDOS
            # FreeDOS requires MBR
            if partition_scheme_id == 1:  # GPT
                self.partition_scheme_group.button(0).setChecked(True)  # Switch to MBR
        
        # Update filesystem options
        self.update_filesystem_options()
    
    def update_start_button(self):
        """Update the state of the start button based on selections."""
        self.start_button.setEnabled(
            self.selected_device is not None and 
            self.selected_iso is not None
        )
    
    def start_process(self):
        """Start the process of creating bootable USB."""
        # Confirm with user before proceeding
        reply = QMessageBox.warning(
            self,
            "Warning - Data Loss",
            f"This will erase ALL data on {self.selected_device['name']}\nDo you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
            
        # Disable UI during process
        self.setEnabled(False)
        QApplication.processEvents()
        
        try:
            # Get selected options
            partition_scheme = "MBR" if self.partition_scheme_group.checkedId() == 0 else "GPT"
            filesystem = self.filesystem_combo.currentText()
            quick_format = self.format_checkbox.isChecked()
            
            # Get boot type
            boot_type_map = {
                0: "bios",
                1: "uefi",
                2: "dual",
                3: "freedos"
            }
            boot_type = boot_type_map.get(self.boot_type_group.checkedId(), "bios")
            
            # Get ISO type
            iso_type = "auto"
            if self.advanced_group.isChecked():
                iso_type_text = self.iso_type_combo.currentText().lower()
                if iso_type_text != "auto-detect":
                    iso_type = iso_type_text
            
            # Direct write option
            direct_write = False
            if self.advanced_group.isChecked():
                direct_write = self.direct_write_checkbox.isChecked()
            
            # Prepare options
            options = {
                'partition_scheme': partition_scheme,
                'filesystem': filesystem,
                'quick_format': quick_format,
                'boot_type': boot_type,
                'iso_type': iso_type,
                'direct_write': direct_write
            }
            
            # Progress callback
            def progress_callback(percent, message):
                self.progress_bar.setValue(percent)
                self.status_label.setText(message)
                QApplication.processEvents()
                
            self.status_label.setText("Starting process...")
            self.progress_bar.setValue(0)
            
            # Step 1: Format the USB drive
            from smartboot.core.disk_formatter import DiskFormatter
            formatter = DiskFormatter()
            
            self.status_label.setText("Formatting USB drive...")
            success_format, drive_path = formatter.format_disk(
                self.selected_device,
                filesystem,
                "SMARTBOOT",  # Label
                partition_scheme,
                quick_format,
                progress_callback
            )
            
            if not success_format:
                self.status_label.setText("Failed to format USB drive.")
                QMessageBox.critical(self, "Error", "Failed to format USB drive.")
                return
                
            # Update device with new drive letter/path
            if drive_path:
                self.selected_device['drive_letter'] = drive_path
            
            # Step 2: Write ISO to USB
            if direct_write:
                # Direct write using dd-like operation
                from smartboot.core.image_writer import ImageWriter
                writer = ImageWriter()
                
                self.status_label.setText("Writing ISO directly to USB...")
                success_write = writer.write_disk_image(
                    self.selected_iso,
                    self.selected_device.get('name'),
                    progress_callback
                )
                
                if success_write:
                    self.status_label.setText("USB drive created successfully!")
                    self.progress_bar.setValue(100)
                    QMessageBox.information(self, "Success", "USB drive created successfully!")
                else:
                    self.status_label.setText("Failed to write ISO to USB drive.")
                    QMessageBox.critical(self, "Error", "Failed to write ISO to USB drive.")
            else:
                # Extract ISO and write boot sector
                self.status_label.setText("Writing ISO to USB...")
                
                # Step 2a: Write ISO files
                from smartboot.core.image_writer import ImageWriter
                writer = ImageWriter()
                
                success_iso = writer.write_iso(
                    self.selected_iso,
                    self.selected_device.get('drive_letter'),
                    iso_type,
                    not direct_write,  # extract_files
                    progress_callback
                )
                
                if not success_iso:
                    self.status_label.setText("Failed to write ISO to USB drive.")
                    QMessageBox.critical(self, "Error", "Failed to write ISO to USB drive.")
                    return
                    
                # Step 2b: Write boot sector
                self.status_label.setText("Writing boot sector...")
                boot_success = self.boot_manager.write_boot_sector(
                    self.selected_device,
                    options,
                    progress_callback
                )
                
                if boot_success:
                    self.status_label.setText("USB drive created successfully!")
                    self.progress_bar.setValue(100)
                    QMessageBox.information(self, "Success", "USB drive created successfully!")
                else:
                    self.status_label.setText("USB drive created but boot sector writing failed.")
                    QMessageBox.warning(self, "Warning", "USB created but could not write boot sector.")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error during writing process: {str(e)}")
        finally:
            # Re-enable UI
            self.setEnabled(True)
