"""Arbitrary PC files to shared phone storage; existing verified write paths."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .engine import Android, Cancelled, check_cancel, discover, safe_relative
from .companion_link import Companion, phone_online, retain_companions
from .theme import TOKENS as T


def send_files(paths, phone, cancel, report):
    if not isinstance(phone, Android):
        raise ValueError('Choose a connected Android phone.')
    if not phone_online(phone, cancel):
        raise OSError('Phone disconnected. Reconnect before sending files.')
    result = dict(status='complete', requested=len(paths), copied=0, present=0, failed=0, errors=[], items=[])
    for index, value in enumerate(paths):
        check_cancel(cancel)
        source = Path(value)
        destination = source.name if isinstance(phone, Companion) else 'Download/TwistMediaBridge/' + source.name
        report(index / max(1, len(paths)), f'Sending {index+1} of {len(paths)} · {source.name}')
        try:
            if source.is_symlink() or not source.is_file():
                raise ValueError('Choose a regular file, rather than a folder or shortcut link.')
            safe_relative(source.name)
            checksum, state = phone.write(source, destination, cancel)
            if state not in ('copied', 'already present'):
                raise OSError('Phone did not confirm completed transfer.')
            result['present' if state == 'already present' else 'copied'] += 1
            result['items'].append(dict(path=str(source), destination=destination, status=state, sha256=checksum))
        except Cancelled:
            raise
        except (OSError, ValueError) as error:
            result['failed'] += 1
            result['errors'].append(dict(path=str(source), error=str(error)))
            result['items'].append(dict(path=str(source), destination=destination, status='failed', error=str(error)))
    if result['failed']:
        result['status'] = 'partial'
    report(1, 'Files checked. See the transfer results below.')
    return result


class SendToPhone(tk.Frame):
    def __init__(self, app):
        super().__init__(app.content, bg=T['bg'])
        self.app = app
        app.heading('Drop it. Send it.', 'Send photos, videos, documents or any other file straight to your phone.')
        self.pack(fill='both', expand=True)
        self.phone_var = tk.StringVar()
        self.auto = tk.BooleanVar(value=app.settings.get('send_on_drop', True))
        self.summary = tk.StringVar(value='Connect a phone, then drop files here. Originals stay on your PC.')
        self.destination = tk.StringVar()
        card = app.card(self)
        app.label(card, 'SEND TO', bold=True, color=T['accent'], size=9).pack(anchor='w')
        row = tk.Frame(card, bg=T['surface']); row.pack(fill='x', pady=8)
        self.combo = ttk.Combobox(row, textvariable=self.phone_var, state='readonly')
        self.combo.pack(side='left', fill='x', expand=True)
        self.combo.bind('<<ComboboxSelected>>', lambda e: self.update_destination())
        find = app.button(row, 'Find phones', self.find); find.pack(side='left', padx=(8,0))
        app.active_controls.extend([(self.combo, 'readonly'), (find, 'normal')])
        tk.Label(card, textvariable=self.destination, bg=T['surface'], fg=T['muted'], anchor='w', wraplength=650, justify='left').pack(fill='x')
        zone = tk.Frame(self, bg=T['list_bg'], highlightthickness=2, highlightbackground=T['accent'], padx=24, pady=20)
        zone.pack(fill='x', pady=(0,12))
        app.label(zone, '↓  Drop files anywhere in this window', size=18, bold=True).pack(anchor='center')
        app.label(zone, 'Keep their names. Copy securely. Leave your originals untouched.', muted=True).pack(anchor='center', pady=6)
        browse = app.button(zone, 'Or choose files…', self.browse, primary=True); browse.pack(anchor='center')
        tick = ttk.Checkbutton(self, text='Send automatically when I drop or choose files', variable=self.auto, command=self.save_auto)
        tick.pack(anchor='w', pady=(0,8))
        app.active_controls.extend([(browse,'normal'),(tick,'normal')])
        self.listbox = tk.Listbox(self, bg=T['list_bg'], fg=T['text'], selectbackground=T['list_selected'],
                                  relief='flat', height=5, activestyle='none', font=(T['font'],10))
        self.listbox.pack(fill='x')
        row = tk.Frame(self, bg=T['bg']);row.pack(fill='x', pady=10)
        send = app.button(row, 'Send files →', self.send, primary=True);send.pack(side='right')
        clear = app.button(row, 'Clear list', self.clear);clear.pack(side='left')
        app.active_controls.extend([(send,'normal'),(clear,'normal')])
        tk.Label(self, textvariable=self.summary, bg=T['bg'], fg=T['success'], justify='left', anchor='w', wraplength=650).pack(fill='x', pady=6)
        app.label(self, 'Existing files with different contents are preserved. APK files are copied; use Apps → Reinstall file to install them.', muted=True, size=9).pack(fill='x')
        self.refresh()
        self.render()
        self.after(1000,self.watch)

    def phones(self):
        return [p for p in self.app.endpoints if isinstance(p,Android) and (not isinstance(p,Companion) or p.online())]

    def refresh(self):
        phones=self.phones();self.combo.configure(values=[p.label for p in phones])
        current=self.phone_var.get()
        if current not in [p.label for p in phones]:
            preferred=self.app.settings.get('send_phone_key')
            phone=next((p for p in phones if p.key==preferred),None)
            self.phone_var.set((phone.label if phone else phones[0].label if len(phones)==1 else ''))
        self.update_destination()

    def update_destination(self):
        phone=self.app.endpoint(self.phone_var)
        self.destination.set('Destination: the Receive folder chosen in Twist Companion on your phone.' if isinstance(phone,Companion)
                             else 'Destination: Download / TwistMediaBridge on the phone.' if phone else 'Choose your phone. If several are connected, select the one you want.')

    def watch(self):
        if not self.winfo_exists():return
        if not self.app.busy:self.refresh()
        self.after(1000,self.watch)

    def save_auto(self):
        self.app.settings['send_on_drop']=self.auto.get();self.app.persist()

    def find(self):
        def done(result):
            phones,blocked=result
            self.app.endpoints=retain_companions(self.app.endpoints,phones)
            self.refresh()
            self.summary.set('Choose your phone, then send the queued files.' if self.phones() else 'No ready phone. Connect via USB, Wi-Fi or Companion Wi-Fi and try again.')
        self.app.run('Find phones',lambda report:discover(self.app.adb),done,record=False)

    def browse(self):
        paths=filedialog.askopenfilenames(title='Send files to your phone')
        if paths:self.add(paths)

    def add(self, paths):
        skipped=0
        for value in paths:
            path=Path(value)
            if path.is_symlink() or not path.is_file():skipped+=1;continue
            if str(path) not in self.app.send_queue:self.app.send_queue.append(str(path))
        self.render()
        if skipped:self.summary.set(f'{skipped} folders or unavailable files skipped. Drop individual files.')
        if self.auto.get() and self.app.send_queue and self.app.endpoint(self.phone_var) and not self.app.busy:self.send()
        elif self.app.send_queue:self.summary.set(f'{len(self.app.send_queue)} files ready. Choose a phone, then click Send files.')

    def render(self):
        self.listbox.delete(0,'end')
        for path in self.app.send_queue:self.listbox.insert('end',Path(path).name)

    def clear(self):
        if self.app.busy:return
        self.app.send_queue.clear();self.render();self.summary.set('Drop files to start a new transfer.')

    def send(self):
        if self.app.busy:return
        phone=self.app.endpoint(self.phone_var)
        if not isinstance(phone,Android):self.summary.set('Choose a connected phone first. Your files are queued.');return
        if not self.app.send_queue:self.summary.set('Drop or choose files first.');return
        paths=list(self.app.send_queue)
        self.app.settings['send_phone_key']=phone.key;self.app.persist()
        def done(result):
            sent={i['path'] for i in result['items'] if i['status'] in ('copied','already present')}
            self.app.send_queue[:]=[p for p in self.app.send_queue if p not in sent]
            self.render()
            self.summary.set(f"{result['copied']} sent · {result['present']} already present · {result['failed']} failed. Originals remain on your PC.")
            if result['errors']:
                detail='\n'.join(Path(i['path']).name+': '+i['error'] for i in result['errors'][:5])
                messagebox.showwarning('Some files were not sent',detail+'\n\nFailed files stay in the list. Full results are in Activity.',parent=self.app)
        self.app.run('Send files to phone',lambda report:send_files(paths,phone,self.app.cancel,report),done)
