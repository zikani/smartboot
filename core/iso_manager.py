"""
ISO Manager module for SmartBoot

Handles ISO file operations, type detection, and validation.
"""

import os
import subprocess
import platform
import json
from typing import Dict, Any, Optional, List

from utils.logger import default_logger as logger


class ISOManager:
    """Manages ISO files: information retrieval and validation."""

    _FILENAME_RULES = [
        (["windows", "win10", "win11", "win7", "win8",
          "microsoft", "server", "enterprise", "professional"], "Windows"),
        (["ubuntu", "debian", "fedora", "centos", "rhel", "red-hat",
          "suse", "opensuse", "arch", "manjaro", "gentoo", "mint",
          "kali", "parrot", "zorin", "elementary", "slackware",
          "puppy", "tails", "knoppix", "bodhi", "deepin", "linux"], "Linux"),
        (["macos", "osx", "mac_os", "apple", "hackintosh",
          "catalina", "mojave", "sierra", "monterey", "ventura",
          "sonoma"], "macOS"),
        (["freedos", "msdos", "ms-dos", "dos"], "FreeDOS"),
    ]

    _CONTENT_SIGNATURES: Dict[str, list] = {
        "Windows": [
            ("sources", "install.wim"),
            ("sources", "install.esd"),
        ],
        "Linux": [
            ("casper",),
            ("isolinux",),
            ("live",),
            ("boot", "grub"),
        ],
        "macOS": [
            ("System", "Library"),
            (".disk",),
        ],
        "FreeDOS": [
            ("kernel.sys",),
            ("command.com",),
            ("fdos",),
        ],
    }

    def __init__(self) -> None:
        logger.debug("ISOManager: Initialising.")
        self.system = platform.system()
        self._history_file = self._get_history_file_path()

    def _get_history_file_path(self) -> str:
        """Get the path to the ISO history JSON file."""
        if self.system == "Windows":
            base_dir = os.environ.get("APPDATA", "")
            return os.path.join(base_dir, "SmartBoot", "iso_history.json")
        elif self.system == "Darwin":
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "SmartBoot", "iso_history.json")
        else:
            return os.path.join(os.path.expanduser("~"), ".smartboot", "iso_history.json")


    def get_iso_info(self, iso_path: str) -> Dict[str, Any]:
        """
        Return metadata about an ISO file.

        Raises:
            FileNotFoundError: if the path does not exist.
            ValueError: if the path is not a regular file.
        """
        if not os.path.exists(iso_path):
            raise FileNotFoundError(f"ISO file not found: {iso_path}")
        if not os.path.isfile(iso_path):
            raise ValueError(f"Path is not a file: {iso_path}")

        size_bytes = os.path.getsize(iso_path)
        size_mb = size_bytes / (1024 * 1024)
        size_str = (
            f"{size_mb / 1024:.2f} GB" if size_mb >= 1024
            else f"{size_mb:.2f} MB"
        )
        iso_type = self._determine_iso_type(iso_path)

        return {
            "path":       iso_path,
            "filename":   os.path.basename(iso_path),
            "size_bytes": size_bytes,
            "size":       size_str,
            "type":       iso_type,
        }

    def validate_iso(self, iso_path: str) -> bool:
        """
        Return True if the file is a plausible bootable ISO.

        Checks:
        - Has .iso extension
        - File exists and is non-empty
        - At least 10 MB (too small to be bootable)
        - ISO 9660 magic bytes or content-based validation
        """
        logger.debug(f"ISOManager: validate_iso({iso_path})")
        try:
            if not iso_path.lower().endswith(".iso"):
                logger.warning("ISOManager: not an .iso extension")
                return False
            if not os.path.exists(iso_path):
                logger.warning("ISOManager: file not found")
                return False
            size = os.path.getsize(iso_path)
            if size < 10 * 1024 * 1024:
                logger.warning("ISOManager: file too small")
                return False

            if self._check_iso9660_magic(iso_path):
                return True

            if self.system in ("Linux", "Darwin"):
                result = subprocess.run(
                    ["file", "-b", iso_path],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.lower()
                if any(k in output for k in ("iso 9660", "iso image", "bootable")):
                    return True

            elif self.system == "Windows":
                return self._validate_windows_mount(iso_path)

            return size > 100 * 1024 * 1024

        except Exception as exc:
            logger.error(f"ISOManager: validate_iso error: {exc}")
            return False

    def get_history(self) -> List[Dict[str, Any]]:
        """Return the list of recently used ISO files."""
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, 'r') as f:
                    return json.load(f)
        except Exception as exc:
            logger.warning(f"ISOManager: failed to load history: {exc}")
        return []

    def clear_history(self) -> None:
        """Clear the ISO history."""
        try:
            if os.path.exists(self._history_file):
                os.remove(self._history_file)
            logger.debug("ISOManager: history cleared")
        except Exception as exc:
            logger.warning(f"ISOManager: failed to clear history: {exc}")

    def add_to_history(self, iso_path: str) -> None:
        """Add an ISO to the recent history."""
        if not os.path.exists(iso_path):
            return

        try:
            history = self.get_history()
            
            history = [h for h in history if h.get("path") != iso_path]
            
            entry = {
                "path": iso_path,
                "filename": os.path.basename(iso_path),
                "timestamp": int(os.path.getmtime(iso_path))
            }
            history.insert(0, entry)
            
            history = history[:20]
            
            os.makedirs(os.path.dirname(self._history_file), exist_ok=True)
            
            with open(self._history_file, 'w') as f:
                json.dump(history, f, indent=2)
            
            logger.debug(f"ISOManager: added to history: {iso_path}")
        except Exception as exc:
            logger.warning(f"ISOManager: failed to add to history: {exc}")


    def _determine_iso_type(self, iso_path: str) -> str:
        """Best-effort ISO type detection."""
        filename = os.path.basename(iso_path).lower()

        for keywords, label in self._FILENAME_RULES:
            if any(kw in filename for kw in keywords):
                logger.debug(f"ISOManager: type={label} (filename)")
                return label

        detected = self._detect_by_content(iso_path)
        if detected:
            logger.debug(f"ISOManager: type={detected} (content)")
            return detected

        size_gb = os.path.getsize(iso_path) / (1024 ** 3)
        if size_gb > 8.0:
            return "Windows (likely)"
        if size_gb > 4.5:
            return "Unknown (large ISO)"
        return "Unknown (small ISO)"

    def _detect_by_content(self, iso_path: str) -> Optional[str]:
        """Mount the ISO (platform-specific) and inspect contents."""
        if self.system == "Windows":
            return self._detect_windows_content(iso_path)
        elif self.system in ("Linux", "Darwin"):
            return self._detect_unix_content(iso_path)
        return None

    def _detect_windows_content(self, iso_path: str) -> Optional[str]:
        script = (
            f"$m = Mount-DiskImage -ImagePath '{iso_path}' -PassThru;"
            "$dl = ($m | Get-Volume).DriveLetter; $dl"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=15
            )
            drive = result.stdout.strip()
            if not drive:
                return None
            root = drive + ":\\"
            try:
                return self._check_content_signatures(root)
            finally:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Dismount-DiskImage -ImagePath '{iso_path}'"],
                    capture_output=True, timeout=8
                )
        except Exception as exc:
            logger.debug(f"ISOManager: Windows content detection failed: {exc}")
            return None

    def _detect_unix_content(self, iso_path: str) -> Optional[str]:
        import tempfile
        mount_point = tempfile.mkdtemp(prefix="smartboot_iso_")
        try:
            result = subprocess.run(
                ["sudo", "mount", "-o", "loop,ro", iso_path, mount_point],
                capture_output=True, timeout=10
            )
            if result.returncode != 0:
                return None
            try:
                return self._check_content_signatures(mount_point)
            finally:
                subprocess.run(
                    ["sudo", "umount", mount_point],
                    capture_output=True, timeout=8
                )
        except Exception as exc:
            logger.debug(f"ISOManager: Unix content detection failed: {exc}")
            return None
        finally:
            try:
                os.rmdir(mount_point)
            except OSError:
                pass

    def _check_content_signatures(self, root: str) -> Optional[str]:
        for iso_type, signatures in self._CONTENT_SIGNATURES.items():
            for sig in signatures:
                path = os.path.join(root, *sig)
                if os.path.exists(path):
                    return iso_type
        return None

    @staticmethod
    def _check_iso9660_magic(iso_path: str) -> bool:
        """Check for ISO 9660 primary volume descriptor magic bytes."""
        try:
            with open(iso_path, "rb") as f:
                f.seek(0x8001)
                magic = f.read(5)
            return magic == b"CD001"
        except OSError:
            return False

    def _validate_windows_mount(self, iso_path: str) -> bool:
        script = (
            f"$m = Mount-DiskImage -ImagePath '{iso_path}' -PassThru;"
            "$dl = ($m | Get-Volume).DriveLetter; $dl"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=15
            )
            drive = result.stdout.strip()
            if not drive:
                return False
            root = drive + ":\\"
            valid_dirs = ["boot", "isolinux", "sources", "casper", "EFI", "live"]
            found = any(os.path.exists(os.path.join(root, d)) for d in valid_dirs)
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Dismount-DiskImage -ImagePath '{iso_path}'"],
                capture_output=True, timeout=8
            )
            return found
        except Exception:
            return False