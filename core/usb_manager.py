"""
USB Manager module for SmartBoot

Handles detection and information retrieval for USB devices.
Supports Windows (WMI/PowerShell), Linux (lsblk/udev), and macOS (diskutil).
"""

import os
import platform
import subprocess
import json
import re
from typing import List, Dict, Any, Optional

from utils.logger import default_logger as logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_usb_device_linux(name: str, transport: Optional[str]) -> bool:
    """
    Determine whether a block device is a USB device on Linux.

    Checks the lsblk 'tran' field first, then falls back to sysfs to avoid
    hard-coding assumptions about device names (e.g. never skipping 'sda').

    Args:
        name: Kernel device name without /dev/ prefix (e.g. 'sda', 'sdb').
        transport: Value of the 'tran' field from lsblk, or None.

    Returns:
        True if the device is connected via USB.
    """
    if transport:
        return transport.lower() == "usb"

    # Fallback: walk sysfs link for the device and look for "usb" in the path.
    sys_block = f"/sys/block/{name}"
    try:
        real = os.path.realpath(sys_block)
        return "usb" in real.lower()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class USBManager:
    """Manages USB device detection and information retrieval."""

    def __init__(self) -> None:
        self.system = platform.system()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Return a list of available USB devices.

        Each entry is a dict with at least:
            name, number, size, filesystem, drive_letter
        On error an 'error' key is also included.
        """
        try:
            if self.system == "Windows":
                return self._get_windows_devices()
            elif self.system == "Linux":
                return self._get_linux_devices()
            elif self.system == "Darwin":
                return self._get_macos_devices()
            else:
                return [self._error_device(f"Unsupported OS: {self.system}")]
        except Exception as exc:
            logger.exception("USBManager: get_devices failed")
            return [self._error_device(str(exc))]

    def get_device_details(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Return details for a device identified by number or name."""
        for device in self.get_devices():
            if (str(device.get("number", "")) == device_id
                    or device.get("name") == device_id):
                return device
        return None

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def _get_windows_devices(self) -> List[Dict[str, Any]]:
        ps_script = (
            "Get-Disk | Where-Object { $_.BusType -eq 'USB' } | ForEach-Object {"
            "  $disk = $_;"
            "  $partition = Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue |"
            "               Select-Object -First 1;"
            "  $volume = if ($partition) {"
            "      Get-Volume -Partition $partition -ErrorAction SilentlyContinue"
            "  } else { $null };"
            "  [PSCustomObject]@{"
            "    Name       = $disk.FriendlyName;"
            "    Number     = $disk.Number;"
            "    Size       = ($disk.Size / 1GB).ToString('F2') + ' GB';"
            "    FileSystem = if ($volume) { $volume.FileSystemType } else { '' };"
            "    DriveLetter= if ($volume) { $volume.DriveLetter } else { '' }"
            "  }"
            "} | ConvertTo-Json -Depth 3"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=20
            )
            if not result.stdout.strip():
                return self._windows_wmic_fallback()

            raw = json.loads(result.stdout)
            if isinstance(raw, dict):
                raw = [raw]

            devices = [
                {
                    "name":         d.get("Name", "Unknown Device"),
                    "number":       d.get("Number", -1),
                    "size":         d.get("Size", "Unknown"),
                    "filesystem":   d.get("FileSystem", "Unknown"),
                    "drive_letter": d.get("DriveLetter", ""),
                }
                for d in raw
            ]
            if devices:
                return devices
            return self._windows_wmic_fallback()

        except Exception as exc:
            logger.warning(f"USBManager: PowerShell device query failed: {exc}")
            return self._windows_wmic_fallback()

    def _windows_wmic_fallback(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["wmic", "diskdrive", "where",
                 "MediaType='Removable Media'",
                 "get", "DeviceID,Model,Size"],
                capture_output=True, text=True, timeout=10
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) > 1:
                devices = []
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        size_str = "Unknown"
                        try:
                            size_str = f"{int(parts[-1]) // (1024**3)} GB"
                        except ValueError:
                            pass
                        devices.append({
                            "name":         " ".join(parts[1:-1]) or parts[0],
                            "number":       -1,
                            "size":         size_str,
                            "filesystem":   "Unknown",
                            "drive_letter": "",
                        })
                if devices:
                    return devices
        except Exception as exc:
            logger.warning(f"USBManager: WMIC fallback failed: {exc}")

        return [self._error_device(
            "No USB devices found or access denied. "
            "Try running as Administrator."
        )]

    # ------------------------------------------------------------------
    # Linux
    # ------------------------------------------------------------------

    def _get_linux_devices(self) -> List[Dict[str, Any]]:
        # --- Primary: lsblk JSON with transport field ---
        devices = self._lsblk_json()
        if devices:
            return devices

        # --- Secondary: lsblk plain text ---
        devices = self._lsblk_plain()
        if devices:
            return devices

        # --- Tertiary: /dev/disk/by-id ---
        devices = self._disk_by_id()
        if devices:
            return devices

        return [self._error_device(
            "No USB devices found or insufficient permissions. "
            "Try running with sudo or check connections."
        )]

    def _lsblk_json(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["lsblk", "-o",
                 "NAME,SIZE,FSTYPE,MOUNTPOINT,VENDOR,MODEL,TRAN,RM",
                 "-J", "-d"],
                capture_output=True, text=True, timeout=8
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            devices = []
            for dev in data.get("blockdevices", []):
                name = dev.get("name", "")
                transport = dev.get("tran")
                removable = str(dev.get("rm", "0")) in ("1", "true", "True")

                if name.startswith("loop"):
                    continue
                if not _is_usb_device_linux(name, transport) and not removable:
                    continue

                friendly = (
                    f"{dev.get('vendor', '')} {dev.get('model', '')}".strip()
                    or name
                )
                devices.append({
                    "name":         name,          # bare name; callers prepend /dev/
                    "number":       -1,
                    "size":         dev.get("size", "Unknown"),
                    "filesystem":   dev.get("fstype") or "Unknown",
                    "drive_letter": dev.get("mountpoint") or "",
                    "friendly":     friendly,
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: lsblk JSON failed: {exc}")
            return []

    def _lsblk_plain(self) -> List[Dict[str, Any]]:
        """Fallback plain-text lsblk using sysfs to identify USB devices."""
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,RM"],
                capture_output=True, text=True, timeout=8
            )
            if result.returncode != 0:
                return []

            devices = []
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if not parts:
                    continue
                name = parts[0]
                if name.startswith("loop"):
                    continue
                removable = len(parts) >= 5 and parts[4] in ("1",)
                if not _is_usb_device_linux(name, None) and not removable:
                    continue
                devices.append({
                    "name":         name,
                    "number":       -1,
                    "size":         parts[1] if len(parts) > 1 else "Unknown",
                    "filesystem":   parts[2] if len(parts) > 2 else "Unknown",
                    "drive_letter": parts[3] if len(parts) > 3 else "",
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: lsblk plain failed: {exc}")
            return []

    def _disk_by_id(self) -> List[Dict[str, Any]]:
        """Last resort: enumerate /dev/disk/by-id for usb- entries."""
        try:
            by_id = "/dev/disk/by-id"
            if not os.path.exists(by_id):
                return []
            devices = []
            seen: set = set()
            for entry in os.listdir(by_id):
                if not entry.startswith("usb-") or "part" in entry:
                    continue
                link = os.path.realpath(os.path.join(by_id, entry))
                base = os.path.basename(link)
                if base in seen:
                    continue
                seen.add(base)
                friendly = re.sub(r"^usb-", "", entry).replace("_", " ")
                devices.append({
                    "name":         base,
                    "number":       -1,
                    "size":         "Unknown",
                    "filesystem":   "Unknown",
                    "drive_letter": "",
                    "friendly":     friendly,
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: disk-by-id fallback failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # macOS
    # ------------------------------------------------------------------

    def _get_macos_devices(self) -> List[Dict[str, Any]]:
        devices = self._diskutil_plist()
        if devices:
            return devices

        devices = self._diskutil_plain()
        if devices:
            return devices

        devices = self._volumes_fallback()
        if devices:
            return devices

        return [self._error_device(
            "No USB devices found. Check connections and permissions."
        )]

    def _diskutil_plist(self) -> List[Dict[str, Any]]:
        try:
            import plistlib
            result = subprocess.run(
                ["diskutil", "list", "external", "-plist"],
                capture_output=True, timeout=8
            )
            if result.returncode != 0 or not result.stdout:
                return []
            pdata = plistlib.loads(result.stdout)
            devices = []
            for disk in pdata.get("AllDisksAndPartitions", []):
                dev_id = disk.get("DeviceIdentifier", "")
                info_result = subprocess.run(
                    ["diskutil", "info", "-plist", dev_id],
                    capture_output=True, timeout=8
                )
                if info_result.returncode != 0 or not info_result.stdout:
                    continue
                info = plistlib.loads(info_result.stdout)
                if not (info.get("Removable") or info.get("RemovableMedia")):
                    continue
                total = info.get("TotalSize", 0)
                devices.append({
                    "name":         dev_id,
                    "number":       -1,
                    "size":         f"{total / (1024**3):.2f} GB",
                    "filesystem":   info.get("FilesystemName", "Unknown"),
                    "drive_letter": info.get("MountPoint", ""),
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: diskutil plist failed: {exc}")
            return []

    def _diskutil_plain(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["diskutil", "list", "external"],
                capture_output=True, text=True, timeout=8
            )
            if result.returncode != 0:
                return []
            devices = []
            for line in result.stdout.splitlines():
                if not line.startswith("/dev/"):
                    continue
                dev = line.split()[0]
                info = subprocess.run(
                    ["diskutil", "info", dev],
                    capture_output=True, text=True, timeout=8
                )
                if info.returncode != 0:
                    continue
                d: Dict[str, Any] = {
                    "name": dev.replace("/dev/", ""),
                    "number": -1,
                    "size": "Unknown",
                    "filesystem": "Unknown",
                    "drive_letter": "",
                }
                for iline in info.stdout.splitlines():
                    if ":" not in iline:
                        continue
                    k, _, v = iline.partition(":")
                    k, v = k.strip(), v.strip()
                    if k == "Device / Media Name":
                        d["name"] = v or d["name"]
                    elif k == "Disk Size":
                        d["size"] = v
                    elif k in ("File System", "Type (Bundle)"):
                        d["filesystem"] = v
                    elif k == "Mount Point":
                        d["drive_letter"] = v
                devices.append(d)
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: diskutil plain failed: {exc}")
            return []

    def _volumes_fallback(self) -> List[Dict[str, Any]]:
        try:
            volumes_dir = "/Volumes"
            if not os.path.exists(volumes_dir):
                return []
            devices = []
            for vol in os.listdir(volumes_dir):
                if vol in ("Macintosh HD", "Macintosh HD - Data"):
                    continue
                path = os.path.join(volumes_dir, vol)
                try:
                    st = os.statvfs(path)
                    size_gb = (st.f_frsize * st.f_blocks) / (1024**3)
                    size_str = f"{size_gb:.2f} GB"
                except OSError:
                    size_str = "Unknown"
                devices.append({
                    "name":         vol,
                    "number":       -1,
                    "size":         size_str,
                    "filesystem":   "Unknown",
                    "drive_letter": path,
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: Volumes fallback failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error_device(msg: str) -> Dict[str, Any]:
        return {
            "name":         msg,
            "number":       -1,
            "size":         "0 GB",
            "filesystem":   "Unknown",
            "drive_letter": "",
            "error":        msg,
        }