import unittest
from core.boot_sector.manager import BootSectorManager
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

    def test_write_boot_sector_bcdboot_fallback(self):
        mgr = BootSectorManager()
        dummy_device = {'drive_letter': 'Z', 'number': 99}
        dummy_options = {'iso_type': 'windows', 'partition_scheme': 'mbr', 'iso_path': 'C:/dummy.iso'}
        with patch('shutil.which', side_effect=lambda exe: None if 'bootsect' in exe else 'bcdboot.exe'), \
             patch('os.path.exists', return_value=False), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = 'BCDboot success'
            mock_run.return_value.stderr = ''
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_write_boot_sector_diskpart_fallback(self):
        mgr = BootSectorManager()
        dummy_device = {'drive_letter': 'Y', 'number': 88}
        dummy_options = {'iso_type': 'windows', 'partition_scheme': 'mbr', 'iso_path': 'C:/dummy.iso'}
        with patch('shutil.which', return_value=None), \
             patch('os.path.exists', side_effect=lambda p: True if 'diskpart' in p else False), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = 'DiskPart successfully completed'
            mock_run.return_value.stderr = ''
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_write_boot_sector_powershell_fallback(self):
        mgr = BootSectorManager()
        dummy_device = {'drive_letter': 'X', 'number': 77}
        dummy_options = {'iso_type': 'windows', 'partition_scheme': 'mbr', 'iso_path': 'C:/dummy.iso'}
        def os_path_exists_side_effect(p):
            if 'usb_boot_fallback.ps1' in p:
                return True
            return False
        with patch('shutil.which', return_value=None), \
             patch('os.path.exists', side_effect=os_path_exists_side_effect), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = 'PowerShell fallback success'
            mock_run.return_value.stderr = ''
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_write_boot_sector_powershell_script_missing(self):
        mgr = BootSectorManager()
        dummy_device = {'drive_letter': 'W', 'number': 66}
        dummy_options = {'iso_type': 'windows', 'partition_scheme': 'mbr', 'iso_path': 'C:/dummy.iso'}
        with patch('shutil.which', return_value=None), \
             patch('os.path.exists', side_effect=lambda p: False if 'usb_boot_fallback.ps1' in p else False), \
             patch('subprocess.run', side_effect=Exception('All fallbacks fail')):
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertFalse(result)

    def test_write_boot_sector_no_iso_path(self):
        mgr = BootSectorManager()
        dummy_device = {'drive_letter': 'V', 'number': 55}
        dummy_options = {'iso_type': 'windows', 'partition_scheme': 'mbr'}
        with patch('shutil.which', return_value=None), \
             patch('os.path.exists', return_value=True), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ''
            mock_run.return_value.stderr = 'No ISO path'
            result = mgr.write_boot_sector(dummy_device, dummy_options, None)
            self.assertIsInstance(result, bool)
            self.assertFalse(result)

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

        boot_sector = WindowsBootSector()
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ['/usr/bin/syslinux', '-maf', 'E:'],
            check=False,
            capture_output=True,
            text=True,
            timeout=30
        )

    @patch('shutil.which')
    def test_syslinux_not_found(self, mock_which):
        """Test when syslinux is not found in PATH."""
        mock_which.return_value = None

        boot_sector = WindowsBootSector()
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

        boot_sector = WindowsBootSector()
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

        boot_sector = WindowsBootSector()
        result = boot_sector._try_windows_syslinux('E', None)
        self.assertFalse(result)

    @patch('os.path.exists')
    @patch('shutil.which')
    def test_drive_not_found(self, mock_which, mock_exists):
        """Test when target drive doesn’t exist."""
        mock_which.return_value = '/usr/bin/syslinux'
        mock_exists.return_value = False

        boot_sector = WindowsBootSector()
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
        
        boot_sector = WindowsBootSector()
        
        def progress_callback(percent, message):
            print(f"{percent}%: {message}")
        
        try:
            result = boot_sector._try_windows_syslinux(DRIVE_LETTER, progress_callback)
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"syslinux failed on test drive: {str(e)}")


if __name__ == "__main__":
    unittest.main()
