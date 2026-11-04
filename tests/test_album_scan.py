import threading
import unittest
from unittest.mock import patch

from bridge.engine import Android, PartialScanOutput, Cancelled
from bridge.media import scan_media, album_counts


class AlbumScanRegressionTests(unittest.TestCase):
    def test_bad_names_and_unreadable_folder_do_not_discard_albums(self):
        phone = Android('adb.exe', 'fixture')
        outputs = [
            b'/sdcard/DCIM/Camera/photo.jpg\0/sdcard/DCIM/notes:unsupported.txt\0/sdcard/DCIM/Camera/bad:name.jpg\0__DEVICEBRIDGE_STATUS__0\0',
            b'/sdcard/Pictures/Screenshots/screen.png\0__DEVICEBRIDGE_STATUS__0\0',
            b'__DEVICEBRIDGE_STATUS__0\0', b'', b'', b'',
            b'/sdcard/Android/media/app/album/clip.mp4\0__DEVICEBRIDGE_STATUS__1\0',
        ]
        with patch('bridge.engine.adb_run', side_effect=outputs):
            items = scan_media(phone, threading.Event(), lambda *args: None)
        self.assertEqual(len(items), 3)
        self.assertEqual(len(album_counts(items)), 3)
        self.assertEqual(len(phone.scan_warnings), 2)
        self.assertTrue(any('1 media files skipped' in w for w in phone.scan_warnings))

    def test_slow_shared_app_folder_retains_complete_partial_records(self):
        phone = Android('adb.exe', 'fixture')
        outputs = [b'/sdcard/DCIM/Camera/photo.jpg\0__DEVICEBRIDGE_STATUS__0\0', b'', b'', b'', b'', b'',
                   PartialScanOutput(b'/sdcard/Android/media/app/clip.mp4\0')]
        with patch('bridge.engine.adb_run', side_effect=outputs):
            items = scan_media(phone, threading.Event(), lambda *args: None)
        self.assertEqual(len(items), 2)
        self.assertTrue(any('partial results' in w for w in phone.scan_warnings))

    def test_cancel_still_stops_scan(self):
        phone = Android('adb.exe', 'fixture')
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            scan_media(phone, cancel, lambda *args: None)


if __name__ == '__main__':
    unittest.main()
