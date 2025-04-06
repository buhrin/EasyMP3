# EasyMP3 Downloader

## Disclaimer

This disclaimer is the only thing I typed by hand. Everything else in this repo is entirely vibe-coded with Windsurf and Google's Gemini 2.5 Pro model. Enjoy!

## Description

EasyMP3 is a simple desktop application for Windows that allows you to download the audio from YouTube videos as MP3 files. It automatically fetches the video thumbnail, crops it to a square, and embeds it into the downloaded MP3 file.

## Features

*   Download audio from YouTube URLs.
*   Automatically extracts audio to MP3 format.
*   Downloads and embeds the video thumbnail.
*   Crops the thumbnail to a square format before embedding.
*   Processes multiple downloads concurrently.
*   Simple interface with dark mode theme.
*   Downloads using URL from clipboard.
*   Option to clear completed/errored tasks from the list.
*   Overwrites existing files with the same name automatically.

## How to Use

1.  **Download the Latest Release:** Grab the `EasyMP3.exe` file from the [**GitHub Releases Page**](https://github.com/buhrin/EasyMP3/releases/latest).
2.  **Run the Executable:** Double-click `EasyMP3.exe` to start the application.
3.  **(Optional) Select Output Folder:** Use the "Browse..." button to choose where your MP3 files will be saved. By default, they are saved in the same folder as the executable.
4.  **Copy YouTube URL:** Copy the full URL of the YouTube video you want to download to your clipboard (e.g., `https://www.youtube.com/watch?v=dQw4w9WgXcQ`).
5.  **Download:** Click the "Download from Clipboard" button. The application will validate the URL and add the download task to the list below.
6.  **Monitor Progress:** The list shows the status of each download (Queued, Processing, Completed, Error). Filenames appear once the download starts.
7.  **(Optional) Clear List:** Click the "Clear Completed" button to remove any tasks marked as "Completed" or "Error" from the list.
8.  **Closing:** Close the application window. If downloads are in progress, you'll be asked to confirm. Ongoing downloads will continue in the background until finished.

## Dependencies

The application relies on external tools:

*   **yt-dlp:** For downloading video/audio from YouTube.
*   **ffmpeg:** For audio extraction, thumbnail processing, and embedding.

These tools are bundled with the executable in the `bin` directory and do not need to be installed separately by the user.

## Building from Source (Optional)

If you want to build the executable yourself:

1.  Clone the repository.
2.  Ensure you have Python 3 installed.
3.  Install dependencies: `pip install pyinstaller pyperclip sv_ttk`
4.  Make sure `yt-dlp.exe` and `ffmpeg.exe` are present in a `bin` directory in the project root.
5.  Run PyInstaller from the project root directory:
    ```bash
    pyinstaller --onefile --windowed --name EasyMP3 --add-data "bin;bin" src/main.py
    ```
6.  The executable will be in the `dist` folder.
