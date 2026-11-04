import unittest
from unittest.mock import patch
from bridge import wireless
from bridge.engine import Android


class WirelessConnectFeedbackTests(unittest.TestCase):
    def test_authentication_failure_is_pairing_required_for_stdout_and_exit_error(self):
        for response in (b'failed to authenticate to 192.168.1.20:44444', OSError('authentication failed')):
            with self.subTest(response=response):
                context = patch('bridge.wireless.adb_run', side_effect=response) if isinstance(response, Exception) else patch('bridge.wireless.adb_run', return_value=response)
                with context, self.assertRaises(wireless.PairingRequired):
                    wireless.connect('adb', '192.168.1.20:44444', None)

    def test_connect_accepts_verified_service_serial_when_ip_serial_not_registered(self):
        serial = 'adb-demo._adb-tls-connect._tcp'
        phone = Android('adb', serial, 'OPPO fixture')
        outputs = [b'already connected to 192.168.1.20:44444', OSError('device not found'), b'device']
        with patch('bridge.wireless.adb_run', side_effect=outputs) as run, patch('bridge.wireless.discover', return_value=([phone], [])):
            self.assertEqual(wireless.connect('adb', '192.168.1.20:44444', None, service='adb-demo')[0], [phone])
        self.assertEqual(run.call_args.args[1], ['-s', serial, 'get-state'])

    def test_changed_connection_port_is_resolved_before_connecting(self):
        row = {'connect_address':'192.168.1.20:44444', 'host':'192.168.1.20',
               'connect_service':'adb-demo', 'connected_serial':''}
        fresh = wireless.parse_services('adb-demo _adb-tls-connect._tcp 192.168.1.20:45555')
        phone = Android('adb', '192.168.1.20:45555', 'fixture')
        with patch('bridge.wireless.service_snapshot', return_value=fresh), patch('bridge.wireless.connect', return_value=([phone], [])) as connect:
            _, serial = wireless.connect_candidate('adb', row, None)
        self.assertEqual(serial, phone.serial)
        self.assertEqual(connect.call_args.args[1], phone.serial)
        self.assertEqual(connect.call_args.kwargs['service'], 'adb-demo')

    def test_daemon_startup_lines_do_not_hide_success(self):
        phone = Android('adb', '192.168.1.20:44444', 'fixture')
        with patch('bridge.wireless.adb_run', side_effect=[b'* daemon started successfully\nconnected to 192.168.1.20:44444', b'device']), patch('bridge.wireless.discover', return_value=([phone], [])):
            self.assertEqual(wireless.connect('adb', phone.serial, None)[0], [phone])

    def test_unrelated_authorized_phone_is_not_reported_as_selected_success(self):
        unrelated = Android('adb', 'adb-other._adb-tls-connect._tcp', 'Other phone')
        with patch('bridge.wireless.adb_run', side_effect=[b'connected to 192.168.1.20:44444', b'device']), patch('bridge.wireless.discover', return_value=([unrelated], [])):
            with self.assertRaises(OSError):
                wireless.connect('adb', '192.168.1.20:44444', None, service='adb-demo')

    def test_reachable_handshake_failure_offers_pairing_but_offline_failure_does_not(self):
        row = {'connect_address':'192.168.1.20:44444', 'host':'192.168.1.20',
               'connect_service':'adb-demo', 'connected_serial':''}
        for reachable in (True, False):
            with self.subTest(reachable=reachable), patch('bridge.wireless.service_snapshot', return_value=[]), patch('bridge.wireless.connect', side_effect=OSError('connection failed')), patch('bridge.wireless.port_reachable', return_value=reachable):
                with self.assertRaises(OSError) as error:
                    wireless.connect_candidate('adb', row, None)
                self.assertEqual(isinstance(error.exception, wireless.PairingRequired), reachable)


if __name__ == '__main__':
    unittest.main()
