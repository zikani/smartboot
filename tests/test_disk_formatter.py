import unittest
from core.disk_formatter import DiskFormatter

class TestDiskFormatter(unittest.TestCase):
    def setUp(self):
        self.formatter = DiskFormatter()

    def test_instantiation(self):
        self.assertIsInstance(self.formatter, DiskFormatter)

    def test_get_supported_filesystems(self):
        fs = self.formatter.get_supported_filesystems()
        self.assertIsInstance(fs, list)
        self.assertTrue(len(fs) > 0)

    def test_format_disk_invalid_device(self):
        # Should fail gracefully with invalid device
        result, msg = self.formatter.format_disk(device={}, filesystem='ntfs')
        self.assertFalse(result)
        self.assertIsInstance(msg, str)

if __name__ == "__main__":
    unittest.main()
