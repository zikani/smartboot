"""
Windows Boot Sector module for SmartBoot

Provides Windows-specific boot sector writing using a layered fallback strategy:
  BIOS:    bootsect.exe → bcdboot.exe → syslinux → PowerShell MBR → generic dd
  UEFI:    copy bootmgfw.efi → Windows ADK efisys.bin → syslinux efi64 → stub
  FreeDOS: mark active → syslinux → bootsect → generic MBR
"""

import ctypes
import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Dict, Optional

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd, timeout: int = 60, **kwargs) -> subprocess.CompletedProcess:
    """Thin wrapper around subprocess.run with consistent defaults."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class WindowsBootSector(BaseBootSector):
    """Windows-specific boot sector implementation."""

    # Known locations for bootsect.exe
    _BOOTSECT_SEARCH = [
        r"C:\Windows\System32\bootsect.exe",
        r"C:\Windows\SysWOW64\bootsect.exe",
    ]
    # Known locations for bcdboot.exe
    _BCDBOOT_SEARCH = [
        r"C:\Windows\System32\bcdboot.exe",
    ]

    def check_admin_privileges(self) -> bool:
        return _is_admin()

    # ------------------------------------------------------------------
    # BIOS boot
    # ------------------------------------------------------------------

    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        if not self._validate_device_dict(device):
            self._update(progress_callback, 0, "Error: Invalid device information")
            return False

        drive = self._get_device_drive(device)
        if not drive:
            self._update(progress_callback, 0,
                         "Error: Drive letter not found in device information")
            return False
        drive = drive.rstrip(":\\")   # normalise to bare letter

        # Layer 1: bootsect.exe
        if self._try_bootsect(drive, progress_callback):
            return True

        # Layer 2: bcdboot.exe (only meaningful when Windows files are on drive)
        if self._try_bcdboot(drive, progress_callback):
            return True

        # Layer 3: syslinux
        if self._try_windows_syslinux(drive, progress_callback):
            return True

        # Layer 4: PowerShell raw MBR write
        if self._write_generic_mbr_windows(device, progress_callback):
            return True

        # Layer 5: PowerShell fallback script
        return self._try_powershell_script(device, options, progress_callback)

    def _try_bootsect(
        self,
        drive: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        bootsect = self._find_exe("bootsect.exe", self._BOOTSECT_SEARCH)
        if not bootsect:
            self._update(progress_callback, 10, "bootsect.exe not found, skipping")
            return False
        self._update(progress_callback, 10, f"Running bootsect.exe from {bootsect}…")
        try:
            r = _run(
                [bootsect, "/nt60", f"{drive}:", "/force", "/mbr"],
                timeout=60,
            )
            if r.returncode == 0:
                self._update(progress_callback, 40, "BIOS boot sector written (bootsect.exe)")
                return True
            self._update(progress_callback, 20,
                         f"bootsect.exe failed (rc={r.returncode}): {r.stderr.strip()}")
        except Exception as exc:
            self._update(progress_callback, 20, f"bootsect.exe error: {exc}")
        return False

    def _try_bcdboot(
        self,
        drive: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        win_dir = os.path.join(f"{drive}:\\", "Windows")
        if not os.path.isdir(win_dir):
            return False
        bcdboot = self._find_exe("bcdboot.exe", self._BCDBOOT_SEARCH)
        if not bcdboot:
            return False
        self._update(progress_callback, 50, "Running bcdboot.exe…")
        try:
            r = _run([bcdboot, win_dir, "/s", f"{drive}:"], timeout=60)
            if r.returncode == 0:
                self._update(progress_callback, 70, "BCD store configured (bcdboot.exe)")
                return True
            self._update(progress_callback, 55,
                         f"bcdboot.exe failed (rc={r.returncode}): {r.stderr.strip()}")
        except Exception as exc:
            self._update(progress_callback, 55, f"bcdboot.exe error: {exc}")
        return False

    def _try_windows_syslinux(
        self,
        drive: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        syslinux = shutil.which("syslinux.exe") or shutil.which("syslinux")
        if not syslinux:
            self._update(progress_callback, 55, "syslinux not found in PATH")
            return False
        target = drive.rstrip(":")
        self._update(progress_callback, 55, f"Trying syslinux on {target}:…")
        try:
            r = _run([syslinux, "-maf", f"{target}:"], timeout=30)
            if r.returncode == 0:
                self._update(progress_callback, 80, "Boot sector written (syslinux)")
                return True
            self._update(progress_callback, 60,
                         f"syslinux failed (rc={r.returncode}): {r.stderr.strip()}")
        except subprocess.TimeoutExpired:
            self._update(progress_callback, 60, "syslinux timed out")
        except Exception as exc:
            self._update(progress_callback, 60, f"syslinux error: {exc}")
        return False

    def _write_generic_mbr_windows(
        self,
        device: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        if not _is_admin():
            self._update(progress_callback, 0,
                         "Error: Administrator required for MBR write")
            return False

        disk_num = device.get("number", -1)
        if int(disk_num) < 0:
            self._update(progress_callback, 0,
                         "Error: Unknown disk number for MBR write")
            return False

        phys_drive = f"\\\\.\\PhysicalDrive{disk_num}"
        mbr_bin = self._find_or_create_mbr()

        # Try dd first (Cygwin / WSL dd)
        dd = shutil.which("dd") or shutil.which("dd.exe")
        if dd:
            self._update(progress_callback, 75, f"Writing MBR with dd to {phys_drive}…")
            try:
                r = _run(
                    [dd, f"if={mbr_bin}", f"of={phys_drive}",
                     "bs=446", "count=1"],
                    timeout=30,
                )
                if r.returncode == 0:
                    self._update(progress_callback, 95,
                                 "Generic MBR written (dd)")
                    return True
                self._update(progress_callback, 80,
                             f"dd failed (rc={r.returncode})")
            except Exception as exc:
                self._update(progress_callback, 80, f"dd error: {exc}")

        # PowerShell WriteFile fallback
        self._update(progress_callback, 80,
                     "Writing MBR with PowerShell FileStream…")
        mbr_escaped = mbr_bin.replace("\\", "\\\\")
        drive_escaped = phys_drive.replace("\\", "\\\\")
        ps = f"""
$ErrorActionPreference = 'Stop'
try {{
    $mbr  = [System.IO.File]::ReadAllBytes('{mbr_escaped}')
    $disk = [System.IO.FileStream]::new(
                '{drive_escaped}',
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite)
    try {{
        $disk.Write($mbr, 0, 446)
        $disk.Flush()
    }} finally {{
        $disk.Close()
    }}
    Write-Host 'MBR written OK'
}} catch {{
    Write-Error "MBR write failed: $_"
    exit 1
}}
"""
        try:
            r = _run(["powershell", "-NoProfile", "-Command", ps], timeout=30)
            if r.returncode == 0:
                self._update(progress_callback, 95,
                             "Generic MBR written (PowerShell)")
                return True
            self._update(progress_callback, 0,
                         f"PowerShell MBR failed: {r.stderr.strip()}")
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"PowerShell MBR error: {exc}")
        return False

    def _try_powershell_script(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        script_path = os.path.join(os.path.dirname(__file__),
                                   "usb_boot_fallback.ps1")
        if not os.path.exists(script_path):
            self._update(progress_callback, 0,
                         "PowerShell fallback script not found")
            return False

        drive = self._get_device_drive(device)
        iso_path = options.get("iso_path", "")
        if not drive or not iso_path:
            return False

        drive = drive.rstrip(":\\")
        boot_mode = {
            "bios": "BIOS", "uefi": "UEFI", "dual": "UEFI",
        }.get(options.get("boot_type", "bios").lower(), "BIOS")

        self._update(progress_callback, 90,
                     "Attempting PowerShell fallback script…")
        try:
            r = _run(
                [
                    "powershell.exe", "-ExecutionPolicy", "Bypass",
                    "-File", script_path,
                    "-DriveLetter", drive,
                    "-ISOPath", iso_path,
                    "-BootMode", boot_mode,
                ],
                timeout=300,
            )
            if r.returncode == 0:
                self._update(progress_callback, 100,
                             "PowerShell fallback script succeeded")
                return True
            self._update(progress_callback, 0,
                         f"Fallback script failed: {r.stderr.strip()}")
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"Fallback script error: {exc}")
        return False

    # ------------------------------------------------------------------
    # UEFI boot
    # ------------------------------------------------------------------

    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        if not self._validate_device_dict(device):
            self._update(progress_callback, 0, "Error: Invalid device information")
            return False
        if not _is_admin():
            self._update(progress_callback, 0,
                         "Error: Administrator privileges required for UEFI boot")
            return False

        drive = self._get_device_drive(device)
        if not drive:
            self._update(progress_callback, 0,
                         "Error: Drive letter not found for UEFI boot")
            return False
        drive = drive.rstrip(":\\")

        # Ensure EFI directory structure
        efi_boot_dir = os.path.join(f"{drive}:\\", "EFI", "BOOT")
        os.makedirs(efi_boot_dir, exist_ok=True)
        self._update(progress_callback, 20, "EFI directory structure created")

        bootx64 = os.path.join(efi_boot_dir, "BOOTX64.EFI")
        iso_type = options.get("iso_type", "generic").lower()

        # Layer 1: Windows bootmgfw.efi
        if iso_type == "windows":
            if self._install_windows_uefi(drive, bootx64, progress_callback):
                return True

        # Layer 2: Generic EFI sources already on the drive
        if self._copy_existing_efi(drive, bootx64, progress_callback):
            return True

        # Layer 3: syslinux efi64
        if self._try_syslinux_efi(bootx64, progress_callback):
            return True

        # Layer 4: Well-known system EFI files
        system_sources = [
            r"C:\syslinux\efi64\syslinux.efi",
            r"C:\boot\bootx64.efi",
            r"D:\boot\bootx64.efi",
            os.path.join(
                os.environ.get("WINDIR", r"C:\Windows"),
                "Boot", "EFI", "bootx64.efi"
            ),
        ]
        for src in system_sources:
            if os.path.exists(src):
                try:
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 90,
                                 f"UEFI bootloader copied from {src}")
                    return True
                except Exception as exc:
                    logger.warning(f"Copy from {src} failed: {exc}")

        # Layer 5: Minimal stub (better than nothing)
        self._update(progress_callback, 95,
                     "No bootloader found — writing minimal UEFI stub…")
        stub = self._find_or_create_uefi_stub()
        try:
            shutil.copy2(stub, bootx64)
            self._update(progress_callback, 100,
                         "Minimal UEFI stub installed (firmware will report error)")
            return True
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"Failed to write UEFI stub: {exc}")
            return False

    def _install_windows_uefi(
        self,
        drive: str,
        bootx64: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        """Try to locate and install Windows bootmgfw.efi."""
        candidates = [
            os.path.join(f"{drive}:\\", "efi", "microsoft", "boot", "bootmgfw.efi"),
            os.path.join(f"{drive}:\\", "boot", "efi", "bootmgfw.efi"),
            os.path.join(
                os.environ.get("WINDIR", r"C:\Windows"),
                "Boot", "EFI", "bootmgfw.efi"
            ),
        ]
        # Also check any mounted DVD/ISO drives
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            candidates.append(
                os.path.join(f"{letter}:\\", "efi", "microsoft", "boot", "bootmgfw.efi")
            )

        for src in candidates:
            if os.path.exists(src):
                try:
                    self._update(progress_callback, 50,
                                 f"Copying Windows EFI bootloader from {src}…")
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 70,
                                 "Windows UEFI bootloader installed")
                    return True
                except Exception as exc:
                    logger.warning(f"_install_windows_uefi: copy {src} failed: {exc}")

        # Windows ADK
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env, "")
            if not base:
                continue
            for ver in ("10", "8.1", "8.0"):
                adk = os.path.join(
                    base, "Windows Kits", ver,
                    "Assessment and Deployment Kit",
                    "Deployment Tools", "amd64", "Oscdimg", "efisys.bin"
                )
                if os.path.exists(adk):
                    try:
                        shutil.copy2(adk, bootx64)
                        self._update(progress_callback, 70,
                                     f"UEFI bootloader installed from ADK ({adk})")
                        return True
                    except Exception as exc:
                        logger.warning(f"ADK copy failed: {exc}")
        return False

    def _copy_existing_efi(
        self,
        drive: str,
        bootx64: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        """Copy any EFI file already present on the drive."""
        efi_search_roots = [
            os.path.join(f"{drive}:\\", "EFI"),
            os.path.join(f"{drive}:\\", "boot"),
        ]
        for root in efi_search_roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _, files in os.walk(root):
                for fname in files:
                    if fname.lower().endswith(".efi") and fname.lower() != "bootx64.efi":
                        src = os.path.join(dirpath, fname)
                        try:
                            shutil.copy2(src, bootx64)
                            self._update(progress_callback, 80,
                                         f"EFI file copied from {src}")
                            return True
                        except Exception:
                            continue
        return False

    def _try_syslinux_efi(
        self,
        bootx64: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        candidates = [
            r"C:\syslinux\efi64\syslinux.efi",
            r"C:\Program Files\Syslinux\efi64\syslinux.efi",
        ]
        for src in candidates:
            if os.path.exists(src):
                try:
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 85,
                                 f"syslinux EFI bootloader copied from {src}")
                    return True
                except Exception as exc:
                    logger.warning(f"syslinux EFI copy failed: {exc}")
        return False

    # ------------------------------------------------------------------
    # FreeDOS boot
    # ------------------------------------------------------------------

    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        if not self._validate_device_dict(device):
            self._update(progress_callback, 0, "Error: Invalid device information")
            return False

        drive = self._get_device_drive(device)
        if not drive:
            self._update(progress_callback, 0,
                         "Error: Drive letter not found for FreeDOS boot")
            return False
        drive = drive.rstrip(":\\")

        self._update(progress_callback, 10,
                     "Preparing FreeDOS boot sector…")

        # Mark partition active via diskpart
        script = f"select volume {drive}\nactive\nexit\n"
        tmp = os.path.join(tempfile.gettempdir(), "sb_active.txt")
        try:
            with open(tmp, "w") as f:
                f.write(script)
            _run(["diskpart", "/s", tmp], timeout=30)
        except Exception as exc:
            self._update(progress_callback, 15,
                         f"Warning: could not mark partition active: {exc}")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

        # Look for FreeDOS SYS.COM
        sys_candidates = [
            os.path.join(f"{drive}:\\", "freedos", "bin", "sys.com"),
            r"C:\freedos\bin\sys.com",
        ]
        for sc in sys_candidates:
            if os.path.exists(sc):
                self._update(progress_callback, 30, f"Found FreeDOS SYS.COM: {sc}")
                try:
                    r = _run([sc, f"{drive}:"], timeout=30)
                    if r.returncode == 0:
                        self._update(progress_callback, 100,
                                     "FreeDOS boot sector written (sys.com)")
                        return True
                except Exception as exc:
                    logger.warning(f"sys.com failed: {exc}")

        # Fall through to generic BIOS boot chain
        return (
            self._try_bootsect(drive, progress_callback)
            or self._try_windows_syslinux(drive, progress_callback)
            or self._write_generic_mbr_windows(device, progress_callback)
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _find_exe(name: str, extra_paths: list) -> Optional[str]:
        """Find an executable in PATH or extra_paths list."""
        found = shutil.which(name)
        if found:
            return found
        for p in extra_paths:
            if os.path.exists(p):
                return p
        return None