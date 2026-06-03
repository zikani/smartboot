"""
Base Boot Sector module for SmartBoot

Provides:
  - Abstract interface every platform implementation must satisfy
  - Shared MBR bootstrap generation (x86 real-mode)
  - Shared minimal PE32+ EFI stub
  - Shared GRUB-cfg writer
  - Progress/logging helpers
  - Device-dict normalisation helpers
"""

import os
import struct
import tempfile
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger()


class BaseBootSector:
    """
    Abstract base for platform-specific boot-sector writers.

    Sub-classes must implement:
        check_admin_privileges() -> bool
        write_bios_boot(device, options, cb) -> bool
        write_uefi_boot(device, options, cb) -> bool
        write_freedos_boot(device, options, cb) -> bool
    """

    def __init__(self, resource_dir: str) -> None:
        self.resource_dir = resource_dir
        self._mounted_paths: List[str] = []

    def __del__(self) -> None:
        self._cleanup_mounts()

    def _cleanup_mounts(self) -> None:
        """Override to unmount anything this instance mounted."""


    def _get_device_drive(self, device: Dict[str, Any]) -> Optional[str]:
        """Return drive letter / mount-point; prefers 'drive_letter' over legacy 'drive'."""
        return device.get("drive_letter") or device.get("drive") or None

    def _get_device_path(self, device: Dict[str, Any]) -> Optional[str]:
        name = device.get("name", "")
        if not name:
            return None
        return name if name.startswith("/dev/") else f"/dev/{name}"

    def _normalize_device_path(self, device_name: str) -> str:
        return device_name if device_name.startswith("/dev/") else f"/dev/{device_name}"

    def _validate_device_dict(
        self,
        device: Dict[str, Any],
        required_keys: Optional[List[str]] = None,
    ) -> bool:
        if required_keys is None:
            required_keys = ["name"]
        return all(k in device for k in required_keys)


    def check_admin_privileges(self) -> bool:
        return False

    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        self._update(progress_callback, 0, "BIOS boot not supported on this platform")
        return False

    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        self._update(progress_callback, 0, "UEFI boot not supported on this platform")
        return False

    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        self._update(progress_callback, 0, "FreeDOS boot not supported on this platform")
        return False


    def _update(
        self,
        progress_callback: Optional[Callable[[int, str], None]],
        progress: int,
        message: str,
    ) -> None:
        logger.debug(f"BootSector {progress}%: {message}")
        if progress_callback and progress is not None:
            progress_callback(progress, message)


    def _find_or_create_mbr(self) -> str:
        """
        Return path to a 446-byte generic MBR boot-code file.

        The MBR prints "No bootable device" and halts.  It is used only
        as a last-resort fallback; it does NOT replace a real bootloader.
        The partition table (bytes 446-509) and boot signature (510-511)
        are always preserved by callers via conv=notrunc / count=1.
        """
        mbr_path = os.path.join(self.resource_dir, "mbr_generic.bin")
        if os.path.exists(mbr_path) and os.path.getsize(mbr_path) == 446:
            return mbr_path

        mbr = bytearray(446)

        MSG = b"No bootable device.\r\n\x00"
        MSG_OFFSET = 0x7C00 + 0x1A

        code = bytearray([
            0xFA, 0xFC,
            0x31, 0xC0,
            0x8E, 0xD0,
            0xBC, 0x00, 0x7C,
            0x8E, 0xD8,
            0xBE, MSG_OFFSET & 0xFF, (MSG_OFFSET >> 8) & 0xFF,
            0xAC,
            0x08, 0xC0, 0x74, 0x09,
            0xB4, 0x0E, 0xBB, 0x07, 0x00, 0xCD, 0x10,
            0xEB, 0xF2,
            0xF4, 0xEB, 0xFD,
        ])
        msg_start = 0x1A
        code_bytes = bytes(code)
        mbr[: len(code_bytes)] = code_bytes
        mbr[msg_start: msg_start + len(MSG)] = MSG

        os.makedirs(self.resource_dir, exist_ok=True)
        with open(mbr_path, "wb") as f:
            f.write(mbr)
        logger.debug(f"BaseBootSector: created generic MBR at {mbr_path}")
        return mbr_path


    def _find_or_create_uefi_stub(self) -> str:
        """
        Return path to a structurally-valid PE32+ EFI application stub.

        The stub returns EFI_UNSUPPORTED (3).  Firmware will show a
        "boot failed" message rather than hanging silently.

        Layout
        ------
        0x000  DOS stub (64 B)
        0x040  PE signature + COFF header (24 B)
        0x058  Optional header PE32+ (240 B) — contains one data-directory
        0x148  Section table — .text (40 B)
        0x200  .text raw data — mov eax,3 ; ret (padded to 512 B)
        Total: 0x400 (1024 B)
        """
        stub_path = os.path.join(self.resource_dir, "BOOTX64_stub.EFI")
        if os.path.exists(stub_path) and os.path.getsize(stub_path) >= 512:
            return stub_path

        PE_OFFSET   = 0x40
        OPT_OFFSET  = PE_OFFSET + 24
        SECT_OFFSET = OPT_OFFSET + 216
        FILE_ALIGN  = 0x200
        SECT_VA     = 0x1000
        IMAGE_SIZE  = 0x2000
        HDR_SIZE    = FILE_ALIGN

        buf = bytearray(0x400)

        buf[0:2]   = b"MZ"
        struct.pack_into("<H", buf, 0x3C, PE_OFFSET)

        buf[PE_OFFSET : PE_OFFSET + 4] = b"PE\x00\x00"
        coff = PE_OFFSET + 4
        struct.pack_into("<H", buf, coff + 0,  0x8664)
        struct.pack_into("<H", buf, coff + 2,  1)
        struct.pack_into("<I", buf, coff + 8,  0)
        struct.pack_into("<I", buf, coff + 12, 0)
        struct.pack_into("<I", buf, coff + 16, 0)
        struct.pack_into("<H", buf, coff + 20, 216)
        struct.pack_into("<H", buf, coff + 22, 0x0022)

        o = OPT_OFFSET
        struct.pack_into("<H", buf, o,       0x020B)
        buf[o + 2] = 14;  buf[o + 3] = 0
        struct.pack_into("<I", buf, o + 4,   16)
        struct.pack_into("<I", buf, o + 8,   0)
        struct.pack_into("<I", buf, o + 12,  0)
        struct.pack_into("<I", buf, o + 16,  SECT_VA)
        struct.pack_into("<I", buf, o + 20,  SECT_VA)
        struct.pack_into("<Q", buf, o + 24,  0x400000)
        struct.pack_into("<I", buf, o + 32,  0x1000)
        struct.pack_into("<I", buf, o + 36,  FILE_ALIGN)
        struct.pack_into("<H", buf, o + 40,  0)
        struct.pack_into("<H", buf, o + 42,  0)
        struct.pack_into("<H", buf, o + 48,  0)
        struct.pack_into("<H", buf, o + 50,  0)
        struct.pack_into("<H", buf, o + 52,  0)
        struct.pack_into("<H", buf, o + 54,  0)
        struct.pack_into("<I", buf, o + 60,  IMAGE_SIZE)
        struct.pack_into("<I", buf, o + 64,  HDR_SIZE)
        struct.pack_into("<I", buf, o + 68,  0)
        struct.pack_into("<H", buf, o + 68,  10)
        struct.pack_into("<H", buf, o + 70,  0)
        struct.pack_into("<Q", buf, o + 72,  0x100000)
        struct.pack_into("<Q", buf, o + 80,  0x1000)
        struct.pack_into("<Q", buf, o + 88,  0x100000)
        struct.pack_into("<Q", buf, o + 96,  0x1000)
        struct.pack_into("<I", buf, o + 104, 0)
        struct.pack_into("<I", buf, o + 108, 0)

        s = SECT_OFFSET
        buf[s : s + 6] = b".text\x00"
        struct.pack_into("<I", buf, s + 8,  16)
        struct.pack_into("<I", buf, s + 12, SECT_VA)
        struct.pack_into("<I", buf, s + 16, FILE_ALIGN)
        struct.pack_into("<I", buf, s + 20, FILE_ALIGN)
        struct.pack_into("<I", buf, s + 36, 0x60000020)

        code = bytes([0xB8, 0x03, 0x00, 0x00, 0x00, 0xC3] + [0x90] * 10)
        buf[FILE_ALIGN : FILE_ALIGN + len(code)] = code

        os.makedirs(self.resource_dir, exist_ok=True)
        with open(stub_path, "wb") as f:
            f.write(buf)
        logger.debug(f"BaseBootSector: created UEFI stub at {stub_path}")
        return stub_path


    def _write_grub_cfg(self, grub_dir: str, iso_type: str = "generic") -> None:
        """Write a minimal grub.cfg appropriate for the ISO type."""
        cfg_path = os.path.join(grub_dir, "grub.cfg")
        try:
            with open(cfg_path, "w") as f:
                f.write("# SmartBoot generated GRUB configuration\n")
                f.write("set timeout=5\n")
                f.write("set default=0\n\n")

                if iso_type.lower() in ("windows",):
                    f.write("menuentry 'Windows Setup' {\n")
                    f.write("  chainloader /bootmgr\n")
                    f.write("}\n")
                elif iso_type.lower() in ("linux", "ubuntu", "debian",
                                           "fedora", "generic"):
                    f.write("search --file --set=root /boot/grub/grub.cfg\n")
                    f.write("set prefix=($root)/boot/grub\n")
                    f.write("configfile /boot/grub/grub.cfg\n\n")
                    f.write("menuentry 'Boot' {\n")
                    f.write("  set root=(hd0,1)\n")
                    f.write("  linux /casper/vmlinuz boot=casper quiet splash\n")
                    f.write("  initrd /casper/initrd\n")
                    f.write("}\n")
                elif iso_type.lower() in ("freedos",):
                    f.write("menuentry 'FreeDOS' {\n")
                    f.write("  set root=(hd0,1)\n")
                    f.write("  chainloader +1\n")
                    f.write("}\n")
                else:
                    f.write("search --file --set=root /boot/grub/grub.cfg\n")
                    f.write("set prefix=($root)/boot/grub\n")
                    f.write("configfile /boot/grub/grub.cfg\n")
        except OSError as exc:
            logger.warning(f"BaseBootSector: could not write grub.cfg: {exc}")


    def _write_syslinux_cfg(self, mount_point: str, iso_type: str = "generic") -> None:
        """Write a basic syslinux.cfg."""
        cfg_path = os.path.join(mount_point, "syslinux.cfg")
        try:
            with open(cfg_path, "w") as f:
                f.write("DEFAULT boot\n")
                f.write("TIMEOUT 50\n\n")
                f.write("LABEL boot\n")
                if iso_type.lower() in ("linux", "ubuntu", "debian",
                                         "fedora", "generic"):
                    f.write("  KERNEL /casper/vmlinuz\n")
                    f.write("  APPEND initrd=/casper/initrd boot=casper quiet splash\n")
                elif iso_type.lower() == "freedos":
                    f.write("  COM32 chain.c32\n")
                    f.write("  APPEND hd0 0\n")
                else:
                    f.write("  KERNEL /boot/vmlinuz\n")
                    f.write("  APPEND initrd=/boot/initrd.img quiet\n")
        except OSError as exc:
            logger.warning(f"BaseBootSector: could not write syslinux.cfg: {exc}")