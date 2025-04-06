# EasyMP3 Downloader & Cropper

This tool downloads audio from YouTube links, extracts MP3s, embeds thumbnails, and crops the thumbnails to be square.

## Setup

1.  **Create Directories:**
    *   Create a `src` directory for the Python code (if it doesn't exist).
    *   Create a `bin` directory in the project root.
2.  **Download Dependencies:**
    *   Download the latest Windows executable for `yt-dlp` from [https://github.com/yt-dlp/yt-dlp/releases](https://github.com/yt-dlp/yt-dlp/releases).
    *   Download the latest Windows `ffmpeg` essentials build from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) (e.g., `ffmpeg-release-essentials.zip`). Extract it.
3.  **Place Executables:**
    *   Place `yt-dlp.exe` into the `bin` directory.
    *   Find `ffmpeg.exe` inside the extracted ffmpeg folder (usually in its `bin` subdirectory) and place it into the project's `bin` directory.
4.  **Prepare Links:**
    *   Edit `links.txt` and add the YouTube video URLs you want to download, one URL per line.
5.  **Install Python Dependencies (for development):**
    ```bash
    pip install -r requirements.txt
    ```

## Usage (Development)

```bash
python src/main.py --links links.txt --output "path/to/your/music/folder"
```

## Building the Executable

1.  Install PyInstaller:
    ```bash
    pip install pyinstaller
    ```
2.  Run PyInstaller:
    ```bash
    pyinstaller --onefile --add-data "bin/yt-dlp.exe;bin" --add-data "bin/ffmpeg.exe;bin" src/main.py -n EasyMP3
    ```
    This will create an `EasyMP3.exe` file in the `dist` directory.

## Usage (Executable)

```bash
EasyMP3.exe --links links.txt --output "path/to/your/music/folder"
```
