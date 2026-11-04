import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from .engine import Android, discover, adb_run, Cancelled
from . import phone_backup as backend
from .theme import TOKENS as T


class PhonePage(tk.Frame):
    def __init__(self, app, apps=False):
        super().__init__(app.content, bg=T['bg'])
        self.app, self.apps = app, apps
        self.rows, self.chosen = [], set()
        self.events = queue.Queue()
        self.token = object()
        self.device = None
        self.stopped = threading.Event()
        self.pack(fill='both', expand=True)
        self.bind('<Destroy>', lambda e: self.stopped.set() if e.widget is self else None)
        app.label(self, 'Your apps.' if apps else 'Your contacts.', size=24, bold=True).pack(anchor='w', pady=(0,12))
        toolbar = tk.Frame(self, bg=T['surface'], padx=12, pady=12)
        toolbar.pack(fill='x')
        self.phone_var = tk.StringVar(value=next((e.label for e in app.endpoints if isinstance(e, Android)), ''))
        self.combo = ttk.Combobox(toolbar, textvariable=self.phone_var, values=[e.label for e in app.endpoints if isinstance(e, Android)], state='readonly')
        self.combo.pack(side='left', fill='x', expand=True, padx=(0,8))
        self.combo.bind('<<ComboboxSelected>>', lambda e: self.clear())
        app.active_controls.append((self.combo, 'readonly'))
        self.button(toolbar, 'Find phones', self.find).pack(side='left', padx=(0,8))
        self.button(toolbar, 'Load apps' if apps else 'Load contacts', self.load, True).pack(side='left')
        if not apps:
            self.button(toolbar, 'Enable contacts', self.enable_contacts).pack(side='left', padx=(8,0))
        note = ('Back up installation files. Private app data and logins are excluded.' if apps else
                'First click Enable contacts and approve access on the phone. Then Load contacts. Exported vCards are also supported.')
        app.label(self, note, muted=True, size=10).pack(fill='x', pady=12)
        search_row = tk.Frame(self, bg=T['bg'])
        search_row.pack(fill='x', pady=(0,12))
        app.label(search_row, 'Search', muted=True, size=10).pack(side='left', padx=(0,8))
        self.search = tk.StringVar()
        entry = tk.Entry(search_row, textvariable=self.search, bg=T['raised'], fg=T['text'], insertbackground=T['accent'], relief='flat')
        entry.pack(side='left', fill='x', expand=True, ipady=9, padx=(0,8))
        app.active_controls.append((entry,'normal'))
        self.search.trace_add('write', lambda *a: self.render())
        self.button(search_row, 'Select all', self.select_all).pack(side='left', padx=(0,8))
        self.button(search_row, 'Clear', self.clear_selection).pack(side='left')
        if not apps:
            self.button(search_row, 'Duplicates', self.find_duplicates).pack(side='left', padx=(8,0))
        footer = tk.Frame(self, bg=T['surface'], padx=12, pady=12)
        footer.pack(side='bottom', fill='x', pady=(12,0))
        self.contact_format = tk.StringVar(value='One .vcf file (all selected)')
        if not apps:
            formats = tk.Frame(footer, bg=T['surface'])
            formats.pack(fill='x', pady=(0,8))
            app.label(formats, 'Contact backup format', size=10, muted=True).pack(side='left', padx=(0,12))
            format_picker = ttk.Combobox(formats, textvariable=self.contact_format, state='readonly', values=['One .vcf file (all selected)', 'Individual .vcf files'], width=29)
            format_picker.pack(side='left', fill='x', expand=True)
            app.active_controls.append((format_picker, 'readonly'))
        self.summary = tk.StringVar(value='Nothing loaded yet')
        label = app.label(footer, '', bold=True, size=10)
        label.configure(textvariable=self.summary)
        label.pack(anchor='w', pady=(0,8))
        self.backup_folder = None
        self.open_backup_button = self.app.button(footer, 'Open backup folder', self.open_backup_folder)
        self.open_backup_button.pack(anchor='w', pady=(0,8))
        self.open_backup_button.configure(state='disabled')
        self.button(footer, 'Back up selected', self.backup, True).pack(side='left', padx=(0,8))
        self.button(footer, 'Delete selected', self.delete_selected).pack(side='left', padx=(0,8))
        self.button(footer, 'Reinstall file' if apps else 'Send vCard to phone', self.restore).pack(side='right')
        if apps:
            self.button(footer, 'Old folder…', self.restore_legacy).pack(side='right', padx=(0,8))
        area = tk.Frame(self, bg=T['surface'])
        area.pack(fill='both', expand=True)
        app.style.configure('Phone.Treeview', background=T['list_bg'], fieldbackground=T['list_bg'], foreground=T['text'], rowheight=44, borderwidth=0)
        app.style.configure('Phone.Treeview.Heading', background=T['raised'], foreground=T['text'], padding=8)
        self.tree = ttk.Treeview(area, columns=('tick','name','detail'), show='headings', selectmode='browse', style='Phone.Treeview')
        self.tree.heading('tick',text='Select')
        self.tree.heading('name',text='App name' if apps else 'Contact name')
        self.tree.heading('detail',text='Package' if apps else 'Phone number')
        self.tree.column('tick',width=60,minwidth=60,stretch=False)
        self.tree.column('name',width=220,minwidth=120)
        self.tree.column('detail',width=240,minwidth=100)
        self.tree.pack(side='left',fill='both',expand=True)
        scroll = ttk.Scrollbar(area,command=self.tree.yview)
        scroll.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure('chosen',foreground=T['success'])
        self.tree.tag_configure('even',background=T['list_bg'])
        self.tree.tag_configure('odd',background=T['list_alt'])
        app.style.map('Phone.Treeview', background=[('selected',T['list_selected'])], foreground=[('selected',T['text'])])
        self.tree.bind('<Button-1>',self.clicked)
        self.tree.bind('<space>',lambda e: self.toggle(self.tree.focus()))
        self.after(100,self.poll)
        threading.Thread(target=self.watch,daemon=True).start()

    def button(self, parent, label, action, primary=False):
        button = self.app.button(parent,label,action,primary)
        self.app.active_controls.append((button,'normal'))
        return button

    def phone(self):
        return next((e for e in self.app.endpoints if isinstance(e,Android) and e.label==self.phone_var.get()),None)

    def clear(self):
        if getattr(self,'duplicate_window',None) and self.duplicate_window.winfo_exists():
            self.duplicate_window.destroy()
        self.token=object()
        self.device=None
        self.rows=[]
        self.chosen.clear()
        self.render()

    def find(self):
        self.clear()
        def done(result):
            phones,_=result
            from .companion_link import retain_companions
            self.app.endpoints=retain_companions(self.app.endpoints,phones)
            phones=[e for e in self.app.endpoints if isinstance(e,Android)]
            self.combo.configure(values=[p.label for p in phones])
            self.phone_var.set(phones[0].label if phones else '')
            self.summary.set('Phone ready. Click Load.' if phones else 'No authorized phone found.')
        self.app.run('Find phones',lambda report: discover(self.app.adb),done,record=False)

    def load(self):
        if self.app.busy:return
        phone=self.phone()
        self.clear()
        if not phone:
            self.summary.set('Connect a phone and click Find phones first.')
            return
        self.device=phone
        token=self.token
        self.summary.set('Loading app names…' if self.apps else 'Reading exported contacts…')
        def read(report):
            from .companion_link import phone_online
            if not phone_online(phone,self.app.cancel,runner=adb_run):
                raise OSError('Phone disconnected')
            if self.apps:
                return backend.list_app_details(phone,self.app.cancel,report,self.app.home/'app-labels.json',lambda rows:self.events.put(('rows',token,rows)))
            return backend.load_contact_details(phone,self.app.cancel,report)
        def done(rows):
            if token is self.token:
                self.rows=rows
                self.render()
                if not rows:self.summary.set('No apps found.' if self.apps else 'No contacts found. Check Contacts access in Twist Contacts Bridge on your phone.')
        self.app.run('Read installed apps' if self.apps else 'Load contacts',read,done,record=False)

    def render(self):
        if not hasattr(self,'tree'):return
        fraction=self.tree.yview()[0] if self.tree.get_children() else 0
        self.tree.delete(*self.tree.get_children())
        query=self.search.get().casefold()
        for index, row in enumerate(self.rows):
            if query and query not in (row['name']+' '+row['detail']).casefold():continue
            chosen=row['id'] in self.chosen
            self.tree.insert('', 'end',iid=row['id'],values=('✓' if chosen else '○',row['name'],row['detail']),tags=(('even' if index % 2 == 0 else 'odd'),) + (('chosen',) if chosen else ()))
        self.tree.yview_moveto(fraction)
        self.summary.set(f'{len(self.rows):,} '+('apps' if self.apps else 'contacts')+f' · {len(self.chosen):,} selected')

    def clicked(self,event):
        if not self.app.busy:self.toggle(self.tree.identify_row(event.y))

    def toggle(self,key):
        if not key or self.app.busy:return
        if key in self.chosen:self.chosen.remove(key)
        else:self.chosen.add(key)
        self.render()
        self.tree.focus(key)

    def select_all(self):
        self.chosen.update(row['id'] for row in self.rows)
        self.render()

    def clear_selection(self):
        self.chosen.clear()
        self.render()

    def complete(self,text):
        self.summary.set(str(text))
        messagebox.showinfo('Twist MediaBridge',str(text),parent=self.app)

    def open_backup_folder(self):
        if self.backup_folder is None:return
        try:
            if not self.backup_folder.is_dir():
                raise FileNotFoundError('The backup folder is unavailable. Reconnect its drive and try again.')
            os.startfile(str(self.backup_folder))
        except OSError as exc:
            messagebox.showerror('Cannot open backup folder',str(exc),parent=self.app)

    def backup(self):
        phone=self.phone()
        rows=[row for row in self.rows if row['id'] in self.chosen]
        if not phone or not rows:
            self.summary.set('Select at least one item first.')
            return
        individual = not self.apps and self.contact_format.get() == 'Individual .vcf files'
        if self.apps:
            destination=filedialog.askdirectory(title='Save app backups')
        elif individual:
            destination=filedialog.askdirectory(title='Choose where to save individual contact files')
        else:
            destination=filedialog.asksaveasfilename(title='Save selected contacts',initialfile=backend.contact_backup_name()+'.vcf',defaultextension='.vcf',filetypes=[('vCard','*.vcf')])
        if not destination:return
        saved_paths = []
        def remember(path):
            self.app.remember_backup(path)
            saved_paths.append(Path(path).resolve())
        def finished(text):
            if not saved_paths:
                self.complete(text); return
            last = saved_paths[-1]
            self.backup_folder = last if last.is_dir() else last.parent
            self.open_backup_button.configure(state='normal')
            summary = str(text)
            if self.apps or not individual:summary += '\n' + str(self.backup_folder)
            self.summary.set(summary)
            if messagebox.askyesno('Backup saved',summary+'\n\nOpen the backup folder now?',parent=self.app):
                self.open_backup_folder()
        def work(report):
            if not self.apps:
                save = backend.save_individual_contacts if individual else backend.save_selected_contacts
                return save(rows,destination,self.app.cancel,phone,report,on_saved=remember)
            saved,failed=[],[]
            for index,row in enumerate(rows):
                try:
                    path=backend.backup_app_file(phone,row['id'],row['name'],destination,self.app.cancel,lambda progress, text: report((index+progress)/len(rows), text))
                    remember(path)
                    saved.append(row['name'])
                except Cancelled:raise
                except (OSError,ValueError) as exc:failed.append(row['name']+': '+str(exc))
                report((index+1)/len(rows),'Backing up selected apps…')
            return f'{len(saved)} app backups saved; {len(failed)} failed.'+('\n'+'\n'.join(failed) if failed else '')
        self.app.run('Back up selected',work,finished,record=False)

    def find_duplicates(self):
        from .duplicate_review import show_review
        show_review(self)

    def enable_contacts(self):
        phone = self.phone()
        if not phone:
            self.summary.set('Connect a phone and click Find phones first.')
            return
        from .contacts_bridge import enable_contacts
        from .companion_link import Companion
        if isinstance(phone,Companion):
            messagebox.showinfo('Contacts access', 'On the phone open Twist Companion and tap Allow contacts access, then Load contacts here.',parent=self.app)
            return
        if messagebox.askyesno('Enable phone contacts?', 'Install or update Twist Companion on this phone?\n\nIt requests Contacts access for loading, exporting and deleting selected contacts. Network permission supports the optional encrypted local Wi-Fi connection.', parent=self.app):
            self.app.run('Enable phone contacts', lambda report: enable_contacts(phone, self.app.cancel, report), self.complete, record=False)

    def delete_selected(self):
        if self.app.busy:
            return
        phone = self.phone()
        rows = [row for row in self.rows if row['id'] in self.chosen]
        if not phone or not rows:
            self.summary.set('Select items on a connected phone first.')
            return
        if not self.apps and any(not row.get('live') for row in rows):
            messagebox.showinfo('Load live contacts', 'These records came from an exported vCard. Enable phone contacts and Load contacts to select actual phone contacts for deletion.', parent=self.app)
            return
        details = '\n'.join(row['name'] for row in rows[:8]) + ('\n…' if len(rows) > 8 else '')
        warning = 'Uninstalling apps also removes their private data on the phone.' if self.apps else 'This deletes the selected phone contacts. Synced contacts may also be removed from the linked account.'
        if not messagebox.askyesno('Delete selected apps?' if self.apps else 'Delete selected contacts?', f'Delete {len(rows)} selected items from this phone?\n\n{details}\n\n{warning}', parent=self.app):
            return
        def work(report):
            if self.apps:
                from .delete_actions import uninstall_apps
                return uninstall_apps(phone, [row['id'] for row in rows], self.app.cancel, report)
            from .contacts_bridge import delete_contacts
            return delete_contacts(phone, rows, self.app.cancel, report)
        def done(results):
            removed = {key for key, success, _ in results if success}
            self.rows = [row for row in self.rows if row['id'] not in removed]
            self.chosen.difference_update(removed)
            self.render()
            self.summary.set(f'{len(removed)} deleted · {len(results)-len(removed)} failed')
            if len(removed) != len(results):
                messagebox.showwarning('Some items were not deleted', '\n'.join(f'{key}: {detail}' for key, success, detail in results if not success), parent=self.app)
        self.app.run('Delete selected apps' if self.apps else 'Delete selected contacts', work, done, record=False)

    def restore(self):
        phone=self.phone()
        if not phone:return
        source=filedialog.askopenfilename(title='Select app backup file',filetypes=[('App backup files','*.apk *.apks')]) if self.apps else filedialog.askopenfilename(title='Select vCard',filetypes=[('vCard','*.vcf')])
        if source:self.app.run('Restore app' if self.apps else 'Send vCard',lambda report:backend.restore_app_file(phone,source,self.app.cancel,report) if self.apps else backend.restore_vcard(phone,source,self.app.cancel),self.complete,record=False)

    def restore_legacy(self):
        phone=self.phone()
        if not phone:return
        source=filedialog.askdirectory(title='Select older app backup folder containing app.json')
        if source:self.app.run('Restore older app backup',lambda report:backend.restore_app(phone,source,self.app.cancel,report),self.complete,record=False)

    def watch(self):
        while not self.stopped.wait(1):
            phone=self.device
            if not phone:continue
            from .companion_link import phone_online
            try:online=phone_online(phone,self.stopped,runner=adb_run)
            except (OSError,Cancelled):online=False
            if not online:self.events.put(('offline',phone,None))

    def poll(self):
        if self.stopped.is_set():return
        try:
            while True:
                kind,token,rows=self.events.get_nowait()
                if kind=='rows' and token is self.token:
                    self.rows=rows
                    self.render()
                elif kind=='offline' and token is self.device:
                    if self.app.busy:self.app.cancel.set()
                    self.clear()
                    self.phone_var.set('')
                    self.summary.set('Phone disconnected. List cleared.')
        except queue.Empty:pass
        self.after(100,self.poll)


def phone_page(app, apps=False):
    app.phone_panel=PhonePage(app,apps)
