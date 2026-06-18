"""
downloader_main.py — Consolidated Entry Point for Download Modules
==================================================================
Routes execution to Web Harvester GUI, Standalone CLI Downloader, or Ledger checks.
Centralizes sys.path initialization.
"""

import os
import sys
import argparse

# Setup python path once for all sub-imports
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

# ── LOAD ENV EARLY ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_path = os.path.join(PROJECT_ROOT, "Credentials", ".env")
    if os.path.exists(_env_path):
        _load_dotenv(_env_path, override=False)
except Exception:
    pass
# ─────────────────────────────────────────────────────────────────────────────

for folder in [".", "Audio_modules", "video_rendering_modules", "Media_guards", "router", "logs_and_tracker"]:
    path = os.path.abspath(os.path.join(PROJECT_ROOT, folder))
    if path not in sys.path:
        sys.path.insert(0, path)

def run_gui():
    flask_host = os.environ.get("FLASK_HOST", "127.0.0.1")
    flask_port = int(os.environ.get("FLASK_PORT", 5000))
    flask_debug = os.environ.get("FLASK_DEBUG", "False").strip().lower() in ("true", "1", "yes")
    print(f"🚀 Starting Web Harvester Server on http://{flask_host}:{flask_port} (debug={flask_debug})")
    # Import locally after sys.path is updated
    from web_harvester import app
    app.run(host=flask_host, port=flask_port, debug=flask_debug, use_reloader=False)

def run_download(url, title=None):
    print(f"📥 Initiating download request for: {url}")
    from downloader import download_video
    result = download_video(url, custom_title=title)
    if result and result[0]:
        print(f"✅ Harvest successful! File located at: {result[0]} (Cache hit: {result[1]})")
    else:
        print("❌ Harvest failed: site not supported, timeout, or invalid URL.")

def run_ledger(url):
    from actress_ledger import get_ledger, extract_shortcode
    sc = extract_shortcode(url)
    if sc:
        seen = get_ledger().shortcode_seen(sc)
        if seen:
            print(f"🚫 [LEDGER] Duplicate detected! Shortcode '{sc}' has already been downloaded.")
        else:
            print(f"✅ [LEDGER] Shortcode '{sc}' is new and safe to process.")
    else:
        print("❌ [LEDGER] Could not parse Instagram shortcode from URL.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🎬 AMTCE Downloader Suite Main Controller")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to run")

    # Command: gui
    subparsers.add_parser("gui", help="Launch the web-based glassmorphic Harvester UI")

    # Command: download
    dl_parser = subparsers.add_parser("download", help="Download a video clip using CLI")
    dl_parser.add_argument("url", type=str, help="Target URL (Instagram, TikTok, YouTube, etc.)")
    dl_parser.add_argument("--title", "-t", type=str, default=None, help="Custom title/alias for downloaded video")

    # Command: ledger
    ledger_parser = subparsers.add_parser("ledger", help="Check actress ledger for duplicate URL/shortcode")
    ledger_parser.add_argument("url", type=str, help="Video URL to check")

    args = parser.parse_args()

    if args.command == "gui":
        run_gui()
    elif args.command == "download":
        run_download(args.url, args.title)
    elif args.command == "ledger":
        run_ledger(args.url)
