import unittest
from core.image_writer import ImageWriter

class TestImageWriter(unittest.TestCase):
    def setUp(self):
        self.writer = ImageWriter()

    def test_instantiation(self):
        self.assertIsInstance(self.writer, ImageWriter)

    def test_dummy_write_iso(self):
        try:
            self.writer.write_iso('dummy.iso', 'dummy_device')
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main()
