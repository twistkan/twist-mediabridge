"""Exercise the real wireless UI with simulated ADB; never pair a real phone."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from unittest.mock import patch
from PIL import ImageGrab
from bridge.app import App
from bridge.engine import Android


def wait(app, dialog):
    deadline = time.monotonic() + 8
    while dialog.winfo_exists() and dialog.running and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    app.update()
    assert not dialog.winfo_exists() or not dialog.running, 'UI worker timed out'


with patch('bridge.wireless.wait_for_pin_server', side_effect=lambda adb,row,cancel,**kwargs: dict(row,pair_address='192.168.1.20:37123')), patch('bridge.wireless.multicast_snapshot', return_value=[]), patch('bridge.wireless_dialog.messagebox.showerror') as errors, patch('bridge.wireless_dialog.simpledialog.askstring', return_value=None) as pin_prompt, tempfile.TemporaryDirectory() as temp:
    app = App(home=Path(temp) / 'data')
    app.attributes('-topmost', True)
    app.open_wireless()
    dialog = app.wireless_dialog
    app.update()
    for size in ('780x710', '720x690'):
        dialog.geometry(size)
        app.update()
        # The fixed status/close footer remains accessible; form can scroll.
        footer = dialog.footer
        assert footer.winfo_viewable()
        assert footer.winfo_rooty() + footer.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
        for widget in footer.winfo_children():
            assert widget.winfo_viewable()
            assert widget.winfo_rooty() + widget.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
    dialog.geometry('780x710')
    assert not dialog.manual.winfo_ismapped(), 'Manual IP entry should be hidden by default'
    mdns = b'adb-demo-pair _adb-tls-pairing._tcp 192.168.1.20:37123\nadb-demo-connect _adb-tls-connect._tcp 192.168.1.20:44444\n'
    live = [False]
    commands = []
    def fake_adb(adb, args, cancel=None, **kwargs):
        commands.append((args, kwargs))
        if args == ['mdns', 'services']:
            return mdns
        if args == ['devices', '-l']:
            return b'List of devices attached\n' + (b'192.168.1.20:44444 device model:Demo_Galaxy\n' if live[0] else b'')
        if args[0] == 'pair':
            assert kwargs['input_data'] == b'012345\n'
            return b'Successfully paired to 192.168.1.20:37123'
        if args[0] == 'connect':
            live[0] = True
            return b'connected to 192.168.1.20:44444'
        if args[-1] == 'get-state':
            return b'device'
        raise AssertionError(args)
    with patch('bridge.wireless.adb_run', side_effect=fake_adb), patch('bridge.engine.adb_run', side_effect=fake_adb):
        dialog.start_find()
        wait(app, dialog)
        assert len(dialog.nearby_rows) == 1
        screenshots = Path(__file__).resolve().parents[1] / 'replica/clone-screens'
        screenshots.mkdir(exist_ok=True)
        x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+dialog.winfo_width(),y+dialog.winfo_height())).save(screenshots / 'Wi-Fi-nearby.png')
        dialog.nearby_tree.selection_set('0')
        dialog.choose_candidate()
        dialog.code.set('012345')
        dialog.start_auto_pair()
        wait(app, dialog)
    assert app.page == 'Media library'
    assert app.gallery.source_var.get().startswith('Demo Galaxy')
    assert [args for args, _ in commands if args[0] == 'connect'] == [['connect', '192.168.1.20:44444']]
    app.open_wireless()
    dialog = app.wireless_dialog
    app.update()
    with patch('bridge.wireless.service_snapshot', return_value=[]), patch('bridge.wireless.discover', return_value=([], [])):
        with patch('bridge.wireless.nearby', return_value=[]):
            dialog.start_find()
            wait(app, dialog)
    assert 'No phone advertised' in dialog.status.get()
    candidate = {'id':'fixture', 'name':'fixture', 'host':'192.168.1.20', 'pair_address':'',
                 'connect_address':'192.168.1.20:44444', 'connect_service':'adb-demo-connect',
                 'connected_serial':'', 'label':'Demo phone'}
    dialog.nearby_rows['0'] = candidate
    dialog.nearby_tree.insert('', 'end', iid='0', values=('Demo phone', 'Detected · not connected'))
    dialog.nearby_tree.selection_set('0')
    dialog.choose_candidate()
    app.update()
    from bridge.wireless import PairingRequired
    with patch('bridge.wireless.connect_candidate', side_effect=PairingRequired('This computer is not paired.')):
        dialog.start_selected_connect()
        wait(app, dialog)
    pin_prompt.assert_called_once()
    assert 'pairing is not complete' in dialog.status.get()
    text = dialog.status.get()
    dialog.choose_candidate()  # Regression: repeated selection erased connection errors.
    assert dialog.status.get() == text
    dialog.code.set('012345')
    dialog.choose_candidate()
    assert dialog.code.get() == '012345', 'Repeated selection erased entered PIN'
    dialog.code.set('')
    with patch('bridge.wireless.connect_candidate', side_effect=OSError('The selected phone is offline.')):
        dialog.start_selected_connect()
        wait(app, dialog)
    assert errors.call_args.args[0] == 'Wi-Fi connection not completed'
    assert dialog.status.get() == 'The selected phone is offline.'
    dialog.choose_candidate()
    assert dialog.status.get() == 'The selected phone is offline.'
    assert dialog.action_status.cget('fg') == '#ffabbf'
    dialog.toggle_manual()
    app.update()
    assert dialog.manual.winfo_ismapped()
    dialog.pair_address.set('192.168.1.20:37123')
    dialog.code.set('012345')
    with patch('bridge.wireless.adb_run', return_value=b'Successfully paired to 192.168.1.20:37123') as run:
        dialog.start_pair()
        wait(app, dialog)
        assert 'Paired.' in dialog.status.get()
        assert dialog.code.get() == ''
        assert run.call_args.kwargs['input_data'] == b'012345\n'
    dialog.connect_address.set('192.168.1.20:44444')
    phone = Android(app.adb, '192.168.1.20:44444', 'Demo Galaxy')
    with patch('bridge.wireless.adb_run', side_effect=[b'connected to 192.168.1.20:44444', b'device']), patch('bridge.wireless.discover', return_value=([phone], [])):
        dialog.start_connect()
        wait(app, dialog)
    assert app.page == 'Media library'
    assert app.gallery.source_var.get() == phone.label
    assert 'Wi-Fi phone connected' in app.gallery.stats.get()
    app.open_wireless()
    dialog = app.wireless_dialog
    app.update()
    with patch('bridge.wireless.adb_run', side_effect=OSError('fixture failed')):
        dialog.connect_address.set(phone.serial)
        dialog.start_connect()
        wait(app, dialog)
        assert 'Could not connect.' in dialog.status.get()
    screenshots = Path(__file__).resolve().parents[1] / 'replica/clone-screens'
    screenshots.mkdir(exist_ok=True)
    x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+dialog.winfo_width(),y+dialog.winfo_height())).save(screenshots / 'Wi-Fi-connection.png')
    with patch('bridge.wireless.adb_run', return_value=b'disconnected 192.168.1.20:44444'):
        dialog.start_disconnect()
        wait(app, dialog)
    assert not app.endpoints
    assert app.gallery.source_var.get() == ''
    app.open_wireless()
    dialog = app.wireless_dialog
    app.update()
    dialog.nearby_rows['0'] = candidate
    dialog.nearby_tree.insert('', 'end', iid='0', values=('Demo phone', 'Detected · not connected'))
    dialog.nearby_tree.selection_set('0')
    dialog.choose_candidate()
    app.update()
    pin_prompt.return_value = '012345'
    with patch('bridge.wireless.connect_candidate', side_effect=PairingRequired('Pair this computer.')), patch('bridge.wireless.pair_and_connect', return_value=(([phone], []), phone.serial)) as pair:
        dialog.start_selected_connect()
        wait(app, dialog)
    assert pair.call_args.args[2] == '012345'
    assert not dialog.winfo_exists()
    assert app.gallery.source_var.get() == phone.label
    app.open_wireless()
    dialog = app.wireless_dialog
    dialog.code.set('123456')
    dialog.close()
    assert dialog.cancel.is_set() and dialog.code.get() == ''
    app.destroy()
    assert not (Path(temp) / 'data/errors.log').exists()
    print('Wireless UI: automatic discovery/PIN/connect, empty discovery, manual fallback, minimum/default layout, secret handling, pair/connect, error, disconnect and cancel passed.')
