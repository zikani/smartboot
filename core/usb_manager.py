"""
USB Manager module for SmartBoot

This module handles detection and information retrieval for USB devices.
"""

import os
import platform
import subprocess
import re
from typing import List, Dict, Any, Optional

from .boot_sector.manager import BootSectorManager
from utils.logger import default_logger as logger


class USBManager:
    """
    Class for managing USB devices.
    Handles detection, information retrieval, and selection of USB devices.
    """
    
    def __init__(self):
        """Initialize the USB Manager."""
        self.system = platform.system()
    
    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Get a list of available USB devices.
        
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing device information
        """
        try:
            if self.system == "Windows":
                devices = self._get_windows_devices()
                if not devices:
                    try:
                        import subprocess
                        result = subprocess.run([
                            "wmic", "diskdrive", "where", "MediaType='Removable Media'", "get", "DeviceID,Model,Size"
                        ], capture_output=True, text=True)
                        lines = result.stdout.strip().splitlines()
                        if len(lines) > 1:
                            devices = []
                            for line in lines[1:]:
                                parts = line.strip().split()
                                if len(parts) >= 3:
                                    devices.append({
                                        'name': parts[1],
                                        'number': -1,
                                        'size': str(int(parts[2]) // (1024*1024*1024)) + ' GB',
                                        'filesystem': 'Unknown',
                                        'drive_letter': ''
                                    })
                    except Exception as e:
                        pass
                if not devices:
                    return [{
                        'name': 'No USB devices found or access denied',
                        'number': -1,
                        'size': '0 GB',
                        'filesystem': 'Unknown',
                        'drive_letter': '',
                        'error': 'No USB devices found or permission denied. Try running as administrator.'
                    }]
                return devices
            elif self.system == "Linux":
                return self._get_linux_devices()
            elif self.system == "Darwin":
                return self._get_macos_devices()
            else:
                return [{
                    'name': f'Unsupported OS: {self.system}',
                    'number': -1,
                    'size': '0 GB',
                    'filesystem': 'Unknown',
                    'drive_letter': '',
                    'error': f'Unsupported OS: {self.system}'
                }]
        except Exception as e:
            return [{
                'name': f'Error: {str(e)}',
                'number': -1,
                'size': '0 GB',
                'filesystem': 'Unknown',
                'drive_letter': '',
                'error': str(e)
            }]
    
    def _get_windows_devices(self) -> List[Dict[str, Any]]:
        """
        Get USB devices on Windows using WMI.
        
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing device information
        """
        try:
            cmd = [
                "powershell",
                "-Command",
                (
                    "Get-Disk | Where-Object { $_.BusType -eq 'USB' } | ForEach-Object { "
                    "$disk = $_; "
                    "$partition = Get-Partition -DiskNumber $disk.Number | Select-Object -First 1; "
                    "if ($partition) { $volume = Get-Volume -Partition $partition -ErrorAction SilentlyContinue } else { $volume = $null } "
                    "[PSCustomObject]@{ "
                    "Name = $disk.FriendlyName; "
                    "Number = $disk.Number; "
                    "Size = ($disk.Size / 1GB).ToString('F2') + ' GB'; "
                    "FileSystem = if ($volume) { $volume.FileSystemType } else { '' }; "
                    "DriveLetter = if ($volume) { $volume.DriveLetter } else { '' } "
                    "} "
                    "} | ConvertTo-Json"
                )
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if not result.stdout.strip():
                return []
            
            import json
            devices_json = json.loads(result.stdout)
            
            if isinstance(devices_json, dict):
                devices_json = [devices_json]
            
            devices = []
            for device in devices_json:
                device_info = {
                    'name': device.get('Name', 'Unknown Device'),
                    'number': device.get('Number', -1),
                    'size': device.get('Size', 'Unknown'),
                    'filesystem': device.get('FileSystem', 'Unknown'),
                    'drive_letter': device.get('DriveLetter', '')
                }
                devices.append(device_info)
            
            return devices
            
        except subprocess.CalledProcessError as e:
            print(f"Error getting USB devices: {e}")
            print(f"Error output: {e.stderr}")
            return []
        except Exception as e:
            print(f"Error getting USB devices: {e}")
            return []
    
    def _get_linux_devices(self) -> List[Dict[str, Any]]:
        """
        Get USB devices on Linux.
        
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing device information
        """
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,VENDOR,MODEL,TRAN", "-J"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                devices_data = json.loads(result.stdout)
                
                if 'blockdevices' in devices_data:
                    devices = []
                    for device in devices_data['blockdevices']:
                        if device.get('tran') == 'usb' and not device['name'].startswith('loop'):
                            device_info = {
                                'name': f"{device.get('vendor', '')} {device.get('model', '')}".strip() or device['name'],
                                'number': -1,
                                'size': device.get('size', 'Unknown'),
                                'filesystem': device.get('fstype', 'Unknown'),
                                'drive_letter': device.get('mountpoint', '')
                            }
                            devices.append(device_info)
                    
                    if devices:
                        return devices
            
            try:
                result = subprocess.run(
                    ["lsblk", "-d", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT"],
                    capture_output=True, text=True, timeout=5
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]
                    devices = []
                    
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 2 and not parts[0].startswith('loop'):
                            if parts[0].startswith('sd') and not parts[0] == 'sda':
                                device_info = {
                                    'name': parts[0],
                                    'number': -1,
                                    'size': parts[1],
                                    'filesystem': parts[2] if len(parts) > 2 else 'Unknown',
                                    'drive_letter': parts[3] if len(parts) > 3 else ''
                                }
                                devices.append(device_info)
                    
                    if devices:
                        return devices
            except Exception:
                pass
                
            try:
                if os.path.exists('/dev/disk/by-id'):
                    usb_devices = []
                    for device in os.listdir('/dev/disk/by-id'):
                        if 'usb' in device and not 'part' in device:
                            usb_devices.append({
                                'name': device.replace('usb-', '').replace('_', ' '),
                                'number': -1,
                                'size': 'Unknown',
                                'filesystem': 'Unknown',
                                'drive_letter': ''
                            })
                    if usb_devices:
                        return usb_devices
            except Exception:
                pass
                
            return [{
                'name': 'No USB devices found or insufficient permissions',
                'number': -1,
                'size': '0 GB',
                'filesystem': 'Unknown',
                'drive_letter': '',
                'error': 'Try running with sudo or check if USB devices are connected'
            }]
            
        except Exception as e:
            return [{
                'name': f'Error detecting USB devices: {str(e)}',
                'number': -1,
                'size': '0 GB',
                'filesystem': 'Unknown',
                'drive_letter': '',
                'error': str(e)
            }]
    
    def _get_macos_devices(self) -> List[Dict[str, Any]]:
        """
        Get USB devices on macOS.
        
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing device information
        """
        try:
            result = subprocess.run(
                ["diskutil", "list", "external", "-plist"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    import plistlib
                    from io import BytesIO
                    
                    plist_data = plistlib.load(BytesIO(result.stdout.encode('utf-8')))
                    
                    if 'AllDisksAndPartitions' in plist_data:
                        devices = []
                        
                        for disk in plist_data['AllDisksAndPartitions']:
                            info_result = subprocess.run(
                                ["diskutil", "info", "-plist", disk['DeviceIdentifier']],
                                capture_output=True, text=True, timeout=5
                            )
                            
                            if info_result.returncode == 0 and info_result.stdout.strip():
                                disk_info = plistlib.load(BytesIO(info_result.stdout.encode('utf-8')))
                                
                                if disk_info.get('Removable', False) or disk_info.get('RemovableMedia', False):
                                    device_info = {
                                        'name': disk_info.get('MediaName', disk['DeviceIdentifier']),
                                        'number': -1,
                                        'size': f"{disk_info.get('TotalSize', 0) / (1024*1024*1024):.2f} GB",
                                        'filesystem': disk_info.get('FilesystemName', 'Unknown'),
                                        'drive_letter': disk_info.get('MountPoint', '')
                                    }
                                    devices.append(device_info)
                        
                        if devices:
                            return devices
                except ImportError:
                    pass
                except Exception as e:
                    pass
            
            try:
                result = subprocess.run(
                    ["diskutil", "list", "external"],
                    capture_output=True, text=True, timeout=5
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    lines = result.stdout.strip().split('\n')
                    devices = []
                    current_disk = None
                    
                    for line in lines:
                        if line.startswith("/dev/"):
                            parts = line.split()
                            current_disk = parts[0]
                            
                            info_result = subprocess.run(
                                ["diskutil", "info", current_disk],
                                capture_output=True, text=True, timeout=5
                            )
                            
                            if info_result.returncode == 0:
                                info_text = info_result.stdout
                                
                                device_name = current_disk
                                device_size = "Unknown"
                                filesystem = "Unknown"
                                mount_point = ""
                                
                                for info_line in info_text.split('\n'):
                                    if ':' in info_line:
                                        key, value = info_line.split(':', 1)
                                        key = key.strip()
                                        value = value.strip()
                                        
                                        if key == "Device / Media Name":
                                            device_name = value
                                        elif key == "Disk Size":
                                            device_size = value
                                        elif key == "File System":
                                            filesystem = value
                                        elif key == "Mount Point":
                                            mount_point = value
                                
                                devices.append({
                                    'name': device_name,
                                    'number': -1,
                                    'size': device_size,
                                    'filesystem': filesystem,
                                    'drive_letter': mount_point
                                })
                    
                    if devices:
                        return devices
            except Exception:
                pass
                
            try:
                if os.path.exists('/Volumes'):
                    volumes = [vol for vol in os.listdir('/Volumes') if vol != 'Macintosh HD']
                    
                    if volumes:
                        devices = []
                        for volume in volumes:
                            try:
                                stat_info = os.statvfs(f"/Volumes/{volume}")
                                size_bytes = stat_info.f_frsize * stat_info.f_blocks
                                size_gb = size_bytes / (1024*1024*1024)
                                
                                devices.append({
                                    'name': volume,
                                    'number': -1,
                                    'size': f"{size_gb:.2f} GB",
                                    'filesystem': 'Unknown',
                                    'drive_letter': f"/Volumes/{volume}"
                                })
                            except:
                                devices.append({
                                    'name': volume,
                                    'number': -1,
                                    'size': 'Unknown',
                                    'filesystem': 'Unknown',
                                    'drive_letter': f"/Volumes/{volume}"
                                })
                        
                        if devices:
                            return devices
            except Exception:
                pass
            
            return [{
                'name': 'No USB devices found or insufficient permissions',
                'number': -1,
                'size': '0 GB',
                'filesystem': 'Unknown',
                'drive_letter': '',
                'error': 'Check if USB devices are connected and mounted'
            }]
            
        except Exception as e:
            return [{
                'name': f'Error detecting USB devices: {str(e)}',
                'number': -1,
                'size': '0 GB',
                'filesystem': 'Unknown',
                'drive_letter': '',
                'error': str(e)
            }]
    
    def get_device_details(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific device.
        
        Args:
            device_id (str): The device identifier
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary with device details or None if not found
        """
        devices = self.get_devices()
        for device in devices:
            if str(device.get('number', '')) == device_id or device.get('name') == device_id:
                return device
        return None
