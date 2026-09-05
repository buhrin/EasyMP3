## Disclaimer

This disclaimer is the only thing I typed by hand. Everything else in this repo is entirely vibe-coded with Windsurf and Google's Gemini 2.5 Pro model. Enjoy!

## EasyMP3 Downloader

### Description

EasyMP3 is a simple desktop application for Windows that allows you to download the audio from YouTube videos as MP3 files. It automatically fetches the video thumbnail, crops it to a square, and embeds it into the downloaded MP3 file.

### Features

*   Download audio from YouTube URLs.
*   Expand YouTube playlist URLs into individual song downloads.
*   Automatically extracts audio to MP3 format.
*   Downloads and embeds the video thumbnail.
*   Crops the thumbnail to a square format before embedding.
*   Processes multiple downloads concurrently.
*   Simple interface with dark mode theme.
*   Downloads using URL from clipboard.
*   Prompts when a copied watch URL also belongs to a playlist, so you can choose a single track or the full playlist.
*   Confirms playlist title and item count before queueing a full playlist.
*   Option to clear completed/errored tasks from the list.
*   Overwrites existing files with the same name automatically.

### How to Use

1.  **Download the Latest Release:** Grab the `EasyMP3.exe` file from the [**GitHub Releases Page**](https://github.com/buhrin/EasyMP3/releases/latest).
2.  **Run the Executable:** Double-click `EasyMP3.exe` to start the application.
3.  **(Optional) Select Output Folder:** Use the "Browse..." button to choose where your MP3 files will be saved. By default, they are saved in the same folder as the executable.
4.  **Copy YouTube URL:** Copy a YouTube video URL or playlist URL to your clipboard.
5.  **Download:** Click the "Download from Clipboard" button.
6.  **Choose Behavior for Ambiguous URLs:** If the URL points to a video that also belongs to a playlist, the app asks whether you want just that video or the full playlist.
7.  **Confirm Playlist Queueing:** For playlist URLs, the app inspects the playlist first, then shows the playlist title plus how many tracks will be queued before adding them.
8.  **Monitor Progress:** The list shows the status of each download (Queued, Processing, Completed, Error). Filenames appear once the download starts.
9.  **(Optional) Clear List:** Click the "Clear Completed" button to remove any tasks marked as "Completed" or "Error" from the list.
10. **Closing:** Close the application window. If downloads are in progress, you'll be asked to confirm. Ongoing downloads will continue in the background until finished.

### Playlist Notes

*   Playlist items are expanded into individual task rows so each track keeps its own status.
*   Private, deleted, or otherwise unavailable playlist entries are skipped when the playlist is inspected.
*   Tracks already queued or completed during the current app session are skipped when queueing a playlist.

### Dependencies

The application relies on external tools:

*   **yt-dlp:** For downloading video/audio from YouTube.
*   **ffmpeg:** For audio extraction, thumbnail processing, and embedding.

These tools are bundled with the executable in the `bin` directory and do not need to be installed separately by the user.

### Building from Source (Optional)

If you want to build the executable yourself:

1.  Clone the repository.
2.  Install uv and Python 3.14 with Tk support.
3.  Install the locked dependencies: `uv sync --locked`
4.  Make sure `yt-dlp.exe` and `ffmpeg.exe` are present in a `bin` directory in the project root.
5.  Run PyInstaller from the project root directory:
    ```powershell
    uv run --locked pyinstaller --onefile --windowed --name EasyMP3 --icon=src/assets/icon.ico --add-data "bin;bin" --add-data "src/assets;assets" src/main.py
    ```
6.  The executable will be in the `dist` folder.

Python dependencies are managed with uv. To update them, run `uv lock --upgrade`,
then `uv sync --locked` and the tests below. Commit both `pyproject.toml` (if
changed) and `uv.lock`. Node.js test dependencies are managed separately with
npm in `extension`.

Generated folders have these purposes:

* `build/`: temporary PyInstaller work files. These can be deleted after a build.
* `dist/`: built executables and the helper's required runtime files. Keep the
  whole `dist/EasyMP3Host` folder together when using that helper build.
* `package/`: release ZIP files made by `scripts/package_release.py`.

Keep test downloads and experiments in a separate temporary folder, not in
`build/`, `dist/`, or `package/`. Remove that folder when testing is complete.

### Chrome extension (private Windows install)

The browser integration uses Chrome Native Messaging. Chrome starts the helper
when the extension connects, and the helper exits after Chrome disconnects.
The extension keeps its output folder separately from the desktop app. Its
default folder is `%USERPROFILE%\Music`.

The helper allows up to ten active downloads, matching the desktop app. Closing
Chrome ends the helper and its child processes; queued work is not resumed. This
is a private, unpacked extension and has not been tested for the Chrome Web
Store.

#### Install a release

1. Download `EasyMP3-native-host.zip` and `EasyMP3-extension.zip` from the same
   release.
2. Extract **both ZIP files directly into** `%LOCALAPPDATA%\EasyMP3`. The result
   must contain these exact paths:

   ```text
   %LOCALAPPDATA%\EasyMP3\native-host\EasyMP3Host.exe
   %LOCALAPPDATA%\EasyMP3\extension\manifest.json
   ```

3. Open `chrome://extensions`, enable **Developer mode**, choose **Load
   unpacked**, and select `%LOCALAPPDATA%\EasyMP3\extension`.
4. Copy the extension ID displayed by Chrome. Replace the example ID below and
   run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\EasyMP3\native-host\install-native-host.ps1" -ExtensionId aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
   ```

5. Select **Reload** on the EasyMP3 extension card. Refresh any YouTube or
   Shazam tabs that were already open.

Python, yt-dlp, and FFmpeg do not need separate installation.

#### Update and test the extension

To install a newer release, close Chrome, extract both new ZIP files into
`%LOCALAPPDATA%\EasyMP3` and replace the existing files. Open Chrome, select
**Reload** on the existing EasyMP3 card at `chrome://extensions`, then refresh
open YouTube and Shazam tabs. Do not use **Load unpacked** again: keeping the
same loaded folder preserves the extension ID. Run `install-native-host.ps1`
again only if the ID or helper path changed.

For extension-only source changes (JavaScript, CSS, HTML, or icons), load the
repository's `extension` folder once. After each change, select **Reload** on
the existing card and refresh the test tabs. The helper does not need a rebuild
for these changes. If Chrome uses an extracted copy, copy the changed extension
files into that same loaded folder before reloading. Chrome shows the loaded
folder on the extension's **Details** page. If you switch to the repository
folder, remove the old extension copy and register the new extension ID with
the helper installer.

Run the tests from the repository root with Node.js, uv, and Python installed:

```powershell
npm ci --prefix extension
npm test --prefix extension
uv sync --locked
uv run --locked python -m unittest discover -s tests
```

Rebuild the helper only after Python code or its bundled dependencies change:

```powershell
uv run --locked pyinstaller --onedir --console --name EasyMP3Host --add-data "bin;bin" src/native_host.py
uv run --locked python scripts/package_release.py --output package
```

For a source checkout (or the local builds already in `dist`):

1. Build the helper from the repository root, unless it is already built:

   ```powershell
   uv run --locked pyinstaller --onedir --console --name EasyMP3Host --add-data "bin;bin" src/native_host.py
   ```

2. Keep the helper in `dist\EasyMP3Host`, or copy its contents so that
   `EasyMP3Host.exe` is directly inside `%LOCALAPPDATA%\EasyMP3\native-host`.
3. In Chrome, open `chrome://extensions`, enable **Developer mode**, choose
   **Load unpacked**, and select this repository's `extension` directory.
4. Copy the extension ID shown by Chrome. Run the installer from the repository
   root. Pass `-InstallRoot .\dist\EasyMP3Host` if the helper remains in `dist`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\install-native-host.ps1 -ExtensionId aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -InstallRoot .\dist\EasyMP3Host
   ```

5. Reload the extension. Open a YouTube video and use **Download MP3**.

#### Remove all installed files

1. Close Chrome and wait for current downloads to stop. In Task Manager, confirm
   that `EasyMP3Host.exe`, `yt-dlp.exe`, and `ffmpeg.exe` are no longer running.
2. Open `chrome://extensions` and select **Remove** on EasyMP3.
3. Remove the Native Messaging registration **before** deleting its files:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\EasyMP3\native-host\uninstall-native-host.ps1"
```

4. Delete `%LOCALAPPDATA%\EasyMP3`. This removes the helper, extension copy,
   registration manifest, and extension settings. If you installed the desktop
   `EasyMP3.exe`, delete that separately together with shortcuts you created.
   Downloaded release ZIP files and a source checkout can also be deleted if no
   longer needed.

Downloaded MP3 files are user data and are never removed by these steps. A
sudden stop can leave a directory named `.easymp3-*` **inside the output folder
selected when that job was queued** (for example,
`%USERPROFILE%\Music\.easymp3-abc123`). After all helper and download processes
have stopped, inspect each folder you used and remove only confirmed leftover
`.easymp3-*` directories. The desktop executable can also leave a PyInstaller
`_MEI*` folder under `%TEMP%` after a crash. Normal exit removes that folder.
Only remove a leftover folder if you can confirm it belongs to EasyMP3; other
apps use the same naming scheme.
