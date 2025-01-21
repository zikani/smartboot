VERSION = "1.0.0"

# Logging configuration
LOG_CONFIG = {
    'filename': 'smartboot.log',
    'level': 'INFO',
    'format': '%(asctime)s - %(levelname)s - %(message)s'
}

# UI Settings
UI_CONFIG = {
    'window_width': 480,
    'window_height': 400,
    'window_title': 'Smart Boot'
}

# Update settings
UPDATE_CONFIG = {
    'check_updates': True,
    'update_url': 'https://api.github.com/repos/yourusername/smartboot/releases/latest',
    'current_version': VERSION,
    'check_interval': 180,  # Days between update checks
    'last_check_file': 'last_update_check.txt'  # File to store last check timestamp
}

# Backup settings
BACKUP_CONFIG = {
    'backup_location': './backups',
    'max_backups': 5,
    'compression': True
}

# Hash verification
HASH_ALGORITHMS = ['MD5', 'SHA1', 'SHA256', 'SHA512']

# Supported configurations
SUPPORTED_FILESYSTEMS = ['FAT32', 'NTFS', 'ext4']
SUPPORTED_BOOTLOADERS = ['UEFI', 'Legacy']
SUPPORTED_PARTITION_SCHEMES = ['MBR', 'GPT']
