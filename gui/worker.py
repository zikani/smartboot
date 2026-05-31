"""
Worker thread for SmartBoot

Runs the long-running disk operations (format → write ISO → boot sector)
on a QThread so the GUI never freezes.

Signals
-------
progress(int, str)   – percent + human message
finished(bool, str)  – success flag + final message
"""

from PyQt5.QtCore import QThread, pyqtSignal


class CreationWorker(QThread):
    """
    Runs the three-stage creation pipeline in a background thread:
        1. DiskFormatter.format_disk()
        2. ImageWriter.write_iso()  OR  ImageWriter.write_disk_image()
        3. BootSectorManager.write_boot_sector()

    All stage objects are passed in at construction so the worker owns no
    GUI references and is safe to use from a non-GUI thread.
    """

    progress = pyqtSignal(int, str)    # (percent, message)
    finished = pyqtSignal(bool, str)   # (success, final_message)

    def __init__(
        self,
        formatter,
        writer,
        boot_manager,
        device: dict,
        iso_path: str,
        options: dict,
        parent=None,
    ):
        super().__init__(parent)
        self._formatter    = formatter
        self._writer       = writer
        self._boot_manager = boot_manager
        self._device       = device
        self._iso_path     = iso_path
        self._options      = options
        self._cancelled    = False

    def cancel(self) -> None:
        """Request a graceful stop after the current sub-operation."""
        self._cancelled = True

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._run_pipeline()
        except Exception as exc:
            self.finished.emit(False, f"Unexpected error: {exc}")

    def _run_pipeline(self) -> None:
        device  = dict(self._device)   # local copy; we may mutate drive_letter
        options = self._options

        # ── Stage 1: Format ─────────────────────────────────────────────
        self._emit(0, "Formatting USB drive…")
        if self._cancelled:
            self.finished.emit(False, "Cancelled before formatting.")
            return

        ok, drive_path = self._formatter.format_disk(
            device,
            options["filesystem"],
            "SMARTBOOT",
            options["partition_scheme"],
            options.get("quick_format", True),
            self._scale_cb(0, 25),
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

        # ── Stage 2: Write ISO ──────────────────────────────────────────
        direct_write = options.get("direct_write", False)

        if direct_write:
            self._emit(26, "Writing ISO directly to device…")
            ok = self._writer.write_disk_image(
                self._iso_path,
                device.get("name", ""),
                self._scale_cb(26, 90),
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
            True,   # extract_files
            self._scale_cb(26, 70),
        )

        if not ok:
            self.finished.emit(False, "Failed to write ISO to USB drive.")
            return

        self._emit(70, "ISO written. Installing boot sector…")

        if self._cancelled:
            self.finished.emit(False, "Cancelled before boot sector.")
            return

        # ── Stage 3: Boot sector ────────────────────────────────────────
        options_with_iso = dict(options)
        options_with_iso["iso_path"] = self._iso_path

        ok = self._boot_manager.write_boot_sector(
            device,
            options_with_iso,
            self._scale_cb(70, 100),
        )

        if ok:
            self.finished.emit(True, "USB drive created successfully!")
        else:
            # Boot sector failure is non-fatal — the drive may still work
            self.finished.emit(
                False,
                "Files written but boot sector installation failed. "
                "The drive may still boot depending on the ISO type."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit(self, pct: int, msg: str) -> None:
        self.progress.emit(pct, msg)

    def _scale_cb(self, lo: int, hi: int):
        """
        Return a progress callback that maps [0, 100] → [lo, hi]
        and forwards to self.progress signal.
        """
        span = hi - lo

        def cb(pct: int, msg: str) -> None:
            mapped = lo + int(pct * span / 100)
            self.progress.emit(mapped, msg)

        return cb