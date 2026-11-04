import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from bridge.engine import Folder, Android, CATEGORIES, backup, transfer, digest, load_manifest, safe_relative, Cancelled


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'DCIM').mkdir()
        (self.source / 'DCIM/photo.jpg').write_bytes(b'photo-data' * 1000)
        (self.source / 'notes.txt').write_text('hello world', encoding='utf-8')
        (self.source / 'empty.bin').write_bytes(b'')
        self.target = self.root / 'target'
        self.target.mkdir()
        self.cancel = threading.Event()
        self.report = lambda *args: None

    def tearDown(self):
        self.tmp.cleanup()

    def make_backup(self):
        return Path(backup(Folder(self.source), self.root / 'library', set(CATEGORIES), self.cancel, self.report)['folder'])

    def test_verified_backup_restore_round_trip(self):
        folder = self.make_backup()
        self.assertEqual(len(load_manifest(folder)['items']), 3)
        result = transfer(Folder(folder / 'files'), Folder(self.target), set(CATEGORIES), self.cancel, self.report, backup_folder=folder)
        self.assertEqual(result['copied'], 3)
        for source in self.source.rglob('*'):
            if source.is_file():
                self.assertEqual(digest(source), digest(self.target / source.relative_to(self.source)))

    def test_selective_restore(self):
        folder = self.make_backup()
        result = transfer(Folder(folder / 'files'), Folder(self.target), {'Photos'}, self.cancel, self.report, backup_folder=folder)
        self.assertEqual(result['copied'], 1)
        self.assertFalse((self.target / 'notes.txt').exists())

    def test_conflict_preserves_existing_file(self):
        (self.target / 'notes.txt').write_text('keep me')
        result = transfer(Folder(self.source), Folder(self.target), set(CATEGORIES), self.cancel, self.report)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual((self.target / 'notes.txt').read_text(), 'keep me')

    def test_duplicate_is_verified_and_skipped(self):
        transfer(Folder(self.source), Folder(self.target), set(CATEGORIES), self.cancel, self.report)
        result = transfer(Folder(self.source), Folder(self.target), set(CATEGORIES), self.cancel, self.report)
        self.assertEqual(result['present'], 3)
        self.assertEqual(result['copied'], 0)

    def test_flat_media_export_preserves_names_without_phone_folders(self):
        (self.source/'0/DCIM/Camera').mkdir(parents=True)
        (self.source/'0/DCIM/Camera/20260801_165759.jpg').write_bytes(b'camera image')
        paths=['0/DCIM/Camera/20260801_165759.jpg','DCIM/photo.jpg']
        result=transfer(Folder(self.source),Folder(self.target),{'Photos'},self.cancel,self.report,paths=paths,flatten=True)
        self.assertEqual(result['copied'],2)
        self.assertEqual({p.name for p in self.target.iterdir()},{'20260801_165759.jpg','photo.jpg'})
        self.assertEqual((self.target/'20260801_165759.jpg').read_bytes(),b'camera image')

    def test_flat_export_duplicate_names_preserve_existing_content(self):
        (self.source/'Pictures').mkdir()
        (self.source/'Pictures/photo.jpg').write_bytes(b'different photo')
        result=transfer(Folder(self.source),Folder(self.target),{'Photos'},self.cancel,self.report,paths=['DCIM/photo.jpg','Pictures/photo.jpg'],flatten=True)
        self.assertEqual((result['copied'],result['failed']),(1,1))
        self.assertEqual((self.target/'photo.jpg').read_bytes(),(self.source/'DCIM/photo.jpg').read_bytes())
        self.assertEqual((self.source/'Pictures/photo.jpg').read_bytes(),b'different photo')
        self.assertEqual(result['errors'][0]['path'],'Pictures/photo.jpg')
        self.assertEqual(list(self.target.iterdir()),[self.target/'photo.jpg'])

    def test_flat_export_existing_same_file_is_verified_and_skipped(self):
        (self.target/'photo.jpg').write_bytes((self.source/'DCIM/photo.jpg').read_bytes())
        result=transfer(Folder(self.source),Folder(self.target),{'Photos'},self.cancel,self.report,paths=['DCIM/photo.jpg'],flatten=True)
        self.assertEqual((result['copied'],result['present'],result['failed']),(0,1,0))

    def test_flat_export_does_not_override_backup_restore_layout(self):
        folder=self.make_backup()
        with self.assertRaises(ValueError):
            transfer(Folder(folder/'files'),Folder(self.target),{'Photos'},self.cancel,self.report,backup_folder=folder,flatten=True)
        self.assertFalse(list(self.target.iterdir()))

    def test_transfer_cleanup_never_deletes_original_outside_its_staging(self):
        original=self.source/'DCIM/photo.jpg'
        class Phone:
            key='fixture-phone'
            def read(inner,name,temp,cancel):return original
        result=transfer(Phone(),Folder(self.target),{'Photos'},self.cancel,self.report,paths=['DCIM/photo.jpg'],flatten=True)
        self.assertEqual(result['copied'],1)
        self.assertTrue(original.exists())

    def test_transfer_reports_every_selected_item_and_existing_file(self):
        (self.source/'other.jpg').write_bytes(b'another image')
        (self.source/'failed.jpg').write_bytes(b'a new image')
        (self.target/'photo.jpg').write_bytes((self.source/'DCIM/photo.jpg').read_bytes())
        (self.target/'failed.jpg').write_bytes(b'preserve existing different image')
        paths=['DCIM/photo.jpg','other.jpg','failed.jpg']
        result=transfer(Folder(self.source),Folder(self.target),{'Photos'},self.cancel,self.report,paths=paths,flatten=True)
        self.assertEqual((result['requested'],result['copied'],result['present'],result['failed']),(3,1,1,1))
        details={row['path']:row for row in result['items']}
        self.assertEqual(set(details),set(paths))
        self.assertEqual(details['DCIM/photo.jpg']['status'],'already present')
        self.assertEqual(details['other.jpg']['sha256'],digest(self.target/'other.jpg'))
        self.assertEqual(details['failed.jpg']['status'],'failed')

    def test_corruption_blocks_all_restore_writes(self):
        folder = self.make_backup()
        (folder / 'files/notes.txt').write_text('corrupted!')
        with self.assertRaises(ValueError):
            transfer(Folder(folder / 'files'), Folder(self.target), set(CATEGORIES), self.cancel, self.report, backup_folder=folder)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_path_traversal_and_windows_devices_rejected(self):
        for name in ('../escape.txt', '/absolute', 'C:/file', 'a\\b', 'a/../b', 'a//b', 'CON.txt', 'a/trailing.', 'a\nfile', 'a:stream'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_relative(name)

    def test_duplicate_manifest_paths_rejected(self):
        folder = self.make_backup()
        data = load_manifest(folder)
        data['items'].append(data['items'][0])
        (folder / 'manifest.json').write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_manifest(folder)

    def test_cancelled_backup_not_restorable(self):
        self.cancel.set()
        with self.assertRaises(Cancelled):
            self.make_backup()
        for child in (self.root / 'library').iterdir():
            with self.assertRaises(ValueError):
                load_manifest(child)

    def test_overlapping_paths_blocked(self):
        nested = self.source / 'target'
        nested.mkdir()
        with self.assertRaises(ValueError):
            transfer(Folder(self.source), Folder(nested), set(CATEGORIES), self.cancel, self.report)
        with self.assertRaises(ValueError):
            backup(Folder(self.source), self.source / 'backups', set(CATEGORIES), self.cancel, self.report)

    def test_source_untouched(self):
        before = {p.relative_to(self.source): digest(p) for p in self.source.rglob('*') if p.is_file()}
        self.make_backup()
        transfer(Folder(self.source), Folder(self.target), set(CATEGORIES), self.cancel, self.report)
        after = {p.relative_to(self.source): digest(p) for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_unicode_and_spaces(self):
        (self.source / 'Violet’s café photo.jpg').write_bytes(b'photo')
        self.assertEqual(transfer(Folder(self.source), Folder(self.target), {'Photos'}, self.cancel, self.report)['copied'], 2)

    def test_empty_selection_cannot_succeed(self):
        with self.assertRaises(ValueError):
            transfer(Folder(self.source), Folder(self.target), set(), self.cancel, self.report)

    def test_android_scope_and_shell_quoting(self):
        android = Android('adb.exe', 'fake-serial')
        for name in ('Android/data/private', '../secret', '/etc/passwd'):
            with self.assertRaises(ValueError):
                android.remote(name)
        self.assertEqual(android.remote('DCIM/a photo.jpg'), '/sdcard/DCIM/a photo.jpg')

    def test_case_colliding_phone_paths_do_not_publish_backup(self):
        class CollisionSource:
            label = 'Android fixture'
            def files(self, selected, cancel):
                return [('DCIM/A.jpg', 1), ('DCIM/a.jpg', 1)]
        with self.assertRaises(ValueError):
            backup(CollisionSource(), self.root / 'library', {'Photos'}, self.cancel, self.report)
        for child in (self.root / 'library').iterdir():
            with self.assertRaises(ValueError):
                load_manifest(child)

    def test_pc_files_map_to_android_shared_storage(self):
        phone = Android('adb.exe', 'fixture')
        self.assertEqual(phone.destination_name('photo.jpg'), 'Pictures/DeviceBridge/photo.jpg')
        self.assertEqual(phone.destination_name('Holiday/clip.mp4'), 'Movies/DeviceBridge/Holiday/clip.mp4')
        self.assertEqual(phone.destination_name('notes.txt'), 'Documents/DeviceBridge/notes.txt')
        self.assertEqual(phone.destination_name('DCIM/original.jpg'), 'DCIM/original.jpg')
        with self.assertRaises(ValueError):
            phone.destination_name('../escape.jpg')


if __name__ == '__main__':
    unittest.main()
