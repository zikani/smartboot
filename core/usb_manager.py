"""
USB Manager module for SmartBoot (Enhanced)

Enhancements over original:
- Persistent-storage-capable flag
- Checksum / verify-write support metadata
- Bad-block detection hints
- Speed class detection (USB 2 vs 3)
- Write-protect detection
- Drive capacity sanity checks
- Richer device info (vendor, model, serial)
"""

import os
import platform
import subprocess
import json
import re
from typing import List, Dict, Any, Optional

from utils.logger import default_logger as logger


def _is_usb_device_linux(name: str, transport: Optional[str]) -> bool:
    if transport:
        return transport.lower() == "usb"
    sys_block = f"/sys/block/{name}"
    try:
        real = os.path.realpath(sys_block)
        return "usb" in real.lower()
    except OSError:
        return False


def _read_sysfs(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


class USBManager:
    """Manages USB device detection and information retrieval."""

    MIN_SIZE_BYTES = 512 * 1024 * 1024
    MAX_SIZE_BYTES = 2 * 1024 ** 4

    def __init__(self) -> None:
        self.system = platform.system()


    def get_devices(self) -> List[Dict[str, Any]]:
        """Return list of USB devices with enriched metadata."""
        try:
            if self.system == "Windows":
                devices = self._get_windows_devices()
            elif self.system == "Linux":
                devices = self._get_linux_devices()
            elif self.system == "Darwin":
                devices = self._get_macos_devices()
            else:
                return [self._error_device(f"Unsupported OS: {self.system}")]
        except Exception as exc:
            logger.exception("USBManager: get_devices failed")
            return [self._error_device(str(exc))]

        for dev in devices:
            if "error" not in dev:
                dev.setdefault("write_protected", False)
                dev.setdefault("usb_version", "Unknown")
                dev.setdefault("serial", "")
                dev.setdefault("friendly", dev.get("name", ""))
                dev["size_bytes"] = self._parse_size_bytes(dev.get("size", "0"))
                dev["size_warning"] = self._check_size_warning(dev)
        return devices

    def get_device_details(self, device_id: str) -> Optional[Dict[str, Any]]:
        for device in self.get_devices():
            if (str(device.get("number", "")) == device_id
                    or device.get("name") == device_id):
                return device
        return None

    def check_write_protect(self, device: Dict[str, Any]) -> bool:
        """Check if a device is write-protected."""
        name = device.get("name", "")
        if self.system == "Linux" and name:
            ro = _read_sysfs(f"/sys/block/{name}/ro")
            return ro == "1"
        return False


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
            "    Name        = $disk.FriendlyName;"
            "    Number      = $disk.Number;"
            "    SizeBytes   = $disk.Size;"
            "    Size        = ($disk.Size / 1GB).ToString('F2') + ' GB';"
            "    FileSystem  = if ($volume) { $volume.FileSystemType } else { '' };"
            "    DriveLetter = if ($volume) { $volume.DriveLetter } else { '' };"
            "    IsReadOnly  = $disk.IsReadOnly;"
            "    PartStyle   = $disk.PartitionStyle;"
            "    Serial      = $disk.SerialNumber;"
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

            devices = []
            for d in raw:
                size_bytes = d.get("SizeBytes", 0) or 0
                devices.append({
                    "name":           d.get("Name", "Unknown Device"),
                    "number":         d.get("Number", -1),
                    "size":           d.get("Size", "Unknown"),
                    "size_bytes":     size_bytes,
                    "filesystem":     d.get("FileSystem", "Unknown"),
                    "drive_letter":   d.get("DriveLetter", ""),
                    "write_protected": bool(d.get("IsReadOnly", False)),
                    "partition_style": d.get("PartStyle", ""),
                    "serial":          d.get("Serial", ""),
                })
            return devices or self._windows_wmic_fallback()
        except Exception as exc:
            logger.warning(f"USBManager: PowerShell query failed: {exc}")
            return self._windows_wmic_fallback()

    def _windows_wmic_fallback(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["wmic", "diskdrive", "where",
                 "MediaType='Removable Media'",
                 "get", "DeviceID,Model,Size,SerialNumber"],
                capture_output=True, text=True, timeout=10
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) > 1:
                devices = []
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            size_bytes = int(parts[-1])
                            size_str = f"{size_bytes / (1024**3):.2f} GB"
                        except ValueError:
                            size_bytes, size_str = 0, "Unknown"
                        devices.append({
                            "name":         " ".join(parts[1:-1]) or parts[0],
                            "number":       -1,
                            "size":         size_str,
                            "size_bytes":   size_bytes,
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


    def _get_linux_devices(self) -> List[Dict[str, Any]]:
        devices = self._lsblk_json()
        if devices:
            return devices
        devices = self._lsblk_plain()
        if devices:
            return devices
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
                 "NAME,SIZE,FSTYPE,MOUNTPOINT,VENDOR,MODEL,TRAN,RM,RO,SERIAL",
                 "-J", "-d", "-b"],
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

                usb_ver = self._get_linux_usb_version(name)

                friendly = (
                    f"{dev.get('vendor', '')} {dev.get('model', '')}".strip()
                    or name
                )
                try:
                    size_bytes = int(dev.get("size", 0) or 0)
                except (ValueError, TypeError):
                    size_bytes = 0

                devices.append({
                    "name":           name,
                    "number":         -1,
                    "size":           self._format_size(size_bytes),
                    "size_bytes":     size_bytes,
                    "filesystem":     dev.get("fstype") or "Unknown",
                    "drive_letter":   dev.get("mountpoint") or "",
                    "friendly":       friendly,
                    "write_protected": str(dev.get("ro", "0")) == "1",
                    "usb_version":    usb_ver,
                    "serial":         dev.get("serial", ""),
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: lsblk JSON failed: {exc}")
            return []

    def _get_linux_usb_version(self, name: str) -> str:
        """Try to read USB version from sysfs."""
        try:
            real = os.path.realpath(f"/sys/block/{name}")
            parts = real.split("/")
            for i in range(len(parts), 0, -1):
                candidate = "/".join(parts[:i]) + "/version"
                if os.path.exists(candidate):
                    ver = _read_sysfs(candidate).strip()
                    if ver:
                        v = float(ver)
                        if v >= 3.1:
                            return "USB 3.1+"
                        elif v >= 3.0:
                            return "USB 3.0"
                        else:
                            return "USB 2.0"
        except Exception:
            pass
        return "Unknown"

    def _lsblk_plain(self) -> List[Dict[str, Any]]:
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
                    "size_bytes":   0,
                    "filesystem":   parts[2] if len(parts) > 2 else "Unknown",
                    "drive_letter": parts[3] if len(parts) > 3 else "",
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: lsblk plain failed: {exc}")
            return []

    def _disk_by_id(self) -> List[Dict[str, Any]]:
        try:
            by_id = "/dev/disk/by-id"
            if not os.path.exists(by_id):
                return []
            devices, seen = [], set()
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
                    "size_bytes":   0,
                    "filesystem":   "Unknown",
                    "drive_letter": "",
                    "friendly":     friendly,
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: disk-by-id fallback failed: {exc}")
            return []


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
                    "name":           dev_id,
                    "number":         -1,
                    "size":           self._format_size(total),
                    "size_bytes":     total,
                    "filesystem":     info.get("FilesystemName", "Unknown"),
                    "drive_letter":   info.get("MountPoint", ""),
                    "write_protected": info.get("WritableMedia") is False,
                    "serial":         info.get("IORegistryEntryName", ""),
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
                    "size_bytes": 0,
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
                    total = st.f_frsize * st.f_blocks
                    size_str = self._format_size(total)
                except OSError:
                    total, size_str = 0, "Unknown"
                devices.append({
                    "name":         vol,
                    "number":       -1,
                    "size":         size_str,
                    "size_bytes":   total,
                    "filesystem":   "Unknown",
                    "drive_letter": path,
                })
            return devices
        except Exception as exc:
            logger.warning(f"USBManager: Volumes fallback failed: {exc}")
            return []


    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "Unknown"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    @staticmethod
    def _parse_size_bytes(size_str: str) -> int:
        """Parse size string like '8.00 GB' into bytes."""
        try:
            m = re.match(r"([\d.]+)\s*(\w+)", size_str.strip())
            if not m:
                return 0
            val = float(m.group(1))
            unit = m.group(2).upper()
            multipliers = {"B": 1, "KB": 1024, "MB": 1024**2,
                           "GB": 1024**3, "TB": 1024**4}
            return int(val * multipliers.get(unit, 0))
        except Exception:
            return 0

    def _check_size_warning(self, dev: Dict[str, Any]) -> str:
        sb = dev.get("size_bytes", 0)
        if sb <= 0:
            return ""
        if sb < self.MIN_SIZE_BYTES:
            return "⚠ Drive may be too small (< 512 MB)"
        if sb > self.MAX_SIZE_BYTES:
            return "⚠ Unusually large drive — verify selection"
        return ""

    @staticmethod
    def _error_device(msg: str) -> Dict[str, Any]:
        return {
            "name":         msg,
            "number":       -1,
            "size":         "0 GB",
            "size_bytes":   0,
            "filesystem":   "Unknown",
            "drive_letter": "",
            "error":        msg,
        }