"""Simulate an unplugged phone and a delayed scan callback in the real Tk app."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from unittest.mock import patch
from bridge.app import App
from bridge.engine import Android


with tempfile.TemporaryDirectory() as temp:
    app = App(home=Path(temp) / 'data')
    app.withdraw()
    gallery = app.gallery
    phone = Android('fixture-adb', '192.168.1.20:44444' if '--wifi' in sys.argv else 'fixture-phone')
    app.endpoints = [phone]
    gallery.enqueue = lambda *args: None
    gallery.source = phone
    items = [{'path': 'DCIM/Camera/private.jpg', 'album': 'DCIM/Camera', 'kind': 'Photos', 'size': 12}]
    gallery.loaded(items)
    gallery.chosen.add(items[0]['path'])
    gallery.open_preview(items[0])
    preview = gallery.preview
    cache = gallery.session_cache
    (cache / 'sensitive-preview.txt').write_text('fixture')
    with patch('bridge.gallery.adb_run', return_value=b'offline'):
        deadline = time.monotonic() + 5
        while gallery.source is not None and time.monotonic() < deadline:
            app.update()
            time.sleep(.02)
    assert gallery.source is None, 'Disconnected source must clear'
    assert not gallery.items and not gallery.chosen
    assert not preview.winfo_exists()
    assert gallery.album_list.size() == 0
    gallery.loaded(items)  # Late worker completion must not repopulate the page.
    assert not gallery.items
    deadline = time.monotonic() + 3
    while cache.exists() and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    assert not cache.exists(), 'Session preview cache must be removed'
    assert 'disconnected' in gallery.stats.get().lower()
    gallery.source = phone
    gallery.source_var.set(phone.label)
    app.endpoints = [phone]
    gallery.loaded(items)
    gallery.chosen.add(items[0]['path'])
    with patch('bridge.gallery.adb_run', side_effect=OSError('offline')), patch('bridge.gallery.scan_media') as scan:
        gallery.load()
        assert not gallery.items and not gallery.chosen, 'Load must clear stale media immediately'
        deadline = time.monotonic() + 5
        while app.busy and time.monotonic() < deadline:
            app.update()
            time.sleep(.02)
        scan.assert_not_called()
        assert not gallery.items
    for page in ['Contacts', 'Apps']:
        app.show(page)
        app.geometry('900x680')
        app.update()
        assert app.page == page
    app.destroy()
    print('Disconnect hides gallery, closes preview, clears selection/cache and rejects late scan results: passed')
    print('Contacts and Apps pages open at minimum window size: passed')
    print('Load albums while offline clears old media and never starts a cached scan: passed')
