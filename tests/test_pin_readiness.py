import threading
import unittest
from unittest.mock import patch
from bridge import wireless
from bridge.engine import Cancelled


class PinReadinessTests(unittest.TestCase):
    def setUp(self):
        self.row={'id':'fixture','host':'192.168.1.20','pair_address':'',
                  'connect_address':'192.168.1.20:45555','connected_serial':''}

    def test_wait_detects_only_selected_phones_code_service(self):
        rows=wireless.parse_services('other _adb-tls-pairing._tcp 192.168.1.21:39999\nselected _adb-tls-pairing._tcp 192.168.1.20:37123')
        with patch('bridge.wireless.service_snapshot',return_value=rows):
            result=wireless.wait_for_pin_server('adb',self.row,None,timeout_seconds=0)
        self.assertEqual(result['pair_address'],'192.168.1.20:37123')

    def test_missing_phone_screen_does_not_attempt_pairing_or_invent_code(self):
        with patch('bridge.wireless.service_snapshot',return_value=[]),patch('bridge.wireless.pair') as pair:
            with self.assertRaisesRegex(TimeoutError,'does not send a notification'):
                wireless.wait_for_pin_server('adb',self.row,None,timeout_seconds=0)
        pair.assert_not_called()

    def test_qr_server_cannot_be_mistaken_for_code_popup(self):
        rows=wireless.parse_services('studio-test _adb-tls-pairing._tcp 192.168.1.20:37123',include_qr=True)
        with patch('bridge.wireless.service_snapshot',return_value=rows):
            with self.assertRaises(TimeoutError):
                wireless.wait_for_pin_server('adb',self.row,None,timeout_seconds=0)

    def test_cancel_wait_without_network_activity(self):
        cancel=threading.Event();cancel.set()
        with patch('bridge.wireless.service_snapshot') as snapshot:
            with self.assertRaises(Cancelled):
                wireless.wait_for_pin_server('adb',self.row,cancel)
        snapshot.assert_not_called()

    def test_ambiguous_services_are_not_guessed(self):
        rows=wireless.parse_services('one _adb-tls-pairing._tcp 192.168.1.20:37123\ntwo _adb-tls-pairing._tcp 192.168.1.20:37124')
        with patch('bridge.wireless.service_snapshot',return_value=rows):
            with self.assertRaisesRegex(OSError,'More than one'):
                wireless.wait_for_pin_server('adb',self.row,None,timeout_seconds=0)


if __name__=='__main__':unittest.main()
