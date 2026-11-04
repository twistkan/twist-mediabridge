import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile
from bridge.engine import atomic_json, digest
from bridge.phone_backup import backup_app_file, restore_app_file, save_selected_contacts


class NamedBackupTests(unittest.TestCase):
    def fixture(self, root, count):
        folder=root/'old-format'
        folder.mkdir()
        files=[]
        for i in range(count):
            file=folder/f'{i:03}.apk'
            file.write_bytes(b'APK fixture '+str(i).encode())
            files.append({'name':file.name,'sha256':digest(file)})
        atomic_json(folder/'app.json',{'format':'twist-apks-1','package':'com.example.app','status':'complete','files':files})
        return folder

    def test_single_apk_has_real_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            fixture=self.fixture(root,1)
            with patch('bridge.phone_backup.backup_app',return_value=fixture):
                saved=backup_app_file(Mock(),'com.example.app','Instagram',root/'out',threading.Event(),lambda *a:None)
            self.assertEqual(saved.name,'Instagram.apk')
            self.assertEqual([p.name for p in (root/'out').iterdir()],['Instagram.apk'])
            with patch('bridge.phone_backup.adb_run',return_value=b'Success') as run:
                restore_app_file(Mock(adb='adb',serial='phone'),saved,threading.Event(),lambda *a:None)
            self.assertIn('install',run.call_args.args[1])

    def test_split_app_one_archive_and_verified_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            fixture=self.fixture(root,4)
            with patch('bridge.phone_backup.backup_app',return_value=fixture):
                saved=backup_app_file(Mock(),'com.example.app','Instagram',root/'out',threading.Event(),lambda *a:None)
            self.assertEqual(saved.name,'Instagram.apks')
            self.assertEqual(len(list((root/'out').iterdir())),1)
            with patch('bridge.phone_backup.adb_run',return_value=b'Success') as run:
                restore_app_file(Mock(adb='adb',serial='phone'),saved,threading.Event(),lambda *a:None)
            args=run.call_args.args[1]
            self.assertIn('install-multiple',args)
            self.assertEqual(sum(arg.endswith('.apk') for arg in args),4)

    def test_archive_tamper_rejected_before_install(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.apks'
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('app.json',json.dumps({'format':'twist-apks-1','status':'complete','package':'com.example.app','files':[{'name':'base.apk','sha256':'wrong'}]}))
                archive.writestr('base.apk',b'altered')
            with patch('bridge.phone_backup.adb_run') as run:
                with self.assertRaises(ValueError):
                    restore_app_file(Mock(),path,threading.Event(),lambda *a:None)
                run.assert_not_called()

    def test_contact_export_batches_progress_and_complete_count(self):
        from bridge.phone_backup import validate_vcard
        rows=[{'id':f'live:{i}','contact_id':str(i),'lookup':f'lookup{i}','live':True} for i in range(23)]
        cards=lambda n:b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Fixture\r\nEND:VCARD\r\n'*n
        updates=[]
        with tempfile.TemporaryDirectory() as temp, patch('bridge.contacts_bridge.adb_run',side_effect=[cards(10),cards(10),cards(3)]) as run:
            output=Path(temp)/'selected.vcf'
            save_selected_contacts(rows,output,threading.Event(),Mock(adb='adb',serial='phone'),lambda *a:updates.append(a))
            self.assertEqual(validate_vcard(output),23)
            self.assertEqual(run.call_count,3)
            self.assertTrue(any('20 of 23' in text for _,text in updates))

    def test_partial_contacts_never_published(self):
        rows=[{'contact_id':'1','lookup':'x','live':True}]
        with tempfile.TemporaryDirectory() as temp, patch('bridge.contacts_bridge.adb_run',return_value=b'BEGIN:VCARD\nFN:Incomplete'):
            output=Path(temp)/'selected.vcf'
            with self.assertRaises(OSError):
                save_selected_contacts(rows,output,threading.Event(),Mock(adb='adb',serial='phone'))
            self.assertFalse(output.exists())
