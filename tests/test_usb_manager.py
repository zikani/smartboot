import unittest
from core.usb_manager import USBManager

class TestUSBManager(unittest.TestCase):
    def setUp(self):
        self.manager = USBManager()

    def test_instantiation(self):
        self.assertIsInstance(self.manager, USBManager)

    def test_get_devices_returns_list(self):
        result = self.manager.get_devices()
        self.assertIsInstance(result, list)

if __name__ == "__main__":
    unittest.main()
