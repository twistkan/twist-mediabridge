"""Own-window native DROPFILES -> Tk page -> real HTTPS upload fixture."""
import ctypes
from ctypes import wintypes as W
import sys
from pathlib import Path
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from bridge.app import App
from bridge.companion_link import Link,Companion
from test_companion_link import Phone


def wait(app, predicate, seconds=20):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.update()
        if predicate():return
        time.sleep(.02)
    raise AssertionError('UI timed out: '+app.status.get())


def drop(app,paths):
    # Test only our own window. HDROP is the documented DROPFILES header + UTF-16 list.
    import struct
    payload=struct.pack('<IiiII',20,0,0,0,1)+('\0'.join(map(str,paths))+'\0\0').encode('utf-16le')
    kernel=ctypes.WinDLL('kernel32');user=ctypes.WinDLL('user32')
    kernel.GlobalAlloc.argtypes=[W.UINT,ctypes.c_size_t];kernel.GlobalAlloc.restype=W.HGLOBAL
    kernel.GlobalLock.argtypes=[W.HGLOBAL];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[W.HGLOBAL]
    user.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];user.SendMessageW.restype=ctypes.c_ssize_t
    handle=kernel.GlobalAlloc(0x42,len(payload));pointer=kernel.GlobalLock(handle)
    ctypes.memmove(pointer,payload,len(payload));kernel.GlobalUnlock(handle)
    user.SendMessageW(app.file_drop.hwnd,0x233,handle,0)


with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    link=Link('127.0.0.1');fixture=Phone(link)
    app=App(home=root/'settings')
    try:
        app.endpoints=[Companion(link)]
        received=[];original=fixture.operation
        def operation(kind,args):
            if kind=='upload_finish':received.append(bytes(fixture.uploads['fixture']))
            return original(kind,args)
        fixture.operation=operation
        paths=[root/'Résumé 你好.bin',root/'photo with spaces.jpg']
        for index,path in enumerate(paths):path.write_bytes(bytes([index+1])*700000)
        assert app.file_drop.hwnd,'Native file drop registration missing'
        drop(app,paths)
        wait(app,lambda:app.last_result is not None and not app.busy)
        assert app.page=='Send to phone'
        assert app.last_result['copied']==2 and len(app.last_result['items'])==2
        assert received==[p.read_bytes() for p in paths]
        assert not app.send_queue and all(p.exists() for p in paths)
        # Queue survives navigation and device discovery; manual mode never auto-sends.
        app.send_panel.auto.set(False);app.send_panel.save_auto()
        drop(app,[paths[0]])
        wait(app,lambda:len(app.send_queue)==1)
        assert not app.busy and len(received)==2
        app.show('Overview');app.show('Send to phone')
        assert app.send_panel.listbox.size()==1 and not app.send_panel.auto.get()
        # Multiple phones require choosing a destination.
        app.send_panel.clear();app.settings.pop('send_phone_key',None)
        second=Companion(link);second.label='Second fixture phone'
        app.endpoints.append(second);app.show('Send to phone')
        app.send_panel.auto.set(True)
        drop(app,[paths[0]])
        wait(app,lambda:len(app.send_queue)==1)
        assert not app.busy and not app.send_panel.phone_var.get()
        app.send_panel.phone_var.set(second.label);app.send_panel.send()
        wait(app,lambda:not app.busy)
        assert not app.send_queue and len(received)==3
    finally:
        fixture.close();link.close();app.destroy()
print('Native Windows drop, Unicode/multiple files, HTTPS upload, manual queue, navigation and multiple-phone selection: passed')
