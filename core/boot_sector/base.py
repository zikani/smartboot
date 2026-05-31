"""
Base Boot Sector module for SmartBoot

Defines the interface that all platform-specific boot sector implementations
must satisfy, plus shared utilities (MBR generation, progress, helpers).
"""

import os
import struct
import tempfile
from typing import Dict, Any, Callable, Optional

from utils.logger import get_logger

logger = get_logger()


class BaseBootSector:
    """
    Abstract base for platform boot-sector writers.

    Sub-classes implement:
        check_admin_privileges()
        write_bios_boot(device, options, progress_callback) -> bool
        write_uefi_boot(device, options, progress_callback) -> bool
        write_freedos_boot(device, options, progress_callback) -> bool
    """

    def __init__(self, resource_dir: str) -> None:
        self.resource_dir = resource_dir
        self._mounted_paths: list = []

    def __del__(self) -> None:
        self._cleanup_mounts()

    def _cleanup_mounts(self) -> None:
        """Sub-classes override to unmount anything they mounted."""

    # ------------------------------------------------------------------
    # Device dictionary helpers
    # ------------------------------------------------------------------

    def _get_device_drive(self, device: Dict[str, Any]) -> Optional[str]:
        """Return drive letter / mount-point from device dict.

        Tries both 'drive_letter' (current key) and legacy 'drive' key.
        """
        return device.get("drive_letter") or device.get("drive") or None

    def _get_device_path(self, device: Dict[str, Any]) -> Optional[str]:
        """Return a /dev/-prefixed path for the device (Linux/macOS)."""
        name = device.get("name", "")
        if not name:
            return None
        return name if name.startswith("/dev/") else f"/dev/{name}"

    def _normalize_device_path(self, device_name: str) -> str:
        if not device_name.startswith("/dev/"):
            return f"/dev/{device_name}"
        return device_name

    def _validate_device_dict(
        self,
        device: Dict[str, Any],
        required_keys: Optional[list] = None,
    ) -> bool:
        if required_keys is None:
            required_keys = ["name"]
        return all(k in device for k in required_keys)

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def check_admin_privileges(self) -> bool:
        return False

    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        self._update(progress_callback, 0,
                     "BIOS boot not supported on this platform")
        return False

    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        self._update(progress_callback, 0,
                     "UEFI boot not supported on this platform")
        return False

    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        self._update(progress_callback, 0,
                     "FreeDOS boot not supported on this platform")
        return False

    # ------------------------------------------------------------------
    # Progress helper
    # ------------------------------------------------------------------

    def _update(
        self,
        progress_callback: Optional[Callable[[int, str], None]],
        progress: int,
        message: str,
    ) -> None:
        logger.debug(f"Boot sector {progress}%: {message}")
        if progress_callback:
            progress_callback(progress, message)

    # ------------------------------------------------------------------
    # MBR generation
    # ------------------------------------------------------------------

    def _find_or_create_mbr(self) -> str:
        """
        Return path to a generic 446-byte MBR boot code file.

        The MBR is a minimal x86 bootstrap that prints an error message
        and halts — it is only a fallback when no proper bootloader is
        available.  Real partitions / VBRs are left untouched (we write
        only bytes 0-445; the partition table at 446-509 and signature
        at 510-511 are preserved by callers using conv=notrunc / count=1).
        """
        mbr_path = os.path.join(self.resource_dir, "mbr_generic.bin")
        if os.path.exists(mbr_path) and os.path.getsize(mbr_path) == 446:
            return mbr_path

        mbr = bytearray(446)
        # --- Minimal real-mode bootstrap ---
        # Clears registers, sets up stack at 0x7C00, prints "No bootable device"
        # and halts.  Written as raw bytes to avoid assembler dependency.
        code = bytes([
            # cli / cld
            0xFA, 0xFC,
            # xor ax, ax
            0x31, 0xC0,
            # mov ss, ax  / mov sp, 0x7C00
            0x8E, 0xD0, 0xBC, 0x00, 0x7C,
            # mov ds, ax
            0x8E, 0xD8,
            # mov si, msg  (offset 0x1E relative to start)
            0xBE, 0x1E, 0x7C,
            # print loop: lodsb / or al,al / jz halt / int 10h / jmp loop
            0xAC, 0x08, 0xC0, 0x74, 0x09,
            0xB4, 0x0E, 0xBB, 0x07, 0x00, 0xCD, 0x10, 0xEB, 0xF2,
            # halt: hlt / jmp halt
            0xF4, 0xEB, 0xFD,
            # msg: "No bootable device.\r\n\0"
            *b"No bootable device.\r\n\x00",
        ])
        mbr[: len(code)] = code

        os.makedirs(self.resource_dir, exist_ok=True)
        with open(mbr_path, "wb") as f:
            f.write(mbr)
        return mbr_path

    def _find_or_create_uefi_stub(self) -> str:
        """
        Return path to a minimal (but structurally valid) PE32+ EFI stub.

        This stub simply prints a message and returns EFI_UNSUPPORTED.
        It is used only when no real EFI bootloader can be located and
        prevents a silent failure — the firmware will at least show an
        error rather than hanging.
        """
        stub_path = os.path.join(self.resource_dir, "BOOTX64_stub.EFI")
        if os.path.exists(stub_path) and os.path.getsize(stub_path) > 0:
            return stub_path

        # Minimal PE32+ EFI application header (DOS stub + PE header).
        # The code section just does `mov eax, 3  ; ret`  (EFI_UNSUPPORTED).
        dos_stub = bytearray(64)
        dos_stub[0:2]   = b"MZ"
        dos_stub[60:64] = struct.pack("<I", 64)   # e_lfanew -> PE header at 64

        pe_header = bytearray(248)
        # Signature
        pe_header[0:4] = b"PE\x00\x00"
        # Machine: IMAGE_FILE_MACHINE_AMD64
        struct.pack_into("<H", pe_header, 4, 0x8664)
        # NumberOfSections
        struct.pack_into("<H", pe_header, 6, 1)
        # Characteristics: EXE | large-address-aware
        struct.pack_into("<H", pe_header, 22, 0x0022)
        # SizeOfOptionalHeader
        struct.pack_into("<H", pe_header, 20, 240 - 24)
        # Optional header magic: PE32+
        struct.pack_into("<H", pe_header, 24, 0x020B)
        # AddressOfEntryPoint
        struct.pack_into("<I", pe_header, 40, 0x1000)
        # ImageBase (EFI default)
        struct.pack_into("<Q", pe_header, 48, 0x400000)
        # SectionAlignment / FileAlignment
        struct.pack_into("<I", pe_header, 56, 0x1000)
        struct.pack_into("<I", pe_header, 60, 0x200)
        # SizeOfImage / SizeOfHeaders
        struct.pack_into("<I", pe_header, 80, 0x2000)
        struct.pack_into("<I", pe_header, 84, 0x200)
        # Subsystem: EFI_APPLICATION
        struct.pack_into("<H", pe_header, 92, 10)

        # One section: .text
        section = bytearray(40)
        section[0:6] = b".text\x00"
        struct.pack_into("<I", section, 8,  0x1000)   # VirtualAddress
        struct.pack_into("<I", section, 12, 16)        # SizeOfRawData
        struct.pack_into("<I", section, 16, 0x200)     # PointerToRawData
        struct.pack_into("<I", section, 36, 0x60000020)  # Characteristics

        # Code: mov eax, 3 (EFI_UNSUPPORTED) ; ret
        code = bytes([0xB8, 0x03, 0x00, 0x00, 0x00, 0xC3] + [0x90] * 10)

        binary = bytearray(0x400)
        binary[0:64]       = dos_stub
        binary[64:64+248]  = pe_header
        binary[64+248-40:64+248] = section  # section table at end of opt header
        # Pad to FileAlignment then write code at RawData offset 0x200
        binary += bytearray(max(0, 0x200 - len(binary)))
        binary += bytearray(code)
        binary += bytearray(max(0, 0x400 - len(binary) - len(code)))

        os.makedirs(self.resource_dir, exist_ok=True)
        with open(stub_path, "wb") as f:
            f.write(binary[: 0x200 + 16])   # header + one sector of code

        return stub_path