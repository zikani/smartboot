import unittest
from core.boot_sector.manager import BootSectorManager
from core.boot_sector.windows import WindowsBootSector
from unittest.mock import patch
from subprocess import CompletedProcess, TimeoutExpired
import shutil
import subprocess
import os


class TestBootSector(unittest.TestCase):
    def test_import(self):
        self.assertTrue(True)

    def test_boot_sector_manager_instantiation(self):
        mgr = BootSectorManager()
        self.assertIsInstance(mgr, BootSectorManager)
        self.assertIsNotNone(mgr._impl)

    def test_write_boot_sector_invalid_device(self):
        mgr = BootSectorManager()
        dummy_device = {'error': 'test error'}
        dummy_options = {'boot_type': 'bios'}
        result = mgr.write_boot_sector(dummy_device, dummy_options, None)
        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_write_boot_sector_no_admin(self):
        mgr = BootSectorManager()
        dummy_device = {'name': 'test', 'number': 1}
        dummy_options = {'boot_type': 'bios'}
        with patch.object(mgr._impl, 'check_admin_privileges', return_value=False):
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertFalse(result)

    def test_write_boot_sector_valid_device(self):
        mgr = BootSectorManager()
        dummy_device = {'name': 'test', 'number': 1}
        dummy_options = {'boot_type': 'bios'}
        with patch.object(mgr._impl, 'check_admin_privileges', return_value=True), \
             patch.object(mgr._impl, 'write_bios_boot', return_value=True):
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_write_boot_sector_uefi(self):
        mgr = BootSectorManager()
        dummy_device = {'name': 'test', 'number': 1}
        dummy_options = {'boot_type': 'uefi'}
        with patch.object(mgr._impl, 'check_admin_privileges', return_value=True), \
             patch.object(mgr._impl, 'write_uefi_boot', return_value=True):
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_write_boot_sector_freedos(self):
        mgr = BootSectorManager()
        dummy_device = {'name': 'test', 'number': 1}
        dummy_options = {'boot_type': 'freedos'}
        with patch.object(mgr._impl, 'check_admin_privileges', return_value=True), \
             patch.object(mgr._impl, 'write_freedos_boot', return_value=True):
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_write_boot_sector_dummy(self):
        mgr = BootSectorManager()
        result = mgr.write_boot_sector({}, {}, None)
        self.assertIsInstance(result, bool)


class TestSyslinuxBoot(unittest.TestCase):
    """Tests for syslinux boot sector writing functionality."""

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('shutil.which')
    def test_syslinux_success(self, mock_which, mock_exists, mock_run):
        """Test successful syslinux execution."""
        mock_which.return_value = '/usr/bin/syslinux'
        mock_exists.return_value = True
        mock_run.return_value = CompletedProcess([], 0, '', '')

        boot_sector = WindowsBootSector(resource_dir="/tmp")
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ['/usr/bin/syslinux', '-maf', 'E:'],
            capture_output=True,
            text=True,
            timeout=30
        )

    @patch('shutil.which')
    def test_syslinux_not_found(self, mock_which):
        """Test when syslinux is not found in PATH."""
        mock_which.return_value = None

        boot_sector = WindowsBootSector(resource_dir="/tmp")
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertFalse(result)

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('shutil.which')
    def test_syslinux_failure(self, mock_which, mock_exists, mock_run):
        """Test syslinux command failure."""
        mock_which.return_value = '/usr/bin/syslinux'
        mock_exists.return_value = True
        mock_run.return_value = CompletedProcess([], 1, '', 'Error message')

        boot_sector = WindowsBootSector(resource_dir="/tmp")
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertFalse(result)

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('shutil.which')
    def test_syslinux_timeout(self, mock_which, mock_exists, mock_run):
        """Test syslinux timeout."""
        mock_which.return_value = '/usr/bin/syslinux'
        mock_exists.return_value = True
        mock_run.side_effect = TimeoutExpired(['syslinux'], 30)

        boot_sector = WindowsBootSector(resource_dir="/tmp")
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertFalse(result)

    @patch('os.path.exists')
    @patch('shutil.which')
    def test_drive_not_found(self, mock_which, mock_exists):
        """Test when target drive doesn’t exist."""
        mock_which.return_value = '/usr/bin/syslinux'
        mock_exists.return_value = False

        boot_sector = WindowsBootSector(resource_dir="/tmp")
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertFalse(result)


class TestSyslinuxIntegration(unittest.TestCase):
    """Integration tests for syslinux that require actual installation."""

    @classmethod
    def setUpClass(cls):
        """Check if syslinux is available before running these tests."""
        cls.syslinux_available = bool(shutil.which('syslinux') or shutil.which('syslinux.exe'))

    @unittest.skipUnless(shutil.which('syslinux') or shutil.which('syslinux.exe'), 
                        "syslinux not installed")
    def test_syslinux_installed(self):
        """Verify syslinux is actually installed on the system."""
        self.assertTrue(self.syslinux_available, "syslinux should be installed for these tests")

    @unittest.skipUnless(shutil.which('syslinux') or shutil.which('syslinux.exe'), 
                        "syslinux not installed")
    def test_syslinux_version(self):
        """Test basic syslinux version check."""
        try:
            result = subprocess.run(
                ['syslinux', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn('syslinux', result.stdout.lower())
        except subprocess.CalledProcessError as e:
            self.fail(f"syslinux version check failed: {e.stderr}")

    @unittest.skipUnless(shutil.which('syslinux') or shutil.which('syslinux.exe'), 
                        "syslinux not installed")
    @unittest.skip("Requires actual test drive - modify DRIVE_LETTER before running")
    def test_syslinux_on_test_drive(self):
        """Test actual syslinux execution on a test drive."""
        DRIVE_LETTER = 'X'
        test_drive = f"{DRIVE_LETTER}:"
        
        if not os.path.exists(test_drive):
            self.skipTest(f"Test drive {test_drive} not available")
        
        boot_sector = WindowsBootSector(resource_dir="/tmp")
        
        def progress_callback(percent, message):
            print(f"{percent}%: {message}")
        
        try:
            result = boot_sector._try_windows_syslinux(DRIVE_LETTER, progress_callback)
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"syslinux failed on test drive: {str(e)}")


if __name__ == "__main__":
    unittest.main()
