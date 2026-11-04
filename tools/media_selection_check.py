"""Native modifier clicks and selected-file transfer using generated fixtures only."""
import sys
from pathlib import Path
ROOT=Path(r'D:\CODING WORKS\ChatGPT\MobileTrans App')
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'vendor'))
import hashlib
import subprocess
import tempfile
import time
from PIL import Image
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

with tempfile.TemporaryDirectory(prefix='bridge-selection-') as temporary:
    root=Path(temporary); source=root/'source'; a=source/'Album A'; a.mkdir(parents=True)
    b=source/'Album B'; b.mkdir(); target=root/'target'; target.mkdir()
    for index in range(120):Image.new('RGB',(80,60),(index,80,150)).save(a/f'keep-{index:03}.jpg')
    Image.new('RGB',(80,60),'yellow').save(a/'outside-search.jpg')
    Image.new('RGB',(80,60),'red').save(b/'other.jpg')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-f','lavfi','-i','color=c=teal:s=160x120:d=0.3','-c:v','libx264',str(a/'keep-005.mp4')],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    app=App(home=root/'data'); app.endpoints=[Folder(source),Folder(target)]
    gallery=app.gallery; gallery.source_var.set(app.endpoints[0].label); gallery.load()
    until(app,lambda:not app.busy and len(gallery.items)==123)
    gallery.album='Album A'; gallery.kind.set('Photos only'); gallery.render(); app.update()
    names=[row['path'] for row in gallery.filtered()]
    def click(name,mask=0,thumbnail=False):
        until(app,lambda:name in gallery.cards)
        card,thumb,_=gallery.cards[name]
        widget=thumb if thumbnail else next(child for child in card.winfo_children() if child.winfo_class()=='TCheckbutton')
        widget.event_generate('<ButtonPress-1>',x=8,y=8,state=mask)
        widget.event_generate('<ButtonRelease-1>',x=8,y=8,state=mask)
        app.update()
    click(names[1]); assert gallery.chosen=={names[1]},'Checkbox must toggle exactly once'
    click(names[4],4); assert gallery.chosen=={names[1],names[4]}
    click(names[4],4); assert gallery.chosen=={names[1]}
    click(names[1],4)  # Deselect the anchor, then select again to start the range.
    click(names[1]); click(names[7],1)
    assert gallery.chosen==set(names[1:8])
    assert gallery.selection_anchor==names[1]
    gallery.clear_selection(); click(names[7]); click(names[2],1)
    assert gallery.chosen==set(names[2:8]),'Reverse Shift range'
    gallery.clear_selection(); click(names[5],1)
    assert gallery.chosen=={names[5]},'Shift with no anchor starts at the clicked file'
    gallery.clear_selection(); click(names[3],4,thumbnail=True)
    assert gallery.chosen=={names[3]} and gallery.preview is None
    click(names[8],1,thumbnail=True)
    assert gallery.chosen==set(names[3:9]) and gallery.preview is None
    # Virtualized off-screen tiles still belong to the range.
    gallery.clear_selection(); click(names[2]); anchor=names[2]
    gallery.thumb_canvas.yview_moveto(1); app.update()
    until(app,lambda:names[-1] in gallery.cards)
    assert anchor not in gallery.cards
    top=gallery.thumb_canvas.canvasy(0)
    click(names[-1],1)
    assert gallery.chosen==set(names[2:])
    assert abs(gallery.thumb_canvas.canvasy(0)-top)<2
    assert all(selected.get()==(name in gallery.chosen) for name,(_,_,selected) in gallery.cards.items())
    # A changed filter resets the anchor, but retains explicit prior selections.
    gallery.chosen={'Album B/other.jpg'}; gallery.search.set('keep-00'); app.update()
    filtered=[row['path'] for row in gallery.filtered()]
    assert len(filtered)==10 and gallery.selection_anchor is None
    click(filtered[1]); click(filtered[8],1)
    expected={'Album B/other.jpg',*filtered[1:9]}
    assert gallery.chosen==expected
    assert 'Album A/keep-005.mp4' not in gallery.chosen
    # Disabled/busy input cannot change the operation's selection.
    app.busy=True; click(filtered[0],4); assert gallery.chosen==expected; app.busy=False
    # Keyboard activation keeps the anchor and the visible checkboxes coherent.
    card,_,_=gallery.cards[filtered[0]]
    check=next(child for child in card.winfo_children() if child.winfo_class()=='TCheckbutton')
    check.invoke(); app.update(); expected.add(filtered[0])
    assert gallery.chosen==expected and gallery.selection_anchor==filtered[0]
    # Only the explicitly selected generated files reach the real copy pipeline.
    gallery.target_var.set(app.endpoints[1].label); gallery.send()
    until(app,lambda:not app.busy)
    assert app.last_result['copied']==len(expected)
    actual={p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
    assert actual==expected,(actual,expected)
    gallery.clear_selection(); assert not gallery.chosen and gallery.selection_anchor is None
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in before.items())
    app.destroy()
    print('PASS: real checkbox modifier events without double toggles; Ctrl individual toggle; forward/reverse/no-anchor Shift; modifier thumbnail clicks; virtualized ranges; scroll/checkbox retention; album/search/type scope; busy guard; keyboard toggle; exact selected-file transfer; original hashes')
