import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from bridge import wireless
from bridge.engine import Android, Cancelled, adb_run


class WirelessTests(unittest.TestCase):
    def test_addresses_reject_commands_and_invalid_targets(self):
        for value in ('', '192.168.1.2', '192.168.1.2:0', '192.168.1.2:65536',
                      'localhost:5555', '127.0.0.1:5555', '0.0.0.0:5555',
                      '192.168.1.2:5555; whoami', '-a:5555', '999.1.1.1:5555'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                wireless.endpoint(value)
        self.assertEqual(wireless.endpoint(' 192.168.1.20:37123 '), '192.168.1.20:37123')
        self.assertEqual(wireless.endpoint('[fd00::2]:37123'), '[fd00::2]:37123')

    def test_pair_code_is_stdin_not_command_argument(self):
        with patch('bridge.wireless.adb_run', return_value=b'Enter pairing code: Successfully paired to 192.168.1.20:37123') as run:
            self.assertIn('Paired.', wireless.pair('adb', '192.168.1.20:37123', '012345', threading.Event()))
        self.assertEqual(run.call_args.args[1], ['pair', '192.168.1.20:37123'])
        self.assertEqual(run.call_args.kwargs['input_data'], b'012345\n')
        self.assertNotIn('012345', repr(run.call_args.args))

    def test_bad_code_and_failed_pairing_do_not_leak_code(self):
        with patch('bridge.wireless.adb_run') as run:
            for code in ('12345', 'abcdef', '１２３４５６', '123456\n'):
                with self.assertRaises(ValueError):
                    wireless.pair('adb', '192.168.1.2:12345', code, None)
            run.assert_not_called()
        with patch('bridge.wireless.adb_run', side_effect=OSError('raw secret 123456')):
            with self.assertRaises(OSError) as error:
                wireless.pair('adb', '192.168.1.2:12345', '123456', None)
            self.assertNotIn('123456', str(error.exception))
        with patch('bridge.wireless.adb_run', return_value=b'Failed: wrong code'):
            with self.assertRaises(OSError):
                wireless.pair('adb', '192.168.1.2:12345', '123456', None)

    def test_connect_requires_live_authorized_exact_target(self):
        phone = Android('adb', '192.168.1.2:34567', 'Galaxy')
        with patch('bridge.wireless.adb_run', side_effect=[b'connected to 192.168.1.2:34567', b'device']), patch('bridge.wireless.discover', return_value=([phone], [])):
            self.assertEqual(wireless.connect('adb', phone.serial, None)[0], [phone])
        for output in (b'failed to connect', b'cannot connect to host', b'already failed'):
            with patch('bridge.wireless.adb_run', return_value=output), self.assertRaises(OSError):
                wireless.connect('adb', phone.serial, None)
        with patch('bridge.wireless.adb_run', side_effect=[b'connected to target', b'unauthorized']), self.assertRaises(OSError):
            wireless.connect('adb', phone.serial, None)
        with patch('bridge.wireless.adb_run', side_effect=[b'connected to target', b'device']), patch('bridge.wireless.discover', return_value=([], [])), self.assertRaises(OSError):
            wireless.connect('adb', phone.serial, None)

    def test_disconnect_only_exact_wifi_target(self):
        with patch('bridge.wireless.adb_run', return_value=b'disconnected 192.168.1.2:34567') as run:
            wireless.disconnect('adb', '192.168.1.2:34567', None)
            self.assertEqual(run.call_args.args[1], ['disconnect', '192.168.1.2:34567'])
            with self.assertRaises(ValueError):
                wireless.disconnect('adb', 'USB-SERIAL', None)
            self.assertEqual(run.call_count, 1)
        self.assertTrue(wireless.wireless_serial('adb-fixture-abc._adb-tls-connect._tcp'))

    def test_cancel_is_not_converted_to_pair_failure(self):
        with patch('bridge.wireless.adb_run', side_effect=Cancelled()):
            with self.assertRaises(Cancelled):
                wireless.pair('adb', '192.168.1.2:12345', '123456', None)

    def test_real_process_receives_stdin_and_remains_cancellable(self):
        output = adb_run(sys.executable, ['-c', 'import sys; print(sys.stdin.readline().strip())'], input_data=b'fixture-input\n', timeout=5)
        self.assertEqual(output.strip(), b'fixture-input')
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            adb_run(sys.executable, ['-c', 'import time; time.sleep(5)'], cancel, input_data=b'fixture\n')


if __name__ == '__main__':
    unittest.main()
