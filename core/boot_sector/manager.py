"""
Boot Sector Manager module for SmartBoot

Responsibilities:
  - Select the platform-appropriate implementation at runtime
  - Validate preconditions (admin, device sanity)
  - Dispatch to write_bios_boot / write_uefi_boot / write_freedos_boot
  - Handle "dual" mode (BIOS + UEFI, succeed if at least one works)
  - Unified progress scaling so sub-callbacks don't overlap
"""

import os
import platform
import tempfile
from typing import Any, Callable, Dict, Optional

from utils.logger import get_logger
from .base    import BaseBootSector
from .windows import WindowsBootSector
from .linux   import LinuxBootSector
from .macos   import MacOSBootSector

logger = get_logger()


class BootSectorManager:
    """
    Platform-agnostic boot-sector orchestrator.

    Supported boot types (options['boot_type']):
        bios     – Legacy BIOS / MBR boot
        uefi     – UEFI-only boot
        dual     – Both BIOS and UEFI (succeeds if either works)
        freedos  – FreeDOS BIOS boot
    """

    def __init__(self) -> None:
        self.system       = platform.system()
        self.resource_dir = os.path.join(
            tempfile.gettempdir(), "smartboot_resources"
        )
        os.makedirs(self.resource_dir, exist_ok=True)

        impl_map = {
            "Windows": WindowsBootSector,
            "Linux":   LinuxBootSector,
            "Darwin":  MacOSBootSector,
        }
        cls = impl_map.get(self.system, BaseBootSector)
        self._impl: BaseBootSector = cls(self.resource_dir)
        logger.debug(
            f"BootSectorManager: using {cls.__name__} on {self.system}"
        )


    def write_boot_sector(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """
        Write the appropriate boot sector to *device* according to *options*.

        Args:
            device:            Device info dict (name, number, drive_letter, …).
            options:           Must contain 'boot_type'; may contain 'iso_path',
                               'iso_type', 'partition_scheme'.
            progress_callback: Called with (percent: int, message: str).

        Returns:
            True on success (or partial success for dual mode).
        """
        try:
            if "error" in device:
                self._emit(progress_callback, 0,
                           f"Error: {device['error']}")
                return False

            if not self._impl.check_admin_privileges():
                self._emit(
                    progress_callback, 0,
                    "Error: Administrator / root privileges are required. "
                    "Please restart SmartBoot with elevated privileges."
                )
                return False

            boot_type = options.get("boot_type", "bios").lower().strip()
            self._emit(progress_callback, 2,
                       f"Preparing {boot_type.upper()} boot sector…")

            if boot_type == "freedos":
                return self._impl.write_freedos_boot(
                    device, options, progress_callback
                )
            if boot_type == "uefi":
                return self._impl.write_uefi_boot(
                    device, options, progress_callback
                )
            if boot_type == "dual":
                return self._write_dual(device, options, progress_callback)

            return self._impl.write_bios_boot(
                device, options, progress_callback
            )

        except Exception as exc:
            logger.exception("BootSectorManager: unexpected error")
            self._emit(progress_callback, 0,
                       f"Error writing boot sector: {exc}")
            return False


    def _write_dual(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        """
        Install BIOS and UEFI boot sectors sequentially.
        Progress is split: BIOS gets 0-48 %, UEFI gets 50-98 %.
        Succeeds if at least one mode completes successfully.
        """

        def bios_cb(pct: int, msg: str) -> None:
            mapped = int(pct * 0.48)
            if progress_callback:
                progress_callback(mapped, f"[BIOS] {msg}")

        def uefi_cb(pct: int, msg: str) -> None:
            mapped = 50 + int(pct * 0.48)
            if progress_callback:
                progress_callback(mapped, f"[UEFI] {msg}")

        self._emit(progress_callback, 2, "Installing BIOS boot sector…")
        bios_ok = False
        try:
            bios_ok = self._impl.write_bios_boot(device, options, bios_cb)
        except Exception as exc:
            logger.warning(f"Dual/BIOS failed: {exc}")
            self._emit(progress_callback, 46,
                       f"Warning: BIOS boot sector failed: {exc}")

        self._emit(progress_callback, 50, "Installing UEFI boot sector…")
        uefi_ok = False
        try:
            uefi_ok = self._impl.write_uefi_boot(device, options, uefi_cb)
        except Exception as exc:
            logger.warning(f"Dual/UEFI failed: {exc}")
            self._emit(progress_callback, 97,
                       f"Warning: UEFI boot sector failed: {exc}")

        if bios_ok and uefi_ok:
            self._emit(progress_callback, 100,
                       "Dual boot sectors installed (BIOS + UEFI)")
        elif bios_ok:
            self._emit(progress_callback, 100,
                       "Dual boot: BIOS OK — UEFI failed (BIOS-only boot)")
        elif uefi_ok:
            self._emit(progress_callback, 100,
                       "Dual boot: UEFI OK — BIOS failed (UEFI-only boot)")
        else:
            self._emit(progress_callback, 0,
                       "Dual boot: both BIOS and UEFI installation failed")

        return bios_ok or uefi_ok


    def _emit(
        self,
        cb: Optional[Callable[[int, str], None]],
        pct: int,
        msg: str,
    ) -> None:
        logger.debug(f"BootSectorManager {pct}%: {msg}")
        if cb:
            cb(pct, msg)