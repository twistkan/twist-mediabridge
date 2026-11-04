"""Real native preview navigation with generated mixed media; no phone access."""
import sys
from pathlib import Path
ROOT=Path(r'D:\CODING WORKS\ChatGPT\MobileTrans App')
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'vendor'))
import hashlib
import subprocess
import tempfile
import time
from unittest.mock import patch
from PIL import Image,ImageGrab
import imageio_ffmpeg
from bridge.app import App
from bridge.engine import Folder

def until(app,condition,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update()
        if condition():return
        time.sleep(.02)
    raise AssertionError('UI condition timed out')

def arrow(app,widget,key):
    widget.focus_force(); app.update()
    widget.event_generate('<KeyPress-'+key+'>'); widget.event_generate('<KeyRelease-'+key+'>'); app.update()

with tempfile.TemporaryDirectory(prefix='bridge-preview-nav-') as temporary:
    root=Path(temporary); source=root/'source'; source.mkdir()
    album=source/'Album A'; album.mkdir(); other=source/'Album B'; other.mkdir()
    for name,color in [('00-photo.jpg','blue'),('02-photo.jpg','green'),('03-photo.jpg','red')]:
        Image.new('RGB',(1200,800),color).save(album/name)
    Image.new('RGB',(800,600),'yellow').save(other/'other.jpg')
    video=album/'01-video.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=12:d=3','-c:v','libx264',str(video)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    app=App(home=root/'data'); app.attributes('-topmost',True)
    app.endpoints=[Folder(source)]; gallery=app.gallery
    gallery.source_var.set(app.endpoints[0].label); gallery.load()
    until(app,lambda:not app.busy and len(gallery.items)==5)
    gallery.album='Album A'; gallery.render()
    first=next(i for i in gallery.filtered() if i['path'].endswith('00-photo.jpg'))
    gallery.open_preview(first); until(app,lambda:gallery.preview_local is not None)
    dialog=gallery.preview; canvas=gallery.preview_image
    assert len(gallery.preview_items)==4 and gallery.preview_index==0
    assert gallery.previous_button.cget('state')=='disabled' and gallery.next_button.cget('state')=='normal'
    gallery.preview.geometry('1040x800'); app.update()
    gallery.next_button.invoke(); until(app,lambda:gallery.preview_local is not None and gallery.video_duration>2)
    assert gallery.preview is dialog and gallery.preview_image is canvas and gallery.preview.winfo_width()==1040
    assert gallery.preview_item['kind']=='Videos' and gallery.preview_timeline.winfo_ismapped()
    gallery.play_button.invoke(); until(app,lambda:gallery.playing and gallery.video_position>.2)
    old_stop=gallery.preview_stop; old_token=gallery.preview_token; old_item=gallery.preview_item
    arrow(app,gallery.play_button,'Right'); until(app,lambda:gallery.preview_local is not None)
    assert gallery.preview_index==2 and not gallery.playing and old_stop.is_set()
    assert gallery.preview_item['path'].endswith('02-photo.jpg') and not gallery.preview_timeline.winfo_ismapped()
    assert '02-photo.jpg' in dialog.title() and '3 / 4' in gallery.preview_album.cget('text')
    gallery.preview_chosen.set(True); gallery.preview_toggle(gallery.preview_item)
    assert 'Album A/02-photo.jpg' in gallery.chosen and 'Album A/00-photo.jpg' not in gallery.chosen
    with patch('bridge.gallery.os.startfile') as launch:
        gallery.open_external(); launch.assert_called_once_with(album/'02-photo.jpg')
    # A shared canvas must reject old decode and duration events after navigation.
    current=gallery.preview_local; current_image=canvas.picture
    gallery.results.put(('preview',old_token,old_item,canvas,Image.new('RGB',(10,10),'pink'),'stale-path',None))
    gallery.results.put(('video_info',old_token,None,canvas,None,999,None))
    until(app,lambda:gallery.results.empty())
    assert gallery.preview_local==current and canvas.picture is current_image and gallery.video_duration==0
    gallery.next_button.invoke(); until(app,lambda:gallery.preview_local is not None)
    assert gallery.preview_index==3 and gallery.next_button.cget('state')=='disabled'
    arrow(app,canvas,'Right'); assert gallery.preview_index==3
    arrow(app,canvas,'Left'); until(app,lambda:gallery.preview_local is not None)
    assert gallery.preview_index==2 and gallery.preview_chosen.get()
    arrow(app,canvas,'Left'); until(app,lambda:gallery.video_duration>2)
    arrow(app,gallery.seek_bar,'Left'); until(app,lambda:gallery.preview_local is not None)
    assert gallery.preview_index==0 and gallery.preview_item['kind']=='Photos'
    arrow(app,canvas,'Left'); assert gallery.preview_index==0
    dialog.attributes('-topmost',True); dialog.lift(); app.update(); time.sleep(.2)
    x,y=dialog.winfo_rootx(),dialog.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+dialog.winfo_width(),y+dialog.winfo_height())).save(Path(__file__).parent/'mediabridge-preview-navigation.png')
    # Rapid switching while decoding must ultimately display only the latest item.
    for step in [1,1,-1,-1,1,1]:gallery.navigate_preview(step)
    until(app,lambda:gallery.preview_local is not None and str(gallery.preview_local).endswith('02-photo.jpg'))
    assert gallery.preview_index==2
    gallery.close_preview(); app.update()
    gallery.kind.set('Photos only'); gallery.search.set('02-photo')
    gallery.open_preview(next(i for i in gallery.filtered()))
    until(app,lambda:gallery.preview_local is not None)
    assert len(gallery.preview_items)==1 and gallery.previous_button.cget('state')==gallery.next_button.cget('state')=='disabled'
    gallery.close_preview()
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in originals.items())
    app.destroy()
    print('PASS: buttons and real keyboard arrows, same preview/size, mixed photo/video navigation, playback cancellation, boundaries, checkbox/external actions, stale-result rejection, rapid navigation, album/search/type filters, original hashes')
