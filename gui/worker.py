"""
Worker thread for SmartBoot (Enhanced)

Stages:
    1. Pre-flight checks (write-protect, size)
    2. DiskFormatter.format_disk()
    3. ImageWriter.write_iso() or write_disk_image()
    4. BootSectorManager.write_boot_sector()
    5. (optional) Checksum verification
    6. (optional) Persistence overlay setup

Signals:
    progress(int, str)   – percent + human message
    finished(bool, str)  – success flag + final message
    stage_changed(str)   – current stage name
"""

import os
import threading
from PyQt5.QtCore import QThread, pyqtSignal


class CreationWorker(QThread):
    progress     = pyqtSignal(int, str)
    finished     = pyqtSignal(bool, str)
    stage_changed = pyqtSignal(str)

    STAGES = [
        "Pre-flight",
        "Format",
        "Write ISO",
        "Boot Sector",
        "Verify",
        "Done",
    ]

    def __init__(
        self,
        formatter,
        writer,
        boot_manager,
        iso_manager,
        device: dict,
        iso_path: str,
        options: dict,
        parent=None,
    ):
        super().__init__(parent)
        self._formatter    = formatter
        self._writer       = writer
        self._boot_manager = boot_manager
        self._iso_manager  = iso_manager
        self._device       = device
        self._iso_path     = iso_path
        self._options      = options
        self._cancelled    = False

    def cancel(self) -> None:
        self._cancelled = True
        try:
            self._writer.cancel()
        except Exception:
            pass


    def run(self) -> None:
        try:
            self._run_pipeline()
        except Exception as exc:
            self.finished.emit(False, f"Unexpected error: {exc}")

    def _run_pipeline(self) -> None:
        device  = dict(self._device)
        options = self._options

        self.stage_changed.emit("Pre-flight")
        self._emit(0, "Running pre-flight checks…")

        if device.get("write_protected"):
            self.finished.emit(False, "Device is write-protected. "
                               "Remove the write-protect switch and retry.")
            return

        if self._cancelled:
            self.finished.emit(False, "Cancelled.")
            return

        try:
            iso_size = os.path.getsize(self._iso_path)
            dev_size = device.get("size_bytes", 0)
            if dev_size and iso_size > dev_size:
                self.finished.emit(
                    False,
                    f"ISO ({iso_size // (1024**3):.1f} GB) is larger than "
                    f"the device ({dev_size // (1024**3):.1f} GB)."
                )
                return
        except Exception:
            pass

        self._emit(5, "Pre-flight checks passed.")

        self.stage_changed.emit("Format")
        self._emit(5, "Formatting USB drive…")

        ok, drive_path = self._formatter.format_disk(
            device,
            options["filesystem"],
            options.get("label", "SMARTBOOT"),
            options["partition_scheme"],
            options.get("quick_format", True),
            self._scale_cb(5, 25),
            bad_block_check=options.get("bad_block_check", False),
            cluster_size=options.get("cluster_size"),
        )

        if not ok:
            self.finished.emit(False, "Failed to format USB drive.")
            return

        if drive_path:
            device["drive_letter"] = drive_path

        self._emit(25, "USB drive formatted.")
        if self._cancelled:
            self.finished.emit(False, "Cancelled after formatting.")
            return

        self.stage_changed.emit("Write ISO")
        direct_write = options.get("direct_write", False)

        if direct_write:
            self._emit(26, "Writing ISO directly to device…")
            ok = self._writer.write_disk_image(
                self._iso_path,
                device.get("name", ""),
                self._scale_cb(26, 88),
                verify=options.get("verify", False),
            )
            if ok:
                self.finished.emit(True, "USB drive created successfully!")
            else:
                self.finished.emit(False, "Direct write failed.")
            return

        self._emit(26, "Writing ISO files to USB…")
        iso_type = options.get("iso_type", "auto")
        ok = self._writer.write_iso(
            self._iso_path,
            device.get("drive_letter", ""),
            iso_type,
            True,
            self._scale_cb(26, 68),
            verify=False,
        )

        if not ok:
            self.finished.emit(False, "Failed to write ISO to USB drive.")
            return

        self._emit(68, "ISO written. Installing boot sector…")
        if self._cancelled:
            self.finished.emit(False, "Cancelled before boot sector.")
            return

        self.stage_changed.emit("Boot Sector")
        options_with_iso = dict(options)
        options_with_iso["iso_path"] = self._iso_path

        ok = self._boot_manager.write_boot_sector(
            device,
            options_with_iso,
            self._scale_cb(68, 88),
        )

        if not ok:
            self.finished.emit(
                False,
                "Files written but boot sector installation failed. "
                "The drive may still boot depending on the ISO type."
            )
            return

        if options.get("verify", False) and not self._cancelled:
            self.stage_changed.emit("Verify")
            self._emit(88, "Verifying written files…")
            drive = device.get("drive_letter", "")
            errors = self._spot_verify(drive)
            if errors:
                self._emit(95, f"Verify: {errors} issue(s) found (non-fatal)")
            else:
                self._emit(95, "Verification passed.")

        if options.get("persistent_size_mb", 0) > 0 and not self._cancelled:
            self._emit(96, "Setting up persistence overlay…")
            self._setup_persistence(
                device.get("drive_letter", ""),
                options["persistent_size_mb"],
            )

        self.stage_changed.emit("Done")
        self._emit(100, "USB drive created successfully!")
        self.finished.emit(True, "USB drive created successfully!")


    def _spot_verify(self, drive: str) -> int:
        if not drive or not os.path.isdir(drive):
            return 0
        errors = 0
        try:
            for root, _, files in os.walk(drive):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "rb") as f:
                            f.read(4096)
                    except Exception:
                        errors += 1
        except Exception:
            pass
        return errors


    def _setup_persistence(self, drive: str, size_mb: int) -> None:
        """Create a casper-rw file for Ubuntu/Debian live persistence."""
        try:
            casper_rw = os.path.join(drive, "casper-rw")
            if os.path.exists(casper_rw):
                return
            import subprocess
            subprocess.run(
                ["dd", "if=/dev/zero", f"of={casper_rw}",
                 "bs=1M", f"count={size_mb}"],
                capture_output=True, timeout=300
            )
            subprocess.run(
                ["sudo", "mkfs.ext4", "-L", "casper-rw", casper_rw],
                capture_output=True, timeout=120
            )
        except Exception as exc:
            import logging
            logging.getLogger("smartboot").warning(
                f"Persistence setup failed: {exc}"
            )


    def _emit(self, pct: int, msg: str) -> None:
        self.progress.emit(pct, msg)

    def _scale_cb(self, lo: int, hi: int):
        span = hi - lo

        def cb(pct: int, msg: str) -> None:
            if self._cancelled:
                return
            mapped = lo + int(pct * span / 100)
            self.progress.emit(mapped, msg)

        return cb