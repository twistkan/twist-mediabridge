"""Real Tk regression: queued thumbnails survive a transfer and all selections export."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from PIL import Image
from bridge.app import App
from bridge.engine import Folder


def wait(app,condition,timeout=15):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:
        app.update();time.sleep(.02)
    app.update();assert condition(),'UI condition timed out'


with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);source=root/'source';target=root/'target'
    source.mkdir();target.mkdir()
    items=[]
    for index in range(12):
        name=f'photo-{index:02}.jpg'
        Image.new('RGB',(200,150),(20,index*15,120)).save(source/name)
        items.append({'path':name,'album':'Main folder','kind':'Photos','size':(source/name).stat().st_size})
    app=App(home=root/'data');app.withdraw()
    gallery=app.gallery
    phone=Folder(source);destination=Folder(target)
    app.endpoints=[phone,destination];gallery.source=phone
    app.busy=True;app.current_task='Selected media transfer'
    gallery.loaded(items);app.update()
    # Give every worker time to dequeue a job while the transfer owns the link.
    end=time.monotonic()+.6
    while time.monotonic()<end:app.update();time.sleep(.02)
    assert not gallery.photos
    visible=set(gallery.cards)
    assert visible
    gallery.chosen={row['path'] for row in items}
    gallery.target_var.set(destination.label)
    app.busy=False;gallery.send()
    wait(app,lambda:not app.busy)
    assert app.last_result['requested']==12
    assert app.last_result['copied']==12 and app.last_result['failed']==0
    assert len(app.last_result['items'])==12
    assert len(list(target.iterdir()))==12
    wait(app,lambda:visible.issubset(gallery.photos))
    assert '12 selected in total' in gallery.stats.get()
    from types import SimpleNamespace
    app.reveal_focus(SimpleNamespace(widget=str(app.content)+'.native-popup'))
    app.destroy()
print('Paused thumbnails resume after transfer; all 12 selections export and receive per-file results: passed')
