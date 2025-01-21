import aiohttp
import logging
from packaging import version
from config import UPDATE_CONFIG
from datetime import datetime, timedelta
import os

class UpdateChecker:
    def __init__(self):
        self.current_version = UPDATE_CONFIG['current_version']
        self.update_url = UPDATE_CONFIG['update_url']
        self.check_interval = timedelta(days=UPDATE_CONFIG['check_interval'])
        self.last_check_file = UPDATE_CONFIG['last_check_file']

    async def check_for_updates(self):
        """Check for updates using aiohttp if enough time has passed."""
        try:
            if not self._should_check_update():
                return False, None, None

            async with aiohttp.ClientSession() as session:
                async with session.get(self.update_url) as response:
                    if response.status == 200:
                        self._update_last_check_time()
                        data = await response.json()
                        latest_version = data['tag_name'].lstrip('v')
                        
                        if version.parse(latest_version) > version.parse(self.current_version):
                            return True, latest_version, data['html_url']
                    return False, None, None
        except Exception as e:
            logging.error(f"Update check failed: {e}")
            return False, None, None

    def _should_check_update(self) -> bool:
        """Determine if enough time has passed since last update check."""
        try:
            if not os.path.exists(self.last_check_file):
                return True

            with open(self.last_check_file, 'r') as f:
                last_check_str = f.read().strip()
                last_check = datetime.fromisoformat(last_check_str)
                return datetime.now() - last_check >= self.check_interval
        except Exception as e:
            logging.error(f"Error reading last update check time: {e}")
            return True

    def _update_last_check_time(self):
        """Update the timestamp of last update check."""
        try:
            with open(self.last_check_file, 'w') as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logging.error(f"Error saving update check time: {e}")
