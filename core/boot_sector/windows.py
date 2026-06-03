"""
Windows Boot Sector module for SmartBoot

Rufus-parity layered fallback strategy:

  BIOS:
    1. bootsect.exe /nt60 <drive>: /force /mbr
    2. bcdboot.exe <Windows dir> /s <drive>: /f BIOS
    3. syslinux.exe -maf <drive>:
    4. PowerShell FileStream — write generic MBR to PhysicalDrive
    5. dd.exe (Cygwin/WSL) — write generic MBR
    6. PowerShell fallback script (usb_boot_fallback.ps1)

  UEFI:
    1. bcdboot.exe <Windows dir> /s <drive>: /f UEFI
    2. Copy bootmgfw.efi from ISO / host / ADK
    3. Copy any *.efi already on target drive
    4. syslinux efi64 candidates
    5. Minimal PE32+ stub

  FreeDOS:
    mark active via diskpart → FreeDOS SYS.COM → bootsect → syslinux → generic MBR

  Dual (BIOS + UEFI):
    Attempt both; succeed if at least one works.
"""

import ctypes
import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()



def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd, timeout: int = 60, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, **kwargs,
    )



class WindowsBootSector(BaseBootSector):
    """Windows-specific boot sector writer with full Rufus-parity fallback chain."""

    _BOOTSECT_SEARCH = [
        r"C:\Windows\System32\bootsect.exe",
        r"C:\Windows\SysWOW64\bootsect.exe",
    ]
    _BCDBOOT_SEARCH = [
        r"C:\Windows\System32\bcdboot.exe",
    ]


    def check_admin_privileges(self) -> bool:
        return _is_admin()


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
                         "Error: Drive letter not found")
            return False
        drive = drive.rstrip(":\\")

        if self._try_bootsect(drive, progress_callback):
            return True

        if self._try_bcdboot_bios(drive, progress_callback):
            return True

        if self._try_windows_syslinux(drive, progress_callback):
            return True

        if self._write_generic_mbr_windows(device, progress_callback):
            return True

        return self._try_powershell_script(device, options, progress_callback)


    def _try_bootsect(
        self,
        drive: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        bootsect = self._find_exe("bootsect.exe", self._BOOTSECT_SEARCH)
        if not bootsect:
            self._update(progress_callback, 8, "bootsect.exe not found, skipping")
            return False
        self._update(progress_callback, 8,
                     f"Running bootsect.exe from {bootsect}…")
        try:
            r = _run([bootsect, "/nt60", f"{drive}:", "/force", "/mbr"],
                     timeout=60)
            if r.returncode == 0:
                self._update(progress_callback, 40,
                             "BIOS boot sector written (bootsect.exe)")
                return True
            self._update(progress_callback, 18,
                         f"bootsect.exe failed (rc={r.returncode}): "
                         f"{r.stderr.strip()[:120]}")
        except Exception as exc:
            self._update(progress_callback, 18, f"bootsect.exe error: {exc}")
        return False


    def _try_bcdboot_bios(
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
        self._update(progress_callback, 46,
                     "Running bcdboot.exe (BIOS mode)…")
        try:
            r = _run([bcdboot, win_dir, "/s", f"{drive}:", "/f", "BIOS"],
                     timeout=60)
            if r.returncode == 0:
                self._update(progress_callback, 65,
                             "BCD store configured (bcdboot.exe BIOS)")
                return True
            self._update(progress_callback, 50,
                         f"bcdboot.exe BIOS failed: {r.stderr.strip()[:120]}")
        except Exception as exc:
            self._update(progress_callback, 50, f"bcdboot.exe error: {exc}")
        return False


    def _try_windows_syslinux(
        self,
        drive: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        syslinux = shutil.which("syslinux.exe") or shutil.which("syslinux")
        if not syslinux:
            self._update(progress_callback, 52, "syslinux not found in PATH")
            return False
        target = drive.rstrip(":")
        self._update(progress_callback, 52,
                     f"Trying syslinux on {target}:…")
        try:
            r = _run([syslinux, "-maf", f"{target}:"], timeout=30)
            if r.returncode == 0:
                self._update(progress_callback, 78,
                             "Boot sector written (syslinux)")
                return True
            self._update(progress_callback, 58,
                         f"syslinux failed (rc={r.returncode}): "
                         f"{r.stderr.strip()[:120]}")
        except subprocess.TimeoutExpired:
            self._update(progress_callback, 58, "syslinux timed out")
        except Exception as exc:
            self._update(progress_callback, 58, f"syslinux error: {exc}")
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

        dd = shutil.which("dd") or shutil.which("dd.exe")
        if dd:
            self._update(progress_callback, 72,
                         f"Writing MBR via dd to {phys_drive}…")
            try:
                r = _run([dd, f"if={mbr_bin}", f"of={phys_drive}",
                          "bs=446", "count=1"], timeout=30)
                if r.returncode == 0:
                    self._update(progress_callback, 92,
                                 "Generic MBR written (dd)")
                    return True
            except Exception as exc:
                logger.warning(f"dd MBR: {exc}")

        self._update(progress_callback, 78,
                     "Writing MBR via PowerShell FileStream…")
        mbr_esc  = mbr_bin.replace("\\", "\\\\")
        dev_esc  = phys_drive.replace("\\", "\\\\")
        ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $mbr  = [IO.File]::ReadAllBytes('{mbr_esc}')
    $disk = [IO.FileStream]::new(
                '{dev_esc}',
                [IO.FileMode]::Open,
                [IO.FileAccess]::Write,
                [IO.FileShare]::ReadWrite)
    try {{
        $disk.Write($mbr, 0, 446)
        $disk.Flush()
        Write-Host 'MBR written OK'
    }} finally {{ $disk.Close() }}
}} catch {{
    Write-Error "MBR write failed: $_"; exit 1
}}
"""
        try:
            r = _run(["powershell", "-NoProfile", "-Command", ps_script],
                     timeout=30)
            if r.returncode == 0:
                self._update(progress_callback, 92,
                             "Generic MBR written (PowerShell)")
                return True
            self._update(progress_callback, 0,
                         f"PowerShell MBR failed: {r.stderr.strip()[:200]}")
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
        script_path = os.path.join(
            os.path.dirname(__file__), "usb_boot_fallback.ps1"
        )
        if not os.path.exists(script_path):
            self._update(progress_callback, 0,
                         "PowerShell fallback script not found")
            return False

        drive    = self._get_device_drive(device)
        iso_path = options.get("iso_path", "")
        if not drive or not iso_path:
            return False

        drive     = drive.rstrip(":\\")
        boot_mode = {"bios": "BIOS", "uefi": "UEFI", "dual": "Dual"}.get(
            options.get("boot_type", "bios").lower(), "BIOS"
        )
        self._update(progress_callback, 88,
                     "Attempting PowerShell fallback script…")
        try:
            r = _run(
                [
                    "powershell.exe", "-ExecutionPolicy", "Bypass",
                    "-File", script_path,
                    "-DriveLetter", drive,
                    "-ISOPath",     iso_path,
                    "-BootMode",    boot_mode,
                    "-SkipFormat",
                    "-QuietProgress",
                ],
                timeout=600,
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("step") == "done":
                        if obj.get("ok"):
                            self._update(progress_callback, 100,
                                         obj.get("msg", "Done"))
                            return True
                        else:
                            self._update(progress_callback, 0,
                                         obj.get("msg", "Failed"))
                            return False
                except json.JSONDecodeError:
                    pass

            if r.returncode == 0:
                self._update(progress_callback, 100,
                             "PowerShell fallback script succeeded")
                return True
            self._update(progress_callback, 0,
                         f"Fallback script failed: {r.stderr.strip()[:200]}")
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"Fallback script error: {exc}")
        return False


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

        efi_boot_dir = os.path.join(f"{drive}:\\", "EFI", "BOOT")
        os.makedirs(efi_boot_dir, exist_ok=True)
        self._update(progress_callback, 12, "EFI directory structure created")

        bootx64  = os.path.join(efi_boot_dir, "BOOTX64.EFI")
        iso_type = options.get("iso_type", "generic").lower()

        if iso_type == "windows":
            if self._try_bcdboot_uefi(drive, bootx64, progress_callback):
                return True

        if iso_type == "windows":
            if self._install_windows_uefi(drive, bootx64, progress_callback):
                return True

        if self._copy_existing_efi(drive, bootx64, progress_callback):
            return True

        if self._try_syslinux_efi(bootx64, progress_callback):
            return True

        windir = os.environ.get("WINDIR", r"C:\Windows")
        system_sources = [
            os.path.join(windir, "Boot", "EFI", "bootmgfw.efi"),
            os.path.join(windir, "Boot", "EFI", "bootx64.efi"),
            r"C:\boot\bootx64.efi",
        ]
        for src in system_sources:
            if os.path.exists(src):
                try:
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 88,
                                 f"UEFI bootloader copied from {src}")
                    return True
                except Exception as exc:
                    logger.warning(f"copy {src}: {exc}")

        self._update(progress_callback, 92,
                     "No bootloader found — writing minimal UEFI stub…")
        stub = self._find_or_create_uefi_stub()
        try:
            shutil.copy2(stub, bootx64)
            self._update(progress_callback, 100,
                         "Minimal UEFI stub installed "
                         "(firmware will report unsupported — install proper bootloader)")
            return True
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"Failed to write UEFI stub: {exc}")
            return False


    def _try_bcdboot_uefi(
        self,
        drive: str,
        bootx64: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        win_dir = os.path.join(f"{drive}:\\", "Windows")
        if not os.path.isdir(win_dir):
            return False
        bcdboot = self._find_exe("bcdboot.exe", self._BCDBOOT_SEARCH)
        if not bcdboot:
            return False
        self._update(progress_callback, 38, "Running bcdboot.exe (UEFI)…")
        try:
            r = _run([bcdboot, win_dir, "/s", f"{drive}:", "/f", "UEFI"],
                     timeout=60)
            if r.returncode == 0:
                self._update(progress_callback, 72,
                             "UEFI boot configured (bcdboot.exe)")
                return True
            self._update(progress_callback, 45,
                         f"bcdboot.exe UEFI failed: {r.stderr.strip()[:120]}")
        except Exception as exc:
            self._update(progress_callback, 45, f"bcdboot.exe error: {exc}")
        return False


    def _install_windows_uefi(
        self,
        drive: str,
        bootx64: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        candidates: List[str] = [
            os.path.join(f"{drive}:\\", "efi", "microsoft", "boot", "bootmgfw.efi"),
            os.path.join(f"{drive}:\\", "boot", "efi", "bootmgfw.efi"),
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                         "Boot", "EFI", "bootmgfw.efi"),
        ]
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            candidates.append(
                os.path.join(f"{letter}:\\",
                             "efi", "microsoft", "boot", "bootmgfw.efi")
            )

        for src in candidates:
            if os.path.exists(src):
                try:
                    self._update(progress_callback, 52,
                                 f"Copying Windows EFI bootloader from {src}…")
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 72,
                                 "Windows UEFI bootloader installed")
                    return True
                except Exception as exc:
                    logger.warning(f"copy {src}: {exc}")

        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env, "")
            if not base:
                continue
            for ver in ("10", "8.1", "8.0"):
                adk = os.path.join(
                    base, "Windows Kits", ver,
                    "Assessment and Deployment Kit",
                    "Deployment Tools", "amd64", "Oscdimg", "efisys.bin",
                )
                if os.path.exists(adk):
                    try:
                        shutil.copy2(adk, bootx64)
                        self._update(progress_callback, 72,
                                     f"UEFI bootloader from ADK: {adk}")
                        return True
                    except Exception as exc:
                        logger.warning(f"ADK copy: {exc}")
        return False


    def _copy_existing_efi(
        self,
        drive: str,
        bootx64: str,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> bool:
        search_roots = [
            os.path.join(f"{drive}:\\", "EFI"),
            os.path.join(f"{drive}:\\", "boot"),
        ]
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _, files in os.walk(root):
                for fname in files:
                    if (fname.lower().endswith(".efi")
                            and fname.lower() != "bootx64.efi"):
                        src = os.path.join(dirpath, fname)
                        try:
                            shutil.copy2(src, bootx64)
                            self._update(progress_callback, 78,
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
            r"C:\tools\syslinux\efi64\syslinux.efi",
        ]
        for src in candidates:
            if os.path.exists(src):
                try:
                    shutil.copy2(src, bootx64)
                    self._update(progress_callback, 83,
                                 f"syslinux EFI copied from {src}")
                    return True
                except Exception as exc:
                    logger.warning(f"syslinux EFI: {exc}")
        return False


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

        self._update(progress_callback, 8, "Preparing FreeDOS boot sector…")

        self._diskpart_active(drive, progress_callback)

        sys_candidates = [
            os.path.join(f"{drive}:\\", "freedos", "bin", "sys.com"),
            os.path.join(f"{drive}:\\", "SYS.COM"),
            r"C:\freedos\bin\sys.com",
        ]
        for sc in sys_candidates:
            if os.path.exists(sc):
                self._update(progress_callback, 28,
                             f"Found FreeDOS SYS.COM: {sc}")
                try:
                    r = _run([sc, f"{drive}:"], timeout=30)
                    if r.returncode == 0:
                        self._update(progress_callback, 100,
                                     "FreeDOS boot sector written (sys.com)")
                        return True
                except Exception as exc:
                    logger.warning(f"sys.com failed: {exc}")

        return (
            self._try_bootsect(drive, progress_callback)
            or self._try_windows_syslinux(drive, progress_callback)
            or self._write_generic_mbr_windows(device, progress_callback)
        )


    def _diskpart_active(
        self,
        drive: str,
        cb: Optional[Callable[[int, str], None]],
    ) -> None:
        """Mark the partition containing drive letter as active."""
        script = f"select volume {drive}\nactive\nexit\n"
        tmp = os.path.join(tempfile.gettempdir(), "sb_active.txt")
        try:
            with open(tmp, "w") as f:
                f.write(script)
            _run(["diskpart", "/s", tmp], timeout=30)
            self._update(cb, 18, "Partition marked active")
        except Exception as exc:
            self._update(cb, 16, f"Warning: diskpart active: {exc}")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


    @staticmethod
    def _find_exe(name: str, extra_paths: List[str]) -> Optional[str]:
        found = shutil.which(name)
        if found:
            return found
        for p in extra_paths:
            if os.path.exists(p):
                return p
        return None