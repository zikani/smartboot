from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QFileDialog, QMessageBox, QProgressBar, QLineEdit, QComboBox, QSystemTrayIcon, QAction, QMenu,QStyle
from PyQt5.QtCore import Qt
from worker import Worker
import os



class SmartBootUI(QWidget):  # Renamed class from RufusCloneUI to SmartBootUI
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Boot")  # Updated window title
        self.resize(515, 584)
        self.worker = Worker()  # Create an instance of the Worker class
        self.worker.progress_update.connect(self.update_progress_bar)  # Connect progress signal
        self.worker.finished.connect(self.handle_worker_finished)  # Connect finished signal
        # Initialize system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.tray_icon.setToolTip("Smart Boot")
        self.create_tray_menu()
        
        self.initUI()

    def closeEvent(self, event):
        # Hide the window and show the system tray icon on close
        event.ignore()
        self.hide()
        self.tray_icon.show()

    def create_tray_menu(self):
        # Create a menu for the system tray icon
        tray_menu = QMenu(self)
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.show)
        tray_menu.addAction(restore_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(exit_action)

        # Set the menu for the system tray icon
        self.tray_icon.setContextMenu(tray_menu)

    def initUI(self):
        layout = QVBoxLayout()

        # Drag and Drop Area
        self.drag_drop_label = QLabel("Drag and drop ISO file here")
        self.drag_drop_label.setAlignment(Qt.AlignCenter)
        self.drag_drop_label.setAcceptDrops(True)
        self.drag_drop_label.setStyleSheet("border: 2px dashed #aaa; padding: 20px;")
        layout.addWidget(self.drag_drop_label)

        # Connect drag and drop event handler
        self.drag_drop_label.dropEvent = self.dropEvent
        self.drag_drop_label.dragEnterEvent = self.dragEnterEvent

        # ISO File Path Input
        self.iso_label = QLabel("ISO file path:")
        self.iso_entry = QLineEdit()
        layout.addWidget(self.iso_label)
        layout.addWidget(self.iso_entry)

        # Other UI elements
        self.create_drive_widgets(layout)
        self.device_combo = self.create_combobox(layout, "Select USB Device:")
        self.boot_type_combo = self.create_combobox(layout, "Select Boot Type:", items=["UEFI", "Legacy"])
        self.partition_scheme_combo = self.create_combobox(layout, "Select Partition Scheme:", items=["MBR", "GPT"])
        self.progress_bar = self.create_progress_bar(layout)
        self.file_system_combo = self.create_combobox(layout, "Select File System:", items=["FAT32", "NTFS", "exFAT"])
        self.volume_label_entry = self.create_widgets(layout, "Volume Label:")

        self.create_button(layout, "Browse", self.select_drive)
        self.create_button(layout, "Create Bootable USB", self.confirm_create_bootable)

        self.status_label = self.create_label(layout)

        self.setLayout(layout)


    def create_combobox(self, layout, label_text, items=[]):
        label = QLabel(label_text)
        combo = QComboBox()
        if items:
            combo.addItems(items)
        layout.addWidget(label)
        layout.addWidget(combo)
        return combo
    
    def handle_worker_finished(self):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Bootable USB creation completed.")
        self.show_notification("USB Creation Completed", "The bootable USB creation process has finished.")

    def show_notification(self, title, message):
        # Show a system notification
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 5000)

    def create_drive_widgets(self, layout):
        self.drive_entry = QLineEdit()
        layout.addWidget(QLabel("Select USB Drive:"))
        layout.addWidget(self.drive_entry)

    def create_progress_bar(self, layout):
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def create_widgets(self, layout, label_text):
        label = QLabel(label_text)
        entry = QLineEdit()
        layout.addWidget(label)
        layout.addWidget(entry)
        return entry

    def create_button(self, layout, button_text, on_click_function):
        button = QPushButton(button_text)
        button.clicked.connect(on_click_function)
        layout.addWidget(button)

    def create_label(self, layout):
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def select_drive(self):
        drive = QFileDialog.getExistingDirectory(self, "Select USB Drive")
        if drive:
            self.drive_entry.setText(drive)

    def dropEvent(self, event):
        # Handle dropped files
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path) and path.endswith('.iso'):
                    self.set_iso_file_path(path)
                    self.auto_label_volume(path)  # Automatically label volume based on ISO file
                    break
            else:
                QMessageBox.warning(self, "Invalid File", "Please drop an ISO file.")
        else:
            QMessageBox.warning(self, "Invalid File", "Please drop an ISO file.")

    def auto_label_volume(self, iso_path):
        # Automatically label volume based on ISO file name
        volume_label = os.path.splitext(os.path.basename(iso_path))[0]
        self.volume_label_entry.setText(volume_label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def set_iso_file_path(self, path):
        self.iso_entry.setText(path)
        self.drag_drop_label.setText("ISO file: " + path)

    def confirm_create_bootable(self):
        # Get selected options
        iso_path = self.iso_entry.text()
        drive_path = self.drive_entry.text()
        file_system = self.file_system_combo.currentText()
        volume_label = self.volume_label_entry.text()
        selected_device = self.device_combo.currentText()
        selected_boot_type = self.boot_type_combo.currentText()
        selected_partition_scheme = self.partition_scheme_combo.currentText()

        # Construct preview message
        preview_message = f"ISO file: {iso_path}\n"
        preview_message += f"USB drive: {drive_path}\n"
        preview_message += f"File System: {file_system}\n"
        preview_message += f"Volume Label: {volume_label}\n"
        preview_message += f"USB Device: {selected_device}\n"
        preview_message += f"Boot Type: {selected_boot_type}\n"
        preview_message += f"Partition Scheme: {selected_partition_scheme}\n"

        # Show confirmation message box with preview
        confirmation = QMessageBox.question(self, "Confirmation", 
                                             f"Are you sure you want to create a bootable USB drive?\n\n{preview_message}",
                                             QMessageBox.Yes | QMessageBox.No)
        if confirmation == QMessageBox.Yes:
            self.create_bootable()

    def create_bootable(self):
        iso_path = self.iso_entry.text()
        drive_path = self.drive_entry.text()
        file_system = self.file_system_combo.currentText()
        volume_label = self.volume_label_entry.text()
        selected_device = self.device_combo.currentText()
        selected_boot_type = self.boot_type_combo.currentText()
        selected_partition_scheme = self.partition_scheme_combo.currentText()

        if not iso_path or not drive_path or not selected_device:
            QMessageBox.warning(self, "Error", "Please select ISO file, USB drive, and USB device.")
            return

        self.progress_bar.setVisible(True)
        self.status_label.setText("Creating bootable USB...")
        self.worker.set_arguments(iso_path, drive_path, file_system, volume_label, selected_device, selected_boot_type, selected_partition_scheme)
        self.worker.start()  # Start the worker thread


    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def handle_worker_finished(self):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Bootable USB creation completed.")

    


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SmartBootUI()
    window.show()
    sys.exit(app.exec_())
