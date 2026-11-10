from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from bridge.engine import Android, Cancelled, Folder
from bridge.send_to_phone import send_files


class Receiver(Android):
    def __init__(self, root):
        super().__init__('fixture','fixture')
        self.folder=Folder(root)

    def write(self, source, name, cancel):
        return self.folder.write(source,name,cancel)


class SendTests(unittest.TestCase):
    def test_arbitrary_files_flat_names_and_existing_conflicts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'phone').mkdir();phone=Receiver(root/'phone')
            source=root/'Résumé 你好.bin';source.write_bytes(b'any file type\0'*100)
            destination=root/'phone/Download/TwistMediaBridge'/source.name
            cancel=threading.Event()
            with patch('bridge.send_to_phone.phone_online',return_value=True):
                first=send_files([source],phone,cancel,lambda *a:None)
                self.assertEqual(first['copied'],1)
                self.assertEqual(destination.read_bytes(),source.read_bytes())
                second=send_files([source],phone,cancel,lambda *a:None)
                self.assertEqual(second['present'],1)
                source.write_bytes(b'different file')
                third=send_files([source],phone,cancel,lambda *a:None)
                self.assertEqual(third['failed'],1)
                self.assertNotEqual(destination.read_bytes(),source.read_bytes())
                self.assertTrue(source.exists())

    def test_duplicate_names_are_reported_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('one','two','phone'):(root/name).mkdir()
            paths=[root/'one/report.pdf',root/'two/report.pdf']
            for index,path in enumerate(paths):path.write_bytes(bytes([index]))
            with patch('bridge.send_to_phone.phone_online',return_value=True):
                result=send_files(paths,Receiver(root/'phone'),threading.Event(),lambda *a:None)
            self.assertEqual((result['requested'],result['copied'],result['failed']),(2,1,1))
            self.assertEqual(len(result['items']),2)
            self.assertEqual((root/'phone/Download/TwistMediaBridge/report.pdf').read_bytes(),b'\0')

    def test_offline_and_cancel_do_not_write(self):
        with tempfile.TemporaryDirectory() as temp:
            receiver=Receiver(temp)
            with patch('bridge.send_to_phone.phone_online',return_value=False):
                with self.assertRaisesRegex(OSError,'disconnected'):
                    send_files(['none'],receiver,threading.Event(),lambda *a:None)
            cancel=threading.Event();cancel.set()
            with patch('bridge.send_to_phone.phone_online',return_value=True):
                with self.assertRaises(Cancelled):send_files(['none'],receiver,cancel,lambda *a:None)
            self.assertFalse(list(Path(temp).iterdir()))

    def test_folder_is_rejected_without_recursively_scanning(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('bridge.send_to_phone.phone_online',return_value=True):
                result=send_files([temp],Receiver(temp),threading.Event(),lambda *a:None)
            self.assertEqual(result['failed'],1)
            self.assertFalse(list(Path(temp).iterdir()))
