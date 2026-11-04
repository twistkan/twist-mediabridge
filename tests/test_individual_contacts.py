from datetime import datetime
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from bridge.engine import Cancelled
from bridge.phone_backup import contact_backup_name, save_individual_contacts, validate_vcard


def row(name, value):
    return {'name': name, 'card': f'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:{value}\r\nTEL:123\r\nEMAIL:test@example.com\r\nEND:VCARD\r\n'.encode()}


class IndividualContactsTests(unittest.TestCase):
    def test_default_filename_has_date_time_and_no_windows_colons(self):
        self.assertEqual(contact_backup_name(datetime(2026,10,21,9,4,5)), 'Contacts_2026-10-21_09-04-05')

    def test_one_complete_vcard_per_selected_contact(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=[row('Alice Example','Alice'),row('Bob Example','Bob')]
            save_individual_contacts(rows,temp,threading.Event())
            folder=next(Path(temp).iterdir())
            self.assertEqual({p.name for p in folder.iterdir()},{'Alice Example.vcf','Bob Example.vcf'})
            for name, expected in [('Alice Example.vcf',rows[0]['card']),('Bob Example.vcf',rows[1]['card'])]:
                self.assertEqual((folder/name).read_bytes(),expected)
                self.assertEqual(validate_vcard(folder/name),1)

    def test_duplicate_unsafe_and_reserved_names_are_safe_and_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            names=['Alice','alice','Alice','CON','../Bad:Name','']
            save_individual_contacts([row(name,str(i)) for i,name in enumerate(names)],temp,threading.Event())
            files=list(next(Path(temp).iterdir()).iterdir())
            self.assertEqual(len(files),6)
            self.assertEqual(len({p.name.casefold() for p in files}),6)
            self.assertTrue(any(p.name=='Contact-CON.vcf' for p in files))
            self.assertTrue(all(p.parent==files[0].parent for p in files))

    def test_repeated_backup_does_not_overwrite_previous_files(self):
        with tempfile.TemporaryDirectory() as temp, patch('bridge.phone_backup.contact_backup_name',return_value='Contacts_2026-10-21_09-04-05'):
            for _ in range(2):
                save_individual_contacts([row('Alice','Alice')],temp,threading.Event())
            self.assertEqual(len(list(Path(temp).iterdir())),2)

    def test_cancelled_export_publishes_no_partial_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            cancel=threading.Event()
            cancel.set()
            with self.assertRaises(Cancelled):
                save_individual_contacts([row('Alice','Alice')],temp,cancel)
            self.assertEqual(list(Path(temp).iterdir()),[])
