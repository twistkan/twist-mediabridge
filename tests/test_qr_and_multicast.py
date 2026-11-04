import threading
import unittest
from unittest.mock import Mock, patch
from bridge import wireless, qr_pairing, network_discovery
from bridge.engine import Android, Cancelled


class QrAndMulticastTests(unittest.TestCase):
    def test_qr_session_is_ephemeral_and_secret_is_not_in_repr(self):
        first, second = qr_pairing.new_session(), qr_pairing.new_session()
        self.assertNotEqual(first.name, second.name)
        self.assertNotEqual(first.secret, second.secret)
        self.assertNotIn(first.secret, repr(first))
        self.assertEqual(first.payload, f'WIFI:T:ADB;S:{first.name};P:{first.secret};;')
        image = qr_pairing.image(first)
        self.assertEqual(image.width, image.height)
        self.assertGreater(image.width, 200)
        self.assertEqual(image.getpixel((0,0)), (255,255,255))

    def test_expired_qr_never_scans_or_pairs(self):
        session = qr_pairing.Session('studio-twist-' + 'a'*12, 'b'*24, 0)
        with patch('bridge.qr_pairing.snapshot') as scan, patch('bridge.qr_pairing.adb_run') as run:
            with self.assertRaisesRegex(TimeoutError, 'expired'):
                qr_pairing.pair_session('adb', session, threading.Event())
        scan.assert_not_called()
        run.assert_not_called()

    def test_qr_cancellation_prevents_network_or_pairing(self):
        cancel = threading.Event()
        cancel.set()
        with patch('bridge.qr_pairing.snapshot') as scan:
            with self.assertRaises(Cancelled):
                qr_pairing.pair_session('adb', qr_pairing.new_session(), cancel)
        scan.assert_not_called()

    def test_qr_pairs_only_exact_session_and_passes_secret_on_stdin(self):
        session = qr_pairing.new_session()
        data = f'{session.name} _adb-tls-pairing._tcp 192.168.1.20:37123\nstudio-other _adb-tls-pairing._tcp 192.168.1.21:44444'
        rows = wireless.parse_services(data, include_qr=True)
        phone = Android('adb', '192.168.1.20:45555', 'fixture')
        with patch('bridge.qr_pairing.snapshot', return_value=rows), patch('bridge.qr_pairing.adb_run', return_value=b'Successfully paired to phone') as run, patch('bridge.wireless.finish_pairing', return_value=(([phone], []), phone.serial)) as finish:
            result = qr_pairing.pair_session('adb', session, threading.Event())
        self.assertEqual(result[1], phone.serial)
        self.assertEqual(run.call_args.args[1], ['pair', '192.168.1.20:37123'])
        self.assertEqual(run.call_args.kwargs['input_data'], (session.secret+'\n').encode())
        self.assertNotIn(session.secret, repr(run.call_args.args))
        self.assertEqual(finish.call_args.args[1]['host'], '192.168.1.20')

    def test_ambiguous_qr_scan_does_not_pair_anyone(self):
        session = qr_pairing.new_session()
        rows = wireless.parse_services(f'{session.name} _adb-tls-pairing._tcp 192.168.1.20:37123\n{session.name} _adb-tls-pairing._tcp 192.168.1.21:37123', include_qr=True)
        with patch('bridge.qr_pairing.snapshot', return_value=rows), patch('bridge.qr_pairing.adb_run') as run:
            with self.assertRaisesRegex(OSError, 'More than one phone'):
                qr_pairing.pair_session('adb', session, threading.Event())
        run.assert_not_called()

    def test_qr_failure_does_not_expose_session_secret(self):
        session = qr_pairing.new_session()
        rows = wireless.parse_services(f'{session.name} _adb-tls-pairing._tcp 192.168.1.20:37123', include_qr=True)
        with patch('bridge.qr_pairing.snapshot', return_value=rows), patch('bridge.qr_pairing.adb_run', side_effect=OSError(session.secret)):
            with self.assertRaises(OSError) as error:
                qr_pairing.pair_session('adb', session, threading.Event())
        self.assertNotIn(session.secret, str(error.exception))

    def test_direct_discovery_finds_phone_when_adb_list_is_empty(self):
        direct = wireless.parse_services('fixture _adb-tls-connect._tcp 192.168.1.20:45555')
        with patch('bridge.wireless.service_snapshot', return_value=[]), patch('bridge.wireless.multicast_snapshot', return_value=direct), patch('bridge.wireless.discover', return_value=([], [])):
            rows = wireless.nearby('adb', threading.Event(), wait_seconds=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['connect_address'], '192.168.1.20:45555')

    def test_direct_refresh_replaces_stale_adb_port(self):
        old = wireless.parse_services('fixture _adb-tls-connect._tcp 192.168.1.20:44444')
        new = wireless.parse_services('fixture _adb-tls-connect._tcp 192.168.1.20:45555')
        self.assertEqual(wireless.merge_services(old,new), new)

    def test_empty_adb_snapshot_uses_direct_discovery(self):
        direct = wireless.parse_services('fixture _adb-tls-connect._tcp 192.168.1.20:45555')
        with patch('bridge.wireless.adb_run', return_value=b'List of discovered mdns services'), patch('bridge.wireless.multicast_snapshot', return_value=direct):
            self.assertEqual(wireless.service_snapshot('adb', None), direct)

    def test_direct_browser_resolves_tls_and_closes_resources(self):
        from zeroconf import ServiceStateChange
        zc = Mock()
        zc.__enter__ = Mock(return_value=zc)
        zc.__exit__ = Mock(return_value=False)
        info = Mock(port=45555)
        info.parsed_addresses.return_value = ['192.168.1.20']
        zc.get_service_info.return_value = info
        browser = Mock()
        def browse(client, types, handlers):
            handlers[0](zeroconf=client, service_type=types[1], name='fixture.'+types[1], state_change=ServiceStateChange.Added)
            return browser
        with patch('zeroconf.Zeroconf', return_value=zc), patch('zeroconf.ServiceBrowser', side_effect=browse), patch('bridge.network_discovery.time.monotonic', side_effect=[0,0,10]):
            rows = network_discovery.scan(threading.Event(), seconds=3)
        self.assertEqual(rows[0]['address'], '192.168.1.20:45555')
        browser.cancel.assert_called_once()
        zc.__exit__.assert_called_once()


if __name__ == '__main__':
    unittest.main()
