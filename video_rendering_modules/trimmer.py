import os
import subprocess
import logging

logger = logging.getLogger("trimmer")

def trim_video(input_path: str, start_time: float = 0, end_time: float = None) -> str:
    """
    Trims a video using FFmpeg.
    - input_path: Path to the source video.
    - start_time: Start offset in seconds.
    - end_time: End time in seconds (not duration).
    Returns the path to the trimmed video.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir = os.path.join(os.path.dirname(input_path), "trimmed")
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.basename(input_path)
    output_path = os.path.join(output_dir, f"trimmed_{base_name}")

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
    ]
    
    if end_time is not None:
        duration = end_time - start_time
        if duration <= 0:
            raise ValueError("End time must be greater than start time.")
        cmd.extend(["-t", str(duration)])

    cmd.extend([
        "-i", input_path,
        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
        "-c:a", "copy",
        output_path
    ])

    logger.info(f"🎬 Trimming video: {input_path} -> {output_path} ({start_time}s to {end_time}s)")
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ FFmpeg Trimming Failed: {e.stderr.decode()}")
        raise RuntimeError(f"FFmpeg trim failed: {e.stderr.decode()}")

if __name__ == "__main__":
    # Quick test if run standalone
    logging.basicConfig(level=logging.INFO)
    print("AMTCE Trimmer Module")
