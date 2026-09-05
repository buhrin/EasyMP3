# EasyMP3 Chrome extension

Release users extract both ZIP files directly into `%LOCALAPPDATA%\EasyMP3`,
then load `%LOCALAPPDATA%\EasyMP3\extension` at `chrome://extensions`. The helper
must be at `%LOCALAPPDATA%\EasyMP3\native-host\EasyMP3Host.exe`. Run the adjacent
`install-native-host.ps1` with the displayed extension ID.

During development, load this `extension` directory once. After changing its
JavaScript, CSS, HTML, or icons, select **Reload** on the existing extension
card and refresh open YouTube and Shazam tabs. Do not load a second copy. These
changes do not require a helper rebuild. Run the browser tests from the repo
root with:

```powershell
npm ci --prefix extension
npm test --prefix extension
```

Use the popup to choose an output folder and enable or disable Shazam redirects.
See the root README for full installation, helper rebuild, update, and removal
instructions.
