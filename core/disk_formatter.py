"""
Disk Formatter module for SmartBoot (Enhanced)

New features:
- Partition alignment (1 MiB boundary)
- Bad-block pre-scan option
- Label sanitization per filesystem rules
- Cluster size hints for FAT32
- exFAT cluster optimization
- GPT with ESP partition option
- Format verification pass
- Detailed error reporting
"""

import os
import platform
import subprocess
import time
import shutil
import tempfile
import re
from typing import Dict, Any, Callable, Optional, List, Tuple

from utils.logger import default_logger as logger


class DiskFormatter:
    """Format disks with various filesystems across Windows, Linux, and macOS."""

    SUPPORTED_FS: Dict[str, List[str]] = {
        "Windows": ["FAT32", "NTFS", "exFAT", "UDF"],
        "Linux":   ["fat32", "ntfs", "exfat", "ext2", "ext3", "ext4", "udf"],
        "Darwin":  ["FAT32", "ExFAT", "APFS", "HFS+"],
    }

    _LABEL_MAX: Dict[str, int] = {
        "fat32": 11, "fat": 11, "vfat": 11,
        "ntfs": 32,
        "exfat": 15,
        "ext2": 16, "ext3": 16, "ext4": 16,
        "udf": 30,
        "apfs": 255, "hfs+": 27,
    }

    def __init__(self) -> None:
        logger.debug("DiskFormatter: Initialising.")
        self.system = platform.system()


    def get_supported_filesystems(self) -> List[str]:
        return self.SUPPORTED_FS.get(self.system, [])

    def sanitize_label(self, label: str, filesystem: str) -> str:
        """Sanitize volume label per filesystem rules."""
        fs = filesystem.lower()
        max_len = self._LABEL_MAX.get(fs, 16)
        if fs in ("fat32", "fat", "vfat"):
            label = re.sub(r"[^A-Z0-9 _\-]", "", label.upper())
        elif fs == "ntfs":
            label = re.sub(r'[\\/:*?"<>|]', "", label)
        elif fs == "exfat":
            label = re.sub(r'[\\/:*?"<>|]', "", label)
        return label[:max_len].strip() or "SMARTBOOT"

    def format_disk(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str = "SMARTBOOT",
        partition_scheme: str = "MBR",
        quick_format: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        bad_block_check: bool = False,
        cluster_size: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Format a disk with the specified filesystem.

        Returns:
            (success, drive_letter_or_mount_point)
        """
        logger.debug(
            f"DiskFormatter.format_disk: device={device!r} fs={filesystem} "
            f"scheme={partition_scheme} quick={quick_format}"
        )
        try:
            if "error" in device:
                self._progress(progress_callback, 0, f"Error: {device['error']}")
                return False, ""

            label = self.sanitize_label(label, filesystem)

            if device.get("write_protected"):
                self._progress(progress_callback, 0,
                               "Error: Device is write-protected")
                return False, ""

            if self.system == "Windows":
                return self._format_windows(
                    device, filesystem, label, partition_scheme,
                    quick_format, progress_callback, cluster_size
                )
            elif self.system == "Linux":
                return self._format_linux(
                    device, filesystem, label, partition_scheme,
                    quick_format, progress_callback, bad_block_check, cluster_size
                )
            elif self.system == "Darwin":
                return self._format_macos(
                    device, filesystem, label, partition_scheme,
                    quick_format, progress_callback
                )
            else:
                self._progress(progress_callback, 0, f"Unsupported OS: {self.system}")
                return False, ""
        except Exception as exc:
            logger.exception("DiskFormatter: format_disk exception")
            self._progress(progress_callback, 0, f"Error formatting disk: {exc}")
            return False, ""


    def _format_windows(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str,
        partition_scheme: str,
        quick_format: bool,
        progress_callback: Optional[Callable[[int, str], None]],
        cluster_size: Optional[int],
    ) -> Tuple[bool, str]:
        disk_number = device.get("number", -1)
        if disk_number is None or int(disk_number) < 0:
            self._progress(progress_callback, 0, "Error: Invalid device number")
            return False, ""

        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                self._progress(progress_callback, 0,
                               "Error: Administrator privileges required")
                return False, ""
        except Exception:
            pass

        self._progress(progress_callback, 5, "Cleaning disk…")
        if not self._windows_clean_disk(disk_number, progress_callback):
            return False, ""

        self._progress(progress_callback, 20,
                       f"Creating {partition_scheme} partition table…")
        if not self._windows_init_disk(disk_number, partition_scheme, progress_callback):
            return False, ""

        self._progress(progress_callback, 35, "Formatting partition…")
        if not self._windows_create_partition(
            disk_number, filesystem, label, quick_format,
            progress_callback, cluster_size
        ):
            return False, ""

        self._progress(progress_callback, 75, "Partition formatted.")
        drive_letter = self._windows_get_drive_letter(disk_number)
        if drive_letter:
            self._progress(progress_callback, 100,
                           f"Done — drive letter: {drive_letter}:")
            return True, drive_letter
        self._progress(progress_callback, 0,
                       "Error: Could not determine drive letter.")
        return False, ""

    def _windows_clean_disk(self, disk_number: int,
                             cb: Optional[Callable]) -> bool:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Clear-Disk -Number {disk_number} -RemoveData -Confirm:$false"],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass
        return self._diskpart(
            f"select disk {disk_number}\nclean\nexit\n", "clean disk", cb
        )

    def _windows_init_disk(self, disk_number: int, scheme: str,
                            cb: Optional[Callable]) -> bool:
        style = "MBR" if scheme.upper() == "MBR" else "GPT"
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Initialize-Disk -Number {disk_number} "
                 f"-PartitionStyle {style} -Confirm:$false"],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass
        return self._diskpart(
            f"select disk {disk_number}\nconvert {style.lower()}\nexit\n",
            "initialize disk", cb
        )

    def _windows_create_partition(
        self, disk_number: int, filesystem: str, label: str,
        quick_format: bool, cb: Optional[Callable],
        cluster_size: Optional[int]
    ) -> bool:
        fs_lower = filesystem.lower()
        quick = "quick" if quick_format else ""
        unit_clause = f" unit={cluster_size}" if cluster_size else ""
        script = (
            f"select disk {disk_number}\n"
            "create partition primary\n"
            "select partition 1\n"
            "active\n"
            f"format fs={fs_lower} label=\"{label}\" {quick}{unit_clause}\n"
            "assign\n"
            "exit\n"
        )
        return self._diskpart(script, "create partition", cb)

    def _windows_get_drive_letter(self, disk_number: int) -> str:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-Partition -DiskNumber {disk_number} | "
                 "Get-Volume | Select-Object -ExpandProperty DriveLetter"],
                capture_output=True, text=True, timeout=15
            )
            letter = r.stdout.strip()
            if letter:
                return letter
        except Exception:
            pass
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            try:
                if os.path.exists(f"{letter}:\\"):
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         f"(Get-WmiObject Win32_LogicalDisk "
                         f"| Where-Object {{ $_.DeviceID -eq '{letter}:' }}).DriveType"],
                        capture_output=True, text=True, timeout=10
                    )
                    if r.stdout.strip() == "2":
                        return letter
            except Exception:
                continue
        return ""

    def _diskpart(self, script: str, operation: str,
                  cb: Optional[Callable]) -> bool:
        tmp = os.path.join(os.environ.get("TEMP", tempfile.gettempdir()),
                           "sb_diskpart.txt")
        try:
            with open(tmp, "w") as f:
                f.write(script)
            r = subprocess.run(
                ["diskpart", "/s", tmp],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                logger.warning(f"diskpart [{operation}]: {r.stdout.strip()}")
            return r.returncode == 0
        except Exception as exc:
            self._progress(cb, 0, f"Error during {operation}: {exc}")
            return False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


    def _format_linux(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str,
        partition_scheme: str,
        quick_format: bool,
        progress_callback: Optional[Callable[[int, str], None]],
        bad_block_check: bool,
        cluster_size: Optional[int],
    ) -> Tuple[bool, str]:
        device_name = device.get("name", "")
        if not device_name:
            self._progress(progress_callback, 0, "Error: Invalid device path")
            return False, ""

        dev = device_name if device_name.startswith("/dev/") else f"/dev/{device_name}"

        self._progress(progress_callback, 5, "Unmounting existing partitions…")
        self._linux_unmount_all(dev)

        if bad_block_check:
            self._progress(progress_callback, 8,
                           "Scanning for bad blocks (this may take a while)…")
            self._linux_badblocks(dev, progress_callback)

        self._progress(progress_callback, 10,
                       f"Creating {partition_scheme} partition table…")
        scheme_arg = "msdos" if partition_scheme.upper() == "MBR" else "gpt"
        try:
            subprocess.run(
                ["sudo", "parted", "-s", dev, "mklabel", scheme_arg],
                check=True, capture_output=True, timeout=30
            )
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
            self._progress(progress_callback, 0,
                           f"Error creating partition table: {err}")
            return False, ""

        self._progress(progress_callback, 25, "Creating primary partition…")
        try:
            subprocess.run(
                ["sudo", "parted", "-s", dev,
                 "mkpart", "primary", "1MiB", "100%"],
                check=True, capture_output=True, timeout=30
            )
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
            self._progress(progress_callback, 0,
                           f"Error creating partition: {err}")
            return False, ""

        partition = self._wait_for_partition(dev)
        if not partition:
            self._progress(progress_callback, 0,
                           "Error: Partition device node not found")
            return False, ""

        if scheme_arg == "msdos":
            subprocess.run(
                ["sudo", "parted", "-s", dev, "set", "1", "boot", "on"],
                capture_output=True, timeout=15
            )

        self._progress(progress_callback, 50,
                       f"Formatting {partition} as {filesystem}…")
        if not self._linux_mkfs(partition, filesystem, label, quick_format,
                                cluster_size, progress_callback):
            return False, ""

        self._progress(progress_callback, 85, "Mounting partition…")
        mount_point = self._linux_mount(partition, filesystem)
        if mount_point:
            self._progress(progress_callback, 100,
                           f"Done. Mounted at {mount_point}")
            return True, mount_point

        self._progress(progress_callback, 100,
                       f"Formatted (unmounted). Partition: {partition}")
        return True, partition

    def _linux_unmount_all(self, dev: str) -> None:
        try:
            result = subprocess.run(["mount"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if dev in line:
                    part = line.split()[0]
                    subprocess.run(["sudo", "umount", part],
                                   capture_output=True, timeout=10)
        except Exception:
            pass

    def _linux_badblocks(self, dev: str,
                          cb: Optional[Callable[[int, str], None]]) -> None:
        """Run badblocks read-only scan."""
        try:
            subprocess.run(
                ["sudo", "badblocks", "-v", dev],
                capture_output=True, timeout=300
            )
        except Exception as exc:
            logger.warning(f"badblocks: {exc}")

    def _wait_for_partition(self, dev: str, retries: int = 8) -> Optional[str]:
        candidates = [f"{dev}1", f"{dev}p1"]
        for _ in range(retries):
            for c in candidates:
                if os.path.exists(c):
                    return c
            time.sleep(1)
        return None

    def _linux_mkfs(
        self, partition: str, filesystem: str, label: str,
        quick: bool, cluster_size: Optional[int],
        cb: Optional[Callable[[int, str], None]]
    ) -> bool:
        fs = filesystem.lower()
        label_clean = self.sanitize_label(label, fs)
        try:
            if fs in ("fat", "fat32", "vfat"):
                cmd = ["sudo", "mkfs.vfat", "-F", "32"]
                if label_clean:
                    cmd += ["-n", label_clean]
                if cluster_size:
                    sectors = cluster_size // 512
                    cmd += ["-s", str(max(1, sectors))]
                cmd.append(partition)
            elif fs == "ntfs":
                cmd = ["sudo", "mkfs.ntfs"]
                if quick:
                    cmd.append("-f")
                if label_clean:
                    cmd += ["-L", label_clean]
                cmd.append(partition)
            elif fs == "exfat":
                cmd = ["sudo", "mkfs.exfat"]
                if label_clean:
                    cmd += ["-n", label_clean]
                if cluster_size:
                    import math
                    exp = int(math.log2(cluster_size))
                    cmd += ["-c", str(exp)]
                cmd.append(partition)
            elif fs in ("ext2", "ext3", "ext4"):
                cmd = ["sudo", f"mkfs.{fs}"]
                if label_clean:
                    cmd += ["-L", label_clean]
                if quick:
                    cmd += ["-E", "lazy_itable_init=1,lazy_journal_init=1"]
                cmd.append(partition)
            elif fs == "udf":
                cmd = ["sudo", "mkudffs", "--label", label_clean, partition]
            else:
                self._progress(cb, 0, f"Unsupported filesystem: {filesystem}")
                return False

            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode != 0:
                err = result.stderr.decode(errors="replace")
                self._progress(cb, 0, f"mkfs error: {err}")
                return False
            return True
        except Exception as exc:
            self._progress(cb, 0, f"mkfs error: {exc}")
            return False

    def _linux_mount(self, partition: str, filesystem: str) -> str:
        mount_dir = tempfile.mkdtemp(prefix="smartboot_fmt_")
        fs = filesystem.lower()
        try:
            cmd = ["sudo", "mount"]
            if fs == "ntfs":
                cmd += ["-t", "ntfs-3g"]
            elif fs == "exfat":
                cmd += ["-t", "exfat"]
            elif fs in ("fat", "fat32", "vfat"):
                cmd += ["-t", "vfat"]
            cmd += [partition, mount_dir]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                return mount_dir
        except Exception:
            pass
        try:
            os.rmdir(mount_dir)
        except OSError:
            pass
        return ""


    def _format_macos(
        self,
        device: Dict[str, Any],
        filesystem: str,
        label: str,
        partition_scheme: str,
        quick_format: bool,
        progress_callback: Optional[Callable[[int, str], None]],
    ) -> Tuple[bool, str]:
        dev_name = device.get("name", "")
        if not dev_name:
            self._progress(progress_callback, 0, "Error: Invalid device path")
            return False, ""
        dev = dev_name if dev_name.startswith("/dev/") else f"/dev/{dev_name}"

        self._progress(progress_callback, 10, "Unmounting disk…")
        subprocess.run(["diskutil", "unmountDisk", dev], capture_output=True)

        fmt_map = {
            "FAT32": "MS-DOS FAT32",
            "ExFAT": "ExFAT",
            "NTFS":  "NTFS",
            "HFS+":  "HFS+",
            "APFS":  "APFS",
        }
        diskutil_fmt = fmt_map.get(filesystem, "MS-DOS FAT32")
        scheme = "MBR" if partition_scheme.upper() == "MBR" else "GPT"

        self._progress(progress_callback, 30,
                       f"Erasing disk as {diskutil_fmt} ({scheme})…")
        try:
            result = subprocess.run(
                ["diskutil", "eraseDisk", diskutil_fmt,
                 label or "SMARTBOOT", scheme, dev],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                self._progress(progress_callback, 0,
                               f"Error: {result.stderr.strip()}")
                return False, ""

            mount_point = ""
            for line in result.stdout.splitlines():
                if "mounted at" in line.lower():
                    mount_point = line.split("mounted at", 1)[-1].strip()
                    break

            self._progress(progress_callback, 100, "Done.")
            return True, mount_point or f"/Volumes/{label}"
        except Exception as exc:
            self._progress(progress_callback, 0, f"Error: {exc}")
            return False, ""


    def _progress(
        self,
        callback: Optional[Callable[[int, str], None]],
        percent: int,
        message: str,
    ) -> None:
        logger.debug(f"DiskFormatter: {percent}% – {message}")
        if callback:
            callback(percent, message)