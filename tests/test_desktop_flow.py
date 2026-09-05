import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import app as app_module
from app import EasyMP3App
from utils import ParsedYouTubeUrl
from ytdlp_wrapper import PlaylistEntry, PlaylistInspectionResult


VIDEO_ID = "abcdefghijk"
PLAYLIST_ID = "PL123456789"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"


class DesktopClipboardFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = EasyMP3App.__new__(EasyMP3App)
        self.app.add_task = Mock()
        self.app.start_playlist_inspection = Mock()
        self.app._show_error_dialog = Mock()

    def test_single_video_from_clipboard_is_queued(self):
        with patch.object(app_module.pyperclip, "paste", return_value=VIDEO_URL):
            self.app.download_from_clipboard()

        self.app.add_task.assert_called_once_with(VIDEO_URL, video_id=VIDEO_ID)
        self.app.start_playlist_inspection.assert_not_called()
        self.app._show_error_dialog.assert_not_called()

    def test_playlist_from_clipboard_starts_inspection(self):
        with patch.object(app_module.pyperclip, "paste", return_value=PLAYLIST_URL):
            self.app.download_from_clipboard()

        self.app.start_playlist_inspection.assert_called_once_with(PLAYLIST_URL)
        self.app.add_task.assert_not_called()

    def test_video_in_playlist_follows_the_users_choice(self):
        parsed = ParsedYouTubeUrl(kind="video_in_playlist", video_id=VIDEO_ID, playlist_id=PLAYLIST_ID)

        for choice, expected_call in (("song", "song"), ("playlist", "playlist"), (None, None)):
            with self.subTest(choice=choice):
                self.app.add_task.reset_mock()
                self.app.start_playlist_inspection.reset_mock()
                self.app._show_choice_dialog = Mock(return_value=choice)

                self.app._handle_video_in_playlist_url(parsed)

                if expected_call == "song":
                    self.app.add_task.assert_called_once_with(VIDEO_URL, video_id=VIDEO_ID)
                    self.app.start_playlist_inspection.assert_not_called()
                elif expected_call == "playlist":
                    self.app.start_playlist_inspection.assert_called_once_with(PLAYLIST_URL)
                    self.app.add_task.assert_not_called()
                else:
                    self.app.add_task.assert_not_called()
                    self.app.start_playlist_inspection.assert_not_called()


class DesktopPlaylistConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.app = EasyMP3App.__new__(EasyMP3App)
        self.app.set_playlist_inspection_state = Mock()
        self.app.get_known_video_ids = Mock(return_value={"existing123"})
        self.app.add_tasks = Mock()
        self.app._show_info_dialog = Mock()
        self.app._show_choice_dialog = Mock()

        self.inspection = PlaylistInspectionResult(
            title="Test Playlist",
            playlist_id=PLAYLIST_ID,
            entries=[
                PlaylistEntry("existing123", "Already queued", "https://youtu.be/existing123"),
                PlaylistEntry(VIDEO_ID, "New song", VIDEO_URL),
                PlaylistEntry(VIDEO_ID, "Repeated song", VIDEO_URL),
            ],
            unavailable_count=2,
        )

    def test_accepting_confirmation_queues_only_new_unique_entries(self):
        self.app._show_choice_dialog.return_value = "playlist"

        self.app._handle_playlist_inspection_success(self.inspection, "C:\\Music")

        self.app.set_playlist_inspection_state.assert_called_once_with(False)
        self.app.add_tasks.assert_called_once()
        tasks, output_path = self.app.add_tasks.call_args.args
        self.assertEqual(output_path, "C:\\Music")
        self.assertEqual(
            tasks,
            [{"url": VIDEO_URL, "video_id": VIDEO_ID, "title": "New song"}],
        )
        confirmation = self.app._show_choice_dialog.call_args.args[1]
        self.assertIn("Found 5 songs", confirmation)
        self.assertIn("Unavailable or private: 2", confirmation)
        self.assertIn("Skipping duplicates: 2", confirmation)
        self.assertIn("Download 1 song?", confirmation)

    def test_rejecting_confirmation_does_not_queue_entries(self):
        self.app._show_choice_dialog.return_value = None

        self.app._handle_playlist_inspection_success(self.inspection, "C:\\Music")

        self.app.set_playlist_inspection_state.assert_called_once_with(False)
        self.app.add_tasks.assert_not_called()


class DesktopFolderTests(unittest.TestCase):
    def test_browse_updates_only_the_desktop_folder_variable(self):
        desktop = EasyMP3App.__new__(EasyMP3App)
        desktop.output_dir_var = Mock()

        with patch.object(app_module.filedialog, "askdirectory", return_value="C:\\Chosen Music"):
            desktop.browse_output_dir()

        desktop.output_dir_var.set.assert_called_once_with("C:\\Chosen Music")

    def test_cancelled_browse_keeps_the_current_folder(self):
        desktop = EasyMP3App.__new__(EasyMP3App)
        desktop.output_dir_var = Mock()

        with patch.object(app_module.filedialog, "askdirectory", return_value=""):
            desktop.browse_output_dir()

        desktop.output_dir_var.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
