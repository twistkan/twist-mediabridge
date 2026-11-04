"""Generated media only: MediaBridge timeline, pause/resume and album retention."""
import sys
from pathlib import Path
ROOT=Path(r'D:\CODING WORKS\ChatGPT\MobileTrans App')
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'vendor'))
import hashlib
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageGrab
import imageio_ffmpeg
from bridge.app import App
from bridge.engine import Folder,Android
from bridge.media import play_frames,video_duration

def until(app,condition,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update()
        if condition():return
        time.sleep(.02)
    raise AssertionError('UI condition timed out')

with tempfile.TemporaryDirectory(prefix='mediabridge-preview-') as temporary:
    root=Path(temporary); source=root/'source'; source.mkdir(); target=root/'target'; target.mkdir()
    for i in range(30):
        folder=source/f'Album-{i:02}'; folder.mkdir()
        Image.new('RGB',(200,140),'blue').save(folder/'one.jpg')
        Image.new('RGB',(200,140),'green').save(folder/'two.jpg')
    video=source/'Album-20'/'clip.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=12:d=8','-c:v','libx264',str(video)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    original=hashlib.sha256(video.read_bytes()).hexdigest()
    assert 7.8<video_duration(video)<8.2
    frames=[]; times=[]
    play_frames(video,threading.Event(),lambda frame:frames.append(frame.copy()),start=5,position=times.append,single=True)
    assert len(frames)==1 and times==[5.]
    first=[]; play_frames(video,threading.Event(),lambda frame:first.append(frame.copy()),single=True)
    assert first[0].tobytes()!=frames[0].tobytes(),'Seek must decode a different frame'
    app=App(home=root/'appdata')
    app.attributes('-topmost',True); app.lift()
    app.endpoints=[Folder(source),Folder(target)]
    gallery=app.gallery; gallery.source_var.set(app.endpoints[0].label); gallery.load()
    until(app,lambda:not app.busy and len(gallery.items)==61)
    assert int(gallery.album_list.cget('borderwidth'))==8
    assert gallery.album_list.bbox(2)[1]-gallery.album_list.bbox(1)[1] > gallery.album_list.bbox(1)[3], 'Album rows need breathing room'
    app.update(); time.sleep(.25)
    x,y=app.winfo_rootx(),app.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(Path(__file__).parent/'mediabridge-album-spacing.png')
    gallery.album='Album-20'; gallery.loaded(list(gallery.items)); app.update()
    gallery.album_list.see(21); gallery.album_list.yview_moveto(.5); app.update()
    sidebar=gallery.album_list.yview()[0]
    gallery.chosen={'Album-20/one.jpg'}; gallery.target_var.set(app.endpoints[1].label)
    gallery.send(); until(app,lambda:not app.busy)
    assert app.last_result['copied']==1 and gallery.album=='Album-20'
    assert abs(gallery.album_list.yview()[0]-sidebar)<.05,'Transfer moved sidebar'
    item=next(i for i in gallery.items if i['path'].endswith('clip.mp4'))
    gallery.open_preview(item)
    until(app,lambda:gallery.preview_local is not None and gallery.video_duration>7)
    bar=gallery.seek_bar
    def pointer(seconds):return SimpleNamespace(x=int(bar.coords(seconds)[0]))
    previous_image=gallery.preview_image.image
    gallery.begin_scrub(pointer(5)); gallery.end_scrub(pointer(5))
    until(app,lambda:not gallery.playing and gallery.video_position>4.7 and gallery.preview_image.image is not previous_image)
    assert gallery.video_position<5.3
    gallery.preview.focus_force(); app.update()
    gallery.preview.event_generate('<KeyPress-space>'); gallery.preview.event_generate('<KeyRelease-space>')
    until(app,lambda:gallery.playing and gallery.video_position>5.3)
    gallery.preview.event_generate('<KeyPress-space>'); gallery.preview.event_generate('<KeyRelease-space>'); app.update()
    assert not gallery.playing
    paused=gallery.video_position
    gallery.play_button.focus_force(); app.update()
    gallery.play_button.event_generate('<KeyPress-space>'); gallery.play_button.event_generate('<KeyRelease-space>')
    until(app,lambda:gallery.playing and gallery.video_position>paused+.15)
    gallery.play_preview(); assert not gallery.playing
    paused=gallery.video_position
    gallery.play_button.invoke(); until(app,lambda:gallery.video_position>paused+.15)
    previous_image=gallery.preview_image.image
    gallery.begin_scrub(pointer(1)); gallery.move_scrub(pointer(3)); gallery.end_scrub(pointer(3))
    until(app,lambda:gallery.playing and 2.8<gallery.video_position<4 and gallery.preview_image.image is not previous_image)
    gallery.play_preview(); assert not gallery.playing
    app.update()
    gallery.preview.attributes('-topmost',True); gallery.preview.lift(); gallery.preview.focus_force()
    app.update(); time.sleep(.3)
    output=Path(__file__).parent/'mediabridge-preview-timeline.png'
    x,y=gallery.preview.winfo_rootx(),gallery.preview.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+gallery.preview.winfo_width(),y+gallery.preview.winfo_height())).save(output)
    gallery.close_preview()
    # Actual delete completion flow, mocked transport only. Never delete phone fixtures.
    gallery.source=Android('fixture-adb','fixture','Fixture phone')
    gallery.chosen={'Album-20/one.jpg'}
    def run(task,fn,done,record=False):done(fn(lambda *args:None))
    gallery.app.run=run
    with patch('bridge.gallery.messagebox.askyesno',return_value=True),patch('bridge.delete_actions.delete_media',return_value=[('Album-20/one.jpg',True,'')]):
        gallery.delete_selected()
    assert gallery.album=='Album-20' and abs(gallery.album_list.yview()[0]-sidebar)<.05
    remaining=[i['path'] for i in gallery.items if i['album']=='Album-20']; gallery.chosen=set(remaining)
    with patch('bridge.gallery.messagebox.askyesno',return_value=True),patch('bridge.delete_actions.delete_media',return_value=[(p,True,'') for p in remaining]):
        gallery.delete_selected()
    assert gallery.album=='Album-21','Empty album must move forward'
    gallery.album='Album-29'; gallery.loaded([i for i in gallery.items if i['album']!='Album-29']); assert gallery.album=='Album-28'
    gallery.loaded([]); assert gallery.album is None
    assert hashlib.sha256(video.read_bytes()).hexdigest()==original
    app.destroy()
    print('PASS: fast seek, decoded frame, click/drag timeline, Space/click pause/resume, transfer retention, delete retention, next/previous empty-album fallback, original unchanged')
