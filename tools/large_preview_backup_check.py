"""Generated-photo and vCard fixtures; mock only app APK transport and Explorer."""
import sys
from pathlib import Path
ROOT=Path(r'D:\CODING WORKS\ChatGPT\MobileTrans App')
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'vendor'))
import hashlib
import tempfile
import time
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageGrab
from bridge.app import App
from bridge.engine import Folder,Android

def until(app,condition,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update()
        if condition():return
        time.sleep(.02)
    raise AssertionError('UI condition timed out')

def screenshot(widget,name):
    widget.attributes('-topmost',True); widget.lift(); widget.update(); time.sleep(.2)
    x,y=widget.winfo_rootx(),widget.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+widget.winfo_width(),y+widget.winfo_height())).save(Path(__file__).parent/name)

with tempfile.TemporaryDirectory(prefix='bridge-large-preview-') as temporary:
    root=Path(temporary); source=root/'photos'; source.mkdir()
    photo=source/'large.jpg'; picture=Image.new('RGB',(1920,1080),'#253850')
    ImageDraw.Draw(picture).text((130,300),'Larger native preview',(240,230,255),font_size=100)
    picture.save(photo); before=hashlib.sha256(photo.read_bytes()).hexdigest()
    Image.new('RGB',(600,1600),'#4e8068').save(source/'portrait.jpg')
    app=App(home=root/'data'); app.attributes('-topmost',True)
    app.endpoints=[Folder(source)]; gallery=app.gallery
    gallery.source_var.set(app.endpoints[0].label); gallery.load()
    until(app,lambda:not app.busy and len(gallery.items)==2)
    gallery.open_preview(next(i for i in gallery.items if i['path']=='large.jpg'))
    until(app,lambda:gallery.preview_local is not None)
    canvas=gallery.preview_image
    assert canvas.picture.size==(1920,1080)
    assert gallery.preview.winfo_width()>800 and canvas.image.width()>680
    initial=canvas.image.width()
    gallery.preview.geometry('900x680')
    until(app,lambda:canvas.image.width()<initial)
    small=canvas.image.width()
    gallery.preview.geometry('1250x920')
    until(app,lambda:canvas.image.width()>small)
    assert abs(canvas.image.width()/canvas.image.height()-1920/1080)<.01
    with patch('bridge.gallery.os.startfile') as launch:
        gallery.play_button.invoke(); launch.assert_not_called()
    screenshot(gallery.preview,'mediabridge-large-photo.png')
    gallery.close_preview(); app.update()
    assert canvas.picture is None
    gallery.open_preview(next(i for i in gallery.items if i['path']=='portrait.jpg'))
    until(app,lambda:gallery.preview_local is not None)
    assert gallery.preview_image.picture.size==(600,1600)
    assert abs(gallery.preview_image.image.width()/gallery.preview_image.image.height()-.375)<.01
    gallery.close_preview(); assert hashlib.sha256(photo.read_bytes()).hexdigest()==before

    phone=Android('fixture-adb','fixture','Fixture phone'); app.endpoints=[phone]
    app.show('Contacts'); panel=app.phone_panel; panel.phone_var.set(phone.label)
    panel.rows=[{'id':'a','name':'Fixture Alice','detail':'123','card':b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Fixture Alice\r\nTEL:123\r\nEND:VCARD\r\n'}]
    panel.chosen={'a'}; panel.render()
    assert panel.open_backup_button.cget('state')=='disabled'
    destination=root/'contact export'; destination.mkdir()
    panel.contact_format.set('Individual .vcf files')
    with patch('bridge.phone_pages.filedialog.askdirectory',return_value=str(destination)),patch('bridge.phone_pages.messagebox.askyesno',return_value=False) as prompt:
        panel.backup(); until(app,lambda:not app.busy)
        prompt.assert_called_once()
    assert panel.backup_folder.parent==destination and (panel.backup_folder/'Fixture Alice.vcf').is_file()
    with patch('bridge.phone_pages.os.startfile') as launch:
        panel.open_backup_button.invoke(); launch.assert_called_once_with(str(panel.backup_folder))
    screenshot(app,'mediabridge-contacts-open-folder.png')
    panel.contact_format.set('One .vcf file (all selected)'); combined=destination/'combined.vcf'
    with patch('bridge.phone_pages.filedialog.asksaveasfilename',return_value=str(combined)),patch('bridge.phone_pages.messagebox.askyesno',return_value=True),patch('bridge.phone_pages.os.startfile') as launch:
        panel.backup(); until(app,lambda:not app.busy)
        assert combined.is_file(); launch.assert_called_once_with(str(destination))
    with patch('bridge.phone_pages.Path.is_dir',return_value=False),patch('bridge.phone_pages.messagebox.showerror') as error,patch('bridge.phone_pages.os.startfile') as launch:
        panel.open_backup_button.invoke(); error.assert_called_once(); launch.assert_not_called()

    app.show('Apps'); panel=app.phone_panel; panel.phone_var.set(phone.label)
    panel.rows=[{'id':'com.fixture.app','name':'Fixture app','detail':'com.fixture.app'}]
    panel.chosen={'com.fixture.app'}; panel.render()
    assert panel.open_backup_button.cget('state')=='disabled'
    appdir=root/'app export'; appdir.mkdir()
    def save_app(*args,**kwargs):
        path=appdir/'Fixture app.apk'; path.write_bytes(b'generated transport fixture'); return path
    with patch('bridge.phone_pages.filedialog.askdirectory',return_value=str(appdir)),patch('bridge.phone_pages.backend.backup_app_file',side_effect=save_app),patch.object(app,'remember_backup'),patch('bridge.phone_pages.messagebox.askyesno',return_value=True) as prompt,patch('bridge.phone_pages.os.startfile') as launch:
        panel.backup(); until(app,lambda:not app.busy)
        prompt.assert_called_once(); launch.assert_called_once_with(str(appdir))
    assert panel.backup_folder==appdir
    with patch('bridge.phone_pages.os.startfile') as launch:
        panel.open_backup_button.invoke(); launch.assert_called_once_with(str(appdir))
    screenshot(app,'mediabridge-apps-open-folder.png')
    for page in ['Apps','Contacts']:
        app.show(page); panel=app.phone_panel; panel.phone_var.set(phone.label)
        panel.rows=[{'id':'fixture','name':'Fixture','detail':'fixture','card':b'invalid vCard'}]; panel.chosen={'fixture'}
        with patch('bridge.phone_pages.filedialog.askdirectory',return_value=''),patch('bridge.phone_pages.filedialog.asksaveasfilename',return_value=''),patch('bridge.phone_pages.messagebox.askyesno') as prompt:
            panel.backup(); assert not app.busy; prompt.assert_not_called()
        with patch('bridge.phone_pages.filedialog.askdirectory',return_value=str(appdir)),patch('bridge.phone_pages.filedialog.asksaveasfilename',return_value=str(destination/'bad.vcf')),patch('bridge.phone_pages.backend.backup_app_file',side_effect=OSError('fixture failure')),patch('bridge.phone_pages.messagebox.askyesno') as prompt,patch('bridge.phone_pages.messagebox.showinfo'):
            panel.backup(); until(app,lambda:not app.busy); prompt.assert_not_called()
        assert panel.backup_folder is None and panel.open_backup_button.cget('state')=='disabled'
        app.geometry('900x680'); app.update()
        assert panel.open_backup_button.winfo_rootx()+panel.open_backup_button.winfo_width()<=app.winfo_rootx()+app.winfo_width()
    app.destroy()
    print('PASS: larger responsive landscape/portrait preview, read-only originals, real individual/combined vCard destinations, Apps destination, prompt and button actions, unavailable folder, cancellation/failure, compact layout')
