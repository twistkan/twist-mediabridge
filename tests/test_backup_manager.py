from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from bridge.backup_catalog import BackupCatalog, restore_backup
from bridge.engine import Folder, Android, backup, digest
from bridge.phone_backup import validate_vcard


CARD=b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Fixture\r\nTEL:123456789\r\nEND:VCARD\r\n'


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.home=self.root/'data'
        self.home.mkdir()
        self.catalog=BackupCatalog(self.home)
        self.cancel=threading.Event()

    def tearDown(self):self.temp.cleanup()

    def test_register_verify_and_detect_modified_contact_backup(self):
        file=self.root/'Contacts.vcf'
        file.write_bytes(CARD)
        row=self.catalog.add(file)
        self.assertEqual(row['kind'],'Contacts')
        self.assertEqual(row['count'],1)
        self.catalog.verify(row,self.cancel,lambda *a:None)
        file.write_bytes(CARD.replace(b'Fixture',b'Changed'))
        self.catalog.add(file)  # Refresh/import cannot silently reset the baseline.
        with self.assertRaises(ValueError):self.catalog.verify(row,self.cancel,lambda *a:None)
        self.assertEqual(self.catalog.rows()[0]['check'],'Changed / unavailable')

    def test_contact_folder_is_one_entry_and_forget_keeps_files(self):
        folder=self.root/'Contacts_date'
        folder.mkdir()
        for i in range(3):(folder/f'Name-{i}.vcf').write_bytes(CARD)
        self.catalog.scan(folder,self.cancel,lambda *a:None)
        rows=self.catalog.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['count'],3)
        self.catalog.forget(rows[0]['id'])
        self.assertFalse(self.catalog.rows())
        self.assertEqual(len(list(folder.glob('*.vcf'))),3)

    def test_saved_files_restore_and_tamper_rejection(self):
        source=self.root/'source'
        source.mkdir()
        (source/'sample.txt').write_text('verified fixture')
        result=backup(Folder(source),self.root/'library',{'Documents'},self.cancel,lambda *a:None)
        row=self.catalog.add(result['folder'])
        target=self.root/'restored'
        target.mkdir()
        restore_backup(row,Folder(target),self.cancel,lambda *a:None)
        self.assertEqual(digest(target/'sample.txt'),digest(source/'sample.txt'))
        (Path(result['folder'])/'files/sample.txt').write_text('changed')
        with patch('bridge.backup_catalog.transfer') as transfer:
            with self.assertRaises(ValueError):restore_backup(row,Folder(target),self.cancel,lambda *a:None)
            transfer.assert_not_called()

    def test_individual_contacts_restore_combines_only_saved_cards(self):
        folder=self.root/'Contacts'
        folder.mkdir()
        for i in range(2):(folder/f'Name-{i}.vcf').write_bytes(CARD)
        row=self.catalog.add(folder)
        def restored(phone,file,cancel):
            self.assertEqual(validate_vcard(file),2)
            return 'Staged 2 contacts for import'
        with patch('bridge.backup_catalog.restore_vcard',side_effect=restored):
            result=restore_backup(row,Android('adb','fixture'),self.cancel,lambda *a:None)
        self.assertIn('2 contacts',result)

    def test_missing_backup_is_kept_in_manager(self):
        file=self.root/'Contacts.vcf'
        file.write_bytes(CARD)
        row=self.catalog.add(file)
        file.unlink()
        self.assertEqual(len(self.catalog.rows()),1)
        with self.assertRaises(ValueError):self.catalog.verify(row,self.cancel,lambda *a:None)
