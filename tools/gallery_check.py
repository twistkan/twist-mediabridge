"""Exercise album selection, previews and real selected-file transfer with generated fixtures."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
import subprocess
from bridge.app import App
from bridge.engine import Folder
from PIL import Image, ImageDraw, ImageGrab
import imageio_ffmpeg


def until(app, condition, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.update()
        if condition():
            return
        time.sleep(.03)
    raise AssertionError('UI condition timed out')


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source, target = root / 'Samsung-media-fixture', root / 'selected-export'
    target.mkdir()
    for album in ('DCIM/Camera', 'Pictures/Screenshots', 'Movies/Screen recordings'):
        (source / album).mkdir(parents=True, exist_ok=True)
    for number in range(15):
        image = Image.new('RGB', (800, 560), (25 + number * 9, 90 + number * 5, 125 + number * 4))
        draw = ImageDraw.Draw(image)
        draw.ellipse((200, 80, 600, 480), fill=(95 + number * 5, 200, 174))
        draw.text((30, 30), f'Camera sample {number + 1:02}', fill='white', font_size=30)
        image.save(source / f'DCIM/Camera/Moment-{number + 1:02}.jpg')
    Image.new('RGB', (400, 700), '#496080').save(source / 'Pictures/Screenshots/Screen.png')
    video = source / 'Movies/Screen recordings/Clip.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=teal:s=640x360:d=1', '-c:v', 'libx264', str(video)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    app = App(home=root / 'appdata')
    app.attributes('-topmost', True)
    app.lift()
    app.endpoints = [Folder(source), Folder(target)]
    app.show('Media library')
    gallery = app.gallery
    gallery.source_var.set(app.endpoints[0].label)
    gallery.load()
    until(app, lambda: not app.busy and len(gallery.items) == 17)
    until(app, lambda: sum(bool(getattr(child, 'image', None)) for card in gallery.tiles.winfo_children() for child in card.winfo_children()) >= 12)
    gallery.album = 'DCIM/Camera'
    gallery.select_album()
    assert len(gallery.chosen) == 15, 'Album selection must include every page'
    gallery.thumb_canvas.yview_moveto(1)
    app.update()
    assert gallery.thumb_canvas.yview()[1] == 1.0
    assert len(gallery.view_items) == 15
    gallery.clear_selection()
    gallery.search.set('Moment-01')
    assert len(gallery.filtered()) == 1
    gallery.search.set('')
    gallery.page_number = 0
    gallery.render()
    gallery.open_preview(next(i for i in gallery.items if i['kind'] == 'Photos'))
    until(app, lambda: gallery.preview_local is not None)
    gallery.close_preview()
    gallery.open_preview(next(i for i in gallery.items if i['kind'] == 'Videos'))
    until(app, lambda: gallery.preview_local is not None)
    gallery.play_preview()
    until(app, lambda: not getattr(gallery, 'playing', False))
    gallery.close_preview()
    gallery.chosen = {'DCIM/Camera/Moment-01.jpg', 'Pictures/Screenshots/Screen.png'}
    gallery.target_var.set(app.endpoints[1].label)
    gallery.send()
    until(app, lambda: not app.busy)
    assert app.last_result['copied'] == 2, app.last_result
    assert len(list(target.rglob('*.jpg'))) == 1
    assert {p.name for p in target.iterdir()}=={'Moment-01.jpg','Screen.png'}
    assert all(p.is_file() for p in target.iterdir()),'Media exports must not recreate phone folders'
    assert not (target / 'DCIM/Camera/Moment-02.jpg').exists()
    gallery.render()
    until(app, lambda: sum(bool(getattr(child, 'image', None)) for card in gallery.tiles.winfo_children() for child in card.winfo_children()) >= 12)
    original = list(gallery.items)
    gallery.album = 'DCIM/Camera'
    gallery.render()
    app.update()
    gallery.thumb_canvas.yview_moveto(.5)
    app.update()
    top = gallery.thumb_canvas.canvasy(0)
    gallery.loaded(list(original), scanning=True)
    app.update()
    assert gallery.album == 'DCIM/Camera'
    assert abs(gallery.thumb_canvas.canvasy(0) - top) < 2, 'Scan update changed scroll position'
    gallery.loaded(original)
    app.update()
    assert abs(gallery.thumb_canvas.canvasy(0) - top) < 2, 'Scan completion changed scroll position'
    enqueue = gallery.enqueue
    queued = []
    gallery.enqueue = lambda priority, task: queued.append(task[2]['path'])
    gallery.items = original + [dict(original[0], path=f'DCIM/Camera/extra-{i}.jpg', album='DCIM/Camera') for i in range(400)]
    gallery.render()
    app.update()
    gallery.thumb_canvas.yview_moveto(.9)
    app.update()
    queued.clear()
    gallery.thumb_canvas.yview_moveto(0)
    app.update()
    cached_names = set(gallery.photos)
    assert not (cached_names & set(queued)), 'Cached thumbnails were queued to reload'
    assert any(getattr(card[1], 'image', None) for name, card in gallery.cards.items() if name in cached_names)
    gallery.enqueue = enqueue
    gallery.loaded(original)
    gallery.render()
    app.update()
    print('Scan batches retain album/scroll position; revisiting cached thumbnails needs no reload')
    output = Path(__file__).resolve().parents[1] / 'replica/clone-screens'
    output.mkdir(exist_ok=True)
    app.update()
    time.sleep(.5)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(output / 'Media-library.png')
    for width, height in ((1160, 790), (900, 680)):
        app.geometry(f'{width}x{height}')
        app.update()
        assert gallery.destination.winfo_rooty() + gallery.destination.winfo_height() <= app.winfo_rooty() + app.winfo_height()
        assert gallery.thumb_canvas.winfo_height() > 50
        for card in gallery.tiles.winfo_children():
            thumb = card.winfo_children()[0]
            assert thumb.winfo_width() == thumb.winfo_height() == 132
            assert card.winfo_x() + card.winfo_width() <= gallery.thumb_canvas.winfo_width()
        print('Gallery scrolling/layout checked at', width, height)
    gallery.items = [dict(gallery.items[0], path=f'DCIM/Camera/Test-{i}.jpg') for i in range(30000)]
    gallery.source = None
    gallery.album = None
    gallery.render()
    app.update()
    gallery.thumb_canvas.yview_moveto(1)
    app.update()
    assert len(gallery.tiles.winfo_children()) < 100
    assert gallery.visible_range[1] == 30000
    print('30,000 item scrolling uses fewer than 100 live tiles')
    print('Continuous album scrolling and selection, search, photo/video preview and 2-file transfer: passed')
    app.destroy()
