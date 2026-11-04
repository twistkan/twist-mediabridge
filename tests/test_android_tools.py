import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from bridge.android_tools import resolve_adb
from bridge.engine import discover


class AndroidToolTests(unittest.TestCase):
    def test_clean_pc_and_legacy_settings_use_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'android').mkdir()
            bundled = root / 'android/adb.exe'
            bundled.touch()
            old = root / 'old-adb.exe'
            old.touch()
            with patch('bridge.android_tools.resource_path', side_effect=lambda name: root / name), patch('bridge.android_tools.shutil.which', return_value=None):
                self.assertEqual(resolve_adb(), str(bundled))
                self.assertEqual(resolve_adb({'adb': str(old)}), str(bundled))
                self.assertEqual(resolve_adb({'adb': str(old), 'adb_mode': 'custom'}), str(old))
                old.unlink()
                self.assertEqual(resolve_adb({'adb': str(old), 'adb_mode': 'custom'}), str(bundled))

    def test_source_checkout_uses_local_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tool = root / 'tools/android/platform-tools/adb.exe'
            tool.parent.mkdir(parents=True)
            tool.touch()
            with patch('bridge.android_tools.resource_path', side_effect=lambda name: root / name), patch('bridge.android_tools.shutil.which', return_value=None):
                self.assertEqual(resolve_adb(), str(tool))

    def test_discovery_accepts_galaxy_generations_and_other_android(self):
        output = 'List of devices attached\n' + '\n'.join(
            f'fixture{i} device product:phone model:{model} transport_id:{i}'
            for i, model in enumerate(('Galaxy_S21_Ultra', 'Galaxy_S22_Ultra', 'Galaxy_S23_Ultra', 'Galaxy_A55', 'Galaxy_Z_Fold', 'TECNO_CL6k'), 1))
        with patch('bridge.engine.adb_run', return_value=output.encode()):
            phones, blocked = discover('adb.exe')
        self.assertEqual(len(phones), 6)
        self.assertFalse(blocked)


if __name__ == '__main__':
    unittest.main()
