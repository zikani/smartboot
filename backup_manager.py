import os
import shutil
import json
import gzip
from datetime import datetime
from config import BACKUP_CONFIG

class BackupManager:
    def __init__(self):
        self.backup_dir = BACKUP_CONFIG['backup_location']
        os.makedirs(self.backup_dir, exist_ok=True)

    def create_backup(self, usb_path, config):
        """Create a backup of USB drive configuration."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(self.backup_dir, f'backup_{timestamp}.gz')

        backup_data = {
            'timestamp': timestamp,
            'usb_path': usb_path,
            'config': config
        }

        with gzip.open(backup_path, 'wt') as f:
            json.dump(backup_data, f)

        self._maintain_backup_limit()
        return backup_path

    def restore_backup(self, backup_path):
        """Restore USB configuration from backup."""
        with gzip.open(backup_path, 'rt') as f:
            backup_data = json.load(f)
        return backup_data

    def _maintain_backup_limit(self):
        """Maintain maximum number of backups."""
        backups = sorted(os.listdir(self.backup_dir))
        while len(backups) > BACKUP_CONFIG['max_backups']:
            os.remove(os.path.join(self.backup_dir, backups.pop(0)))
