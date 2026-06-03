"""Logger module for SmartBoot."""
import os
import logging
from logging.handlers import RotatingFileHandler
import platform

def _get_log_directory() -> str:
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "SmartBoot", "logs")
    elif system == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Logs", "SmartBoot")
    return os.path.join(os.path.expanduser("~"), ".smartboot", "logs")

def _build_logger() -> logging.Logger:
    logger = logging.getLogger("smartboot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    try:
        log_dir = _get_log_directory()
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(
            os.path.join(log_dir, "smartboot.log"),
            maxBytes=5 * 1024 * 1024, backupCount=5
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    return logger

default_logger = _build_logger()

def get_logger() -> logging.Logger:
    return default_logger