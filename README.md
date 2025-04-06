# EasyMP3 Downloader & Cropper

This tool downloads audio from YouTube links, extracts MP3s, embeds thumbnails, and crops the thumbnails to be square.

## Setup

1.  **Create `bin` Directory:** Create a `bin` directory in the project root (`EasyMP3/bin`).
2.  **Download Dependencies:**
    *   Download the latest Windows executable for `yt-dlp` from its [official releases page](https://github.com/yt-dlp/yt-dlp/releases).
    *   Download the latest Windows `ffmpeg` essentials build from [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (e.g., `ffmpeg-release-essentials.zip`). Extract it.
3.  **Place Executables in `bin`:**
    *   Place `yt-dlp.exe` into the `bin` directory.
    *   Find `ffmpeg.exe` inside the extracted ffmpeg folder (usually in its `bin` subdirectory) and place it into the project's `bin` directory.

## Usage (Development)

```bash
python src/main.py
```
This will launch the graphical interface.

## Building the Executable

1.  Install PyInstaller:
    ```bash
python -m pip install pyinstaller
    ```
2.  Run PyInstaller:
    ```bash
pyinstaller --noconsole --onefile --add-data "bin/yt-dlp.exe;bin" --add-data "bin/ffmpeg.exe;bin" src/main.py -n EasyMP3
    ```
    *   `--noconsole` (or `-w`) hides the background command prompt window when the `.exe` is run.
    This will create an `EasyMP3.exe` file in the `dist` directory.

## Usage (Executable)

Navigate to the `dist` folder and double-click `EasyMP3.exe`.
*   Enter a YouTube URL.
*   Browse for an output folder (defaults to the folder containing `EasyMP3.exe`).
*   Click "Start Download & Crop".
*   Monitor the status window for progress.
