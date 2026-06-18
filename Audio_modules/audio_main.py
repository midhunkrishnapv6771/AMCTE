"""
audio_main.py — Consolidated Entry Point for Audio Modules
==========================================================
Routes execution to BeatEngine transient analysis or Audio Pool Manager tracking.
Centralizes sys.path initialization.
"""

import os
import sys
import argparse

# Setup python path once for all sub-imports
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

for folder in [".", "Audio_modules", "video_rendering_modules", "Media_guards", "router", "logs_and_tracker"]:
    path = os.path.abspath(os.path.join(PROJECT_ROOT, folder))
    if path not in sys.path:
        sys.path.insert(0, path)

def run_beat_analysis(audio_path):
    if not os.path.exists(audio_path):
        print(f"❌ Error: Audio file not found: {audio_path}")
        return
    print(f"🎵 Extracting BPM and transient grids for: {audio_path}")
    from beat_engine import BeatEngine
    engine = BeatEngine()
    beats = engine.analyze_beats(audio_path)
    if beats:
        print(f"✅ Transient detection successful! Found {len(beats)} beats/transients.")
        print(f"ℹ️ First few beats (seconds): {beats[:10]}")
    else:
        print("❌ Transient detection returned no results.")

def run_pool_add(video_path):
    if not os.path.exists(video_path):
        print(f"❌ Error: Video file not found: {video_path}")
        return
    print(f"🔊 Extracting original audio track from: {video_path}")
    from audio_pool_manager import pool_manager
    track_path = pool_manager.track_video(video_path)
    if track_path:
        print(f"✅ Audio extracted and registered successfully: {track_path}")
    else:
        print("❌ Audio extraction or registration failed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🎵 AMTCE Audio Suite Main Controller")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to run")

    # Command: beat
    beat_parser = subparsers.add_parser("beat", help="Analyze beats and transients of an audio track")
    beat_parser.add_argument("audio_path", type=str, help="Path to input audio file (.mp3, .wav)")

    # Command: track
    track_parser = subparsers.add_parser("track", help="Extract audio from a downloaded video and register it to the pool")
    track_parser.add_argument("video_path", type=str, help="Path to input video file (.mp4)")

    args = parser.parse_args()

    if args.command == "beat":
        run_beat_analysis(args.audio_path)
    elif args.command == "track":
        run_pool_add(args.video_path)
