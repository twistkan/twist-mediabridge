"""Real Tk + HTTPS companion fixture: pairing, contacts, media privacy, old methods."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import tempfile
import time
from unittest.mock import patch
from bridge.app import App
from bridge.companion_link import Companion
from test_companion_link import Phone


def wait(app,predicate,seconds=15):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        app.update();time.sleep(.02)
    app.update()
    assert predicate(),'UI check timed out'


with tempfile.TemporaryDirectory() as folder:
    app=App(home=Path(folder)/'settings');app.withdraw()
    with patch('bridge.companion_dialog.local_addresses',return_value=['127.0.0.1']):
        app.open_companion()
    dialog=app.companion_dialog
    dialog.start()
    wait(app,lambda:dialog.link is not None)
    assert dialog.photo is not None
    dialog.geometry('660x650');app.update()
    assert dialog.qr.winfo_height()>=dialog.photo.height(),'Pairing QR must not be cropped at minimum size'
    fixture=Phone(dialog.link)
    original_operation=fixture.operation
    deleted=[]
    def operation(kind,args):
        if kind=='files':return original_operation(kind,args)+[{'path':'DCIM/unselected.jpg','size':12,'modified':1}]
        if kind=='delete_media':deleted.append(args['path']);return True
        return original_operation(kind,args)
    fixture.operation=operation
    wait(app,lambda:any(isinstance(e,Companion) for e in app.endpoints))
    phone=app.endpoints[-1]
    assert app.gallery.source_var.get()==phone.label
    app.show('Contacts');panel=app.phone_panel
    panel.phone_var.set(phone.label);panel.load()
    wait(app,lambda:not app.busy)
    assert len(panel.rows)==1 and panel.rows[0]['name']=='Fixture Person'
    # Exercise the actual Apps > Reinstall file handler against HTTPS staging.
    app.show('Apps');panel=app.phone_panel
    panel.phone_var.set(phone.label)
    apk=Path(folder)/'Fixture.apk';apk.write_bytes(b'APK fixture'*60000)
    with patch('bridge.phone_pages.filedialog.askopenfilename',return_value=str(apk)), patch('bridge.phone_pages.messagebox.showinfo') as installed:
        panel.restore()
        wait(app,lambda:not app.busy)
        assert 'confirmed' in panel.summary.get() and installed.called
    assert fixture.operations.count('install_upload_begin')==1
    assert 'install_release' in fixture.operations
    # Existing ADB dialog must still open with a companion endpoint present.
    app.open_wireless();app.update();assert app.wireless_dialog.winfo_exists();app.wireless_dialog.close()
    app.show('Media library');gallery=app.gallery
    gallery.enqueue=lambda *args:None
    gallery.source_var.set(phone.label);gallery.load()
    wait(app,lambda:not app.busy)
    assert len(gallery.items)==2
    selected=gallery.items[0]['path']
    gallery.chosen.add(selected)
    with patch('bridge.gallery.messagebox.askyesno',return_value=True):
        gallery.delete_selected()
        wait(app,lambda:not app.busy)
    assert deleted==[selected] and len(gallery.items)==1
    assert gallery.items[0]['path']=='DCIM/unselected.jpg' and not gallery.chosen
    gallery.chosen.add(gallery.items[0]['path'])
    gallery.open_preview(gallery.items[0]);preview=gallery.preview
    cache=gallery.session_cache;(cache/'private-fixture').write_text('fixture')
    fixture.close();dialog.disconnect()
    wait(app,lambda:gallery.source is None,6)
    assert not gallery.items and not gallery.chosen and not preview.winfo_exists()
    wait(app,lambda:not cache.exists(),4)
    assert phone not in app.endpoints
    dialog.close();app.destroy()
print('Companion QR, HTTPS pairing, contacts, media scan, selected-media deletion, privacy clearing and existing wireless dialog: passed')
