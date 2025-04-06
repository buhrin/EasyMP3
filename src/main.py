import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def get_script_directory():
    """Gets the directory containing the running script or frozen executable."""
    if getattr(sys, 'frozen', False):
        # The application is frozen (packaged by PyInstaller)
        return Path(sys.executable).parent
    else:
        # The application is running as a normal Python script
        return Path(__file__).parent.parent # Go up two levels (src -> project root)

SCRIPT_DIR = get_script_directory()
BIN_DIR = SCRIPT_DIR / "bin"
YT_DLP_PATH = BIN_DIR / "yt-dlp.exe"
FFMPEG_PATH = BIN_DIR / "ffmpeg.exe"

def check_dependencies():
    """Checks if required executables exist."""
    if not YT_DLP_PATH.is_file():
        print(f"Error: yt-dlp.exe not found in {BIN_DIR}")
        sys.exit(1)
    if not FFMPEG_PATH.is_file():
        print(f"Error: ffmpeg.exe not found in {BIN_DIR}")
        sys.exit(1)
    print("Dependencies found.")

def download_audio(link, output_dir):
    """Downloads audio for a single link using yt-dlp."""
    print(f"Starting download for: {link.strip()}")
    output_template = output_dir / "%(channel)s - %(title)s.%(ext)s"
    output_template_final = output_dir / "%(channel)s - %(title)s.mp3"

    command = [
        str(YT_DLP_PATH),
        "-f", "bestaudio/best",
        "-q", # Quiet
        # "-ciw", # --continue --ignore-errors --write-info-json - Replaced by trying individually
        "--ignore-errors",
        "-o", str(output_template),
        "-O", str(output_template_final), # Specify final mp3 name for download stage
        "--no-simulate",
        "--embed-thumbnail",
        "--extract-audio",
        "--audio-quality", "0",
        "--audio-format", "mp3",
        link.strip()
    ]

    try:
        # Use CREATE_NO_WINDOW on Windows to prevent console windows popping up
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(command, check=True, capture_output=True, text=True, creationflags=creationflags)
        print(f"Finished download for: {link.strip()}")
        # print(result.stdout)
        # print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error downloading {link.strip()}: {e}")
        print(f"Stderr: {e.stderr}")
    except Exception as e:
        print(f"An unexpected error occurred during download for {link.strip()}: {e}")

def crop_thumbnail(mp3_file):
    """Extracts, crops, and re-embeds the thumbnail for an MP3 file."""
    if not mp3_file.exists() or mp3_file.suffix.lower() != '.mp3':
        print(f"Skipping invalid file: {mp3_file}")
        return

    print(f"Processing thumbnail for: {mp3_file.name}")
    base_name = mp3_file.stem
    temp_image_name = mp3_file.with_name(f"{base_name}_temp.jpg")
    cropped_image_name = mp3_file.with_name(f"{base_name}_temp_cropped.jpg")
    final_track_name = mp3_file.with_name(f"{base_name}_temp_final.mp3")

    try:
        # Use CREATE_NO_WINDOW on Windows to prevent console windows popping up
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        # 1. Extract thumbnail
        cmd_extract = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3_file), str(temp_image_name)]
        subprocess.run(cmd_extract, check=True, creationflags=creationflags)

        # 2. Crop thumbnail
        cmd_crop = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(temp_image_name), "-vf", "crop=ih:ih", str(cropped_image_name)]
        subprocess.run(cmd_crop, check=True, creationflags=creationflags)

        # 3. Re-embed cropped thumbnail
        cmd_embed = [
            str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(mp3_file),
            "-i", str(cropped_image_name),
            "-map_metadata", "0",
            "-map_metadata:s:1", "0:s:1", # Map image metadata
            "-map", "0:a", # Map audio stream
            "-map", "1",   # Map new image stream
            "-acodec", "copy",
            str(final_track_name)
        ]
        subprocess.run(cmd_embed, check=True, creationflags=creationflags)

        # 4. Cleanup and rename
        os.remove(temp_image_name)
        os.remove(cropped_image_name)
        os.remove(mp3_file)
        os.rename(final_track_name, mp3_file)
        print(f"Successfully processed thumbnail for: {mp3_file.name}")

    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error processing {mp3_file.name}: {e}")
        # Cleanup partial files if error occurred
        if temp_image_name.exists(): os.remove(temp_image_name)
        if cropped_image_name.exists(): os.remove(cropped_image_name)
        if final_track_name.exists(): os.remove(final_track_name)
    except Exception as e:
        print(f"An unexpected error occurred processing {mp3_file.name}: {e}")
        # Cleanup partial files if error occurred
        if temp_image_name.exists(): os.remove(temp_image_name)
        if cropped_image_name.exists(): os.remove(cropped_image_name)
        if final_track_name.exists(): os.remove(final_track_name)

def main():
    parser = argparse.ArgumentParser(description="Download YouTube audio and crop thumbnails.")
    parser.add_argument("--links", required=True, help="Path to the text file containing YouTube links (one per line).")
    parser.add_argument("--output", required=True, help="Path to the directory to save downloaded and processed MP3 files.")
    parser.add_argument("--exclude", default="timo", help="Comma-separated list of directory names to exclude during cropping (e.g., 'timo,archive'). Default: 'timo'.")
    parser.add_argument("--threads", type=int, default=10, help="Number of parallel downloads. Default: 10.")
    parser.add_argument("--skip-download", action="store_true", help="Skip the download step and only perform cropping.")
    parser.add_argument("--skip-crop", action="store_true", help="Skip the cropping step and only perform downloads.")

    args = parser.parse_args()

    links_file = Path(args.links)
    output_dir = Path(args.output)
    exclude_dirs = {ex.strip() for ex in args.exclude.split(',')} if args.exclude else set()

    check_dependencies()

    if not links_file.is_file():
        print(f"Error: Links file not found at {links_file}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Download Step ---
    if not args.skip_download:
        print("--- Starting Download Phase ---")
        with open(links_file, 'r') as f:
            links = f.readlines()

        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            # Create a list of futures
            futures = [executor.submit(download_audio, link, output_dir) for link in links if link.strip()]
            # Wait for all futures to complete (optional, but good practice)
            for future in futures:
                future.result() # Can capture return values or exceptions here if needed
        print("--- Download Phase Complete ---")
    else:
        print("--- Skipping Download Phase ---")

    # --- Cropping Step ---
    if not args.skip_crop:
        print("--- Starting Cropping Phase ---")
        files_to_process = []
        for item in output_dir.rglob('*.mp3'):
            if item.is_file():
                # Check if any part of the path contains an excluded directory name
                if not any(excluded in item.parts for excluded in exclude_dirs):
                    files_to_process.append(item)
                else:
                    print(f"Skipping {item} due to exclusion rules.")

        # Crop sequentially for now, parallelizing ffmpeg can be tricky
        print(f"Found {len(files_to_process)} MP3 files to process for cropping.")
        for mp3_file in files_to_process:
            crop_thumbnail(mp3_file)

        print("--- Cropping Phase Complete ---")
    else:
        print("--- Skipping Cropping Phase ---")

    print("All tasks finished.")

if __name__ == "__main__":
    main()
