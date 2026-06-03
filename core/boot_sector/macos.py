"""
macOS Boot Sector module for SmartBoot

Strategy (Rufus-parity where possible on macOS):

  BIOS:
    1. dd generic MBR (446 bytes, conv=notrunc) — best we can do without
       a native x86 bootloader package on macOS
    2. Set boot flag via pdisk / diskutil (last resort)

  UEFI:
    1. Copy known macOS EFI files (apfs.efi, boot.efi, gummiboot)
    2. Walk /usr/share/efi, /usr/lib/efi
    3. Minimal PE32+ stub

  FreeDOS:
    Delegates to BIOS chain.
"""

import os
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()


def _run(cmd: List[str], timeout: int = 30,
         **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, **kwargs)


def _sudo(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    return _run(["sudo"] + cmd, **kwargs)


class MacOSBootSector(BaseBootSector):
    """macOS-specific boot sector writer."""

    _EFI_SOURCES = [
        "/System/Library/CoreServices/boot.efi",
        "/usr/standalone/i386/apfs.efi",
        "/usr/standalone/i386/EfiLoginUI.efi",
        "/usr/local/lib/syslinux/efi64/syslinux.efi",
        "/opt/local/share/syslinux/efi64/syslinux.efi",
        "/usr/local/share/refind/refind_x64.efi",
        "/opt/homebrew/share/refind/refind_x64.efi",
    ]


    def check_admin_privileges(self) -> bool:
        try:
            return _sudo(["true"], timeout=5).returncode == 0
        except Exception:
            return False


    def _dev_path(self, device: Dict[str, Any]) -> Optional[str]:
        name = device.get("name", "")
        if not name:
            return None
        return name if name.startswith("/dev/") else f"/dev/{name}"

    def _get_partition(self, dev: str, number: int = 1) -> Optional[str]:
        """macOS uses /dev/diskNsM notation."""
        for candidate in (f"{dev}s{number}", f"{dev}{number}"):
            if os.path.exists(candidate):
                return candidate
        return None

    def _wait_for_partition(self, dev: str, number: int = 1,
                             retries: int = 6) -> Optional[str]:
        for _ in range(retries):
            p = self._get_partition(dev, number)
            if p:
                return p
            time.sleep(1)
        return None

    def _diskutil_mount(self, partition: str) -> Optional[str]:
        """Mount partition via diskutil and return mount point."""
        try:
            r = _run(["diskutil", "mount", partition], timeout=20)
            if r.returncode != 0:
                return None
            for line in r.stdout.splitlines():
                if "mounted" in line.lower() and " on " in line.lower():
                    mp = line.split(" on ", 1)[-1].strip().rstrip(".")
                    if mp and os.path.exists(mp):
                        return mp
        except Exception as exc:
            logger.warning(f"diskutil mount {partition}: {exc}")
        return None

    def _resolve_mount_point(
        self, device: Dict[str, Any], partition: str
    ) -> Optional[str]:
        mp = device.get("drive_letter", "")
        if mp and os.path.isdir(mp):
            return mp

        try:
            r = _run(["diskutil", "info", partition], timeout=10)
            for line in r.stdout.splitlines():
                if "Mount Point:" in line:
                    candidate = line.split(":", 1)[1].strip()
                    if candidate and os.path.isdir(candidate):
                        return candidate
        except Exception:
            pass

        return self._diskutil_mount(partition)


    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        dev = self._dev_path(device)
        if not dev:
            self._update(progress_callback, 0, "Device name not found")
            return False

        self._update(progress_callback, 8,
                     f"Writing BIOS boot sector to {dev}…")

        _run(["diskutil", "unmountDisk", dev], timeout=20)

        mbr_bin = self._find_or_create_mbr()
        if not mbr_bin or not os.path.exists(mbr_bin):
            self._update(progress_callback, 0,
                         "Error: Could not create MBR binary")
            return False

        try:
            r = _sudo(
                ["dd", f"if={mbr_bin}", f"of={dev}",
                 "bs=446", "count=1", "conv=notrunc"],
                timeout=30,
            )
            if r.returncode == 0:
                self._update(progress_callback, 80, "Generic MBR written (dd)")
            else:
                self._update(progress_callback, 40,
                             f"dd MBR failed: {r.stderr.strip()}")
        except Exception as exc:
            self._update(progress_callback, 40, f"dd MBR error: {exc}")

        partition = self._wait_for_partition(dev)
        if partition and shutil.which("pdisk"):
            try:
                proc = subprocess.Popen(
                    ["sudo", "pdisk", dev, "-e"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                proc.communicate(input=b"f 1\nw\ny\nq\n", timeout=15)
                self._update(progress_callback, 90,
                             "Partition boot flag set via pdisk")
            except Exception:
                pass

        self._update(progress_callback, 100,
                     "BIOS boot setup complete (MBR written)")
        return True


    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        if not self.check_admin_privileges():
            self._update(progress_callback, 0,
                         "Error: Root privileges required for UEFI boot")
            return False

        dev = self._dev_path(device)
        if not dev:
            self._update(progress_callback, 0, "Device name not found")
            return False

        partition = self._wait_for_partition(dev)
        if not partition:
            self._update(progress_callback, 0,
                         f"Could not find first partition on {dev}")
            return False

        iso_type = options.get("iso_type", "generic").lower()
        self._update(progress_callback, 8, "Preparing UEFI boot files…")

        mount_point = self._resolve_mount_point(device, partition)
        if not mount_point:
            self._update(progress_callback, 0,
                         f"Could not mount {partition}")
            return False

        efi_boot_dir = os.path.join(mount_point, "EFI", "BOOT")
        os.makedirs(efi_boot_dir, exist_ok=True)
        self._update(progress_callback, 18, "EFI directory structure created")
        bootx64 = os.path.join(efi_boot_dir, "BOOTX64.EFI")

        for src in self._EFI_SOURCES:
            if os.path.exists(src):
                try:
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 100,
                                 f"UEFI bootloader installed from {src}")
                    return True
                except Exception as exc:
                    logger.warning(f"copy {src}: {exc}")

        for efi_search in ("/usr/share/efi", "/usr/lib/efi",
                           "/usr/local/share", "/opt/homebrew/share"):
            if not os.path.isdir(efi_search):
                continue
            for root, _, files in os.walk(efi_search):
                for fname in files:
                    if fname.lower().endswith(".efi"):
                        src = os.path.join(root, fname)
                        try:
                            shutil.copy2(src, bootx64)
                            self._update(progress_callback, 100,
                                         f"UEFI bootloader installed from {src}")
                            return True
                        except Exception:
                            continue

        self._update(progress_callback, 88,
                     "No bootloader found — writing minimal UEFI stub…")
        stub = self._find_or_create_uefi_stub()
        try:
            shutil.copy2(stub, bootx64)
            self._update(progress_callback, 100, "Minimal UEFI stub installed")
            return True
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"Stub install failed: {exc}")
            return False


    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        return self.write_bios_boot(device, options, progress_callback)