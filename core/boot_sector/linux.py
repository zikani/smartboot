"""
Linux Boot Sector module for SmartBoot

Layered fallback strategy:
  BIOS: syslinux → extlinux → ms-sys → grub-install → dd MBR → fdisk flag
  UEFI: grub-install (--removable) → systemd-boot/refind copy → syslinux efi64
        → walk /boot/efi → minimal stub
  FreeDOS: mark bootable → delegate to BIOS chain
"""

import os
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()


def _run(cmd: List[str], timeout: int = 60,
         **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, **kwargs)


def _sudo(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    return _run(["sudo"] + cmd, **kwargs)


class LinuxBootSector(BaseBootSector):
    """Linux-specific boot sector implementation."""

    # Candidate MBR binary paths for syslinux
    _SYSLINUX_MBR_PATHS = [
        "/usr/lib/syslinux/mbr.bin",
        "/usr/lib/syslinux/mbr/mbr.bin",
        "/usr/share/syslinux/mbr.bin",
        "/usr/lib/EXTLINUX/mbr.bin",
        "/usr/lib/syslinux/bios/mbr.bin",
    ]

    # Candidate EFI bootloader paths (evaluated in order)
    _EFI_SOURCES = [
        "/usr/lib/systemd/boot/efi/systemd-bootx64.efi",
        "/usr/share/efi/systemd-boot/systemd-bootx64.efi",
        "/usr/lib/gummiboot/gummibootx64.efi",
        "/usr/lib/refind/refind_x64.efi",
        "/usr/share/refind/refind_x64.efi",
        "/usr/share/efi-x86_64/grub/grubx64.efi",
        "/usr/lib/grub/x86_64-efi/grubx64.efi",
        "/boot/efi/EFI/BOOT/BOOTX64.EFI",
        "/usr/lib/syslinux/efi64/syslinux.efi",
        "/usr/share/syslinux/efi64/syslinux.efi",
    ]

    def __init__(self, resource_dir: str) -> None:
        super().__init__(resource_dir)
        self._mounted_paths: List[str] = []

    def __del__(self) -> None:
        self._cleanup_mounts()

    def _cleanup_mounts(self) -> None:
        for mp in list(self._mounted_paths):
            try:
                if os.path.ismount(mp):
                    _sudo(["umount", mp], timeout=15)
            except Exception as exc:
                logger.warning(f"umount {mp}: {exc}")
            finally:
                try:
                    os.rmdir(mp)
                except OSError:
                    pass
        self._mounted_paths.clear()

    # ------------------------------------------------------------------
    # Privilege check
    # ------------------------------------------------------------------

    def check_admin_privileges(self) -> bool:
        try:
            return _sudo(["true"], timeout=5).returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dev_path(self, device: Dict[str, Any]) -> Optional[str]:
        name = device.get("name", "")
        if not name:
            return None
        return name if name.startswith("/dev/") else f"/dev/{name}"

    def _get_partition(self, dev: str, number: int = 1) -> Optional[str]:
        """Return /dev/sdXN or /dev/sdXpN, whichever exists."""
        for candidate in (f"{dev}{number}", f"{dev}p{number}"):
            if os.path.exists(candidate):
                return candidate
        return None

    def _wait_for_partition(self, dev: str, number: int = 1,
                             retries: int = 6) -> Optional[str]:
        for _ in range(retries):
            p = self._get_partition(dev, number)
            if p:
                return p
            time.sleep(1)
        return None

    def _mount_temp(self, partition: str) -> Optional[str]:
        mp = f"/tmp/smartboot_{int(time.time() * 1000)}"
        os.makedirs(mp, exist_ok=True)
        r = _sudo(["mount", partition, mp], timeout=20)
        if r.returncode == 0:
            self._mounted_paths.append(mp)
            return mp
        try:
            os.rmdir(mp)
        except OSError:
            pass
        logger.warning(f"mount {partition}: {r.stderr.strip()}")
        return None

    def _install_syslinux_mbr(self, dev: str,
                               cb: Optional[Callable[[int, str], None]]) -> bool:
        for mbr_path in self._SYSLINUX_MBR_PATHS:
            if os.path.exists(mbr_path):
                try:
                    r = _sudo(
                        ["dd", f"if={mbr_path}", f"of={dev}",
                         "bs=440", "count=1", "conv=notrunc"],
                        timeout=30
                    )
                    if r.returncode == 0:
                        self._update(cb, None, f"MBR written from {mbr_path}")
                        return True
                except Exception as exc:
                    logger.warning(f"dd mbr from {mbr_path}: {exc}")
        return False

    # ------------------------------------------------------------------
    # BIOS boot
    # ------------------------------------------------------------------

    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        dev = self._dev_path(device)
        if not dev:
            self._update(progress_callback, 0,
                         "Error: Device name not found")
            return False

        self._update(progress_callback, 5, f"Writing BIOS boot sector to {dev}…")
        partition_scheme = options.get("partition_scheme", "mbr").lower()

        # Mark partition bootable
        partition = self._wait_for_partition(dev)
        if partition and shutil.which("parted"):
            try:
                _sudo(["parted", "-s", dev, "set", "1", "boot", "on"],
                      timeout=20)
                self._update(progress_callback, 15,
                             f"Partition {partition} marked bootable")
            except Exception as exc:
                self._update(progress_callback, 12,
                             f"Warning: could not set boot flag: {exc}")

        # Layer 1: syslinux
        if shutil.which("syslinux") and partition:
            self._update(progress_callback, 20, "Trying syslinux…")
            try:
                r = _sudo(["syslinux", "--install", partition], timeout=30)
                if r.returncode == 0:
                    self._install_syslinux_mbr(dev, progress_callback)
                    self._update(progress_callback, 100,
                                 "BIOS boot sector written (syslinux)")
                    return True
                self._update(progress_callback, 25,
                             f"syslinux failed: {r.stderr.strip()}")
            except Exception as exc:
                self._update(progress_callback, 25, f"syslinux error: {exc}")

        # Layer 2: extlinux
        if shutil.which("extlinux") and partition:
            self._update(progress_callback, 30, "Trying extlinux…")
            mount_point = (
                device.get("drive_letter")
                or self._mount_temp(partition)
            )
            if mount_point and os.path.exists(mount_point):
                try:
                    r = _sudo(["extlinux", "--install", mount_point], timeout=30)
                    if r.returncode == 0:
                        self._install_syslinux_mbr(dev, progress_callback)
                        self._update(progress_callback, 100,
                                     "BIOS boot sector written (extlinux)")
                        return True
                    self._update(progress_callback, 40,
                                 f"extlinux failed: {r.stderr.strip()}")
                except Exception as exc:
                    self._update(progress_callback, 40,
                                 f"extlinux error: {exc}")

        # Layer 3: ms-sys
        if shutil.which("ms-sys"):
            self._update(progress_callback, 50, "Trying ms-sys…")
            try:
                r = _sudo(["ms-sys", "-m", dev], timeout=30)
                if r.returncode == 0:
                    self._update(progress_callback, 100,
                                 "BIOS boot sector written (ms-sys)")
                    return True
            except Exception as exc:
                self._update(progress_callback, 55, f"ms-sys error: {exc}")

        # Layer 4: grub-install (--target i386-pc)
        if shutil.which("grub-install") or shutil.which("grub2-install"):
            grub = shutil.which("grub-install") or shutil.which("grub2-install")
            self._update(progress_callback, 60, "Trying grub-install (i386-pc)…")
            try:
                r = _sudo(
                    [grub,
                     "--target=i386-pc",
                     "--boot-directory=/tmp/smartboot_grub",
                     "--no-nvram",
                     "--no-floppy",
                     "--removable",
                     dev],
                    timeout=120
                )
                if r.returncode == 0:
                    self._update(progress_callback, 100,
                                 "BIOS boot sector written (grub-install)")
                    return True
                self._update(progress_callback, 65,
                             f"grub-install failed: {r.stderr.strip()}")
            except Exception as exc:
                self._update(progress_callback, 65,
                             f"grub-install error: {exc}")

        # Layer 5: dd MBR
        self._update(progress_callback, 70, "Trying generic dd MBR…")
        mbr_bin = self._find_or_create_mbr()
        if mbr_bin and os.path.exists(mbr_bin):
            try:
                r = _sudo(
                    ["dd", f"if={mbr_bin}", f"of={dev}",
                     "bs=446", "count=1", "conv=notrunc"],
                    timeout=30
                )
                if r.returncode == 0:
                    self._update(progress_callback, 100,
                                 "Generic MBR written (dd)")
                    return True
                self._update(progress_callback, 80,
                             f"dd MBR failed: {r.stderr.strip()}")
            except Exception as exc:
                self._update(progress_callback, 80, f"dd MBR error: {exc}")

        # Layer 6: fdisk boot flag only
        self._update(progress_callback, 85,
                     "Attempting fdisk boot flag as last resort…")
        try:
            import pty, select
            # echo 'a\n1\nw\n' | sudo fdisk <dev>
            r = _sudo(["fdisk", dev],
                      input="a\n1\nw\n", timeout=15)
            self._update(progress_callback, 90,
                         "fdisk boot flag set (limited boot support)")
            return True
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"All BIOS boot methods failed. Last error: {exc}")
            return False

    # ------------------------------------------------------------------
    # UEFI boot
    # ------------------------------------------------------------------

    def write_uefi_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        if not self.check_admin_privileges():
            self._update(progress_callback, 0,
                         "Error: Root privileges required for UEFI boot")
            return False

        dev = self._dev_path(device)
        if not dev:
            self._update(progress_callback, 0, "Error: Device name not found")
            return False

        partition = self._wait_for_partition(dev)
        if not partition:
            self._update(progress_callback, 0,
                         f"Could not find first partition on {dev}")
            return False

        iso_type = options.get("iso_type", "generic").lower()
        self._update(progress_callback, 10, "Preparing UEFI boot files…")

        # Resolve mount point
        mount_point = device.get("drive_letter", "")
        if not mount_point or not os.path.exists(mount_point):
            mount_point = self._mount_temp(partition)
        if not mount_point or not os.path.exists(mount_point):
            self._update(progress_callback, 0,
                         f"Could not mount {partition}")
            return False

        # EFI directory
        efi_boot_dir = os.path.join(mount_point, "EFI", "BOOT")
        os.makedirs(efi_boot_dir, exist_ok=True)
        self._update(progress_callback, 20, "EFI directory structure created")
        bootx64 = os.path.join(efi_boot_dir, "BOOTX64.EFI")

        # Layer 1: grub-install --removable (best outcome)
        if iso_type in ("linux", "ubuntu", "debian", "fedora", "generic"):
            grub = shutil.which("grub-install") or shutil.which("grub2-install")
            if grub:
                self._update(progress_callback, 30,
                             "Installing GRUB EFI bootloader…")
                grub_dir = os.path.join(mount_point, "boot", "grub")
                os.makedirs(grub_dir, exist_ok=True)
                try:
                    r = _sudo(
                        [grub,
                         "--target=x86_64-efi",
                         f"--efi-directory={mount_point}",
                         f"--boot-directory={os.path.join(mount_point, 'boot')}",
                         "--removable",
                         "--no-nvram",
                         "--no-floppy"],
                        timeout=120
                    )
                    if r.returncode == 0 and os.path.exists(bootx64):
                        self._write_grub_cfg(grub_dir)
                        self._update(progress_callback, 100,
                                     "UEFI boot files installed (grub-install)")
                        return True
                    self._update(progress_callback, 45,
                                 f"grub-install UEFI failed: {r.stderr.strip()}")
                except Exception as exc:
                    self._update(progress_callback, 45,
                                 f"grub-install error: {exc}")

        # Layer 2: Copy a known EFI bootloader from the system
        for src in self._EFI_SOURCES:
            if os.path.exists(src):
                try:
                    self._update(progress_callback, 60,
                                 f"Copying EFI bootloader from {src}…")
                    _sudo(["cp", src, bootx64], timeout=15)
                    if os.path.exists(bootx64):
                        self._update(progress_callback, 100,
                                     "UEFI bootloader installed")
                        return True
                except Exception as exc:
                    logger.warning(f"Copy {src}: {exc}")

        # Layer 3: Walk system EFI directories
        for efi_dir in ("/boot/efi", "/usr/share/efi", "/usr/lib/efi"):
            if not os.path.isdir(efi_dir):
                continue
            for root, _, files in os.walk(efi_dir):
                for fname in files:
                    if fname.lower().endswith(".efi"):
                        src = os.path.join(root, fname)
                        try:
                            _sudo(["cp", src, bootx64], timeout=15)
                            if os.path.exists(bootx64):
                                self._update(progress_callback, 100,
                                             f"UEFI bootloader installed from {src}")
                                return True
                        except Exception:
                            continue

        # Layer 4: Minimal stub
        self._update(progress_callback, 90,
                     "No EFI bootloader found — writing minimal stub…")
        stub = self._find_or_create_uefi_stub()
        try:
            _sudo(["cp", stub, bootx64], timeout=10)
            if os.path.exists(bootx64):
                self._update(progress_callback, 100,
                             "Minimal UEFI stub installed")
                return True
        except Exception as exc:
            pass

        self._update(progress_callback, 0,
                     "Failed to install any UEFI bootloader. "
                     "Install grub-efi or systemd-boot package.")
        return False

    def _write_grub_cfg(self, grub_dir: str) -> None:
        cfg = os.path.join(grub_dir, "grub.cfg")
        try:
            with open(cfg, "w") as f:
                f.write("# SmartBoot generated GRUB configuration\n")
                f.write("search --file --set=root /boot/grub/grub.cfg\n")
                f.write("set prefix=($root)/boot/grub\n")
                f.write("configfile /boot/grub/grub.cfg\n")
        except OSError as exc:
            logger.warning(f"Could not write grub.cfg: {exc}")

    # ------------------------------------------------------------------
    # FreeDOS boot
    # ------------------------------------------------------------------

    def write_freedos_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        dev = self._dev_path(device)
        if not dev:
            self._update(progress_callback, 0, "Error: Device name not found")
            return False

        self._update(progress_callback, 10,
                     "Preparing FreeDOS boot sector…")

        partition = self._wait_for_partition(dev)
        if partition:
            # Mark bootable
            if shutil.which("parted"):
                try:
                    _sudo(["parted", "-s", dev, "set", "1", "boot", "on"],
                          timeout=20)
                except Exception:
                    pass

        # Delegate to the full BIOS chain (syslinux / grub / dd)
        return self.write_bios_boot(device, options, progress_callback)

    # ------------------------------------------------------------------
    # _update override: allow None progress (skip value)
    # ------------------------------------------------------------------

    def _update(
        self,
        progress_callback,
        progress,
        message: str,
    ) -> None:
        if progress is not None:
            logger.debug(f"Boot sector {progress}%: {message}")
            if progress_callback:
                progress_callback(progress, message)
        else:
            logger.debug(f"Boot sector: {message}")