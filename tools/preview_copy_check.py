"""Generated photos only; validates real Windows clipboard image payloads."""
import sys
from pathlib import Path
ROOT=Path(r'D:\CODING WORKS\ChatGPT\MobileTrans App')
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'vendor'))
import ctypes
from ctypes import wintypes
import hashlib
import io
import tempfile
import threading
import time
from unittest.mock import patch
from PIL import Image,ImageGrab
from bridge.app import App
from bridge.engine import Folder
from bridge.clipboard_image import image_payloads,put_image_on_clipboard

def until(app,condition,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update()
        if condition():return
        time.sleep(.02)
    raise AssertionError('UI condition timed out')

with tempfile.TemporaryDirectory(prefix='bridge-copy-') as temporary:
    root=Path(temporary); source=root/'source'; source.mkdir()
    first=source/'00-blue.jpg'; Image.new('RGB',(1400,900),'blue').save(first)
    second=source/'01-oriented.jpg'; exif=Image.Exif(); exif[274]=6
    Image.new('RGB',(120,80),'green').save(second,exif=exif)
    transparent=source/'02-alpha.png'; Image.new('RGBA',(60,40),(255,0,0,0)).save(transparent)
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    app=App(home=root/'data'); app.attributes('-topmost',True)
    app.endpoints=[Folder(source)]; gallery=app.gallery; gallery.source_var.set(app.endpoints[0].label); gallery.load()
    until(app,lambda:not app.busy and len(gallery.items)==3)
    gallery.open_preview(gallery.items[0]); until(app,lambda:gallery.preview_local is not None)
    gallery.copy_button.invoke()
    until(app,lambda:'Image copied.' in gallery.preview_status.get())
    image=ImageGrab.grabclipboard()
    assert image.size==(1400,900) and image.getpixel((5,5))[2]>240
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR]; user.RegisterClipboardFormatW.restype=wintypes.UINT
    assert user.IsClipboardFormatAvailable(8) and user.IsClipboardFormatAvailable(user.RegisterClipboardFormatW('PNG'))
    gallery.next_button.invoke(); until(app,lambda:gallery.preview_local is not None)
    gallery.copy_button.focus_force(); app.update()
    gallery.copy_button.event_generate('<Control-c>')
    until(app,lambda:'Image copied.' in gallery.preview_status.get())
    image=ImageGrab.grabclipboard(); assert image.size==(80,120),'Clipboard must apply EXIF orientation'
    gallery.next_button.invoke(); until(app,lambda:gallery.preview_local is not None)
    gallery.copy_button.invoke(); until(app,lambda:'Image copied.' in gallery.preview_status.get())
    image=ImageGrab.grabclipboard(); assert image.getpixel((2,2))[:3]==(255,255,255)
    dib,png=image_payloads(transparent)
    assert Image.open(io.BytesIO(png)).getpixel((1,1))[3]==0
    # Decoding/clipboard contention errors remain visible; source bytes never change.
    with patch('bridge.gallery.put_image_on_clipboard',side_effect=OSError('Clipboard busy')),patch('bridge.gallery.messagebox.showerror') as error:
        gallery.copy_button.invoke(); until(app,lambda:error.called)
        assert gallery.copy_button.cget('state')=='normal'
    assert ImageGrab.grabclipboard().size==(60,40)
    # A cancelled load cannot overwrite the clipboard after a different item is shown.
    release=threading.Event(); started=threading.Event()
    def slow(path):started.set(); release.wait(5); return image_payloads(path)
    with patch('bridge.gallery.image_payloads',side_effect=slow),patch('bridge.gallery.put_image_on_clipboard') as publish:
        gallery.copy_button.invoke(); until(app,started.is_set)
        gallery.previous_button.invoke(); until(app,lambda:gallery.preview_local is not None)
        release.set()
        end=time.monotonic()+.5
        while time.monotonic()<end:app.update(); time.sleep(.02)
        publish.assert_not_called()
    with patch('bridge.gallery.image_payloads',side_effect=FileNotFoundError('Reconnect the source')),patch('bridge.gallery.messagebox.showerror') as error:
        gallery.copy_button.invoke(); until(app,lambda:error.called)
    assert ImageGrab.grabclipboard().size==(60,40)
    # Video entries never copy a misleading still frame.
    video=dict(gallery.preview_item,path='not-a-photo.mp4',kind='Videos')
    gallery.preview_items.append(video); gallery.preview_index=len(gallery.preview_items)-1; gallery.show_preview_item()
    assert gallery.copy_button.cget('state')=='disabled'
    gallery.close_preview(); app.update()
    assert ImageGrab.grabclipboard().size==(60,40),'Copied pixels survive closing the preview'
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==before for p,before in originals.items())
    app.destroy()
    print('PASS: native DIB/PNG clipboard, full-size photo pixels, Copy button, Ctrl+C, current photo after navigation, EXIF orientation, transparency, contention/decode errors, stale copy cancellation, video disabled, clipboard survives preview close, original hashes')
