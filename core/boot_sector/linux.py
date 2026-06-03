"""
Linux Boot Sector module for SmartBoot

Rufus-parity layered fallback strategy:

  BIOS:
    1. syslinux --install <partition>  + syslinux MBR dd
    2. extlinux --install <mount>      + syslinux MBR dd
    3. ms-sys -m <device>
    4. grub-install --target=i386-pc
    5. dd generic MBR (446 bytes, conv=notrunc)
    6. fdisk boot flag (last resort)

  UEFI:
    1. grub-install --target=x86_64-efi --removable
    2. Copy known system EFI bootloader (systemd-boot, refind, grub efi, syslinux efi)
    3. Walk /boot/efi, /usr/share/efi, /usr/lib/efi for any *.efi
    4. Minimal PE32+ stub

  FreeDOS:
    mark partition bootable → delegate to BIOS chain

  Windows-on-Linux (ISO already extracted):
    Use grub-install i386-pc + generate Windows-aware grub.cfg
"""

import os
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger
from .base import BaseBootSector

logger = get_logger()


def _run(cmd: List[str], timeout: int = 60, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, **kwargs)


def _sudo(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    return _run(["sudo"] + cmd, **kwargs)


class LinuxBootSector(BaseBootSector):
    """Linux-specific boot sector writer with full Rufus-parity fallback chain."""

    _SYSLINUX_MBR_PATHS = [
        "/usr/lib/syslinux/mbr/mbr.bin",
        "/usr/lib/syslinux/mbr.bin",
        "/usr/share/syslinux/mbr.bin",
        "/usr/lib/EXTLINUX/mbr.bin",
        "/usr/lib/syslinux/bios/mbr.bin",
        "/usr/lib/syslinux/modules/bios/mbr.bin",
    ]

    _SYSLINUX_ALTMBR_PATHS = [
        "/usr/lib/syslinux/mbr/altmbr.bin",
        "/usr/share/syslinux/altmbr.bin",
    ]

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

    def _mount_temp(self, partition: str,
                    options: str = "") -> Optional[str]:
        mp = f"/tmp/smartboot_{int(time.time() * 1000)}"
        os.makedirs(mp, exist_ok=True)
        cmd = ["sudo", "mount"]
        if options:
            cmd += ["-o", options]
        cmd += [partition, mp]
        r = _sudo(cmd[1:], timeout=20)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            self._mounted_paths.append(mp)
            return mp
        try:
            os.rmdir(mp)
        except OSError:
            pass
        logger.warning(f"mount {partition}: {r.stderr.strip()}")
        return None

    def _unmount(self, mp: str) -> None:
        try:
            _sudo(["umount", mp], timeout=15)
            if mp in self._mounted_paths:
                self._mounted_paths.remove(mp)
        except Exception:
            pass


    def check_admin_privileges(self) -> bool:
        try:
            return _sudo(["true"], timeout=5).returncode == 0
        except Exception:
            return False


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
                             retries: int = 8) -> Optional[str]:
        for _ in range(retries):
            p = self._get_partition(dev, number)
            if p:
                return p
            time.sleep(1)
        return None

    def _get_disk_size(self, dev: str) -> int:
        """Return device size in bytes via lsblk."""
        try:
            r = _run(["lsblk", "-b", "-d", "-o", "SIZE", "-n", dev], timeout=5)
            return int(r.stdout.strip())
        except Exception:
            return 0


    def _install_syslinux_mbr(self, dev: str,
                               cb: Optional[Callable[[int, str], None]]) -> bool:
        for mbr_path in self._SYSLINUX_MBR_PATHS:
            if os.path.exists(mbr_path):
                try:
                    r = _sudo(
                        ["dd", f"if={mbr_path}", f"of={dev}",
                         "bs=440", "count=1", "conv=notrunc"],
                        timeout=30,
                    )
                    if r.returncode == 0:
                        self._update(cb, None, f"MBR written from {mbr_path}")
                        return True
                except Exception as exc:
                    logger.warning(f"dd syslinux MBR {mbr_path}: {exc}")
        mbr_bin = self._find_or_create_mbr()
        try:
            r = _sudo(
                ["dd", f"if={mbr_bin}", f"of={dev}",
                 "bs=446", "count=1", "conv=notrunc"],
                timeout=30,
            )
            if r.returncode == 0:
                self._update(cb, None, "Generic MBR written via dd")
                return True
        except Exception as exc:
            logger.warning(f"dd generic MBR: {exc}")
        return False


    def write_bios_boot(
        self,
        device: Dict[str, Any],
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        dev = self._dev_path(device)
        if not dev:
            self._update(progress_callback, 0, "Error: Device name not found")
            return False

        self._update(progress_callback, 5, f"Writing BIOS boot sector to {dev}…")
        iso_type = options.get("iso_type", "generic").lower()

        partition = self._wait_for_partition(dev)
        if partition and shutil.which("parted"):
            try:
                _sudo(["parted", "-s", dev, "set", "1", "boot", "on"],
                      timeout=20)
                self._update(progress_callback, 12,
                             f"Partition {partition} marked bootable")
            except Exception as exc:
                self._update(progress_callback, 10,
                             f"Warning: could not set boot flag: {exc}")

        if shutil.which("syslinux") and partition:
            self._update(progress_callback, 18, "Trying syslinux…")
            try:
                r = _sudo(["syslinux", "--install", partition], timeout=30)
                if r.returncode == 0:
                    self._install_syslinux_mbr(dev, progress_callback)
                    mp = device.get("drive_letter") or self._mount_temp(partition)
                    if mp:
                        self._write_syslinux_cfg(mp, iso_type)
                    self._update(progress_callback, 100,
                                 "BIOS boot sector written (syslinux)")
                    return True
                self._update(progress_callback, 22,
                             f"syslinux failed: {r.stderr.strip()}")
            except Exception as exc:
                self._update(progress_callback, 22, f"syslinux error: {exc}")

        if shutil.which("extlinux") and partition:
            self._update(progress_callback, 28, "Trying extlinux…")
            mount_point = device.get("drive_letter") or self._mount_temp(partition)
            if mount_point and os.path.exists(mount_point):
                try:
                    r = _sudo(["extlinux", "--install", mount_point], timeout=30)
                    if r.returncode == 0:
                        self._install_syslinux_mbr(dev, progress_callback)
                        self._write_syslinux_cfg(mount_point, iso_type)
                        self._update(progress_callback, 100,
                                     "BIOS boot sector written (extlinux)")
                        return True
                    self._update(progress_callback, 35,
                                 f"extlinux failed: {r.stderr.strip()}")
                except Exception as exc:
                    self._update(progress_callback, 35,
                                 f"extlinux error: {exc}")

        if shutil.which("ms-sys"):
            self._update(progress_callback, 42, "Trying ms-sys…")
            try:
                r = _sudo(["ms-sys", "-m", dev], timeout=30)
                if r.returncode == 0:
                    self._update(progress_callback, 100,
                                 "BIOS boot sector written (ms-sys)")
                    return True
            except Exception as exc:
                self._update(progress_callback, 46, f"ms-sys error: {exc}")

        grub = shutil.which("grub-install") or shutil.which("grub2-install")
        if grub:
            self._update(progress_callback, 52, "Trying grub-install (i386-pc)…")
            grub_boot_dir = os.path.join(
                device.get("drive_letter", "/tmp"), "boot", "grub"
            )
            try:
                r = _sudo(
                    [grub,
                     "--target=i386-pc",
                     f"--boot-directory={os.path.dirname(grub_boot_dir)}",
                     "--no-nvram",
                     "--no-floppy",
                     "--removable",
                     dev],
                    timeout=120,
                )
                if r.returncode == 0:
                    os.makedirs(grub_boot_dir, exist_ok=True)
                    self._write_grub_cfg(grub_boot_dir, iso_type)
                    self._update(progress_callback, 100,
                                 "BIOS boot sector written (grub-install i386-pc)")
                    return True
                self._update(progress_callback, 58,
                             f"grub-install failed: {r.stderr.strip()[:200]}")
            except Exception as exc:
                self._update(progress_callback, 58,
                             f"grub-install error: {exc}")

        self._update(progress_callback, 68, "Writing generic dd MBR…")
        mbr_bin = self._find_or_create_mbr()
        if mbr_bin and os.path.exists(mbr_bin):
            try:
                r = _sudo(
                    ["dd", f"if={mbr_bin}", f"of={dev}",
                     "bs=446", "count=1", "conv=notrunc"],
                    timeout=30,
                )
                if r.returncode == 0:
                    self._update(progress_callback, 100,
                                 "Generic MBR written (dd)")
                    return True
                self._update(progress_callback, 74,
                             f"dd MBR failed: {r.stderr.strip()}")
            except Exception as exc:
                self._update(progress_callback, 74, f"dd MBR error: {exc}")

        self._update(progress_callback, 82,
                     "Setting fdisk boot flag (last resort)…")
        try:
            _sudo(["fdisk", dev], timeout=15,
                  input="a\n1\nw\n")
            self._update(progress_callback, 90,
                         "fdisk boot flag set (limited boot support)")
            return True
        except Exception as exc:
            self._update(progress_callback, 0,
                         f"All BIOS boot methods failed. Last error: {exc}")
            return False


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
        self._update(progress_callback, 8, "Preparing UEFI boot files…")

        mount_point = device.get("drive_letter", "")
        if not mount_point or not os.path.exists(mount_point):
            mount_point = self._mount_temp(partition)
        if not mount_point or not os.path.exists(mount_point):
            self._update(progress_callback, 0,
                         f"Could not mount {partition}")
            return False

        efi_boot_dir = os.path.join(mount_point, "EFI", "BOOT")
        os.makedirs(efi_boot_dir, exist_ok=True)
        self._update(progress_callback, 15, "EFI directory structure created")
        bootx64 = os.path.join(efi_boot_dir, "BOOTX64.EFI")

        grub = shutil.which("grub-install") or shutil.which("grub2-install")
        if grub and iso_type in ("linux", "ubuntu", "debian",
                                  "fedora", "generic", "windows"):
            self._update(progress_callback, 22, "Installing GRUB EFI bootloader…")
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
                    timeout=120,
                )
                if r.returncode == 0 and os.path.exists(bootx64):
                    self._write_grub_cfg(grub_dir, iso_type)
                    self._update(progress_callback, 100,
                                 "UEFI boot files installed (grub-install)")
                    return True
                self._update(progress_callback, 38,
                             f"grub-install UEFI failed: {r.stderr.strip()[:200]}")
            except Exception as exc:
                self._update(progress_callback, 38,
                             f"grub-install error: {exc}")

        for src in self._EFI_SOURCES:
            if os.path.exists(src):
                try:
                    self._update(progress_callback, 55,
                                 f"Copying EFI bootloader from {src}…")
                    _sudo(["cp", "--preserve=mode", src, bootx64], timeout=15)
                    if os.path.exists(bootx64):
                        self._update(progress_callback, 100,
                                     f"UEFI bootloader installed ({os.path.basename(src)})")
                        return True
                except Exception as exc:
                    logger.warning(f"copy EFI {src}: {exc}")

        for efi_search in ("/boot/efi", "/usr/share/efi",
                           "/usr/lib/efi", "/usr/share/ovmf"):
            if not os.path.isdir(efi_search):
                continue
            for root, _, files in os.walk(efi_search):
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

        self._update(progress_callback, 88,
                     "No EFI bootloader found — writing minimal stub…")
        stub = self._find_or_create_uefi_stub()
        try:
            _sudo(["cp", stub, bootx64], timeout=10)
            if os.path.exists(bootx64):
                self._update(progress_callback, 100,
                             "Minimal UEFI stub installed "
                             "(install grub-efi or systemd-boot for real boot)")
                return True
        except Exception as exc:
            pass

        self._update(progress_callback, 0,
                     "Failed to install any UEFI bootloader. "
                     "Install grub-efi-amd64 or systemd-boot and retry.")
        return False


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

        self._update(progress_callback, 8, "Preparing FreeDOS boot sector…")

        partition = self._wait_for_partition(dev)
        if partition and shutil.which("parted"):
            try:
                _sudo(["parted", "-s", dev, "set", "1", "boot", "on"],
                      timeout=20)
            except Exception:
                pass

        mp = device.get("drive_letter", "")
        if mp and os.path.isdir(mp):
            for sys_path in (
                os.path.join(mp, "freedos", "bin", "sys.com"),
                os.path.join(mp, "SYS.COM"),
                os.path.join(mp, "sys.com"),
            ):
                if os.path.exists(sys_path):
                    try:
                        r = _sudo([sys_path, dev], timeout=30)
                        if r.returncode == 0:
                            self._update(progress_callback, 100,
                                         "FreeDOS boot sector written (sys.com)")
                            return True
                    except Exception as exc:
                        logger.warning(f"sys.com failed: {exc}")

        return self.write_bios_boot(device, options, progress_callback)


    def _update(
        self,
        progress_callback: Optional[Callable],
        progress,
        message: str,
    ) -> None:
        if progress is not None:
            logger.debug(f"LinuxBootSector {progress}%: {message}")
            if progress_callback:
                progress_callback(progress, message)
        else:
            logger.debug(f"LinuxBootSector: {message}")