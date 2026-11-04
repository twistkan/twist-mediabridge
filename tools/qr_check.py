"""Real QR widgets and session lifecycle, with simulated phone responses."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from unittest.mock import patch
from bridge.app import App
from bridge.engine import Android, Cancelled


def wait(app, dialog):
    deadline = time.monotonic()+5
    while dialog.winfo_exists() and dialog.running and time.monotonic()<deadline:
        app.update()
        time.sleep(.02)
    app.update()
    assert not dialog.winfo_exists() or not dialog.running


with tempfile.TemporaryDirectory() as folder, patch('bridge.wireless_dialog.messagebox.showerror') as errors:
    app = App(home=Path(folder)/'data')
    app.open_wireless()
    dialog = app.wireless_dialog
    def cancelled(adb,session,cancel,report):
        cancel.wait(5)
        raise Cancelled()
    with patch('bridge.qr_pairing.pair_session', side_effect=cancelled):
        dialog.start_qr()
        app.update()
        assert dialog.qr_window.winfo_viewable()
        assert dialog.qr_photo.width()>200
        assert dialog.qr_window.winfo_width()>=520
        secret = dialog.qr_session.secret
        dialog.cancel_qr()
        wait(app,dialog)
        assert dialog.qr_window is None and dialog.qr_photo is None and dialog.qr_session is None
        assert dialog.status.get()=='Cancelled.'
    errors.assert_not_called()
    with patch('bridge.qr_pairing.pair_session', side_effect=TimeoutError('QR code expired.')):
        dialog.start_qr()
        wait(app,dialog)
        assert dialog.qr_window is None
        assert 'expired' in dialog.status.get()
        errors.assert_called_once()
    phone = Android(app.adb,'192.168.1.20:45555','Demo Galaxy')
    with patch('bridge.qr_pairing.pair_session', return_value=(([phone],[]),phone.serial)):
        dialog.start_qr()
        wait(app,dialog)
    assert not dialog.winfo_exists()
    assert app.gallery.source_var.get()==phone.label
    for path in (Path(folder)/'data').rglob('*'):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()
    app.destroy()
    print('QR UI: generation, cancel, expiry, verified success and in-memory credential cleanup passed.')
