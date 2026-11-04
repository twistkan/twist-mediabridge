"""Exercise real Tk pages and the threaded backup/restore UI with disposable data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from bridge.app import App
from bridge.engine import Folder, digest


def wait(app):
    end = time.monotonic() + 20
    while app.busy and time.monotonic() < end:
        app.update()
        time.sleep(.02)
    assert not app.busy, 'UI task timed out'
    app.update()


with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    source, target = root / 'source', root / 'target'
    source.mkdir()
    target.mkdir()
    (source / 'test.txt').write_text('A real UI round trip.')
    app = App(home=root / 'appdata')
    app.attributes('-topmost', True)
    app.lift()
    app.endpoints = [Folder(source), Folder(target)]
    for page in app.nav:
        app.show(page)
        app.update()
        print('Opened', page)
    app.show('Create backup')
    app.source_var.set(app.endpoints[0].label)
    app.start_backup()
    wait(app)
    assert app.last_result['status'] == 'complete', app.last_result
    app.show('Restore backup')
    app.target_var.set(app.endpoints[1].label)
    app.start_restore()
    wait(app)
    assert app.last_result['status'] == 'complete', app.last_result
    assert digest(source / 'test.txt') == digest(target / 'test.txt')
    print('UI backup -> restore round trip passed')
    app.show('Overview')
    app.update()
    try:
        from PIL import ImageGrab
        folder = Path(__file__).resolve().parents[1] / 'replica/clone-screens'
        folder.mkdir(exist_ok=True)
        for page in ('Overview', 'Phone transfer', 'Create backup', 'Restore backup', 'Connection help'):
            app.show(page)
            app.update()
            time.sleep(.2)
            x, y = app.winfo_rootx(), app.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(folder / (page.replace(' ', '-') + '.png'))
        print('UI screenshots saved')
    except ImportError:
        print('Pillow unavailable: screenshots not captured')
    app.destroy()
