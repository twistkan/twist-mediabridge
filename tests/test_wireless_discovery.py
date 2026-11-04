import threading
import unittest
from unittest.mock import patch
from bridge import wireless
from bridge.engine import Android, Cancelled


SERVICES = '''List of discovered mdns services
adb-test-pair _adb-tls-pairing._tcp 192.168.1.20:37123
adb-test-connect _adb-tls-connect._tcp 192.168.1.20:44444
adb-other-connect _adb-tls-connect._tcp 192.168.1.21:45555
'''


class WirelessDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.multicast = patch('bridge.wireless.multicast_snapshot', return_value=[])
        self.multicast.start()
        self.addCleanup(self.multicast.stop)

    def test_only_valid_tls_services_accept_pin_pairing(self):
        data = SERVICES + '''
adb-test-pair _adb-tls-pairing._tcp 192.168.1.20:37123
legacy _adb._tcp 192.168.1.23:5555
studio-qr _adb-tls-pairing._tcp 192.168.1.24:12345
bad _adb-tls-connect._tcp 192.168.1.1:99999
bad;command _adb-tls-connect._tcp 192.168.1.1:5555
bad _http._tcp 192.168.1.1:80
'''
        rows = wireless.parse_services(data)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['address'], '192.168.1.20:37123')

    def test_candidates_join_ports_and_use_known_model_only_when_verified(self):
        phone = Android('adb', '192.168.1.20:44444', 'Galaxy S23 Ultra')
        rows = wireless.candidates(wireless.parse_services(SERVICES), [phone])
        self.assertEqual(len(rows), 2)
        row = next(row for row in rows if row['pair_address'])
        self.assertEqual(row['connect_address'], phone.serial)
        self.assertEqual(row['connected_serial'], phone.serial)
        self.assertEqual(row['label'], phone.label)
        self.assertTrue(all('Galaxy' not in r['label'] for r in rows if not r['connected_serial']))

    def test_ambiguous_shared_host_does_not_guess_connection_port(self):
        data = SERVICES + 'adb-second _adb-tls-connect._tcp 192.168.1.20:46666\n'
        row = next(row for row in wireless.candidates(wireless.parse_services(data), []) if row['pair_address'])
        self.assertEqual(row['connect_address'], '')
        with patch('bridge.wireless.pair'), patch('bridge.wireless.service_snapshot', return_value=wireless.parse_services(data)), patch('bridge.wireless.connect') as connect:
            with self.assertRaisesRegex(OSError, 'Pairing succeeded'):
                wireless.pair_and_connect('adb', row, '123456', threading.Event())
            connect.assert_not_called()

    def test_pair_then_fresh_discovery_connects_only_selected_host(self):
        row = wireless.candidates(wireless.parse_services(SERVICES), [])[0]
        changed = SERVICES.replace(':44444', ':47777')
        phone = Android('adb', '192.168.1.20:47777', 'Demo')
        with patch('bridge.wireless.pair') as pair, patch('bridge.wireless.service_snapshot', return_value=wireless.parse_services(changed)), patch('bridge.wireless.discover', return_value=([], [])), patch('bridge.wireless.connect', return_value=([phone], [])) as connect:
            result, target = wireless.pair_and_connect('adb', row, '123456', threading.Event())
            pair.assert_called_once()
            connect.assert_called_once_with('adb', phone.serial, unittest.mock.ANY)
            self.assertEqual(target, phone.serial)
            self.assertEqual(result[0], [phone])

    def test_phone_pairing_popup_can_be_opened_after_selection(self):
        initial = wireless.parse_services('adb-test-connect _adb-tls-connect._tcp 192.168.1.20:44444')
        row = wireless.candidates(initial, [])[0]
        phone = Android('adb', '192.168.1.20:44444', 'Demo')
        with patch('bridge.wireless.service_snapshot', return_value=wireless.parse_services(SERVICES)), patch('bridge.wireless.pair') as pair, patch('bridge.wireless.discover', return_value=([], [])), patch('bridge.wireless.connect', return_value=([phone], [])):
            wireless.pair_and_connect('adb', row, '123456', None)
        self.assertEqual(pair.call_args.args[1], '192.168.1.20:37123')

    def test_adb_automatic_mdns_connection_is_verified_without_duplicate_connect(self):
        row = wireless.candidates(wireless.parse_services(SERVICES), [])[0]
        phone = Android('adb', 'adb-test-connect._adb-tls-connect._tcp', 'Demo')
        with patch('bridge.wireless.pair'), patch('bridge.wireless.service_snapshot', return_value=wireless.parse_services(SERVICES)), patch('bridge.wireless.discover', return_value=([phone], [])), patch('bridge.wireless.adb_run', return_value=b'device') as run, patch('bridge.wireless.connect') as connect:
            result, target = wireless.pair_and_connect('adb', row, '123456', None)
        connect.assert_not_called()
        self.assertEqual(target, phone.serial)
        self.assertEqual(run.call_args.args[1], ['-s', phone.serial, 'get-state'])
        self.assertEqual(result[0], [phone])

    def test_scan_returns_live_connected_wifi_without_mdns(self):
        wifi = Android('adb', '192.168.1.30:45555', 'Demo')
        usb = Android('adb', 'usb-serial', 'USB phone')
        with patch('bridge.wireless.service_snapshot', return_value=[]), patch('bridge.wireless.discover', return_value=([wifi, usb], [])):
            rows = wireless.nearby('adb', threading.Event(), wait_seconds=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['connected_serial'], wifi.serial)

    def test_selected_connected_mdns_device_is_verified_before_returning(self):
        phone = Android('adb', 'adb-demo._adb-tls-connect._tcp', 'Demo')
        row = wireless.candidates([], [phone])[0]
        with patch('bridge.wireless.adb_run', return_value=b'device'), patch('bridge.wireless.discover', return_value=([phone], [])):
            result, serial = wireless.connect_candidate('adb', row, None)
        self.assertEqual(serial, phone.serial)
        self.assertEqual(result[0], [phone])

    def test_cancelled_scan_and_pair_do_not_continue(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch('bridge.wireless.adb_run') as run, self.assertRaises(Cancelled):
            wireless.nearby('adb', cancelled)
        run.assert_not_called()
        row = wireless.candidates(wireless.parse_services(SERVICES), [])[0]
        with patch('bridge.wireless.pair', side_effect=OSError('wrong code')), patch('bridge.wireless.connect') as connect:
            with self.assertRaises(OSError):
                wireless.pair_and_connect('adb', row, '123456', None)
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
