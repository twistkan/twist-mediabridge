import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from unittest.mock import patch
from bridge.app import App
from bridge.engine import Folder, backup, digest
from PIL import ImageGrab


def wait(app):
    end=time.monotonic()+20
    while app.busy and time.monotonic()<end:
        app.update()
        time.sleep(.02)
    assert not app.busy
    app.update()


def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)


def button(widget,text):
    return next(child for child in children(widget) if child.winfo_class()=='Button' and child.cget('text')==text)


with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    source,target=root/'source',root/'restored'
    source.mkdir();target.mkdir()
    (source/'sample.txt').write_text('Manager restore fixture')
    app=App(home=root/'data')
    app.attributes('-topmost',True)
    app.endpoints=[Folder(target)]
    result=backup(Folder(source),root/'library',{'Documents'},app.cancel,lambda *a:None)
    record=app.remember_backup(result['folder'])
    vcf=root/'Contacts.vcf'
    vcf.write_text('BEGIN:VCARD\nVERSION:3.0\nFN:Fixture\nEND:VCARD\n')
    app.remember_backup(vcf)
    app.show('Backup manager')
    manager=app.backup_panel
    assert len(manager.tree.get_children())==2
    manager.tree.selection_set(record['id'])
    manager.verify();wait(app)
    assert app.catalog.rows()[0]['check'].startswith('Verified')
    with patch('bridge.backup_manager.os.startfile') as opened:
        manager.open_folder()
        opened.assert_called_once()
    manager.target.set(app.endpoints[0].label)
    with patch('bridge.backup_manager.messagebox.askyesno',return_value=True),patch('bridge.backup_manager.messagebox.showinfo'):
        manager.restore();wait(app)
    assert digest(target/'sample.txt')==digest(source/'sample.txt')
    manager.kind.set('Contacts');manager.render()
    assert len(manager.tree.get_children())==1
    manager.kind.set('All backups');manager.render()
    for geometry in ['900x680','1160x790']:
        app.geometry(geometry);app.update()
        assert manager.tree.winfo_height()>80
        footer=next(w for w in app.sidebar.winfo_children() if w.winfo_class()=='Label' and str(w.cget('text')).startswith('LOCAL FIRST'))
        assert footer.winfo_ismapped()
        last=app.nav['Connection help']
        assert last.winfo_y()+last.winfo_height()<=footer.winfo_y()
        for control in children(manager):
            if control.winfo_class()=='Button':
                assert control.winfo_rootx()+control.winfo_width()<=app.winfo_rootx()+app.winfo_width()
    screen=Path('replica/clone-screens')
    x,y=app.winfo_rootx(),app.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(screen/'Backup-manager.png')
    app.show('Contacts')
    panel=app.phone_panel
    panel.rows=[{'id':'a','name':'Alice Example','detail':'+256 700 123456'},
                {'id':'b','name':'Alice Example','detail':'00256 700123456'},
                {'id':'c','name':'Different Person','detail':'0700555666'}]
    panel.render()
    with patch('bridge.contacts_bridge.delete_contacts') as deleted:
        panel.find_duplicates();app.update()
        dialog=panel.duplicate_window
        for geometry in ['820x560','1000x650']:
            dialog.geometry(geometry);app.update()
            for control in children(dialog):
                if control.winfo_class()=='Button':
                    assert control.winfo_rooty()+control.winfo_height()<=dialog.winfo_rooty()+dialog.winfo_height()
        tree=next(child for child in children(dialog) if child.winfo_class()=='Treeview')
        assert len(tree.get_children())==2
        assert not panel.chosen
        tree.focus('a')
        button(dialog,'Keep highlighted only').invoke();app.update()
        x,y=dialog.winfo_rootx(),dialog.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+dialog.winfo_width(),y+dialog.winfo_height())).save(screen/'Duplicate-review.png')
        button(dialog,'Select marked contacts').invoke();app.update()
        assert panel.chosen=={'b'}
        assert len(panel.rows)==3
        deleted.assert_not_called()
        panel.find_duplicates();app.update()
        dialog=panel.duplicate_window
        panel.clear();app.update()
        assert not dialog.winfo_exists(),'Disconnect/reset must close private review dialog'
    assert not (app.home/'errors.log').exists()
    app.destroy()
    print('Manager: indexes, verifies, filters, opens folder and restores real fixture files at both window sizes')
    print('Duplicate review: keeps chosen contact, selects only reviewed extra, never deletes, and closes on reset')
