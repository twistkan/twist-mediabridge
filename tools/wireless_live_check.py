"""Optional user-assisted pairing test; reads connection metadata, not media."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from bridge.app import App
from bridge.engine import atomic_json

project = Path(__file__).resolve().parents[1]
report = project/'replica/wireless-live-check.json'
stop = project/'replica/wireless-live-check.stop'
with tempfile.TemporaryDirectory(prefix='twist-live-pair-') as folder:
    app = App(home=Path(folder)/'data')
    app.title('Twist MediaBridge · Wi-Fi pairing check')
    app.open_wireless()
    app.wireless_dialog.start_qr()
    panel = app.wireless_dialog
    session_name = panel.qr_session.name
    deadline = panel.qr_session.expires
    def stage(*args):
        atomic_json(report, {'status':'waiting_for_authorization', 'stage':panel.status.get(),
                            'qr_service':session_name, 'expires_in_seconds':max(0,round(deadline-time.monotonic())),
                            'media_read':False})
    panel.status.trace_add('write', stage)
    stage()
    def check():
        if stop.exists():
            app.destroy()
            return
        if app.status.get().startswith('Wi-Fi connected'):
            atomic_json(report,{'status':'authorized_connection_verified','transport':'Wi-Fi','media_read':False})
            app.status.set('Connection verified. This temporary test will close; use the installed app for transfers.')
            app.after(2000,app.destroy)
            return
        app.after(250,check)
    app.after(250,check)
    app.mainloop()
