"""
SmartBoot — Main Window (Enhanced)

Feature parity with Rufus plus extras:
  ✔ Device selection with write-protect / size warning icons
  ✔ ISO picker with drag-and-drop + recent history
  ✔ Auto-recommend partition scheme, boot type, filesystem from ISO
  ✔ Checksum panel (MD5 / SHA1 / SHA256) with progress
  ✔ Persistent storage slider (Linux live)
  ✔ Bad-block pre-scan toggle
  ✔ Cluster size selector
  ✔ Volume label editor
  ✔ Stage progress bar (5 stages)
  ✔ Detailed log panel (collapsible)
  ✔ Dark / Light theme toggle
  ✔ Cancel with confirmation
  ✔ Write-protect warning
  ✔ Size-mismatch warning
  ✔ About dialog
"""

import os
import tempfile

from PyQt5.QtCore    import Qt, QSize, QThread, pyqtSignal, QTimer
from PyQt5.QtGui     import QIcon, QFont, QDragEnterEvent, QDropEvent, QColor, QPalette
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QProgressBar,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout,
    QCheckBox, QRadioButton, QButtonGroup, QSizePolicy,
    QApplication, QSlider, QSpinBox, QLineEdit, QTextEdit,
    QSplitter, QFrame, QTabWidget, QDialog, QDialogButtonBox,
    QAction, QMenuBar, QStatusBar, QToolButton, QScrollArea,
)

from resources.icons import get_icon

from core.usb_manager          import USBManager
from core.iso_manager          import ISOManager
from core.image_writer         import ImageWriter
from core.disk_formatter       import DiskFormatter
from core.boot_sector.manager  import BootSectorManager
from gui.worker                import CreationWorker



class ChecksumWorker(QThread):
    progress = pyqtSignal(int, str)
    result   = pyqtSignal(str, str)

    def __init__(self, iso_manager, iso_path: str, algorithm: str, parent=None):
        super().__init__(parent)
        self._mgr  = iso_manager
        self._path = iso_path
        self._algo = algorithm

    def run(self) -> None:
        def cb(pct, msg):
            self.progress.emit(pct, msg)
        digest = self._mgr.compute_checksum(self._path, self._algo, cb)
        self.result.emit(self._algo, digest)



class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About SmartBoot")
        self.setFixedSize(400, 300)
        layout = QVBoxLayout(self)

        title = QLabel("SmartBoot")
        title.setFont(QFont("Georgia", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("USB Boot Media Creator  •  v0.2.0")
        subtitle.setAlignment(Qt.AlignCenter)

        desc = QLabel(
            "A cross-platform, Rufus-inspired tool for creating\n"
            "bootable USB drives from ISO images.\n\n"
            "Supports Windows, Linux, FreeDOS & generic ISOs.\n"
            "BIOS, UEFI, and Dual boot modes.\n\n"
            "MIT License  •  github.com/zikani/smartboot"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addWidget(btns)



class MainWindow(QMainWindow):

    _BOOT_TYPE_MAP  = {0: "bios", 1: "uefi", 2: "dual", 3: "freedos"}
    _SCHEME_MAP     = {0: "MBR",  1: "GPT"}
    _CLUSTER_SIZES  = ["Auto", "512", "1024", "2048", "4096",
                        "8192", "16384", "32768", "65536"]

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

        self.resource_dir = os.path.join(tempfile.gettempdir(), "smartboot_resources")
        os.makedirs(self.resource_dir, exist_ok=True)

        self.usb_manager  = USBManager()
        self.iso_manager  = ISOManager()
        self.writer       = ImageWriter()
        self.formatter    = DiskFormatter()
        self.boot_manager = BootSectorManager()

        self.devices: list         = []
        self.selected_device: dict = {}
        self.selected_iso: str     = ""
        self.iso_info: dict        = {}
        self._worker               = None
        self._checksum_worker      = None
        self._dark_mode            = False

        self._build_ui()
        self._apply_theme()
        self._build_menu()
        self.refresh_devices()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh_devices)
        self._refresh_timer.start(3000)


    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(".iso"):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".iso"):
                self._load_iso(path)


    def _build_menu(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        open_iso = QAction("&Open ISO…", self)
        open_iso.setShortcut("Ctrl+O")
        open_iso.triggered.connect(self._browse_iso)
        file_menu.addAction(open_iso)

        recent_menu = file_menu.addMenu("&Recent ISOs")
        self._recent_menu = recent_menu
        self._populate_recent_menu()
        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = mb.addMenu("&View")
        self._theme_action = QAction("Switch to Dark Theme", self)
        self._theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._theme_action)

        log_action = QAction("Show &Log Panel", self)
        log_action.setCheckable(True)
        log_action.setChecked(False)
        log_action.triggered.connect(self._toggle_log)
        self._log_action = log_action
        view_menu.addAction(log_action)

        tools_menu = mb.addMenu("&Tools")
        refresh_action = QAction("&Refresh Devices", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_devices)
        tools_menu.addAction(refresh_action)

        checksum_action = QAction("Compute &Checksum…", self)
        checksum_action.triggered.connect(self._open_checksum_tab)
        tools_menu.addAction(checksum_action)

        help_menu = mb.addMenu("&Help")
        about_action = QAction("&About SmartBoot", self)
        about_action.triggered.connect(lambda: AboutDialog(self).exec_())
        help_menu.addAction(about_action)

    def _populate_recent_menu(self) -> None:
        self._recent_menu.clear()
        history = self.iso_manager.get_history()
        if not history:
            self._recent_menu.addAction("(none)").setEnabled(False)
            return
        for entry in history[:10]:
            path = entry.get("path", "")
            name = entry.get("filename", os.path.basename(path))
            action = QAction(name, self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self._load_iso(p))
            self._recent_menu.addAction(action)
        self._recent_menu.addSeparator()
        clear = QAction("Clear History", self)
        clear.triggered.connect(self._clear_history)
        self._recent_menu.addAction(clear)

    def _clear_history(self) -> None:
        self.iso_manager.clear_history()
        self._populate_recent_menu()


    def _build_ui(self) -> None:
        self.setWindowTitle("SmartBoot — USB Boot Media Creator")
        self.setMinimumSize(700, 700)
        self.resize(760, 800)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        self._splitter = QSplitter(Qt.Vertical)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 8, 10, 8)

        main_layout.addWidget(self._make_header())
        main_layout.addWidget(self._make_device_group())
        main_layout.addWidget(self._make_iso_group())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._make_options_widget(), "Options")
        self._tabs.addTab(self._make_checksum_widget(), "Checksum")
        self._tabs.addTab(self._make_advanced_widget(), "Advanced")
        main_layout.addWidget(self._tabs)

        main_layout.addWidget(self._make_progress_group())
        main_layout.addLayout(self._make_button_row())

        self._splitter.addWidget(main_widget)

        self._log_panel = self._make_log_panel()
        self._log_panel.setVisible(False)
        self._splitter.addWidget(self._log_panel)
        self._splitter.setSizes([700, 0])

        self.setCentralWidget(self._splitter)

    def _make_header(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(QIcon(get_icon("app_logo")).pixmap(32, 32))

        title_lbl = QLabel("SmartBoot")
        title_lbl.setFont(QFont("Georgia", 18, QFont.Bold))
        title_lbl.setObjectName("headerTitle")

        tagline = QLabel("USB Boot Media Creator")
        tagline.setFont(QFont("Segoe UI", 9))
        tagline.setObjectName("tagline")

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(title_lbl)
        title_col.addWidget(tagline)

        h.addWidget(icon_lbl)
        h.addSpacing(6)
        h.addLayout(title_col)
        h.addStretch()

        self._theme_btn = QToolButton()
        self._theme_btn.setIcon(QIcon(get_icon("dark_mode")))
        self._theme_btn.setIconSize(QSize(24, 24))
        self._theme_btn.setToolTip("Toggle dark/light theme")
        self._theme_btn.clicked.connect(self._toggle_theme)
        self._theme_btn.setStyleSheet("border: none; padding: 4px;")
        h.addWidget(self._theme_btn)
        return w


    def _make_device_group(self) -> QGroupBox:
        grp = QGroupBox("① Device")
        grp.setObjectName("sectionGroup")
        vbox = QVBoxLayout(grp)

        row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(400)
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setIcon(QIcon(get_icon("refresh")))
        self.refresh_btn.setFixedWidth(90)
        self.refresh_btn.clicked.connect(self.refresh_devices)

        row.addWidget(self.device_combo)
        row.addWidget(self.refresh_btn)
        vbox.addLayout(row)

        self.device_info_lbl = QLabel("No device selected.")
        self.device_info_lbl.setObjectName("infoLabel")
        self.device_info_lbl.setWordWrap(True)
        vbox.addWidget(self.device_info_lbl)

        self.device_warn_lbl = QLabel("")
        self.device_warn_lbl.setObjectName("warnLabel")
        self.device_warn_lbl.setWordWrap(True)
        self.device_warn_lbl.setVisible(False)
        vbox.addWidget(self.device_warn_lbl)
        return grp


    def _make_iso_group(self) -> QGroupBox:
        grp = QGroupBox("② ISO Image  (drag & drop supported)")
        grp.setObjectName("sectionGroup")
        vbox = QVBoxLayout(grp)

        row = QHBoxLayout()
        self.iso_path_lbl = QLabel("No ISO selected.")
        self.iso_path_lbl.setObjectName("infoLabel")
        self.iso_path_lbl.setWordWrap(True)
        self.iso_path_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setIcon(QIcon(get_icon("browse_folder")))
        self.browse_btn.setFixedWidth(100)
        self.browse_btn.clicked.connect(self._browse_iso)

        row.addWidget(self.iso_path_lbl, 1)
        row.addWidget(self.browse_btn)
        vbox.addLayout(row)

        self.iso_info_lbl = QLabel("")
        self.iso_info_lbl.setObjectName("infoLabel")
        self.iso_info_lbl.setWordWrap(True)
        vbox.addWidget(self.iso_info_lbl)

        self.iso_rec_lbl = QLabel("")
        self.iso_rec_lbl.setObjectName("recLabel")
        self.iso_rec_lbl.setWordWrap(True)
        self.iso_rec_lbl.setVisible(False)
        vbox.addWidget(self.iso_rec_lbl)
        return grp


    def _make_options_widget(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.scheme_group = QButtonGroup(self)
        mbr_rb = QRadioButton("MBR  (Legacy BIOS)")
        gpt_rb = QRadioButton("GPT  (UEFI / Modern)")
        self.scheme_group.addButton(mbr_rb, 0)
        self.scheme_group.addButton(gpt_rb, 1)
        mbr_rb.setChecked(True)
        scheme_row = QHBoxLayout()
        scheme_row.addWidget(mbr_rb)
        scheme_row.addWidget(gpt_rb)
        form.addRow("Partition Scheme:", scheme_row)

        self.boot_group = QButtonGroup(self)
        bios_rb = QRadioButton("BIOS")
        uefi_rb = QRadioButton("UEFI")
        dual_rb = QRadioButton("Dual (BIOS + UEFI)")
        fdos_rb = QRadioButton("FreeDOS")
        for bid, rb in enumerate([bios_rb, uefi_rb, dual_rb, fdos_rb]):
            self.boot_group.addButton(rb, bid)
        bios_rb.setChecked(True)

        boot_grid = QGridLayout()
        boot_grid.addWidget(bios_rb, 0, 0)
        boot_grid.addWidget(uefi_rb, 0, 1)
        boot_grid.addWidget(dual_rb, 1, 0)
        boot_grid.addWidget(fdos_rb, 1, 1)
        form.addRow("Boot Type:", boot_grid)

        for btn in self.scheme_group.buttons() + self.boot_group.buttons():
            btn.toggled.connect(self._sync_boot_options)

        self.fs_combo = QComboBox()
        self._update_fs_options()
        form.addRow("Filesystem:", self.fs_combo)

        self.label_edit = QLineEdit("SMARTBOOT")
        self.label_edit.setMaxLength(32)
        self.label_edit.setPlaceholderText("Volume label (max 11 chars for FAT32)")
        form.addRow("Volume Label:", self.label_edit)

        self.cluster_combo = QComboBox()
        self.cluster_combo.addItems(self._CLUSTER_SIZES)
        form.addRow("Cluster Size:", self.cluster_combo)

        self.quick_fmt_chk = QCheckBox("Quick Format  (skip zero-fill)")
        self.quick_fmt_chk.setChecked(True)
        form.addRow("", self.quick_fmt_chk)

        return w


    def _make_checksum_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        algo_row = QHBoxLayout()
        algo_row.addWidget(QLabel("Algorithm:"))
        self.checksum_algo_combo = QComboBox()
        self.checksum_algo_combo.addItems(["SHA256", "SHA1", "MD5"])
        algo_row.addWidget(self.checksum_algo_combo)
        algo_row.addStretch()
        layout.addLayout(algo_row)

        self.checksum_progress = QProgressBar()
        self.checksum_progress.setValue(0)
        layout.addWidget(self.checksum_progress)

        self.checksum_result = QLineEdit()
        self.checksum_result.setReadOnly(True)
        self.checksum_result.setPlaceholderText("Computed checksum will appear here")
        self.checksum_result.setFont(QFont("Courier New", 9))
        layout.addWidget(self.checksum_result)

        verify_row = QHBoxLayout()
        verify_row.addWidget(QLabel("Expected:"))
        self.checksum_expected = QLineEdit()
        self.checksum_expected.setPlaceholderText("Paste expected checksum to verify…")
        self.checksum_expected.setFont(QFont("Courier New", 9))
        verify_row.addWidget(self.checksum_expected)
        layout.addLayout(verify_row)

        self.checksum_match_lbl = QLabel("")
        self.checksum_match_lbl.setObjectName("checksumMatch")
        layout.addWidget(self.checksum_match_lbl)

        btn_row = QHBoxLayout()
        self.compute_hash_btn = QPushButton("Compute Checksum")
        self.compute_hash_btn.clicked.connect(self._compute_checksum)
        self.compute_hash_btn.setEnabled(False)
        btn_row.addWidget(self.compute_hash_btn)

        self.verify_hash_btn = QPushButton("Verify")
        self.verify_hash_btn.clicked.connect(self._verify_checksum)
        self.verify_hash_btn.setEnabled(False)
        btn_row.addWidget(self.verify_hash_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        return w


    def _make_advanced_widget(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.direct_write_chk = QCheckBox(
            "Direct Write  (write ISO bytes directly — skips file extraction)"
        )
        form.addRow("", self.direct_write_chk)

        self.verify_chk = QCheckBox("Verify written files after creation")
        form.addRow("", self.verify_chk)

        self.bad_block_chk = QCheckBox(
            "Bad Block Check  (read-only scan before format — slow)"
        )
        form.addRow("", self.bad_block_chk)

        self.iso_type_combo = QComboBox()
        self.iso_type_combo.addItems(
            ["Auto-detect", "Windows", "Linux", "FreeDOS", "Generic"]
        )
        form.addRow("ISO Type Override:", self.iso_type_combo)

        persist_row = QHBoxLayout()
        self.persist_spin = QSpinBox()
        self.persist_spin.setRange(0, 32768)
        self.persist_spin.setValue(0)
        self.persist_spin.setSuffix(" MB")
        self.persist_spin.setSpecialValueText("Disabled")
        self.persist_spin.setToolTip(
            "Create a casper-rw persistence overlay for Linux live USBs.\n"
            "Set to 0 to disable. Requires ext4-capable system."
        )
        persist_row.addWidget(self.persist_spin)
        persist_row.addWidget(QLabel("(Linux live only)"))
        persist_row.addStretch()
        form.addRow("Persistence:", persist_row)

        return w


    def _make_progress_group(self) -> QGroupBox:
        grp = QGroupBox("Progress")
        grp.setObjectName("sectionGroup")
        vbox = QVBoxLayout(grp)

        stage_row = QHBoxLayout()
        self._stage_labels = []
        stages = ["Pre-flight", "Format", "Write ISO", "Boot Sector", "Verify", "Done"]
        for i, name in enumerate(stages):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("stageLabel")
            lbl.setFixedHeight(22)
            self._stage_labels.append(lbl)
            stage_row.addWidget(lbl)
            if i < len(stages) - 1:
                arrow = QLabel("›")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setObjectName("stageArrow")
                stage_row.addWidget(arrow)
        vbox.addLayout(stage_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimumHeight(22)
        vbox.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Ready.")
        self.status_lbl.setObjectName("statusLabel")
        self.status_lbl.setWordWrap(True)
        vbox.addWidget(self.status_lbl)
        return grp


    def _make_button_row(self) -> QHBoxLayout:
        hbox = QHBoxLayout()

        self.log_toggle_btn = QPushButton("Log")
        self.log_toggle_btn.setIcon(QIcon(get_icon("log_panel")))
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.setFixedWidth(70)
        self.log_toggle_btn.toggled.connect(self._toggle_log)
        hbox.addWidget(self.log_toggle_btn)

        hbox.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(QIcon(get_icon("cancel")))
        self.cancel_btn.setMinimumSize(110, 38)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setObjectName("cancelBtn")
        hbox.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("START")
        self.start_btn.setIcon(QIcon(get_icon("start")))
        self.start_btn.setMinimumSize(130, 38)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setObjectName("startBtn")
        hbox.addWidget(self.start_btn)
        return hbox


    def _make_log_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 4, 10, 4)
        hdr = QHBoxLayout()
        log_title = QLabel("Operation Log")
        log_title.setPixmap(QIcon(get_icon("log_panel")).pixmap(16, 16))
        hdr.addWidget(log_title)
        hdr.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._clear_log)
        hdr.addWidget(clear_btn)
        layout.addLayout(hdr)
        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(QFont("Courier New", 9))
        self._log_edit.setMinimumHeight(120)
        layout.addWidget(self._log_edit)
        return w


    def _apply_theme(self) -> None:
        if self._dark_mode:
            bg      = "#1e1e2e"
            surface = "#2a2a3e"
            text    = "#cdd6f4"
            accent  = "#89b4fa"
            warn    = "#fab387"
            ok      = "#a6e3a1"
            border  = "#45475a"
            prog    = "#89b4fa"
            stage_inactive = "#313244"
        else:
            bg      = "#f4f4f8"
            surface = "#ffffff"
            text    = "#1c1c2e"
            accent  = "#1565C0"
            warn    = "#d84315"
            ok      = "#2e7d32"
            border  = "#c9c9d6"
            prog    = "#1565C0"
            stage_inactive = "#e0e0ec"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {bg};
                color: {text};
                font-family: "Segoe UI", "SF Pro Display", Ubuntu, sans-serif;
                font-size: 10pt;
            }}
            QGroupBox
                border: 1px solid {border};
                border-radius: 6px;
                margin-top: 10px;
                padding: 8px 6px 6px 6px;
                background-color: {surface};
            }}
            QGroupBox
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {accent};
                font-weight: bold;
            }}
            QLabel
                color: {accent};
                font-size: 18pt;
                font-weight: bold;
            }}
            QLabel
                color: {text};
                font-size: 9pt;
                opacity: 0.7;
            }}
            QLabel
                color: {text};
                font-size: 9pt;
            }}
            QLabel
                color: {warn};
                font-weight: bold;
            }}
            QLabel
                color: {ok};
            }}
            QLabel
                font-size: 9pt;
                color: {text};
            }}
            QLabel
                background: {stage_inactive};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 8pt;
                color: {text};
            }}
            QLabel
                background: {accent};
                color: white;
                font-weight: bold;
            }}
            QLabel
                background: {ok};
                color: white;
            }}
            QLabel
                color: {border};
                font-size: 14pt;
            }}
            QLabel
                color: {ok};
                font-weight: bold;
            }}
            QLabel
                color: {warn};
                font-weight: bold;
            }}
            QComboBox, QLineEdit, QSpinBox {{
                background: {surface};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {text};
                selection-background-color: {accent};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QPushButton {{
                background: {surface};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 14px;
                color: {text};
            }}
            QPushButton:hover {{
                background: {accent};
                color: white;
                border-color: {accent};
            }}
            QPushButton
                background: {accent};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                font-size: 11pt;
            }}
            QPushButton
                background: {border};
                color: {text};
            }}
            QPushButton
                background: {'#1976D2' if not self._dark_mode else '#74c7ec'};
            }}
            QPushButton
                border-color: {warn};
                color: {warn};
            }}
            QPushButton
                background: {warn};
                color: white;
            }}
            QProgressBar {{
                border: 1px solid {border};
                border-radius: 5px;
                background: {stage_inactive};
                text-align: center;
                color: {text};
            }}
            QProgressBar::chunk {{
                background: {prog};
                border-radius: 5px;
            }}
            QTabWidget::pane {{
                border: 1px solid {border};
                border-radius: 4px;
                background: {surface};
            }}
            QTabBar::tab {{
                background: {stage_inactive};
                color: {text};
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {surface};
                color: {accent};
                font-weight: bold;
            }}
            QTextEdit {{
                background: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                font-family: "Courier New", monospace;
                font-size: 9pt;
            }}
            QMenuBar {{
                background: {bg};
                color: {text};
            }}
            QMenuBar::item:selected {{
                background: {accent};
                color: white;
            }}
            QMenu {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
            }}
            QMenu::item:selected {{
                background: {accent};
                color: white;
            }}
            QStatusBar {{
                background: {surface};
                color: {text};
                border-top: 1px solid {border};
            }}
            QCheckBox, QRadioButton {{
                spacing: 6px;
            }}
            QCheckBox::indicator, QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
        """)

    def _toggle_theme(self) -> None:
        self._dark_mode = not self._dark_mode
        self._apply_theme()
        self._theme_btn.setIcon(QIcon(get_icon("light_mode" if self._dark_mode else "dark_mode")))
        if hasattr(self, "_theme_action"):
            self._theme_action.setText(
                "Switch to Light Theme" if self._dark_mode
                else "Switch to Dark Theme"
            )


    def refresh_devices(self) -> None:
        prev_name = self.selected_device.get("name", "")
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        try:
            self.devices = self.usb_manager.get_devices()
            if not self.devices:
                self.device_combo.addItem("No USB devices found")
                self.selected_device = {}
            else:
                for dev in self.devices:
                    name = dev.get("friendly") or dev.get("name", "Unknown")
                    size = dev.get("size", "")
                    label = f"{name}  ({size})"
                    self.device_combo.addItem(label)
                self.selected_device = self.devices[0]
                for i, dev in enumerate(self.devices):
                    if dev.get("name") == prev_name:
                        self.device_combo.setCurrentIndex(i)
                        self.selected_device = dev
                        break
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"Failed to enumerate devices:\n{exc}")
            self.selected_device = {}
        finally:
            self.device_combo.blockSignals(False)
            self._update_device_info()

    def _auto_refresh_devices(self) -> None:
        """Silent refresh — only update if device count changes."""
        if self._worker and self._worker.isRunning():
            return
        try:
            new_devices = self.usb_manager.get_devices()
            if len(new_devices) != len(self.devices):
                self.refresh_devices()
                self._log(f"Device list updated ({len(new_devices)} device(s))")
        except Exception:
            pass

    def _on_device_changed(self, idx: int) -> None:
        if self.devices and 0 <= idx < len(self.devices):
            self.selected_device = self.devices[idx]
        else:
            self.selected_device = {}
        self._update_device_info()

    def _update_device_info(self) -> None:
        d = self.selected_device
        if d and "error" not in d:
            parts = [
                f"Size: {d.get('size','?')}",
                f"FS: {d.get('filesystem','?')}",
            ]
            if d.get("usb_version") and d["usb_version"] != "Unknown":
                parts.append(d["usb_version"])
            if d.get("drive_letter"):
                parts.append(f"Mount: {d['drive_letter']}")
            self.device_info_lbl.setText("  •  ".join(parts))

            warn = d.get("size_warning", "")
            if d.get("write_protected"):
                warn = "Write-protected — remove write-protect switch before continuing"
            if warn:
                self.device_warn_lbl.setText(warn)
                self.device_warn_lbl.setVisible(True)
            else:
                self.device_warn_lbl.setVisible(False)
        else:
            self.device_info_lbl.setText("No device selected.")
            self.device_warn_lbl.setVisible(False)
        self._update_start_btn()


    def _browse_iso(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO File", "",
            "ISO Images (*.iso);;All Files (*)"
        )
        if path:
            self._load_iso(path)

    def _load_iso(self, path: str) -> None:
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found",
                                f"ISO file not found:\n{path}")
            return
        self.selected_iso = path
        self.iso_path_lbl.setText(os.path.basename(path))
        self.iso_path_lbl.setToolTip(path)
        self._status_bar.showMessage(f"Loading ISO info: {os.path.basename(path)}…")
        try:
            self.iso_info = self.iso_manager.get_iso_info(path)
            info = self.iso_info
            parts = [
                f"Size: {info['size']}",
                f"Type: {info.get('type','Unknown')}",
            ]
            if info.get("label"):
                parts.append(f"Label: {info['label']}")
            if info.get("is_hybrid"):
                parts.append("Hybrid ISO")
            if info.get("has_efi"):
                parts.append("EFI")
            self.iso_info_lbl.setText("  •  ".join(parts))

            recs = []
            if info.get("recommended_scheme"):
                recs.append(f"Scheme: {info['recommended_scheme']}")
            if info.get("recommended_boot"):
                recs.append(f"Boot: {info['recommended_boot'].upper()}")
            if info.get("recommended_fs"):
                recs.append(f"FS: {info['recommended_fs']}")
            if info.get("persistence_capable"):
                recs.append("Persistence supported")
            if recs:
                self.iso_rec_lbl.setText("Recommended: " + "  •  ".join(recs))
                self.iso_rec_lbl.setVisible(True)
                self._apply_recommendations(info)
            else:
                self.iso_rec_lbl.setVisible(False)

            self.compute_hash_btn.setEnabled(True)
            self.verify_hash_btn.setEnabled(True)
            self._populate_recent_menu()
            self.iso_manager.add_to_history(path)
            self._log(f"ISO loaded: {os.path.basename(path)} ({info['size']}, {info.get('type','?')})")
        except Exception as exc:
            self.iso_info_lbl.setText(f"Could not read ISO info: {exc}")
            self.iso_rec_lbl.setVisible(False)
        self._status_bar.showMessage("Ready")
        self._update_start_btn()

    def _apply_recommendations(self, info: dict) -> None:
        """Auto-select recommended options based on ISO analysis."""
        scheme = info.get("recommended_scheme", "").upper()
        if scheme == "GPT":
            self.scheme_group.button(1).setChecked(True)
        elif scheme == "MBR":
            self.scheme_group.button(0).setChecked(True)

        boot = info.get("recommended_boot", "").lower()
        boot_map = {"bios": 0, "uefi": 1, "dual": 2, "freedos": 3}
        if boot in boot_map:
            self.boot_group.button(boot_map[boot]).setChecked(True)

        fs = info.get("recommended_fs", "")
        if fs:
            idx = self.fs_combo.findText(fs, Qt.MatchFixedString)
            if idx >= 0:
                self.fs_combo.setCurrentIndex(idx)

        label = info.get("label", "")
        if label:
            self.label_edit.setText(label[:32])


    def _sync_boot_options(self) -> None:
        boot_id   = self.boot_group.checkedId()
        scheme_id = self.scheme_group.checkedId()

        if boot_id in (1, 2) and scheme_id == 0:
            self.scheme_group.button(1).setChecked(True)
        elif boot_id == 3 and scheme_id == 1:
            self.scheme_group.button(0).setChecked(True)

        self._update_fs_options()

    def _update_fs_options(self) -> None:
        current = self.fs_combo.currentText() if self.fs_combo.count() else "FAT32"
        self.fs_combo.clear()
        boot_id = self.boot_group.checkedId() if hasattr(self, "boot_group") else 0
        all_supported = self.formatter.get_supported_filesystems()

        if boot_id == 3:
            options = [fs for fs in all_supported
                       if fs.upper() in ("FAT", "FAT32")]
        elif boot_id in (1, 2):
            options = [fs for fs in all_supported
                       if fs.upper() in ("FAT32", "NTFS", "EXFAT")]
        else:
            options = all_supported

        options = sorted(set(options), key=str.upper)
        self.fs_combo.addItems(options)
        idx = self.fs_combo.findText(current, Qt.MatchFixedString)
        if idx >= 0:
            self.fs_combo.setCurrentIndex(idx)

    def _update_start_btn(self) -> None:
        can_start = (
            bool(self.selected_device)
            and "error" not in self.selected_device
            and bool(self.selected_iso)
            and os.path.exists(self.selected_iso)
            and self._worker is None
        )
        self.start_btn.setEnabled(can_start)


    def _open_checksum_tab(self) -> None:
        self._tabs.setCurrentIndex(1)

    def _compute_checksum(self) -> None:
        if not self.selected_iso:
            return
        algo = self.checksum_algo_combo.currentText().lower()
        self.checksum_result.clear()
        self.checksum_match_lbl.clear()
        self.compute_hash_btn.setEnabled(False)
        self.verify_hash_btn.setEnabled(False)

        self._checksum_worker = ChecksumWorker(
            self.iso_manager, self.selected_iso, algo, self
        )
        self._checksum_worker.progress.connect(
            lambda pct, _: self.checksum_progress.setValue(pct)
        )
        self._checksum_worker.result.connect(self._on_checksum_done)
        self._checksum_worker.start()

    def _on_checksum_done(self, algo: str, digest: str) -> None:
        self.checksum_result.setText(digest)
        self.checksum_progress.setValue(100)
        self.compute_hash_btn.setEnabled(True)
        self.verify_hash_btn.setEnabled(True)
        self._log(f"{algo.upper()} checksum: {digest}")
        if self.checksum_expected.text().strip():
            self._verify_checksum()

    def _verify_checksum(self) -> None:
        computed = self.checksum_result.text().strip().lower()
        expected = self.checksum_expected.text().strip().lower()
        if not computed:
            QMessageBox.information(self, "Checksum",
                                    "Click 'Compute Checksum' first.")
            return
        if not expected:
            return
        match = computed == expected
        self.checksum_match_lbl.setProperty("ok", str(match).lower())
        self.checksum_match_lbl.setText(
            "Checksum MATCHES" if match else "Checksum MISMATCH"
        )
        self.checksum_match_lbl.style().unpolish(self.checksum_match_lbl)
        self.checksum_match_lbl.style().polish(self.checksum_match_lbl)


    def _on_start(self) -> None:
        d = self.selected_device
        name = d.get("friendly") or d.get("name", "the selected device")
        size = d.get("size", "")

        if d.get("write_protected"):
            QMessageBox.warning(
                self, "Write Protected",
                "The selected device is write-protected.\n"
                "Please remove the write-protect switch and refresh."
            )
            return

        try:
            iso_size = os.path.getsize(self.selected_iso)
            dev_size = d.get("size_bytes", 0)
            if dev_size and iso_size > dev_size:
                QMessageBox.critical(
                    self, "Device Too Small",
                    f"The ISO ({iso_size // (1024**3):.1f} GB) is larger than "
                    f"the device ({dev_size // (1024**3):.1f} GB).\n"
                    "Select a larger drive."
                )
                return
        except Exception:
            pass

        reply = QMessageBox.warning(
            self,
            "Data Loss Warning",
            f"ALL data on '{name}' ({size}) will be permanently erased.\n\n"
            "This action CANNOT be undone.\n\n"
            "Are you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        options = self._collect_options()
        self._set_working(True)
        self._reset_stage_labels()

        self._worker = CreationWorker(
            formatter    = self.formatter,
            writer       = self.writer,
            boot_manager = self.boot_manager,
            iso_manager  = self.iso_manager,
            device       = self.selected_device,
            iso_path     = self.selected_iso,
            options      = options,
            parent       = self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.stage_changed.connect(self._on_stage_changed)
        self._worker.start()
        self._log(f"Started: {os.path.basename(self.selected_iso)} → {name}")

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "Cancel",
                "Cancel the current operation?\n"
                "(The drive may be left in an unusable state.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._worker.cancel()
                self.status_lbl.setText("Cancelling… please wait.")
                self.cancel_btn.setEnabled(False)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)
        self._status_bar.showMessage(f"{pct}% — {msg}")
        self._log(f"[{pct:3d}%] {msg}")

    def _on_stage_changed(self, stage: str) -> None:
        stage_order = ["Pre-flight", "Format", "Write ISO",
                        "Boot Sector", "Verify", "Done"]
        try:
            active_idx = stage_order.index(stage)
        except ValueError:
            return

        for i, lbl in enumerate(self._stage_labels):
            if i < active_idx:
                lbl.setProperty("done", "true")
                lbl.setProperty("active", "false")
            elif i == active_idx:
                lbl.setProperty("active", "true")
                lbl.setProperty("done", "false")
            else:
                lbl.setProperty("active", "false")
                lbl.setProperty("done", "false")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _on_finished(self, success: bool, msg: str) -> None:
        self._set_working(False)
        self._worker = None
        pct = 100 if success else self.progress_bar.value()
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)
        self._status_bar.showMessage(msg)
        self._log(f"FINISHED (success={success}): {msg}")

        if success:
            for lbl in self._stage_labels:
                lbl.setProperty("done", "true")
                lbl.setProperty("active", "false")
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.warning(self, "Completed with Issues", msg)


    def _collect_options(self) -> dict:
        scheme  = self._SCHEME_MAP.get(self.scheme_group.checkedId(), "MBR")
        boot    = self._BOOT_TYPE_MAP.get(self.boot_group.checkedId(), "bios")
        fs      = self.fs_combo.currentText()
        label   = self.label_edit.text().strip() or "SMARTBOOT"
        quick   = self.quick_fmt_chk.isChecked()
        direct  = self.direct_write_chk.isChecked()
        verify  = self.verify_chk.isChecked()
        bb      = self.bad_block_chk.isChecked()
        persist = self.persist_spin.value()

        cluster_raw = self.cluster_combo.currentText()
        cluster = int(cluster_raw) if cluster_raw != "Auto" else None

        iso_type = "auto"
        raw = self.iso_type_combo.currentText().lower()
        if raw != "auto-detect":
            iso_type = raw

        return {
            "partition_scheme": scheme,
            "boot_type":        boot,
            "filesystem":       fs,
            "label":            label,
            "quick_format":     quick,
            "direct_write":     direct,
            "verify":           verify,
            "bad_block_check":  bb,
            "iso_type":         iso_type,
            "cluster_size":     cluster,
            "persistent_size_mb": persist,
        }

    def _set_working(self, working: bool) -> None:
        self.start_btn.setVisible(not working)
        self.cancel_btn.setVisible(working)
        self.cancel_btn.setEnabled(working)
        self.refresh_btn.setEnabled(not working)
        self.browse_btn.setEnabled(not working)
        self.device_combo.setEnabled(not working)
        self._tabs.setEnabled(not working)
        if working:
            self.progress_bar.setValue(0)
            self.status_lbl.setText("Starting…")
        else:
            self._update_start_btn()

    def _reset_stage_labels(self) -> None:
        for lbl in self._stage_labels:
            lbl.setProperty("active", "false")
            lbl.setProperty("done", "false")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _toggle_log(self, checked: bool) -> None:
        self._log_panel.setVisible(checked)
        if checked:
            self._splitter.setSizes([500, 200])
        else:
            self._splitter.setSizes([700, 0])
        if hasattr(self, "_log_action"):
            self._log_action.setChecked(checked)
        if hasattr(self, "log_toggle_btn"):
            self.log_toggle_btn.setChecked(checked)

    def _log(self, message: str) -> None:
        if hasattr(self, "_log_edit"):
            import time
            ts = time.strftime("%H:%M:%S")
            self._log_edit.append(f"[{ts}] {message}")
            sb = self._log_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _clear_log(self) -> None:
        if hasattr(self, "_log_edit"):
            self._log_edit.clear()

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "Quit",
                "An operation is in progress. Cancel and quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._worker.cancel()
            self._worker.wait(8000)
        self._refresh_timer.stop()
        event.accept()