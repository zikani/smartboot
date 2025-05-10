import unittest
from core.image_writer import ImageWriter

class TestImageWriter(unittest.TestCase):
    def setUp(self):
        self.writer = ImageWriter()

    def test_instantiation(self):
        self.assertIsInstance(self.writer, ImageWriter)

    def test_detect_iso_type_filename(self):
        # Should detect 'windows' from filename
        result = self.writer._detect_iso_type('Windows10.iso')
        self.assertEqual(result, 'windows')
        result = self.writer._detect_iso_type('ubuntu-22.04.iso')
        self.assertEqual(result, 'linux')
        result = self.writer._detect_iso_type('FreeDOS.iso')
        self.assertEqual(result, 'freedos')

    def test_write_iso_file_not_found(self):
        # Should fail gracefully if ISO file does not exist
        success = self.writer.write_iso('nonexistent.iso', 'Z:')
        self.assertFalse(success)

if __name__ == "__main__":
    unittest.main()
