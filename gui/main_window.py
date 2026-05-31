"""
Main window for SmartBoot

All long-running operations run on a CreationWorker (QThread) so the UI
stays responsive.  A Cancel button is exposed while work is in progress.
"""

import os
import tempfile

from PyQt5.QtCore    import Qt, QSize
from PyQt5.QtGui     import QIcon, QFont
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QProgressBar,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout,
    QCheckBox, QRadioButton, QButtonGroup, QSizePolicy,
    QGridLayout, QApplication,
)

from core.usb_manager          import USBManager
from core.iso_manager          import ISOManager
from core.image_writer         import ImageWriter
from core.disk_formatter       import DiskFormatter
from core.boot_sector.manager  import BootSectorManager
from gui.worker                import CreationWorker


class MainWindow(QMainWindow):
    """Main application window."""

    # Map boot_type_group button id → internal string
    _BOOT_TYPE_MAP = {0: "bios", 1: "uefi", 2: "dual", 3: "freedos"}

    def __init__(self) -> None:
        super().__init__()

        self.resource_dir = os.path.join(
            tempfile.gettempdir(), "smartboot_resources"
        )
        os.makedirs(self.resource_dir, exist_ok=True)

        # Core objects (stateless; re-used across operations)
        self.usb_manager  = USBManager()
        self.iso_manager  = ISOManager()
        self.writer       = ImageWriter()
        self.formatter    = DiskFormatter()
        self.boot_manager = BootSectorManager()

        # State
        self.devices: list         = []
        self.selected_device: dict = {}
        self.selected_iso: str     = ""
        self._worker: CreationWorker | None = None

        self._build_ui()
        self.refresh_devices()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("SmartBoot — USB Boot Media Creator")
        self.setMinimumSize(640, 560)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(8)

        layout.addLayout(self._make_header())
        layout.addWidget(self._make_device_group())
        layout.addWidget(self._make_iso_group())
        layout.addWidget(self._make_options_group())
        layout.addWidget(self._make_progress_group())
        layout.addLayout(self._make_button_row())

        self.setCentralWidget(root)

    def _make_header(self) -> QHBoxLayout:
        hbox = QHBoxLayout()
        logo = QLabel("SB")
        logo.setFont(QFont("Arial", 20, QFont.Bold))
        logo.setStyleSheet("color: #1565C0;")
        title = QLabel("SmartBoot")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        hbox.addWidget(logo)
        hbox.addWidget(title)
        hbox.addStretch()
        return hbox

    def _make_device_group(self) -> QGroupBox:
        grp = QGroupBox("Step 1 — Select USB Device")
        vbox = QVBoxLayout(grp)

        row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(380)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        row.addWidget(self.device_combo)
        row.addWidget(self.refresh_btn)
        vbox.addLayout(row)

        self.device_info_lbl = QLabel("No device selected.")
        self.device_info_lbl.setWordWrap(True)
        vbox.addWidget(self.device_info_lbl)
        return grp

    def _make_iso_group(self) -> QGroupBox:
        grp = QGroupBox("Step 2 — Select ISO Image")
        vbox = QVBoxLayout(grp)

        row = QHBoxLayout()
        self.iso_path_lbl = QLabel("No ISO selected.")
        self.iso_path_lbl.setWordWrap(True)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._browse_iso)
        row.addWidget(self.iso_path_lbl, 1)
        row.addWidget(self.browse_btn)
        vbox.addLayout(row)

        self.iso_info_lbl = QLabel("")
        vbox.addWidget(self.iso_info_lbl)
        return grp

    def _make_options_group(self) -> QGroupBox:
        grp = QGroupBox("Step 3 — Options")
        form = QFormLayout(grp)

        # Partition scheme
        self.scheme_group = QButtonGroup(self)
        mbr_rb = QRadioButton("MBR (Legacy BIOS)")
        gpt_rb = QRadioButton("GPT (UEFI)")
        self.scheme_group.addButton(mbr_rb, 0)
        self.scheme_group.addButton(gpt_rb, 1)
        mbr_rb.setChecked(True)
        scheme_row = QHBoxLayout()
        scheme_row.addWidget(mbr_rb)
        scheme_row.addWidget(gpt_rb)
        form.addRow("Partition Scheme:", scheme_row)

        # Boot type
        self.boot_group = QButtonGroup(self)
        bios_rb   = QRadioButton("BIOS")
        uefi_rb   = QRadioButton("UEFI")
        dual_rb   = QRadioButton("Dual (BIOS+UEFI)")
        fdos_rb   = QRadioButton("FreeDOS")
        for bid, rb in enumerate([bios_rb, uefi_rb, dual_rb, fdos_rb]):
            self.boot_group.addButton(rb, bid)
        bios_rb.setChecked(True)

        boot_grid = QGridLayout()
        boot_grid.addWidget(bios_rb,  0, 0)
        boot_grid.addWidget(uefi_rb,  0, 1)
        boot_grid.addWidget(dual_rb,  1, 0)
        boot_grid.addWidget(fdos_rb,  1, 1)
        form.addRow("Boot Type:", boot_grid)

        # Wire scheme/boot interdependency
        for btn in self.scheme_group.buttons() + self.boot_group.buttons():
            btn.toggled.connect(self._sync_boot_options)

        # Filesystem
        self.fs_combo = QComboBox()
        self._update_fs_options()
        form.addRow("Filesystem:", self.fs_combo)

        # Quick format
        self.quick_fmt_chk = QCheckBox("Quick Format")
        self.quick_fmt_chk.setChecked(True)
        form.addRow("", self.quick_fmt_chk)

        # Advanced options (collapsible)
        adv_grp = QGroupBox("Advanced Options")
        adv_grp.setCheckable(True)
        adv_grp.setChecked(False)
        adv_form = QFormLayout(adv_grp)

        self.direct_write_chk = QCheckBox("Direct Write (dd-like)")
        self.direct_write_chk.setToolTip(
            "Write ISO bytes directly to the device — faster, "
            "but skips file extraction and boot sector steps."
        )
        adv_form.addRow("", self.direct_write_chk)

        self.iso_type_combo = QComboBox()
        self.iso_type_combo.addItems(
            ["Auto-detect", "Windows", "Linux", "FreeDOS", "Generic"]
        )
        adv_form.addRow("ISO Type Override:", self.iso_type_combo)
        self._adv_grp = adv_grp
        form.addRow("", adv_grp)

        return grp

    def _make_progress_group(self) -> QGroupBox:
        grp = QGroupBox("Progress")
        vbox = QVBoxLayout(grp)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_lbl = QLabel("Ready.")
        self.status_lbl.setWordWrap(True)
        vbox.addWidget(self.progress_bar)
        vbox.addWidget(self.status_lbl)
        return grp

    def _make_button_row(self) -> QHBoxLayout:
        hbox = QHBoxLayout()
        hbox.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumSize(100, 38)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        hbox.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("START")
        self.start_btn.setMinimumSize(110, 38)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:disabled { background-color: #90A4AE; }"
        )
        hbox.addWidget(self.start_btn)
        return hbox

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def refresh_devices(self) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        try:
            self.devices = self.usb_manager.get_devices()
            if not self.devices:
                self.device_combo.addItem("No USB devices found")
                self.selected_device = {}
            else:
                for dev in self.devices:
                    self.device_combo.addItem(
                        f"{dev['name']}  ({dev['size']})"
                    )
                self.selected_device = self.devices[0]
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"Failed to enumerate devices:\n{exc}")
            self.selected_device = {}
        finally:
            self.device_combo.blockSignals(False)
            self.device_combo.setCurrentIndex(0)
            self._update_device_info()

    def _on_device_changed(self, idx: int) -> None:
        if self.devices and 0 <= idx < len(self.devices):
            self.selected_device = self.devices[idx]
        else:
            self.selected_device = {}
        self._update_device_info()

    def _update_device_info(self) -> None:
        if self.selected_device:
            d = self.selected_device
            self.device_info_lbl.setText(
                f"Name: {d.get('name','?')}   "
                f"Size: {d.get('size','?')}   "
                f"FS: {d.get('filesystem','?')}"
            )
        else:
            self.device_info_lbl.setText("No device selected.")
        self._update_start_btn()

    # ------------------------------------------------------------------
    # ISO selection
    # ------------------------------------------------------------------

    def _browse_iso(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO File", "",
            "ISO Images (*.iso);;All Files (*)"
        )
        if not path:
            return
        self.selected_iso = path
        self.iso_path_lbl.setText(path)
        try:
            info = self.iso_manager.get_iso_info(path)
            self.iso_info_lbl.setText(
                f"Size: {info['size']}   Type: {info.get('type','Unknown')}"
            )
        except Exception as exc:
            self.iso_info_lbl.setText(f"Could not read ISO info: {exc}")
        self._update_start_btn()

    # ------------------------------------------------------------------
    # Options synchronisation
    # ------------------------------------------------------------------

    def _sync_boot_options(self) -> None:
        boot_id   = self.boot_group.checkedId()
        scheme_id = self.scheme_group.checkedId()

        # UEFI / Dual should prefer GPT
        if boot_id in (1, 2) and scheme_id == 0:
            self.scheme_group.button(1).setChecked(True)
        # FreeDOS needs MBR
        elif boot_id == 3 and scheme_id == 1:
            self.scheme_group.button(0).setChecked(True)

        self._update_fs_options()

    def _update_fs_options(self) -> None:
        current = self.fs_combo.currentText() if self.fs_combo.count() else "FAT32"
        self.fs_combo.clear()

        boot_id = self.boot_group.checkedId() if hasattr(self, "boot_group") else 0

        # Get platform-specific supported filesystems
        all_supported = self.formatter.get_supported_filesystems()

        if boot_id == 3:                        # FreeDOS
            # FreeDOS only works with FAT filesystems
            options = [fs for fs in all_supported if fs.upper() in ["FAT", "FAT32"]]
        elif boot_id in (1, 2):                 # UEFI / Dual
            # UEFI works best with FAT32, but also supports NTFS/exFAT
            options = [fs for fs in all_supported if fs.upper() in ["FAT32", "NTFS", "EXFAT"]]
        else:                                   # BIOS
            # BIOS supports most filesystems
            options = all_supported

        # Sort options for consistency
        options = sorted(options, key=lambda x: x.upper())

        self.fs_combo.addItems(options)
        idx = self.fs_combo.findText(current)
        if idx >= 0:
            self.fs_combo.setCurrentIndex(idx)

    def _update_start_btn(self) -> None:
        self.start_btn.setEnabled(
            bool(self.selected_device)
            and bool(self.selected_iso)
            and self._worker is None
        )

    # ------------------------------------------------------------------
    # Start / Cancel
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        # Safety confirmation
        name = self.selected_device.get("name", "the selected device")
        reply = QMessageBox.warning(
            self,
            "Data Loss Warning",
            f"ALL data on '{name}' will be permanently erased.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        options = self._collect_options()
        self._set_working(True)

        self._worker = CreationWorker(
            formatter    = self.formatter,
            writer       = self.writer,
            boot_manager = self.boot_manager,
            device       = self.selected_device,
            iso_path     = self.selected_iso,
            options      = options,
            parent       = self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_lbl.setText("Cancelling… please wait.")
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_finished(self, success: bool, msg: str) -> None:
        self._set_working(False)
        self._worker = None
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.status_lbl.setText(msg)

        if success:
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.warning(self, "Completed with issues", msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_options(self) -> dict:
        scheme   = "MBR" if self.scheme_group.checkedId() == 0 else "GPT"
        boot     = self._BOOT_TYPE_MAP.get(self.boot_group.checkedId(), "bios")
        fs       = self.fs_combo.currentText()
        quick    = self.quick_fmt_chk.isChecked()
        advanced = self._adv_grp.isChecked()
        direct   = self.direct_write_chk.isChecked() if advanced else False

        iso_type = "auto"
        if advanced:
            raw = self.iso_type_combo.currentText().lower()
            if raw != "auto-detect":
                iso_type = raw

        return {
            "partition_scheme": scheme,
            "boot_type":        boot,
            "filesystem":       fs,
            "quick_format":     quick,
            "direct_write":     direct,
            "iso_type":         iso_type,
        }

    def _set_working(self, working: bool) -> None:
        """Toggle UI elements between idle and working states."""
        self.start_btn.setVisible(not working)
        self.cancel_btn.setVisible(working)
        self.cancel_btn.setEnabled(working)

        self.refresh_btn.setEnabled(not working)
        self.browse_btn.setEnabled(not working)
        self.device_combo.setEnabled(not working)

        if working:
            self.progress_bar.setValue(0)
            self.status_lbl.setText("Starting…")
        else:
            self._update_start_btn()

    def closeEvent(self, event) -> None:
        """Ensure the worker thread is stopped before the window closes."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)   # 5 s grace period
        event.accept()