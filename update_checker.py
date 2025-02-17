import aiohttp
import json
import logging
from datetime import datetime, timedelta
import os
from config import UPDATE_CONFIG

class UpdateChecker:
    def __init__(self):
        self.current_version = UPDATE_CONFIG['current_version']
        self.update_url = UPDATE_CONFIG['update_url']
        self.check_interval = UPDATE_CONFIG['check_interval']
        self.last_check_file = UPDATE_CONFIG['last_check_file']

    async def check_for_updates(self):
        """Check for updates if enough time has passed since last check."""
        if not self._should_check():
            return False, None, None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.update_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        latest_version = data.get('tag_name', '').lstrip('v')
                        download_url = data.get('html_url', '')
                        
                        self._update_last_check()
                        
                        if self._is_newer_version(latest_version):
                            return True, latest_version, download_url
                    else:
                        logging.warning(f"Update check failed with status {response.status}")
        except Exception as e:
            logging.error(f"Error checking for updates: {e}")
        
        return False, None, None

    async def force_check_for_updates(self):
        """Force check for updates regardless of the interval."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.update_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        latest_version = data.get('tag_name', '').lstrip('v')
                        download_url = data.get('html_url', '')
                        
                        if self._is_newer_version(latest_version):
                            return True, latest_version, download_url
                    else:
                        logging.warning(f"Update check failed with status {response.status}")
        except Exception as e:
            logging.error(f"Error checking for updates: {e}")
        
        return False, None, None

    def _should_check(self):
        """Determine if enough time has passed since last check."""
        if not os.path.exists(self.last_check_file):
            return True

        try:
            with open(self.last_check_file, 'r') as f:
                last_check = datetime.fromisoformat(f.read().strip())
            return datetime.now() - last_check > timedelta(days=self.check_interval)
        except Exception:
            return True

    def _update_last_check(self):
        """Update the timestamp of last update check."""
        try:
            with open(self.last_check_file, 'w') as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logging.error(f"Failed to update last check time: {e}")

    def _is_newer_version(self, latest_version):
        """Compare version numbers to determine if update is available."""
        try:
            current = [int(x) for x in self.current_version.split('.')]
            latest = [int(x) for x in latest_version.split('.')]
            return latest > current
        except Exception:
            return False

    def _is_current_version_newer(self, latest_version):
        """Compare version numbers to determine if the current version is newer than the latest version."""
        try:
            current = [int(x) for x in self.current_version.split('.')]
            latest = [int(x) for x in latest_version.split('.')]
            return current > latest
        except Exception:
            return False
