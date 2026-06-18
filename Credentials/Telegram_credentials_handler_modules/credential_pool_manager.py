"""
credential_pool_manager.py — Credentials Rotation, Verification, & Storage Handler
==================================================================================
Manages secure load-balancing and retrieval of user-submitted Apify tokens
and Instagram cookies. Persisted in an encrypted pool file, backed up to Telegram.
"""

import os
import json
import sqlite3
import logging
import hashlib
from typing import Dict, Optional, Tuple, List
from .encryption_engine import encrypt_data, decrypt_data

def hash_passphrase(passphrase: str) -> str:
    """Computes a secure SHA-256 hash of a user passphrase."""
    if not passphrase:
        return ""
    return hashlib.sha256(passphrase.encode("utf-8")).hexdigest()

logger = logging.getLogger("credential_pool")

# ── Paths & Environment Configuration ─────────────────────────────────────────
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))

# Ensure temporary cookies cache folder exists
COOKIE_CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")
os.makedirs(COOKIE_CACHE_DIR, exist_ok=True)

# Database path (share same index.db as downloader)
_DB_PATH = os.path.join(PROJECT_ROOT, "Download_Modules", "Downloader_db", "index.db")

# Encryption Key Fallback
PASSPHRASE = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "default_amtce_encryption_passphrase").strip()
if PASSPHRASE == "default_amtce_encryption_passphrase":
    logger.warning("⚠️ CREDENTIALS_ENCRYPTION_KEY env var not set. Using insecure default passphrase!")

class CredentialPoolManager:
    """
    Handles encrypted credentials storage, retrieval, and load balancing.
    Synchronizes the encrypted pool file with Telegram utilizing SQLite index.db configuration.
    """
    def __init__(self) -> None:
        self._pool_data: Dict[str, dict] = {}
        self._rotation_index = 0
        self._ensure_config_table()
        self.load_pool()

    def _ensure_config_table(self):
        """Creates the system config table in SQLite if it does not exist."""
        try:
            os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
            with sqlite3.connect(_DB_PATH, timeout=10) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_config (
                        config_key   TEXT PRIMARY KEY,
                        config_value TEXT NOT NULL
                    )
                """)
        except Exception as e:
            logger.error("💥 Failed to initialize system_config table in SQLite: %s", e)

    def _get_config_value(self, key: str) -> Optional[str]:
        """Reads a configuration value from index.db."""
        try:
            with sqlite3.connect(_DB_PATH, timeout=10) as conn:
                row = conn.execute("SELECT config_value FROM system_config WHERE config_key = ?", (key,)).fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error("💥 Failed to read config %s: %s", key, e)
            return None

    def _set_config_value(self, key: str, value: str):
        """Writes a configuration value to index.db."""
        try:
            with sqlite3.connect(_DB_PATH, timeout=10) as conn:
                conn.execute("INSERT OR REPLACE INTO system_config (config_key, config_value) VALUES (?, ?)", (key, value))
        except Exception as e:
            logger.error("💥 Failed to write config %s: %s", key, e)

    def _get_telegram_manager(self) -> Optional[object]:
        """Helper to dynamically import and instantiate TelegramBackupManager to avoid circular dependencies."""
        try:
            from Download_Modules.Downloader_db.telegram_backup_for_downloads import TelegramBackupManager
            tg = TelegramBackupManager()
            return tg if tg.enabled else None
        except Exception as e:
            logger.error("[CREDENTIALS] Failed to import TelegramBackupManager: %s", e)
            return None

    def load_pool(self) -> None:
        """Loads and decrypts the credential pool from Telegram, falling back to local storage."""
        tg = self._get_telegram_manager()
        file_id = self._get_config_value("credentials_file_id")
        
        # Determine local encrypted pool path
        local_enc_path = os.path.join(PROJECT_ROOT, "cache", "credentials_pool.json.enc")
        
        # If running on Telegram cloud and we have a pinned file_id, download it
        if tg and file_id:
            logger.info("☁️  Restoring credentials pool from Telegram cloud...")
            success = tg.download_file(file_id, local_enc_path)
            if not success:
                logger.warning("[CREDENTIALS] Cloud download failed. Falling back to local cache.")

        # Read and decrypt local encrypted file if it exists
        if os.path.exists(local_enc_path) and os.path.getsize(local_enc_path) > 0:
            try:
                with open(local_enc_path, "r", encoding="utf-8") as f:
                    cipher_text = f.read().strip()
                if cipher_text:
                    plain_text = decrypt_data(cipher_text, PASSPHRASE)
                    self._pool_data = json.loads(plain_text)
                    logger.info("🔓 Decrypted credentials pool successfully. Registered users: %d", len(self._pool_data))
                    return
            except Exception as e:
                logger.error("💥 Decryption/Loading of credentials pool failed: %s", e)
        
        logger.info("ℹ️  Credentials pool is empty or unitialized. Starting fresh.")
        self._pool_data = {}

    def save_pool(self) -> Tuple[bool, str]:
        """Encrypts, saves locally, and uploads the updated credentials pool to Telegram."""
        try:
            local_enc_path = os.path.join(PROJECT_ROOT, "cache", "credentials_pool.json.enc")
            os.makedirs(os.path.dirname(local_enc_path), exist_ok=True)
            
            # Encrypt
            plain_text = json.dumps(self._pool_data)
            cipher_text = encrypt_data(plain_text, PASSPHRASE)
            
            # Save locally
            with open(local_enc_path, "w", encoding="utf-8") as f:
                f.write(cipher_text)
            
            tg = self._get_telegram_manager()
            if tg:
                logger.info("☁️  Uploading updated credentials pool to Telegram...")
                file_id = tg.upload_media(local_enc_path)
                if file_id:
                    self._set_config_value("credentials_file_id", file_id)
                    logger.info("✅ Pinned new credentials pool to SQLite. File ID: %s", file_id[:15] + "...")
                    
                    # Backup the modified DB since configuration updated
                    from Download_Modules.downloader import DownloadIndex
                    DownloadIndex.trigger_backup(force=True)
                else:
                    logger.warning("[CREDENTIALS] Upload to Telegram returned no File ID. Saved only locally.")
            else:
                logger.warning("[CREDENTIALS] Telegram backup disabled. Saved only locally.")
            
            return True, "Success"
        except Exception as e:
            err_msg = f"Failed to save credentials pool: {str(e)}"
            logger.error("💥 %s", err_msg)
            return False, err_msg

    def verify_and_get_user(self, user_id: str, passphrase: str) -> Tuple[bool, str, dict]:
        """
        Verifies user identity against stored hash or registers a new profile if not found.
        Returns (success, message, user_dict).
        """
        user_id = user_id.strip()
        if not user_id or not passphrase:
            return False, "User ID and Passphrase cannot be empty.", {}
            
        self.load_pool()
        p_hash = hash_passphrase(passphrase)
        
        if user_id in self._pool_data:
            stored_hash = self._pool_data[user_id].get("passphrase_hash")
            if stored_hash and stored_hash != p_hash:
                return False, "Unauthorized: Incorrect profile passphrase.", {}
            return True, "Success", self._pool_data[user_id]
        else:
            # Register new profile with passphrase
            self._pool_data[user_id] = {"passphrase_hash": p_hash}
            return True, "Created new profile", self._pool_data[user_id]

    def verify_and_get_user_by_hash(self, user_id: str, p_hash: str) -> Tuple[bool, str, dict]:
        """Verifies profile against pre-computed passphrase hash (used in OAuth callbacks)."""
        user_id = user_id.strip()
        if not user_id or not p_hash:
            return False, "User ID and Passphrase hash cannot be empty.", {}
            
        self.load_pool()
        if user_id in self._pool_data:
            stored_hash = self._pool_data[user_id].get("passphrase_hash")
            if stored_hash and stored_hash != p_hash:
                return False, "Unauthorized: Incorrect profile passphrase.", {}
            return True, "Success", self._pool_data[user_id]
        else:
            # Register new profile
            self._pool_data[user_id] = {"passphrase_hash": p_hash}
            return True, "Created new profile", self._pool_data[user_id]

    def get_user_credentials(self, user_id: str, passphrase: Optional[str] = None) -> dict:
        """Retrieves credentials specifically for user_id. Optionally verifies passphrase."""
        self.load_pool() # Ensure we have latest remote updates
        creds = self._pool_data.get(user_id, {})
        if creds and passphrase:
            stored_hash = creds.get("passphrase_hash")
            if stored_hash and stored_hash != hash_passphrase(passphrase):
                logger.warning("🚫 Unauthorized credentials access attempt for user: %s", user_id)
                return {}
        return creds

    def add_user_credentials(self, user_id: str, passphrase: str, apify_token: str, instagram_cookie: str) -> Tuple[bool, str]:
        """Registers or updates credentials for a user after verifying passphrase."""
        success, msg, user_data = self.verify_and_get_user(user_id, passphrase)
        if not success:
            return False, msg
            
        # Standardize inputs
        user_data["apify_token"] = apify_token.strip()
        user_data["instagram_cookie"] = instagram_cookie.strip()
        
        # Clean up empty values
        if not user_data.get("apify_token"):
            user_data.pop("apify_token", None)
        if not user_data.get("instagram_cookie"):
            user_data.pop("instagram_cookie", None)
            
        return self.save_pool()

    def add_telegram_chat_id(self, user_id: str, passphrase: str, telegram_chat_id: str) -> Tuple[bool, str]:
        """Registers or updates custom Telegram chat ID specifically for a user after verifying passphrase."""
        success, msg, user_data = self.verify_and_get_user(user_id, passphrase)
        if not success:
            return False, msg
            
        user_data["telegram_chat_id"] = telegram_chat_id.strip()
        if not telegram_chat_id:
            user_data.pop("telegram_chat_id", None)
            
        return self.save_pool()

    def add_social_credentials(self, user_id: str, passphrase: str, platform: str, refresh_token: str) -> Tuple[bool, str]:
        """Registers or updates OAuth refresh tokens for a user's social platform after verifying passphrase."""
        if platform not in ["youtube", "instagram", "github"]:
            return False, f"Unsupported platform: {platform}"
            
        success, msg, user_data = self.verify_and_get_user(user_id, passphrase)
        if not success:
            return False, msg
            
        if "socials" not in user_data:
            user_data["socials"] = {}
            
        user_data["socials"][platform] = {
            "refresh_token": refresh_token.strip()
        }
        
        if not refresh_token:
            user_data["socials"].pop(platform, None)
        if not user_data["socials"]:
            user_data.pop("socials", None)
            
        return self.save_pool()

    def add_social_credentials_with_hash(self, user_id: str, p_hash: str, platform: str, refresh_token: str) -> Tuple[bool, str]:
        """Registers or updates OAuth refresh tokens using pre-computed passphrase hash (for OAuth callbacks)."""
        if platform not in ["youtube", "instagram", "github"]:
            return False, f"Unsupported platform: {platform}"
            
        success, msg, user_data = self.verify_and_get_user_by_hash(user_id, p_hash)
        if not success:
            return False, msg
            
        if "socials" not in user_data:
            user_data["socials"] = {}
            
        user_data["socials"][platform] = {
            "refresh_token": refresh_token.strip()
        }
        
        if not refresh_token:
            user_data["socials"].pop(platform, None)
        if not user_data["socials"]:
            user_data.pop("socials", None)
            
        return self.save_pool()

    def get_next_rotated_credentials(self) -> dict:
        """Rotates and retrieves the next valid set of credentials for admin load balancing."""
        self.load_pool()
        if not self._pool_data:
            return {}
            
        users = list(self._pool_data.keys())
        if self._rotation_index >= len(users):
            self._rotation_index = 0
            
        user_id = users[self._rotation_index]
        self._rotation_index = (self._rotation_index + 1) % len(users)
        
        logger.info("🔄 Rotated to credentials of user: %s", user_id)
        return self._pool_data[user_id]

    def get_cookie_file_path(self, user_id: str, cookie_string: str) -> Optional[str]:
        """
        Parses a raw cookie string and writes it to a temporary Netscape cookies file
        so that it is fully compatible with yt-dlp.
        """
        if not cookie_string:
            return None
            
        cookie_file = os.path.join(COOKIE_CACHE_DIR, f"cookies_{user_id}.txt")
        try:
            # Check if it already looks like a Netscape or JSON format
            if cookie_string.strip().startswith("# Netscape") or cookie_string.strip().startswith("["):
                with open(cookie_file, "w", encoding="utf-8") as f:
                    f.write(cookie_string.strip())
                return cookie_file
                
            # If it's a raw cookie header string, parse and format it
            lines = ["# Netscape HTTP Cookie File\n"]
            # e.g., "sessionid=123; csrftoken=abc;"
            pairs = cookie_string.split(";")
            for pair in pairs:
                pair = pair.strip()
                if not pair or "=" not in pair:
                    continue
                name, value = pair.split("=", 1)
                name = name.strip()
                value = value.strip()
                # Use wildcard domain for Instagram
                lines.append(f".instagram.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
                
            with open(cookie_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
                
            logger.info("🍪 Formatted and wrote Netscape cookies file for %s", user_id)
            return cookie_file
        except Exception as e:
            logger.error("💥 Failed to write Netscape cookies file: %s", e)
            return None

# Global single instance
pool_manager = CredentialPoolManager()
