import unittest
from core.iso_manager import ISOManager

class TestISOManager(unittest.TestCase):
    def setUp(self):
        self.manager = ISOManager()

    def test_instantiation(self):
        self.assertIsInstance(self.manager, ISOManager)

    def test_validate_iso_invalid_extension(self):
        self.assertFalse(self.manager.validate_iso('notaniso.txt'))

    def test_validate_iso_missing_file(self):
        self.assertFalse(self.manager.validate_iso('missing.iso'))

    def test_get_iso_info_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            self.manager.get_iso_info('missing.iso')

if __name__ == "__main__":
    unittest.main()
