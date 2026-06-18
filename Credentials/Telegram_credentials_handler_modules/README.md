# Telegram Credentials Handler Module

This directory manages the secure storage, encryption, rotation, and Telegram-backed syncing of user credentials (such as Apify API tokens, Instagram cookies, and OAuth refresh tokens).

## Architecture & Integration with `Download_Modules`

The components in this directory work in close integration with the server and downloader modules in `Download_Modules` to deliver isolated, secure, and zero-maintenance credential onboarding.

Below is a detailed breakdown of how they connect:

### 1. Onboarding & OAuth Token Acquisition (`Download_Modules` → `Credentials`)
- **Flask GUI Server (`Download_Modules/web_harvester.py`)**: Defines endpoints for submitting credentials (`/api/credentials/submit` and `/api/credentials/telegram`) and starting the OAuth connection flow for YouTube, Instagram, and GitHub.
- **Callback Capturing**: Once the user approves permissions on the provider's consent page, Google, Facebook, or GitHub redirects to the callback routes in the Flask web harvester. The harvester exchanges the authorization code for a long-lived credentials token.
- **Syncing to Pool**: The web harvester invokes the global `pool_manager` from `Credentials/Telegram_credentials_handler_modules/credential_pool_manager.py` to register or update these tokens for the given `user_id`.

### 2. Encryption & Decryption (`Credentials`)
- **Passphrase derivation**: `credential_pool_manager.py` reads `CREDENTIALS_ENCRYPTION_KEY` from the environment (loaded from `Credentials/.env`).
- **AES Encryption (`Credentials/Telegram_credentials_handler_modules/encryption_engine.py`)**: Provides clean `encrypt_data` and `decrypt_data` functions using `cryptography.fernet` (AES-128 in CBC mode) or PBKDF2 standard derivation to cryptographically protect the JSON credentials file before saving it to disk.

### 3. Remote Cloud Syncing (`Credentials` ↔ `Download_Modules`)
- **Telegram Backups**: The `pool_manager` references `TelegramBackupManager` from `Download_Modules/Downloader_db/telegram_backup_for_downloads.py`.
- **Saving Pool**: When user credentials update, they are saved locally as `cache/credentials_pool.json.enc` and immediately uploaded to a locked Telegram private chat. The resulting Telegram `file_id` is pinned inside the SQLite index database (`Download_Modules/Downloader_db/index.db`) in the `system_config` table.
- **Loading Pool**: When the application boots or requests credentials, it checks the SQLite database for a pinned `credentials_file_id`, downloads the encrypted JSON file from Telegram to `cache/credentials_pool.json.enc`, and decrypts it into memory.

### 4. Fetching Credentials During Downloads (`Download_Modules` → `Credentials`)
- **Apify Downloader (`Download_Modules/apify_downloader.py`)**: When running an Apify scraper, the script queries `pool_manager.get_user_credentials(user_id)` to run the actor using that specific user's token.
- **Video Downloader (`Download_Modules/downloader.py`)**: When downloading a video via `yt-dlp` (especially for private/restricted Reels), the script queries `pool_manager` to obtain the user's Instagram cookies.
- **Cookie Parsing**: The `pool_manager` parses the raw cookie headers, formats them into standard Netscape cookie format, writes them to a temporary file (`cache/cookies_[user_id].txt`), and returns the path for `yt-dlp` to consume securely.

---

## Data Flow Diagram

```
   [Web Browser GUI] 
          │
          │ Submit Credentials / OAuth
          ▼
   [Download_Modules/web_harvester.py]
          │
          │ pool_manager.add_social_credentials()
          ▼
   [Credentials/Telegram_credentials_handler_modules/credential_pool_manager.py]
          │
          ├─► Encrypt JSON pool using encryption_engine.py
          │
          ├─► Save locally to cache/credentials_pool.json.enc
          │
          └─► Upload via Download_Modules/Downloader_db/telegram_backup_for_downloads.py
                    │
                    ▼
             [Telegram Cloud] (Isolated private chat backup)
```
