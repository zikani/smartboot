"""
Boot sector management package for SmartBoot.

This package handles writing boot sectors to USB devices for different operating systems.
"""

from .manager import BootSectorManager

__all__ = ['BootSectorManager']
