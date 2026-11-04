import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from bridge.phone_backup import validate_vcard, package_name, restore_app, backup_app, restore_vcard, parse_vcards, save_selected_contacts
from bridge.engine import digest


class PhoneBackupTests(unittest.TestCase):
    def test_individual_contacts_and_selected_export(self):
        raw = b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Alice Example\r\nTEL;TYPE=CELL:+12345\r\nEND:VCARD\r\nBEGIN:VCARD\r\nVERSION:3.0\r\nFN:Bob Example\r\nTEL:67890\r\nEND:VCARD\r\n'
        rows = parse_vcards(raw)
        self.assertEqual([r['name'] for r in rows], ['Alice Example', 'Bob Example'])
        self.assertEqual(rows[0]['detail'], '+12345')
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'selected.vcf'
            save_selected_contacts([rows[1]], destination, threading.Event())
            self.assertEqual(validate_vcard(destination), 1)
            self.assertNotIn(b'Alice', destination.read_bytes())

    def test_package_validation(self):
        self.assertEqual(package_name('com.example.app'), 'com.example.app')
        for name in ['a;reboot', '../bad', 'com.test\nreboot']:
            with self.assertRaises(ValueError):
                package_name(name)

    def test_vcard_and_restore_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'contacts.vcf'
            file.write_text('BEGIN:VCARD\nVERSION:3.0\nFN:Test Person\nEND:VCARD\n')
            self.assertEqual(validate_vcard(file), 1)
            phone = Mock()
            result = restore_vcard(phone, file, threading.Event())
            self.assertIn('not been imported', result)
            self.assertTrue(phone.write.call_args.args[1].startswith('Download/TwistMediaBridge/'))
            file.write_text('BEGIN:VCARD\n')
            with self.assertRaises(ValueError):
                validate_vcard(file)

    def test_split_backup_and_verified_reinstall(self):
        with tempfile.TemporaryDirectory() as temp:
            phone = Mock(adb='adb', serial='fixture')
            phone.shell.return_value = b'package:/data/app/x/base.apk\npackage:/data/app/x/split.apk\n'
            fixture = Path(temp) / 'fixture.apk'
            fixture.write_bytes(b'apk fixture')
            phone.remote_digest.return_value = digest(fixture)
            def run(adb, args, *rest, **kwargs):
                if 'pull' in args:
                    Path(args[-1]).write_bytes(fixture.read_bytes())
                    return b''
                self.assertIn('install-multiple', args)
                self.assertIn('-r', args)
                self.assertEqual(sum(p.endswith('.apk') for p in args), 2)
                return b'Success'
            with patch('bridge.phone_backup.adb_run', side_effect=run) as runner:
                folder = backup_app(phone, 'com.example.app', temp, threading.Event(), lambda *a: None)
                self.assertIn('Installed', restore_app(phone, folder, threading.Event(), lambda *a: None))
                (folder / '000.apk').write_bytes(b'corrupted')
                runner.reset_mock()
                with self.assertRaises(ValueError):
                    restore_app(phone, folder, threading.Event(), lambda *a: None)
                runner.assert_not_called()

    def test_restore_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'app.json').write_text(json.dumps({'format': 'twist-apks-1', 'status': 'complete', 'package': 'com.test.app', 'files': [{'name': '../outside.apk', 'sha256': 'invalid'}]}))
            with self.assertRaises(ValueError):
                restore_app(Mock(), folder, threading.Event(), lambda *a: None)


class DesktopInstallTests(unittest.TestCase):
    def test_old_marker_does_not_skip_shortcut_check(self):
        from bridge.desktop import ensure_shortcut
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            installed=home/'Application/TwistMediaBridge.exe'
            installed.parent.mkdir()
            installed.write_bytes(b'fixture')
            (home/'desktop-shortcut.json').write_text(json.dumps({'target':str(installed)}))
            with patch('bridge.desktop.sys.executable',str(installed)), patch('bridge.desktop.create_shortcut') as shortcut:
                ensure_shortcut(home)
            shortcut.assert_called_once_with(str(installed))

    def test_deleted_shortcut_recreated_with_existing_marker(self):
        from bridge.desktop import ensure_shortcut
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)/'AppData'
            home.mkdir()
            desktop=Path(temp)/'Desktop'
            desktop.mkdir()
            installed=home/'Application/TwistMediaBridge.exe'
            installed.parent.mkdir()
            installed.write_bytes(b'fixture')
            link=desktop/'Twist MediaBridge.lnk'
            with patch('bridge.desktop.sys.executable',str(installed)):
                ensure_shortcut(home,desktop)
                self.assertTrue(link.exists())
                original=link.read_bytes()
                ensure_shortcut(home,desktop)
                self.assertEqual(original,link.read_bytes())
                link.unlink()
                ensure_shortcut(home,desktop)
            self.assertTrue(link.is_file())
            self.assertGreater(link.stat().st_size,0)

    def test_shortcut_points_to_private_copy(self):
        from bridge.desktop import ensure_shortcut
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            download = root / 'download.exe'
            download.write_bytes(b'packaged fixture')
            home = root / 'AppData'
            home.mkdir()
            with patch('bridge.desktop.sys.executable', str(download)), patch('bridge.desktop.create_shortcut') as shortcut:
                ensure_shortcut(home)
            installed = home / 'Application/TwistMediaBridge.exe'
            self.assertEqual(installed.read_bytes(), download.read_bytes())
            self.assertEqual(shortcut.call_args.args[0], str(installed))
            download.unlink()
            self.assertTrue(installed.exists())
