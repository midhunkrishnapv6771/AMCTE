# 📥 Download Modules (The Harvester)

This directory houses the **Harvester** domain—the front-line media extraction pipeline of the AMTCE engine. It is responsible for fetching high-quality social clips (Instagram Reels, TikToks, YouTube Shorts, etc.) and verifying they haven't been downloaded or processed before.

---

## 📁 Directory Structure & Components

For a standard technical overview, here is what is inside this directory:
- **`downloader_main.py`**: The unified console wrapper. All CLI/GUI operations should run through this file.
- **`downloader.py`**: Core downloader logic (uses `yt-dlp` underneath with auth-fallbacks and transaction guards).
- **`web_harvester.py`**: The Flask server hosting the premium glassmorphic visual interface.
- **`apify_downloader.py`**: Scraper integrations and account scheduler algorithms.
- **`actress_ledger.py`**: Deduplication registry managing historical reel hashes and shortcodes.
- **`Downloader_db/`**: Houses the SQLite transaction index database (`index.db`).

---

## ⚙️ Path Scoping (Where files go)

To keep the codebase cleanly organized, database and media paths are redirected to dedicated directories:
1. **SQLite Database Index:** Stored in `Download_Modules/Downloader_db/index.db`.
2. **Visual Fingerprints Cache:** Stored in the project root `/cache/video_fingerprint_db.json`.
3. **Downloaded Media:** Scoped to the project root `/downloads/`.
4. **Extracted Audio:** Scoped to the project root `/Original_audio/`.

---

## 🚀 Step-by-Step Usage

### 1. Installation
Install core dependencies inside the virtual environment:
```bash
pip install flask yt-dlp opencv-python numpy scipy open-clip-torch torch
```

### 2. Run the Glassmorphic Web Harvester GUI
Launches the Flask web server at `http://127.0.0.1:5000`:
```powershell
$env:PYTHONIOENCODING="utf-8"; python Download_Modules/downloader_main.py gui
```

### 3. Run Standalone CLI Downloads
Download a video from a direct Instagram/TikTok/YouTube URL:
```powershell
$env:PYTHONIOENCODING="utf-8"; python Download_Modules/downloader_main.py download "https://www.instagram.com/reel/example_id/"
```
*Optional: Add `--title "custom_alias"` to customize the file name.*

### 4. Check the Actress Ledger for Duplicates
Inspect if a reel has already been seen/processed in the database:
```powershell
$env:PYTHONIOENCODING="utf-8"; python Download_Modules/downloader_main.py ledger "https://www.instagram.com/reel/example_id/"
```

### 5. Python API Usage
Incorporate the harvester directly into other pipeline modules:
```python
from downloader import download_video

# Returns (file_path, is_cached)
file_path, is_cached = download_video("https://www.instagram.com/reel/example_id/")
```
