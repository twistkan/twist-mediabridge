"""PIN prompt appears only after a simulated phone opens its code screen."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile,time,threading
from unittest.mock import patch
from bridge.app import App
from bridge.engine import Android

with tempfile.TemporaryDirectory() as folder,patch('bridge.wireless_dialog.simpledialog.askstring',return_value='012345') as prompt,patch('bridge.wireless_dialog.messagebox.showerror') as errors:
    app=App(home=Path(folder)/'data')
    app.open_wireless()
    dialog=app.wireless_dialog
    row={'id':'fixture','name':'fixture','host':'192.168.1.20','pair_address':'',
         'connect_address':'192.168.1.20:45555','connect_service':'fixture','connected_serial':'','label':'Demo phone'}
    dialog.nearby_rows['0']=row
    dialog.nearby_tree.insert('','end',iid='0',values=('Demo phone','Open code screen on phone'))
    dialog.nearby_tree.selection_set('0');dialog.choose_candidate();app.update()
    ready=threading.Event()
    def wait_phone(adb,row,cancel,**kwargs):
        kwargs['report']('Waiting for the phone code screen. No notification is sent.')
        assert ready.wait(5)
        return dict(row,pair_address='192.168.1.20:37123')
    phone=Android(app.adb,'192.168.1.20:45555','Demo phone')
    with patch('bridge.wireless.wait_for_pin_server',side_effect=wait_phone),patch('bridge.wireless.pair_and_connect',return_value=(([phone],[]),phone.serial)) as pair:
        dialog.start_auto_pair()
        end=time.monotonic()+.3
        while time.monotonic()<end:app.update();time.sleep(.02)
        prompt.assert_not_called();pair.assert_not_called()
        assert dialog.running and 'No notification' in dialog.status.get()
        ready.set()
        end=time.monotonic()+5
        while dialog.winfo_exists() and time.monotonic()<end:app.update();time.sleep(.02)
        assert not dialog.winfo_exists()
        prompt.assert_called_once()
        assert pair.call_args.args[2]=='012345'
    assert app.gallery.source_var.get()==phone.label
    app.open_wireless();dialog=app.wireless_dialog
    dialog.selected_candidate=row
    prompt.reset_mock()
    with patch('bridge.wireless.wait_for_pin_server',side_effect=TimeoutError('Code screen was not detected.')):
        dialog.prompt_pairing('Pairing required')
        end=time.monotonic()+5
        while dialog.running and time.monotonic()<end:app.update();time.sleep(.02)
        prompt.assert_not_called()
        assert 'not detected' in dialog.status.get()
        errors.assert_called_once()
    app.destroy()
    print('PIN readiness UI: no premature prompt, code-screen detection, successful pairing and clear timeout passed.')
