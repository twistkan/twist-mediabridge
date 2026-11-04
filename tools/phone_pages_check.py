import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from unittest.mock import patch
from bridge.app import App
from bridge.engine import Android
from PIL import ImageGrab


with tempfile.TemporaryDirectory() as temp:
    app = App(home=Path(temp) / 'data')
    app.attributes('-topmost', True)
    for page in ['Apps', 'Contacts']:
        app.show(page)
        panel = app.phone_panel
        panel.rows = [{'id': str(i), 'name': f'Sample {page} {i:03}', 'detail': f'com.example.app{i}' if page == 'Apps' else f'+256 700 {i:06}'} for i in range(200)]
        panel.render()
        panel.toggle('1')
        phone = Android('fixture-adb', 'fixture')
        app.endpoints = [phone]
        panel.phone_var.set(phone.label)
        if page == 'Apps':
            with patch('bridge.phone_pages.messagebox.askyesno', return_value=False), patch('bridge.delete_actions.uninstall_apps') as delete:
                panel.delete_selected()
                delete.assert_not_called()
        else:
            panel.rows[1].update(live=True, contact_id='1', lookup='fixture')
            with patch('bridge.phone_pages.messagebox.askyesno', return_value=False), patch('bridge.contacts_bridge.delete_contacts') as delete:
                panel.delete_selected()
                delete.assert_not_called()
        assert panel.chosen == {'1'}
        panel.select_all()
        assert len(panel.chosen) == 200
        panel.clear_selection()
        assert not panel.chosen
        panel.search.set(f'Sample {page} 019')
        assert len(panel.tree.get_children()) == 1, (page, len(panel.tree.get_children()), [panel.tree.item(i,'values') for i in panel.tree.get_children()][:5])
        panel.search.set('')
        panel.toggle('1')
        for size in ['1160x790', '900x680']:
            app.geometry(size)
            app.update()
            panel.tree.yview_moveto(1)
            app.update()
            assert panel.tree.yview()[1] == 1
            assert panel.winfo_height() > 400
            panel.tree.yview_moveto(0)
        app.geometry('1160x790')
        app.update()
        time.sleep(.2)
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(Path('replica/clone-screens') / f'{page}-redesigned.png')
    panel.rows = [{'id':f'live:{i}','contact_id':str(i),'lookup':f'fixture{i}','live':True,'name':f'Fixture {i}','detail':'123'} for i in range(23)]
    panel.select_all()
    panel.complete = lambda text: panel.summary.set(str(text))
    output = Path(temp) / 'all-selected.vcf'
    cards = lambda n: b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Fixture\r\nEND:VCARD\r\n' * n
    with patch('bridge.phone_pages.filedialog.asksaveasfilename',return_value=str(output)) as save_dialog, patch('bridge.contacts_bridge.adb_run',side_effect=[cards(10),cards(10),cards(3)]):
        panel.backup()
        assert save_dialog.call_args.kwargs['initialfile'].startswith('Contacts_')
        assert save_dialog.call_args.kwargs['initialfile'].endswith('.vcf')
        deadline = time.monotonic()+10
        while app.busy and time.monotonic()<deadline:
            app.update()
            time.sleep(.02)
    assert not app.busy
    from bridge.phone_backup import validate_vcard
    assert validate_vcard(output)==23
    assert 'Saved 23' in panel.summary.get()
    panel.contact_format.set('Individual .vcf files')
    individual_root=Path(temp)/'individual-backups'
    individual_root.mkdir()
    with patch('bridge.phone_pages.filedialog.askdirectory',return_value=str(individual_root)), patch('bridge.contacts_bridge.adb_run',side_effect=[cards(10),cards(10),cards(3)]):
        panel.backup()
        deadline=time.monotonic()+10
        while app.busy and time.monotonic()<deadline:
            app.update()
            time.sleep(.02)
    assert not app.busy
    exported=list(next(individual_root.iterdir()).glob('*.vcf'))
    assert len(exported)==23
    assert all(validate_vcard(file)==1 for file in exported)
    indexed=app.catalog.rows()
    assert len(indexed)==2
    assert {row['kind'] for row in indexed}=={'Contacts','Contact files'}
    assert all(row['count']==23 for row in indexed)
    print('Individual backup format exports 23 named files; combined Save dialog suggests dated filename')
    def children(widget):
        for child in widget.winfo_children():
            yield child
            yield from children(child)
    for button in children(panel):
        if button.winfo_class()=='Button' and button.cget('text') in ['Load contacts','Back up selected']:
            assert button.cget('foreground')==button.cget('disabledforeground')
    print('Select all > Back up selected finishes through the real UI event queue; primary button disabled text stays dark')
    app.destroy()
    print('Apps and Contacts: individual/all selection, search, 200 scrollable rows and two desktop sizes passed')

