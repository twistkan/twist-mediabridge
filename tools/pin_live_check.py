"""User-assisted six-digit pairing test; never records the PIN or phone files."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from bridge.app import App
from bridge.engine import discover, atomic_json
from bridge.android_tools import resolve_adb
from bridge.wireless import service_snapshot, candidates
from bridge import wireless

project=Path(__file__).resolve().parents[1]
report=project/'replica/pin-live-check.json'
stop=project/'replica/pin-live-check.stop'
pin_pair_verified=False
original_pair=wireless.pair
def tracked_pair(*args,**kwargs):
    global pin_pair_verified
    result=original_pair(*args,**kwargs)
    pin_pair_verified=True
    return result
wireless.pair=tracked_pair
with tempfile.TemporaryDirectory(prefix='twist-pin-check-') as temp:
    app=App(home=Path(temp)/'data')
    app.title('Twist MediaBridge · Six-digit pairing test')
    ready,_=discover(app.adb)
    rows=candidates(service_snapshot(app.adb,app.cancel),ready)
    row=next((r for r in rows if '6d82dc0c' in r['name']),None)
    if row is None:
        atomic_json(report,{'status':'selected_phone_not_advertising','media_read':False})
        app.destroy()
    else:
        app.open_wireless()
        panel=app.wireless_dialog
        panel.nearby_rows['0']=row
        panel.nearby_tree.insert('','end',iid='0',values=(row['label'],'Open code screen on phone'))
        panel.nearby_tree.selection_set('0')
        panel.choose_candidate()
        def stage(*args):
            atomic_json(report,{'status':'testing_six_digit_pairing','stage':panel.status.get(),'media_read':False})
        panel.status.trace_add('write',stage)
        stage()
        app.after(250,panel.start_auto_pair)
        def check():
            if stop.exists():
                app.destroy()
                return
            if app.status.get().startswith('Wi-Fi connected'):
                atomic_json(report,{'status':'six_digit_pairing_and_connection_verified' if pin_pair_verified else 'existing_connection_only_PIN_unverified','pin_pair_command_verified':pin_pair_verified,'media_read':False})
                app.status.set('Six-digit pairing verified.' if pin_pair_verified else 'Existing connection is active; six-digit pairing was not completed.')
                app.after(2000,app.destroy)
                return
            app.after(250,check)
        app.after(250,check)
        app.mainloop()
