"""
telegram_backup_for_downloads.py — Telegram-backed Cloud Cache Manager
======================================================================
Handles state persistence (index.db backup/restore) and media caching (mp4/mp3)
on Telegram. Avoids ephemeral data loss on GitHub Actions.
"""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger("telegram_backup")

class TelegramBackupManager:
    """
    Manages synchronization of SQLite database and media files with a Telegram group/channel.
    Gracefully disables itself if credentials are not provided.
    """
    def __init__(self) -> None:
        import sys
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        
        # Auto-disable backup uploads during automated test runs
        if "pytest" in sys.modules or os.getenv("TESTING") == "true":
            logger.info("🧪 Test environment detected. Disabling Telegram backup uploads.")
            self.enabled = False
            return
            
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            logger.warning("⚠️ Telegram credentials missing (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID). "
                           "Cloud backup and cache are disabled.")
        else:
            logger.info("🤖 Telegram Backup Manager initialized successfully (Chat ID: %s)", self.chat_id)

    def _get_api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def get_pinned_file_id(self) -> Optional[str]:
        """Fetches the file_id of the pinned database document in the Telegram group."""
        if not self.enabled:
            return None
        try:
            url = self._get_api_url("getChat")
            resp = requests.post(url, data={"chat_id": self.chat_id}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            pinned = data.get("result", {}).get("pinned_message", {})
            if not pinned:
                logger.warning("[TELEGRAM] No pinned message found in chat.")
                return None
                
            document = pinned.get("document", {})
            file_id = document.get("file_id")
            if file_id:
                logger.info("[TELEGRAM] Found pinned database document. File ID: %s", file_id[:15] + "...")
                return file_id
            
            logger.warning("[TELEGRAM] Pinned message exists but is not a document.")
            return None
        except Exception as e:
            logger.error("[TELEGRAM] Failed to retrieve pinned message: %s", e)
            return None

    def download_file(self, file_id: str, dest_path: str) -> bool:
        """Downloads a file from Telegram by its file ID."""
        if not self.enabled:
            return False
        try:
            # Step 1: Get file path from file_id
            url = self._get_api_url("getFile")
            resp = requests.post(url, data={"file_id": file_id}, timeout=15)
            resp.raise_for_status()
            file_path = resp.json().get("result", {}).get("file_path")
            
            if not file_path:
                logger.error("[TELEGRAM] Could not resolve file path from File ID.")
                return False
                
            # Step 2: Download the file content
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            logger.info("[TELEGRAM] Downloading file from Telegram CDN...")
            
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with requests.get(download_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            logger.info("[TELEGRAM] Download complete! Saved to %s", dest_path)
            return True
        except Exception as e:
            logger.error("[TELEGRAM] File download failed: %s", e)
            return False

    def upload_file(self, file_path: str, caption: Optional[str] = None) -> Optional[dict]:
        """
        Uploads a local file as a document and returns the message details dict.
        Returns None on failure.
        """
        if not self.enabled:
            return None
        if not os.path.exists(file_path):
            logger.error("[TELEGRAM] Local file not found: %s", file_path)
            return None
            
        try:
            url = self._get_api_url("sendDocument")
            logger.info("[TELEGRAM] Uploading %s...", os.path.basename(file_path))
            
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': self.chat_id}
                if caption:
                    data['caption'] = caption
                    
                resp = requests.post(url, files=files, data=data, timeout=120)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                logger.info("[TELEGRAM] Upload successful. Message ID: %s", result.get("message_id"))
                return result
        except Exception as e:
            logger.error("[TELEGRAM] File upload failed: %s", e)
            return None

    def pin_message(self, message_id: int) -> bool:
        """Pins a message in the chat."""
        if not self.enabled:
            return False
        try:
            url = self._get_api_url("pinChatMessage")
            resp = requests.post(url, data={
                "chat_id": self.chat_id,
                "message_id": message_id,
                "disable_notification": True
            }, timeout=15)
            resp.raise_for_status()
            logger.info("[TELEGRAM] Message pinned as latest reference.")
            return True
        except Exception as e:
            logger.error("[TELEGRAM] Failed to pin message: %s", e)
            return False

    def restore_database(self, local_db_path: str) -> bool:
        """Restores the SQLite database from the Telegram pinned message."""
        if not self.enabled:
            return False
        logger.info("[TELEGRAM] Attempting cloud database restore...")
        file_id = self.get_pinned_file_id()
        if not file_id:
            logger.warning("[TELEGRAM] No remote database backup available.")
            return False
            
        # Download to a temporary path first to prevent corruption
        temp_path = local_db_path + ".restore.tmp"
        if self.download_file(file_id, temp_path):
            try:
                # Safely overwrite local file
                if os.path.exists(local_db_path):
                    os.remove(local_db_path)
                os.rename(temp_path, local_db_path)
                logger.info("[TELEGRAM] Database successfully restored from cloud backup!")
                return True
            except Exception as e:
                logger.error("[TELEGRAM] Failed to overwrite local database: %s", e)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        return False

    def backup_database(self, local_db_path: str) -> bool:
        """Uploads the local database SQLite file and pins it as the new reference."""
        if not self.enabled:
            return False
        logger.info("[TELEGRAM] Uploading database backup...")
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        caption = f"🗄️ AMTCE Database Backup | {timestamp}"
        
        result = self.upload_file(local_db_path, caption=caption)
        if result:
            msg_id = result.get("message_id")
            if msg_id:
                return self.pin_message(msg_id)
        return False

    def upload_media(self, file_path: str) -> Optional[str]:
        """Uploads a video or audio file to the cloud storage and returns its Telegram file_id."""
        if not self.enabled:
            return None
        logger.info("[TELEGRAM] Archiving media file to cloud storage...")
        filename = os.path.basename(file_path)
        caption = f"📦 Cached Media: {filename}"
        
        result = self.upload_file(file_path, caption=caption)
        if result:
            file_id = result.get("document", {}).get("file_id")
            if file_id:
                logger.info("[TELEGRAM] Media archived. File ID: %s", file_id[:15] + "...")
                return file_id
        return None
