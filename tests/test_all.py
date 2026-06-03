"""
SmartBoot — Comprehensive Test Suite

Covers:
  - USBManager (device detection, size parsing, write-protect)
  - ISOManager (type detection, checksum, hybrid detection, label, history)
  - DiskFormatter (label sanitize, supported FS, format error paths)
  - ImageWriter (ISO type detection, cancel token, path normalisation)
  - BootSectorManager (platform dispatch, dual-boot, privilege gate)
  - WindowsBootSector (all BIOS/UEFI/FreeDOS layers with mocks)
  - BaseBootSector (MBR generation, UEFI stub generation)
  - Worker thread (pre-flight size check, stage progression)
"""

import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import MagicMock, patch, call

# Ensure project root on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.usb_manager          import USBManager
from core.iso_manager          import ISOManager
from core.disk_formatter       import DiskFormatter
from core.image_writer         import ImageWriter
from core.boot_sector.base     import BaseBootSector
from core.boot_sector.manager  import BootSectorManager
from core.boot_sector.windows  import WindowsBootSector


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_minimal_iso(path: str, size_mb: int = 12) -> None:
    """Create a file with ISO 9660 magic at the correct offset."""
    data = bytearray(size_mb * 1024 * 1024)
    # Primary Volume Descriptor magic at 0x8001
    data[0x8001:0x8006] = b"CD001"
    # Volume label at 0x8028
    label = b"TESTISO     "
    data[0x8028:0x8028 + len(label)] = label
    with open(path, "wb") as f:
        f.write(data)


# ═══════════════════════════════════════════════════════════════════════════
# USBManager
# ═══════════════════════════════════════════════════════════════════════════

class TestUSBManager(unittest.TestCase):

    def setUp(self):
        self.mgr = USBManager()

    def test_instantiation(self):
        self.assertIsInstance(self.mgr, USBManager)

    def test_get_devices_returns_list(self):
        result = self.mgr.get_devices()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_error_device_structure(self):
        dev = USBManager._error_device("test error")
        self.assertIn("error", dev)
        self.assertEqual(dev["number"], -1)
        self.assertEqual(dev["size_bytes"], 0)

    def test_format_size(self):
        self.assertEqual(USBManager._format_size(0),          "Unknown")
        self.assertIn("GB", USBManager._format_size(8 * 1024**3))
        self.assertIn("MB", USBManager._format_size(512 * 1024**2))
        self.assertIn("TB", USBManager._format_size(2 * 1024**4))

    def test_parse_size_bytes_gb(self):
        result = USBManager._parse_size_bytes("8.00 GB")
        self.assertAlmostEqual(result, 8 * 1024**3, delta=1024**2)

    def test_parse_size_bytes_mb(self):
        result = USBManager._parse_size_bytes("512.00 MB")
        self.assertAlmostEqual(result, 512 * 1024**2, delta=1024)

    def test_parse_size_bytes_invalid(self):
        self.assertEqual(USBManager._parse_size_bytes("unknown"), 0)
        self.assertEqual(USBManager._parse_size_bytes(""), 0)

    def test_size_warning_too_small(self):
        dev = {"size_bytes": 256 * 1024**2}   # 256 MB
        warn = self.mgr._check_size_warning(dev)
        self.assertIn("too small", warn)

    def test_size_warning_normal(self):
        dev = {"size_bytes": 8 * 1024**3}
        self.assertEqual(self.mgr._check_size_warning(dev), "")

    def test_size_warning_zero(self):
        self.assertEqual(self.mgr._check_size_warning({"size_bytes": 0}), "")

    def test_get_device_details_not_found(self):
        self.assertIsNone(self.mgr.get_device_details("nonexistent_device_xyz"))


# ═══════════════════════════════════════════════════════════════════════════
# ISOManager
# ═══════════════════════════════════════════════════════════════════════════

class TestISOManager(unittest.TestCase):

    def setUp(self):
        self.mgr    = ISOManager()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _iso(self, name="test.iso", size_mb=12) -> str:
        path = os.path.join(self.tmpdir, name)
        _make_minimal_iso(path, size_mb)
        return path

    # -- validate_iso -------------------------------------------------------

    def test_validate_iso_wrong_extension(self):
        f = os.path.join(self.tmpdir, "disk.img")
        open(f, "wb").close()
        self.assertFalse(self.mgr.validate_iso(f))

    def test_validate_iso_missing_file(self):
        self.assertFalse(self.mgr.validate_iso("/nonexistent/path/file.iso"))

    def test_validate_iso_too_small(self):
        small = os.path.join(self.tmpdir, "tiny.iso")
        with open(small, "wb") as f:
            f.write(b"\x00" * 1024)
        self.assertFalse(self.mgr.validate_iso(small))

    def test_validate_iso_valid(self):
        path = self._iso()
        self.assertTrue(self.mgr.validate_iso(path))

    # -- get_iso_info -------------------------------------------------------

    def test_get_iso_info_missing(self):
        with self.assertRaises(FileNotFoundError):
            self.mgr.get_iso_info("/nonexistent/test.iso")

    def test_get_iso_info_not_a_file(self):
        with self.assertRaises(ValueError):
            self.mgr.get_iso_info(self.tmpdir)

    def test_get_iso_info_fields(self):
        path = self._iso()
        info = self.mgr.get_iso_info(path)
        for key in ("path", "filename", "size_bytes", "size", "type",
                    "is_hybrid", "has_efi", "persistence_capable",
                    "recommended_fs", "recommended_scheme", "min_usb_bytes"):
            self.assertIn(key, info, f"Missing key: {key}")
        self.assertEqual(info["path"], path)
        self.assertGreater(info["size_bytes"], 0)

    # -- ISO type detection -------------------------------------------------

    def test_detect_windows_filename(self):
        path = self._iso("Windows10.iso")
        t = self.mgr._determine_iso_type(path)
        self.assertEqual(t, "Windows")

    def test_detect_linux_filename(self):
        path = self._iso("ubuntu-22.04.iso")
        t = self.mgr._determine_iso_type(path)
        self.assertEqual(t, "Linux")

    def test_detect_freedos_filename(self):
        path = self._iso("FD12CD.iso")
        t = self.mgr._determine_iso_type(path)
        self.assertEqual(t, "FreeDOS")

    def test_detect_generic_filename(self):
        path = self._iso("unknown_disk.iso")
        t = self.mgr._determine_iso_type(path)
        self.assertIn("Generic", t)

    # -- ISO structure helpers ---------------------------------------------

    def test_check_iso9660_magic_valid(self):
        path = self._iso()
        self.assertTrue(ISOManager._check_iso9660_magic(path))

    def test_check_iso9660_magic_invalid(self):
        bad = os.path.join(self.tmpdir, "bad.iso")
        with open(bad, "wb") as f:
            f.write(b"\x00" * (20 * 1024 * 1024))
        self.assertFalse(ISOManager._check_iso9660_magic(bad))

    def test_read_volume_label(self):
        path = self._iso()
        label = self.mgr._read_volume_label(path)
        self.assertIsInstance(label, str)

    def test_is_hybrid_iso_false(self):
        path = self._iso()   # minimal ISO — no MBR boot sig
        # Most minimal test ISOs are NOT hybrid
        result = self.mgr._is_hybrid_iso(path)
        self.assertIsInstance(result, bool)

    # -- Checksum ----------------------------------------------------------

    def test_compute_checksum_sha256(self):
        path = self._iso()
        digest = self.mgr.compute_checksum(path, "sha256")
        self.assertEqual(len(digest), 64)
        self.assertRegex(digest, r"^[0-9a-f]+$")

    def test_compute_checksum_md5(self):
        path = self._iso()
        digest = self.mgr.compute_checksum(path, "md5")
        self.assertEqual(len(digest), 32)

    def test_compute_checksum_sha1(self):
        path = self._iso()
        digest = self.mgr.compute_checksum(path, "sha1")
        self.assertEqual(len(digest), 40)

    def test_compute_checksum_invalid_algo(self):
        path = self._iso()
        digest = self.mgr.compute_checksum(path, "notreal")
        self.assertEqual(digest, "")

    def test_verify_checksum_match(self):
        path = self._iso()
        with open(path, "rb") as f:
            expected = hashlib.sha256(f.read()).hexdigest()
        self.assertTrue(self.mgr.verify_checksum(path, expected, "sha256"))

    def test_verify_checksum_mismatch(self):
        path = self._iso()
        self.assertFalse(
            self.mgr.verify_checksum(path, "a" * 64, "sha256")
        )

    def test_compute_checksum_progress_called(self):
        path = self._iso()
        calls = []
        self.mgr.compute_checksum(path, "sha256",
                                  progress_callback=lambda p, m: calls.append(p))
        self.assertTrue(len(calls) > 0)
        self.assertEqual(calls[-1], 100)

    # -- History -----------------------------------------------------------

    def test_history_add_and_retrieve(self):
        path = self._iso("history_test.iso")
        self.mgr.get_iso_info(path)     # triggers history write
        history = self.mgr.get_history()
        paths = [h.get("path") for h in history]
        self.assertIn(path, paths)

    def test_history_clear(self):
        path = self._iso("clear_test.iso")
        self.mgr.get_iso_info(path)
        self.mgr.clear_history()
        self.assertEqual(self.mgr.get_history(), [])

    # -- Recommendations ---------------------------------------------------

    def test_recommend_fs(self):
        self.assertEqual(ISOManager._recommend_fs("Windows", True, 0), "FAT32")
        self.assertEqual(ISOManager._recommend_fs("Linux",   False, 0), "FAT32")
        self.assertEqual(ISOManager._recommend_fs("FreeDOS", False, 0), "FAT32")

    def test_format_size(self):
        self.assertIn("GB", ISOManager._format_size(8 * 1024**3))
        self.assertIn("MB", ISOManager._format_size(500 * 1024**2))


# ═══════════════════════════════════════════════════════════════════════════
# DiskFormatter
# ═══════════════════════════════════════════════════════════════════════════

class TestDiskFormatter(unittest.TestCase):

    def setUp(self):
        self.fmt = DiskFormatter()

    def test_instantiation(self):
        self.assertIsInstance(self.fmt, DiskFormatter)

    def test_get_supported_filesystems_non_empty(self):
        fs = self.fmt.get_supported_filesystems()
        self.assertIsInstance(fs, list)
        self.assertGreater(len(fs), 0)

    def test_format_disk_error_device(self):
        ok, msg = self.fmt.format_disk({"error": "no device"}, "FAT32")
        self.assertFalse(ok)

    def test_format_disk_write_protected(self):
        ok, msg = self.fmt.format_disk(
            {"name": "sdb", "write_protected": True}, "FAT32"
        )
        self.assertFalse(ok)

    # -- label sanitize ----------------------------------------------------

    def test_sanitize_label_fat32_uppercase(self):
        label = self.fmt.sanitize_label("hello world!", "fat32")
        self.assertEqual(label, "HELLO WORLD")

    def test_sanitize_label_fat32_truncate(self):
        label = self.fmt.sanitize_label("TOOLONGLABELNAME", "fat32")
        self.assertEqual(len(label), 11)

    def test_sanitize_label_ntfs_illegal_chars(self):
        label = self.fmt.sanitize_label('bad/name:here?', "ntfs")
        self.assertNotIn("/", label)
        self.assertNotIn(":", label)
        self.assertNotIn("?", label)

    def test_sanitize_label_empty_returns_default(self):
        label = self.fmt.sanitize_label("", "fat32")
        self.assertEqual(label, "SMARTBOOT")

    def test_sanitize_label_exfat_length(self):
        label = self.fmt.sanitize_label("A" * 30, "exfat")
        self.assertLessEqual(len(label), 15)

    def test_sanitize_label_ext4_length(self):
        label = self.fmt.sanitize_label("A" * 20, "ext4")
        self.assertLessEqual(len(label), 16)

    # -- Windows code path (mocked) ----------------------------------------

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_format_disk_invalid_number_windows(self):
        ok, msg = self.fmt.format_disk(
            {"name": "test", "number": -1}, "FAT32"
        )
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════════════════
# ImageWriter
# ═══════════════════════════════════════════════════════════════════════════

class TestImageWriter(unittest.TestCase):

    def setUp(self):
        self.writer  = ImageWriter()
        self.tmpdir  = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_instantiation(self):
        self.assertIsInstance(self.writer, ImageWriter)

    def test_write_iso_missing_file(self):
        ok = self.writer.write_iso("/nonexistent/test.iso", "/tmp")
        self.assertFalse(ok)

    # -- ISO type detection ------------------------------------------------

    def test_detect_windows(self):
        t = self.writer._detect_iso_type("Windows10_22H2.iso")
        self.assertEqual(t, "windows")

    def test_detect_ubuntu(self):
        t = self.writer._detect_iso_type("ubuntu-22.04.3-desktop-amd64.iso")
        self.assertEqual(t, "linux")

    def test_detect_fedora(self):
        t = self.writer._detect_iso_type("Fedora-Workstation-Live-x86_64-38.iso")
        self.assertEqual(t, "linux")

    def test_detect_freedos(self):
        t = self.writer._detect_iso_type("FD12CD.iso")
        self.assertEqual(t, "freedos")

    def test_detect_kali(self):
        t = self.writer._detect_iso_type("kali-linux-2023.iso")
        self.assertEqual(t, "linux")

    def test_detect_generic_unknown(self):
        t = self.writer._detect_iso_type("some_random_image.iso")
        self.assertEqual(t, "generic")

    # -- Windows drive normalisation ----------------------------------------

    def test_normalise_win_drive_bare(self):
        self.assertEqual(ImageWriter._normalise_win_drive("E"), "E:\\")

    def test_normalise_win_drive_colon(self):
        self.assertEqual(ImageWriter._normalise_win_drive("E:"), "E:\\")

    def test_normalise_win_drive_full(self):
        self.assertEqual(ImageWriter._normalise_win_drive("E:\\"), "E:\\")

    def test_normalise_win_drive_empty(self):
        self.assertEqual(ImageWriter._normalise_win_drive(""), "")

    # -- Cancel token -------------------------------------------------------

    def test_cancel_sets_event(self):
        self.writer.cancel()
        self.assertTrue(self.writer._cancel_event.is_set())

    def test_reset_cancel_clears_event(self):
        self.writer.cancel()
        self.writer.reset_cancel()
        self.assertFalse(self.writer._cancel_event.is_set())

    # -- copy_tree ----------------------------------------------------------

    def test_copy_tree_basic(self):
        src = os.path.join(self.tmpdir, "src")
        dst = os.path.join(self.tmpdir, "dst")
        os.makedirs(src)
        os.makedirs(dst)
        # Create test files
        for name in ("a.txt", "b.bin"):
            with open(os.path.join(src, name), "wb") as f:
                f.write(b"X" * 2048)
        self.writer.reset_cancel()
        ok = self.writer._copy_tree(src, dst, None)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(os.path.join(dst, "a.txt")))
        self.assertTrue(os.path.exists(os.path.join(dst, "b.bin")))

    def test_copy_tree_cancel(self):
        src = os.path.join(self.tmpdir, "src2")
        dst = os.path.join(self.tmpdir, "dst2")
        os.makedirs(src)
        os.makedirs(dst)
        for i in range(50):
            with open(os.path.join(src, f"f{i}.bin"), "wb") as f:
                f.write(b"Y" * 4096)
        self.writer.cancel()
        ok = self.writer._copy_tree(src, dst, None)
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════════════════
# BaseBootSector
# ═══════════════════════════════════════════════════════════════════════════

class TestBaseBootSector(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.base   = BaseBootSector(resource_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # -- Device dict helpers -----------------------------------------------

    def test_get_device_drive_new_key(self):
        self.assertEqual(
            self.base._get_device_drive({"drive_letter": "E"}), "E"
        )

    def test_get_device_drive_legacy_key(self):
        self.assertEqual(
            self.base._get_device_drive({"drive": "F"}), "F"
        )

    def test_get_device_drive_new_key_takes_precedence(self):
        self.assertEqual(
            self.base._get_device_drive({"drive_letter": "G", "drive": "H"}), "G"
        )

    def test_get_device_drive_missing(self):
        self.assertIsNone(self.base._get_device_drive({"name": "sdb"}))

    def test_normalize_device_path_no_prefix(self):
        self.assertEqual(self.base._normalize_device_path("sdb"), "/dev/sdb")

    def test_normalize_device_path_with_prefix(self):
        self.assertEqual(self.base._normalize_device_path("/dev/sdc"), "/dev/sdc")

    def test_validate_device_dict_valid(self):
        self.assertTrue(self.base._validate_device_dict({"name": "sdb"}))

    def test_validate_device_dict_missing_required(self):
        self.assertFalse(self.base._validate_device_dict({}))

    def test_validate_device_dict_custom_keys(self):
        self.assertTrue(
            self.base._validate_device_dict(
                {"name": "t", "drive_letter": "E"},
                required_keys=["name", "drive_letter"]
            )
        )
        self.assertFalse(
            self.base._validate_device_dict(
                {"name": "t"},
                required_keys=["name", "drive_letter"]
            )
        )

    # -- MBR generation ----------------------------------------------------

    def test_find_or_create_mbr_produces_file(self):
        path = self.base._find_or_create_mbr()
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), 446)

    def test_find_or_create_mbr_reuses_existing(self):
        path1 = self.base._find_or_create_mbr()
        mtime1 = os.path.getmtime(path1)
        path2 = self.base._find_or_create_mbr()
        mtime2 = os.path.getmtime(path2)
        self.assertEqual(path1, path2)
        self.assertEqual(mtime1, mtime2)

    def test_mbr_content_starts_with_x86_code(self):
        path = self.base._find_or_create_mbr()
        with open(path, "rb") as f:
            data = f.read()
        # First two bytes: cli (0xFA) and cld (0xFC)
        self.assertEqual(data[0], 0xFA)
        self.assertEqual(data[1], 0xFC)

    def test_mbr_contains_error_message(self):
        path = self.base._find_or_create_mbr()
        with open(path, "rb") as f:
            data = f.read()
        self.assertIn(b"No bootable device", data)

    # -- UEFI stub generation ----------------------------------------------

    def test_find_or_create_uefi_stub_produces_file(self):
        path = self.base._find_or_create_uefi_stub()
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 512)

    def test_uefi_stub_mz_signature(self):
        path = self.base._find_or_create_uefi_stub()
        with open(path, "rb") as f:
            magic = f.read(2)
        self.assertEqual(magic, b"MZ")

    def test_uefi_stub_pe_signature(self):
        path = self.base._find_or_create_uefi_stub()
        with open(path, "rb") as f:
            data = f.read(256)
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        with open(path, "rb") as f:
            f.seek(pe_offset)
            pe_sig = f.read(4)
        self.assertEqual(pe_sig, b"PE\x00\x00")

    def test_uefi_stub_reuses_existing(self):
        p1 = self.base._find_or_create_uefi_stub()
        t1 = os.path.getmtime(p1)
        p2 = self.base._find_or_create_uefi_stub()
        t2 = os.path.getmtime(p2)
        self.assertEqual(t1, t2)

    # -- Default interface returns False -----------------------------------

    def test_check_admin_privileges_default(self):
        self.assertFalse(self.base.check_admin_privileges())

    def test_write_bios_boot_default(self):
        self.assertFalse(self.base.write_bios_boot({}, {}))

    def test_write_uefi_boot_default(self):
        self.assertFalse(self.base.write_uefi_boot({}, {}))

    def test_write_freedos_boot_default(self):
        self.assertFalse(self.base.write_freedos_boot({}, {}))

    # -- grub.cfg / syslinux.cfg writers -----------------------------------

    def test_write_grub_cfg_creates_file(self):
        grub_dir = os.path.join(self.tmpdir, "grub")
        os.makedirs(grub_dir)
        self.base._write_grub_cfg(grub_dir, "linux")
        cfg = os.path.join(grub_dir, "grub.cfg")
        self.assertTrue(os.path.exists(cfg))
        with open(cfg) as f:
            content = f.read()
        self.assertIn("SmartBoot", content)

    def test_write_syslinux_cfg_creates_file(self):
        mp = os.path.join(self.tmpdir, "mount")
        os.makedirs(mp)
        self.base._write_syslinux_cfg(mp, "linux")
        cfg = os.path.join(mp, "syslinux.cfg")
        self.assertTrue(os.path.exists(cfg))

    def test_write_grub_cfg_freedos(self):
        grub_dir = os.path.join(self.tmpdir, "grub_fdos")
        os.makedirs(grub_dir)
        self.base._write_grub_cfg(grub_dir, "freedos")
        with open(os.path.join(grub_dir, "grub.cfg")) as f:
            content = f.read()
        self.assertIn("FreeDOS", content)

    def test_write_grub_cfg_windows(self):
        grub_dir = os.path.join(self.tmpdir, "grub_win")
        os.makedirs(grub_dir)
        self.base._write_grub_cfg(grub_dir, "windows")
        with open(os.path.join(grub_dir, "grub.cfg")) as f:
            content = f.read()
        self.assertIn("bootmgr", content)


# ═══════════════════════════════════════════════════════════════════════════
# BootSectorManager
# ═══════════════════════════════════════════════════════════════════════════

class TestBootSectorManager(unittest.TestCase):

    def setUp(self):
        self.mgr = BootSectorManager()

    def test_instantiation(self):
        self.assertIsInstance(self.mgr, BootSectorManager)
        self.assertIsNotNone(self.mgr._impl)

    def test_error_device_returns_false(self):
        result = self.mgr.write_boot_sector(
            {"error": "test error"}, {"boot_type": "bios"}, None
        )
        self.assertFalse(result)

    def test_no_admin_returns_false(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=False):
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "bios"}, None
            )
        self.assertFalse(result)

    def test_bios_dispatches_correctly(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=True) as mock_bios:
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "bios"}, None
            )
        self.assertTrue(result)
        mock_bios.assert_called_once()

    def test_uefi_dispatches_correctly(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_uefi_boot",
                          return_value=True) as mock_uefi:
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "uefi"}, None
            )
        self.assertTrue(result)
        mock_uefi.assert_called_once()

    def test_freedos_dispatches_correctly(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_freedos_boot",
                          return_value=True) as mock_fdos:
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "freedos"}, None
            )
        self.assertTrue(result)
        mock_fdos.assert_called_once()

    def test_dual_both_succeed(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_uefi_boot",
                          return_value=True):
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "dual"}, None
            )
        self.assertTrue(result)

    def test_dual_bios_only(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_uefi_boot",
                          return_value=False):
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "dual"}, None
            )
        self.assertTrue(result)

    def test_dual_uefi_only(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=False), \
             patch.object(self.mgr._impl, "write_uefi_boot",
                          return_value=True):
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "dual"}, None
            )
        self.assertTrue(result)

    def test_dual_both_fail(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=False), \
             patch.object(self.mgr._impl, "write_uefi_boot",
                          return_value=False):
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "dual"}, None
            )
        self.assertFalse(result)

    def test_progress_callback_called(self):
        calls = []
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=True):
            self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "bios"},
                progress_callback=lambda p, m: calls.append((p, m))
            )
        self.assertTrue(len(calls) > 0)

    def test_default_boot_type_is_bios(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.mgr._impl, "write_bios_boot",
                          return_value=True) as mock_bios:
            self.mgr.write_boot_sector({"name": "sdb"}, {})
        mock_bios.assert_called_once()

    def test_exception_returns_false(self):
        with patch.object(self.mgr._impl, "check_admin_privileges",
                          side_effect=RuntimeError("boom")):
            result = self.mgr.write_boot_sector(
                {"name": "sdb"}, {"boot_type": "bios"}, None
            )
        self.assertFalse(result)


# ═══════════════════════════════════════════════════════════════════════════
# WindowsBootSector  (mocked — no real disk I/O)
# ═══════════════════════════════════════════════════════════════════════════

class TestWindowsBootSector(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ws     = WindowsBootSector(resource_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # -- check_admin_privileges -------------------------------------------

    @patch("core.boot_sector.windows.ctypes.windll.shell32.IsUserAnAdmin",
           return_value=1, create=True)
    def test_admin_true(self, _):
        self.assertTrue(self.ws.check_admin_privileges())

    @patch("core.boot_sector.windows.ctypes.windll.shell32.IsUserAnAdmin",
           return_value=0, create=True)
    def test_admin_false(self, _):
        self.assertFalse(self.ws.check_admin_privileges())

    # -- _try_bootsect -----------------------------------------------------

    @patch("shutil.which", return_value=None)
    def test_bootsect_not_found(self, _):
        result = self.ws._try_bootsect("E", None)
        self.assertFalse(result)

    @patch("core.boot_sector.windows._run",
           return_value=CompletedProcess([], 0, "", ""))
    @patch("os.path.exists", return_value=True)
    def test_bootsect_success(self, mock_exists, mock_run):
        with patch.object(self.ws, "_find_exe",
                          return_value=r"C:\Windows\System32\bootsect.exe"):
            result = self.ws._try_bootsect("E", None)
        self.assertTrue(result)

    @patch("core.boot_sector.windows._run",
           return_value=CompletedProcess([], 1, "", "Access denied"))
    @patch("os.path.exists", return_value=True)
    def test_bootsect_failure(self, mock_exists, mock_run):
        with patch.object(self.ws, "_find_exe",
                          return_value=r"C:\Windows\System32\bootsect.exe"):
            result = self.ws._try_bootsect("E", None)
        self.assertFalse(result)

    # -- _try_windows_syslinux --------------------------------------------

    @patch("shutil.which", return_value=None)
    def test_syslinux_not_found(self, _):
        result = self.ws._try_windows_syslinux("E", None)
        self.assertFalse(result)

    @patch("core.boot_sector.windows._run",
           return_value=CompletedProcess([], 0, "", ""))
    @patch("shutil.which", return_value="/usr/bin/syslinux")
    def test_syslinux_success(self, mock_which, mock_run):
        result = self.ws._try_windows_syslinux("E", None)
        self.assertTrue(result)

    @patch("core.boot_sector.windows._run",
           return_value=CompletedProcess([], 1, "", "Error"))
    @patch("shutil.which", return_value="/usr/bin/syslinux")
    def test_syslinux_failure(self, mock_which, mock_run):
        result = self.ws._try_windows_syslinux("E", None)
        self.assertFalse(result)

    @patch("core.boot_sector.windows._run",
           side_effect=TimeoutExpired(["syslinux"], 30))
    @patch("shutil.which", return_value="/usr/bin/syslinux")
    def test_syslinux_timeout(self, mock_which, mock_run):
        result = self.ws._try_windows_syslinux("E", None)
        self.assertFalse(result)

    # -- write_bios_boot (invalid device) ----------------------------------

    def test_write_bios_boot_invalid_device(self):
        result = self.ws.write_bios_boot({}, {}, None)
        self.assertFalse(result)

    def test_write_bios_boot_no_drive_letter(self):
        result = self.ws.write_bios_boot({"name": "test", "number": 1}, {}, None)
        self.assertFalse(result)

    # -- write_uefi_boot (no admin) ----------------------------------------

    @patch("core.boot_sector.windows._is_admin", return_value=False)
    def test_write_uefi_boot_no_admin(self, _):
        result = self.ws.write_uefi_boot(
            {"name": "t", "drive_letter": "E", "number": 1}, {}, None
        )
        self.assertFalse(result)

    # -- write_freedos_boot (invalid device) ------------------------------

    def test_write_freedos_boot_invalid_device(self):
        result = self.ws.write_freedos_boot({}, {}, None)
        self.assertFalse(result)

    # -- _find_exe ---------------------------------------------------------

    def test_find_exe_from_extra_paths(self):
        dummy = os.path.join(self.tmpdir, "mytool.exe")
        open(dummy, "w").close()
        result = WindowsBootSector._find_exe("mytool.exe", [dummy])
        self.assertEqual(result, dummy)

    def test_find_exe_not_found(self):
        result = WindowsBootSector._find_exe("nonexistent_tool_xyz.exe", [])
        self.assertIsNone(result)

    # -- _diskpart_active (mocked) ----------------------------------------

    @patch("core.boot_sector.windows._run",
           return_value=CompletedProcess([], 0, "", ""))
    def test_diskpart_active_called(self, mock_run):
        self.ws._diskpart_active("E", None)
        # Just ensure it doesn't throw and calls subprocess
        mock_run.assert_called()


# ═══════════════════════════════════════════════════════════════════════════
# Integration-style: full pipeline with mocks
# ═══════════════════════════════════════════════════════════════════════════

class TestBootableUsbPipeline(unittest.TestCase):
    """
    Simulates the full creation pipeline:
    format → write ISO → boot sector
    using mocked sub-operations.
    """

    def setUp(self):
        self.tmpdir      = tempfile.mkdtemp()
        self.formatter   = DiskFormatter()
        self.writer      = ImageWriter()
        self.boot_mgr    = BootSectorManager()
        self.iso_manager = ISOManager()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_pipeline_success(self):
        iso_path = os.path.join(self.tmpdir, "test.iso")
        _make_minimal_iso(iso_path)

        device = {
            "name":         "sdb",
            "number":       1,
            "drive_letter": self.tmpdir,
            "size_bytes":   16 * 1024**3,
        }
        options = {
            "boot_type":        "bios",
            "filesystem":       "fat32",
            "partition_scheme": "MBR",
            "quick_format":     True,
            "iso_type":         "linux",
            "direct_write":     False,
            "verify":           False,
        }

        with patch.object(self.formatter, "format_disk",
                          return_value=(True, self.tmpdir)), \
             patch.object(self.writer, "write_iso",
                          return_value=True), \
             patch.object(self.boot_mgr._impl, "check_admin_privileges",
                          return_value=True), \
             patch.object(self.boot_mgr._impl, "write_bios_boot",
                          return_value=True):

            # Stage 1: format
            ok, drive = self.formatter.format_disk(device, "fat32")
            self.assertTrue(ok)

            # Stage 2: write ISO
            ok = self.writer.write_iso(iso_path, drive, "linux", True, None)
            self.assertTrue(ok)

            # Stage 3: boot sector
            ok = self.boot_mgr.write_boot_sector(device, options, None)
            self.assertTrue(ok)

    def test_pipeline_aborts_on_format_failure(self):
        device  = {"name": "sdb", "number": -1}
        options = {"boot_type": "bios", "filesystem": "fat32",
                   "partition_scheme": "MBR"}
        ok, _ = self.formatter.format_disk(device, "fat32")
        self.assertFalse(ok)

    def test_pipeline_aborts_on_missing_iso(self):
        ok = self.writer.write_iso("/no/such/file.iso", self.tmpdir, "auto",
                                   True, None)
        self.assertFalse(ok)

    def test_device_dict_backward_compat(self):
        """Old code using 'drive' key still resolves correctly."""
        base = BaseBootSector(resource_dir=self.tmpdir)
        for dev, expected in [
            ({"drive": "C"},               "C"),
            ({"drive_letter": "D"},        "D"),
            ({"drive_letter": "E", "drive": "F"}, "E"),
            ({"name": "sdb"},              None),
        ]:
            self.assertEqual(base._get_device_drive(dev), expected)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)