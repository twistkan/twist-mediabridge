import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .engine import Android, Folder, discover
from .backup_catalog import restore_backup
from .theme import TOKENS as T


class BackupManager(tk.Frame):
    def __init__(self,app):
        super().__init__(app.content,bg=T['bg'])
        self.app=app
        self.pack(fill='both',expand=True)
        app.label(self,'Your backup library.',size=24,bold=True).pack(anchor='w',pady=(0,T['space_sm']))
        app.label(self,'New backups appear here automatically. Add older backups from their file or folder.',muted=True,size=10).pack(fill='x',pady=(0,T['space_md']))
        toolbar=tk.Frame(self,bg=T['surface'],padx=T['space_sm'],pady=T['space_sm'])
        toolbar.pack(fill='x')
        for label,fn in [('Refresh library',self.refresh),('Add backup file',self.add_file),('Scan backup folder',self.scan_folder)]:
            self.control(toolbar,label,fn).pack(side='left',padx=(0,T['space_sm']))
        filters=tk.Frame(self,bg=T['bg'])
        filters.pack(fill='x',pady=T['space_sm'])
        app.label(filters,'Search',muted=True,size=10).pack(side='left',padx=(0,T['space_sm']))
        self.search=tk.StringVar()
        entry=tk.Entry(filters,textvariable=self.search,bg=T['raised'],fg=T['text'],insertbackground=T['accent'],relief='flat')
        entry.pack(side='left',fill='x',expand=True,ipady=T['space_sm'])
        app.active_controls.append((entry,'normal'))
        self.kind=tk.StringVar(value='All backups')
        kinds=ttk.Combobox(filters,textvariable=self.kind,values=['All backups','Contacts','Apps','Files'],state='readonly',width=14)
        kinds.pack(side='left',padx=(T['space_sm'],0))
        app.active_controls.append((kinds,'readonly'))
        kinds.bind('<<ComboboxSelected>>',lambda e:self.render())
        self.search.trace_add('write',lambda *a:self.render())
        footer=tk.Frame(self,bg=T['surface'],padx=T['space_sm'],pady=T['space_sm'])
        footer.pack(side='bottom',fill='x',pady=(T['space_sm'],0))
        self.summary=tk.StringVar(value='No backups yet. Create a backup or add an older one.')
        label=app.label(footer,'',muted=True,size=9)
        label.configure(textvariable=self.summary)
        label.pack(fill='x',pady=(0,T['space_sm']))
        targetrow=tk.Frame(footer,bg=T['surface'])
        targetrow.pack(fill='x',pady=(0,T['space_sm']))
        app.label(targetrow,'Restore to',size=10).pack(side='left',padx=(0,T['space_sm']))
        self.target=tk.StringVar(value=next((e.label for e in app.endpoints if isinstance(e,Android)),app.endpoints[0].label if app.endpoints else ''))
        self.targets=ttk.Combobox(targetrow,textvariable=self.target,values=[e.label for e in app.endpoints],state='readonly')
        self.targets.pack(side='left',fill='x',expand=True)
        app.active_controls.append((self.targets,'readonly'))
        self.control(targetrow,'Find phones',self.find_phones).pack(side='left',padx=T['space_sm'])
        self.control(targetrow,'PC folder',self.pc_folder).pack(side='left')
        actions=tk.Frame(footer,bg=T['surface'])
        actions.pack(fill='x')
        for label,fn in [('Open folder',self.open_folder),('Verify',self.verify),('Remove from list',self.forget)]:
            self.control(actions,label,fn).pack(side='left',padx=(0,T['space_sm']))
        self.control(actions,'Restore selected',self.restore,True).pack(side='right')
        area=tk.Frame(self,bg=T['list_bg'])
        area.pack(fill='both',expand=True)
        app.style.configure('Backup.Treeview',background=T['list_bg'],fieldbackground=T['list_bg'],foreground=T['text'],rowheight=38)
        app.style.configure('Backup.Treeview.Heading',background=T['raised'],foreground=T['text'],padding=T['space_sm'])
        app.style.map('Backup.Treeview',background=[('selected',T['list_selected'])],foreground=[('selected',T['text'])])
        self.tree=ttk.Treeview(area,columns=('name','kind','date','count','check'),show='headings',selectmode='browse',style='Backup.Treeview')
        for col,title,width in [('name','Backup',235),('kind','Type',110),('date','Saved',140),('count','Items',60),('check','Last check',170)]:
            self.tree.heading(col,text=title)
            self.tree.column(col,width=width,minwidth=60)
        self.tree.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(area,command=self.tree.yview)
        bar.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind('<<TreeviewSelect>>',self.selected)
        self.records={}
        self.render()

    def control(self,parent,label,fn,primary=False):
        button=self.app.button(parent,label,fn,primary)
        self.app.active_controls.append((button,'normal'))
        return button

    def render(self):
        if not hasattr(self,'tree'):return
        selection=self.tree.selection()
        key=selection[0] if selection else None
        self.tree.delete(*self.tree.get_children())
        rows=self.app.catalog.rows()
        self.records={row['id']:row for row in rows}
        for row in rows:
            if self.search.get().casefold() not in (row['name']+' '+row['path']).casefold():continue
            kind=self.kind.get()
            if kind=='Contacts' and not row['kind'].startswith('Contact'):continue
            if kind=='Apps' and not row['kind'].startswith('App'):continue
            if kind=='Files' and row['kind']!='Files':continue
            state=row['check'] if Path(row['path']).exists() else 'Missing location'
            if state.startswith('Verified '):state='Verified '+state.split()[1]
            self.tree.insert('','end',iid=row['id'],values=(row['name'],row['kind'],row['date'],row['count'],state))
        children=self.tree.get_children()
        if children:self.tree.selection_set(key if key in children else children[0])
        self.summary.set(f'{len(rows)} backups indexed. Verify checks for changes since a backup was added.' if rows else 'No backups yet. Create a backup, Refresh library, or add older backup files/folders.')

    def item(self):
        selected=self.tree.selection()
        if not selected:
            self.summary.set('Select a backup first.')
            return None
        return self.records[selected[0]]

    def selected(self,event=None):
        row=self.item()
        if row:self.summary.set(f"{row['size']/1024/1024:.1f} MB · {row['path']}")

    def finished(self,text):
        self.render()
        self.summary.set(str(text))

    def refresh(self):
        self.app.run('Refresh backup library',lambda report:self.app.catalog.scan(self.app.library,self.app.cancel,report),self.finished,record=False)

    def add_file(self):
        path=filedialog.askopenfilename(title='Add an existing backup',filetypes=[('Backups','*.vcf *.apk *.apks')])
        if path:self.app.run('Add backup',lambda report:self.app.catalog.add(path),lambda row:self.finished('Backup added. Its current checksums form the verification baseline.'),record=False)

    def scan_folder(self):
        path=filedialog.askdirectory(title='Choose a backup or a folder containing backups')
        if path:self.app.run('Find saved backups',lambda report:self.app.catalog.scan(path,self.app.cancel,report),self.finished,record=False)

    def open_folder(self):
        row=self.item()
        if not row:return
        path=Path(row['path'])
        folder=path if path.is_dir() else path.parent
        if not path.exists():
            self.summary.set('Backup location is missing. Reconnect its drive.')
            return
        try:os.startfile(folder)
        except OSError as exc:messagebox.showerror('Cannot open folder',str(exc),parent=self)

    def verify(self):
        row=self.item()
        if row:self.app.run('Verify saved backup',lambda report:self.app.catalog.verify(row,self.app.cancel,report),self.finished,record=False)

    def forget(self):
        row=self.item()
        if row and messagebox.askyesno('Remove from manager?', 'Remove this entry from the list? The backup files will stay on disk.',parent=self):
            self.app.catalog.forget(row['id'])
            self.finished('Entry removed. Backup files were kept.')

    def find_phones(self):
        def done(result):
            phones,_=result
            from .companion_link import retain_companions
            self.app.endpoints=retain_companions(self.app.endpoints,phones)
            from .engine import Android
            phones=[e for e in self.app.endpoints if isinstance(e,Android)]
            self.targets.configure(values=[e.label for e in self.app.endpoints])
            self.target.set(phones[0].label if phones else '')
            self.summary.set('Choose the restore destination.' if phones else 'No authorized Android phone found.')
        self.app.run('Find restore phones',lambda report:discover(self.app.adb),done,record=False)

    def pc_folder(self):
        path=filedialog.askdirectory(title='Choose restore destination for file backups')
        if path:
            endpoint=Folder(path)
            if not any(e.key==endpoint.key for e in self.app.endpoints):self.app.endpoints.append(endpoint)
            self.targets.configure(values=[e.label for e in self.app.endpoints])
            self.target.set(endpoint.label)

    def restore(self):
        row=self.item()
        if not row:return
        target=next((e for e in self.app.endpoints if e.label==self.target.get()),None)
        if not target or (row['kind']!='Files' and not isinstance(target,Android)):
            self.summary.set('Choose an authorized Android phone, or a PC folder for file backups.')
            return
        action='Install the saved app (Android may update an existing installation).' if row['kind'].startswith('App') else 'Copy contacts to the phone; finish importing them in its Contacts app.' if row['kind'].startswith('Contact') else 'Restore saved files. Existing different files are kept as conflicts.'
        if messagebox.askyesno('Restore this backup?',f"{row['name']}\n\nDestination: {target.label}\n\n{action}\n\nChecksums are verified before writing anything.",parent=self):
            def done(text):
                self.app.catalog.mark_verified(row['id'])
                self.finished(text)
                messagebox.showinfo('Restore finished',str(text),parent=self)
            self.app.run('Restore saved backup',lambda report:restore_backup(row,target,self.app.cancel,report),done,record=False)
