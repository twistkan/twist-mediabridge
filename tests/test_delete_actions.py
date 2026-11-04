import base64
import json
import threading
import unittest
from unittest.mock import Mock, patch
from bridge.engine import Android
from bridge.delete_actions import delete_media, uninstall_apps
from bridge.contacts_bridge import contact_path, delete_contacts, load_contacts


class DeleteTests(unittest.TestCase):
    def test_media_selection_validated_before_any_delete(self):
        phone = Android('adb', 'fixture')
        phone.shell = Mock(return_value=b'')
        with self.assertRaises(ValueError):
            delete_media(phone, ['DCIM/photo.jpg', '../escape.jpg'], threading.Event(), lambda *a:None)
        phone.shell.assert_not_called()

    def test_media_deletes_only_selected_files_and_rejects_links(self):
        phone = Android('adb', 'fixture')
        phone.shell = Mock(return_value=b'')
        result = delete_media(phone, ['DCIM/Camera/selected.jpg'], threading.Event(), lambda *a:None)
        script = phone.shell.call_args.args[0]
        self.assertIn('rm -- /sdcard/DCIM/Camera/selected.jpg', script)
        self.assertIn('[ ! -L /sdcard/DCIM/Camera ]', script)
        self.assertNotIn('rm -r', script)
        self.assertEqual(result[0][:2], ('DCIM/Camera/selected.jpg', True))

    def test_uninstall_selected_package_only(self):
        phone = Android('adb', 'fixture')
        with patch('bridge.delete_actions.adb_run', return_value=b'Success') as run:
            result = uninstall_apps(phone, ['com.example.selected'], threading.Event(), lambda *a:None)
        self.assertEqual(run.call_args.args[1], ['-s', 'fixture', 'uninstall', 'com.example.selected'])
        self.assertTrue(result[0][1])

    def test_exported_vcard_cannot_be_used_for_phone_deletion(self):
        with self.assertRaises(ValueError):
            contact_path({'id':'exported', 'name':'Test'})

    def test_live_contacts_load_and_delete_specific_lookup(self):
        phone = Mock()
        value = [{'contact_id':'42','lookup':'lookup/key','name':'Test Contact','numbers':['123']}]
        phone.shell.return_value = ('Row: 0 payload='+base64.b64encode(json.dumps(value).encode()).decode()).encode()
        rows = load_contacts(phone, threading.Event(), lambda *a:None)
        self.assertEqual(rows[0]['id'],'live:42')
        phone.shell.return_value = b'Deleted 1 rows'
        result = delete_contacts(phone, rows, threading.Event(), lambda *a:None)
        self.assertTrue(result[0][1])
        self.assertIn('/contacts/42?lookup=lookup%2Fkey',phone.shell.call_args.args[0])
        phone.shell.return_value = b'Error: permission denied'
        self.assertFalse(delete_contacts(phone,rows,threading.Event(),lambda *a:None)[0][1])
