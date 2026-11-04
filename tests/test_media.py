import tempfile
import threading
import unittest
from pathlib import Path

from bridge.engine import Folder, Android, transfer, digest
from bridge.media import MediaCache, scan_media, album_counts, MEDIA_TYPES, play_frames
from PIL import Image
import imageio_ffmpeg
import subprocess


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'phone'
        for album in ('DCIM/Camera', 'Pictures/Screenshots', 'Movies/Screen recordings'):
            (self.source / album).mkdir(parents=True)
        Image.new('RGB', (600, 400), '#246d88').save(self.source / 'DCIM/Camera/one.jpg')
        Image.new('RGB', (400, 600), '#7b4d9a').save(self.source / 'Pictures/Screenshots/two.png')
        (self.source / 'notes.txt').write_text('Do not transfer me')
        self.cancel = threading.Event()
        self.folder = Folder(self.source)
        self.cache = MediaCache(self.root / 'cache')

    def tearDown(self):
        self.tmp.cleanup()

    def test_album_index_contains_only_media(self):
        items = scan_media(self.folder, self.cancel, lambda *args: None)
        self.assertEqual(len(items), 2)
        self.assertEqual(album_counts(items), {'DCIM/Camera': 1, 'Pictures/Screenshots': 1})

    def test_selected_transfer_excludes_unselected_media(self):
        target = self.root / 'target'
        target.mkdir()
        result = transfer(self.folder, Folder(target), MEDIA_TYPES, self.cancel, lambda *args: None, paths=['DCIM/Camera/one.jpg'])
        self.assertEqual(result['copied'], 1)
        self.assertFalse((target / 'Pictures/Screenshots/two.png').exists())
        self.assertFalse((target / 'notes.txt').exists())
        self.assertEqual(digest(self.source / 'DCIM/Camera/one.jpg'), digest(target / 'DCIM/Camera/one.jpg'))

    def test_selected_transfer_rejects_traversal(self):
        target = self.root / 'target'
        target.mkdir()
        with self.assertRaises(ValueError):
            transfer(self.folder, Folder(target), MEDIA_TYPES, self.cancel, lambda *args: None, paths=['../escape.jpg'])

    def test_samsung_folders_and_shared_app_media_scope(self):
        phone = Android('adb.exe', 'fixture', 'Samsung Galaxy S21 Ultra')
        for name in ('DCIM/Camera/20261019_105000.jpg', 'DCIM/Screenshots/screen.png', 'Movies/Screen recordings/video.mp4', 'Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/a.jpg'):
            self.assertEqual(phone.remote(name), '/sdcard/' + name)
        with self.assertRaises(ValueError):
            phone.remote('Android/data/com.private/files/a.jpg')

    def test_photo_thumbnail_and_preview(self):
        for size in ((150, 108), (680, 390)):
            picture, local = self.cache.image(self.folder, 'DCIM/Camera/one.jpg', self.cancel, size=size)
            self.assertEqual(picture.size, size)
            self.assertEqual(local, self.source / 'DCIM/Camera/one.jpg')

    def test_thumbnail_cache_reuses_decode_and_invalidates_changed_file(self):
        from unittest.mock import patch
        name = 'DCIM/Camera/one.jpg'
        first, _ = self.cache.image(self.folder, name, self.cancel)
        with patch('bridge.media.ImageOps.exif_transpose', side_effect=AssertionError('decoded again')):
            repeated, _ = self.cache.image(self.folder, name, self.cancel)
        self.assertEqual(first.tobytes(), repeated.tobytes())
        Image.new('RGB', (601, 401), '#ff0000').save(self.source / name)
        changed, _ = self.cache.image(self.folder, name, self.cancel)
        self.assertNotEqual(first.tobytes(), changed.tobytes())

    def test_heic_photo_preview(self):
        # A real HEIF encode/decode, not an extension-only fixture.
        path = self.source / 'DCIM/Camera/high-efficiency.heic'
        Image.new('RGB', (120, 80), '#557799').save(path, format='HEIF')
        picture, _ = self.cache.image(self.folder, 'DCIM/Camera/high-efficiency.heic', self.cancel)
        self.assertEqual(picture.size, (150, 108))

    def test_video_thumbnail_and_muted_playback(self):
        path = self.source / 'Movies/Screen recordings/clip.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=teal:s=320x180:d=0.5', '-c:v', 'libx264', str(path)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        picture, _ = self.cache.image(self.folder, 'Movies/Screen recordings/clip.mp4', self.cancel)
        self.assertEqual(picture.size, (150, 108))
        frames = []
        play_frames(path, self.cancel, lambda frame: frames.append(frame.size))
        self.assertTrue(frames)
        self.assertEqual(frames[0], (640, 360))


if __name__ == '__main__':
    unittest.main()
