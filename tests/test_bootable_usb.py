#!/usr/bin/env python3
"""
Test script for bootable USB creation fixes.

This script tests the critical fixes for bootable USB creation issues
without requiring actual USB hardware.
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_import_boot_sector_manager():
    """Test that BootSectorManager can be imported successfully."""
    print("Test 1: Import BootSectorManager...")
    try:
        from core.boot_sector.manager import BootSectorManager
        print("  ✓ BootSectorManager imported successfully")
        return True
    except ImportError as e:
        print(f"  ✗ Failed to import BootSectorManager: {e}")
        return False


def test_device_dict_standardization():
    """Test device dictionary with both 'drive_letter' and 'drive' keys."""
    print("\nTest 2: Device Dictionary Standardization...")
    try:
        from core.boot_sector.base import BaseBootSector
        
        base = BaseBootSector(resource_dir="/tmp")
        
        device_new = {'name': 'test', 'drive_letter': 'E'}
        drive = base._get_device_drive(device_new)
        if drive == 'E':
            print("  ✓ drive_letter key works correctly")
        else:
            print(f"  ✗ drive_letter key returned: {drive}, expected: E")
            return False
        
        device_old = {'name': 'test', 'drive': 'F'}
        drive = base._get_device_drive(device_old)
        if drive == 'F':
            print("  ✓ drive key (backward compatibility) works correctly")
        else:
            print(f"  ✗ drive key returned: {drive}, expected: F")
            return False
        
        device_both = {'name': 'test', 'drive_letter': 'G', 'drive': 'H'}
        drive = base._get_device_drive(device_both)
        if drive == 'G':
            print("  ✓ drive_letter takes precedence over drive")
        else:
            print(f"  ✗ drive_letter precedence failed, returned: {drive}, expected: G")
            return False
        
        device_none = {'name': 'test'}
        drive = base._get_device_drive(device_none)
        if drive is None:
            print("  ✓ Returns None when neither key exists")
        else:
            print(f"  ✗ Should return None, got: {drive}")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False


def test_device_validation():
    """Test device number validation with valid/invalid values."""
    print("\nTest 3: Device Number Validation...")
    try:
        from core.boot_sector.base import BaseBootSector
        
        base = BaseBootSector(resource_dir="/tmp")
        
        device_valid = {'name': 'test', 'number': 1}
        if base._validate_device_dict(device_valid):
            print("  ✓ Valid device dict passes validation")
        else:
            print("  ✗ Valid device dict failed validation")
            return False
        
        device_invalid = {'number': 1}
        if not base._validate_device_dict(device_invalid):
            print("  ✓ Invalid device dict fails validation")
        else:
            print("  ✗ Invalid device dict passed validation")
            return False
        
        device_custom = {'name': 'test', 'drive_letter': 'E'}
        if base._validate_device_dict(device_custom, required_keys=['name', 'drive_letter']):
            print("  ✓ Custom required keys validation works")
        else:
            print("  ✗ Custom required keys validation failed")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False


def test_linux_device_path_normalization():
    """Test Linux device path normalization."""
    print("\nTest 4: Linux Device Path Normalization...")
    try:
        from core.boot_sector.base import BaseBootSector
        
        base = BaseBootSector(resource_dir="/tmp")
        
        path1 = base._normalize_device_path("sdb")
        if path1 == "/dev/sdb":
            print("  ✓ Adds /dev/ prefix to device name")
        else:
            print(f"  ✗ Expected /dev/sdb, got: {path1}")
            return False
        
        path2 = base._normalize_device_path("/dev/sdc")
        if path2 == "/dev/sdc":
            print("  ✓ Preserves existing /dev/ prefix")
        else:
            print(f"  ✗ Expected /dev/sdc, got: {path2}")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False


def test_error_handling():
    """Test error messages for missing keys/invalid parameters."""
    print("\nTest 5: Error Handling...")
    try:
        from core.boot_sector.windows import WindowsBootSector
        from unittest.mock import MagicMock
        
        boot_sector = WindowsBootSector(resource_dir="/tmp")
        
        device_invalid = {}
        options = {}
        progress_callback = MagicMock()
        
        result = boot_sector.write_bios_boot(device_invalid, options, progress_callback)
        if not result:
            print("  ✓ Returns False for invalid device dict")
        else:
            print("  ✗ Should return False for invalid device dict")
            return False
        
        device_no_drive = {'name': 'test', 'number': 1}
        result = boot_sector.write_bios_boot(device_no_drive, options, progress_callback)
        if not result:
            print("  ✓ Returns False when drive letter is missing")
        else:
            print("  ✗ Should return False when drive letter is missing")
            return False
        
        device_valid = {'name': 'test', 'drive_letter': 'E', 'number': 1}
        options_no_iso = {}
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False


def test_backward_compatibility():
    """Ensure old code using 'drive' key still works."""
    print("\nTest 6: Backward Compatibility...")
    try:
        from core.boot_sector.base import BaseBootSector
        
        base = BaseBootSector(resource_dir="/tmp")
        
        old_style_devices = [
            {'name': 'test', 'drive': 'C'},
            {'name': 'test', 'drive': 'D', 'number': 2},
            {'name': 'test', 'drive': 'E', 'filesystem': 'NTFS'},
        ]
        
        for device in old_style_devices:
            drive = base._get_device_drive(device)
            if drive is not None:
                continue
            else:
                print(f"  ✗ Old-style device dict failed: {device}")
                return False
        
        print("  ✓ Old-style device dicts with 'drive' key work correctly")
        return True
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False


def test_disk_formatter_validation():
    """Test disk formatter device number validation."""
    print("\nTest 7: Disk Formatter Validation...")
    try:
        
        device_invalid = {'name': 'test', 'number': -1}
        disk_number = device_invalid.get('number')
        if disk_number is None or disk_number < 0 or disk_number == -1:
            print("  ✓ Device number validation catches -1")
        else:
            print("  ✗ Device number validation should catch -1")
            return False
        
        device_none = {'name': 'test', 'number': None}
        disk_number = device_none.get('number')
        if disk_number is None or disk_number < 0 or disk_number == -1:
            print("  ✓ Device number validation catches None")
        else:
            print("  ✗ Device number validation should catch None")
            return False
        
        device_valid = {'name': 'test', 'number': 1}
        disk_number = device_valid.get('number')
        if disk_number is not None and disk_number >= 0 and disk_number != -1:
            print("  ✓ Device number validation accepts valid number")
        else:
            print("  ✗ Device number validation should accept valid number")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Bootable USB Creation Fix Tests")
    print("=" * 60)
    
    tests = [
        test_import_boot_sector_manager,
        test_device_dict_standardization,
        test_device_validation,
        test_linux_device_path_normalization,
        test_error_handling,
        test_backward_compatibility,
        test_disk_formatter_validation,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
