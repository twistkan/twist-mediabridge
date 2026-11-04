import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from bridge.app import App

with tempfile.TemporaryDirectory() as temp:
    app = App(home=temp)
    for width, height in ((1160, 790), (900, 680)):
        app.geometry(f'{width}x{height}')
        for page in app.nav:
            app.show(page)
            app.update()
            assert app.canvas.bbox('all')[3] >= app.content.winfo_reqheight()
            assert app.statusbox.winfo_rooty() + app.statusbox.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            def inspect(widget):
                for child in widget.winfo_children():
                    if child.winfo_class() == 'Button' and child.winfo_reqwidth() > child.winfo_width() + 2:
                        print('CLIPPED BUTTON', width, page, child.cget('text'), child.winfo_reqwidth(), child.winfo_width())
                    inspect(child)
            inspect(app.content)
            print(width, height, page, 'scrollable content', app.content.winfo_height(), 'viewport', app.canvas.winfo_height())
    app.destroy()
