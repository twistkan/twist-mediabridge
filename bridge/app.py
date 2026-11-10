from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone

from .engine import Folder, CATEGORIES, backup, transfer, discover, load_manifest, atomic_json, Cancelled
from .theme import TOKENS as T


def app_home():
    if getattr(sys, 'frozen', False):
        import shutil
        home = Path(os.environ['LOCALAPPDATA']) / 'TwistMediaBridge'
        home.mkdir(parents=True, exist_ok=True)
        settings = home / 'settings.json'
        if not settings.exists():
            candidates = [Path(sys.executable).parent / 'DeviceBridge-data/settings.json',
                          Path(sys.executable).parent.parent / 'DeviceBridge-data/settings.json']
            for old in candidates:
                if old.is_file():
                    shutil.copy2(old, settings)
                    break
        return home
    return Path(__file__).resolve().parents[1] / 'data'


class App(tk.Tk):
    def __init__(self, home=None):
        super().__init__()
        self.home = Path(home) if home else app_home()
        self.home.mkdir(parents=True, exist_ok=True)
        from .backup_catalog import BackupCatalog
        self.catalog = BackupCatalog(self.home)
        self.config_file = self.home / 'settings.json'
        try:
            self.settings = json.loads(self.config_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        self.library = Path(self.settings.get('library', str(self.home / 'Backups')))
        self.endpoints = []
        self.send_queue = []
        self.pending_drops = []
        for folder in self.settings.get('folders', []):
            try:
                self.endpoints.append(Folder(folder))
            except ValueError:
                pass
        from .android_tools import resolve_adb
        from .desktop import resource_path
        self.adb_mode = self.settings.get('adb_mode', 'automatic')
        self.adb = resolve_adb(self.settings)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.page = 'Overview'
        self.last_result = None
        self.active_controls = []
        self.title('Twist MediaBridge · Media, transfer & backup')
        self.geometry(f"{T['width']}x{T['height']}")
        self.minsize(900, 680)
        self.configure(bg=T['bg'])
        self.option_add('*Font', (T['font'], T['body']))
        self.option_add('*Dialog.msg.font', (T['font'], T['body']))
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('.', background=T['bg'], foreground=T['text'], font=(T['font'], T['body']))
        self.style.configure('TCombobox', fieldbackground=T['raised'], background=T['raised'], foreground=T['text'], arrowcolor=T['text'], padding=T['space_sm'])
        self.style.map('TCombobox', fieldbackground=[('readonly', T['raised'])], selectbackground=[('readonly', T['raised'])], selectforeground=[('readonly', T['text'])])
        self.style.configure('Horizontal.TProgressbar', troughcolor=T['raised'], background=T['accent'], borderwidth=0)
        self.style.configure('TCheckbutton', background=T['surface'], foreground=T['text'], padding=T['space_sm'])
        from .widgets import install_ticks
        install_ticks(self)
        icon = resource_path('assets/twist-mediabridge.ico')
        if icon.is_file():
            self.iconbitmap(str(icon))
        self.style.map('TCheckbutton', background=[('active', T['raised'])], foreground=[('disabled', T['muted'])])
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = tk.Frame(self, bg=T['surface'], width=T['sidebar'])
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.sidebar.grid_propagate(False)
        from PIL import Image, ImageTk
        mark = resource_path('assets/twist-mediabridge.png')
        if mark.is_file():
            self.brand_icon = ImageTk.PhotoImage(Image.open(mark).resize((56, 56)))
            tk.Label(self.sidebar, image=self.brand_icon, bg=T['surface']).pack(anchor='w', padx=T['space_lg'], pady=(T['space_lg'], T['space_sm']))
        self.label(self.sidebar, 'Twist MediaBridge', size=15, bold=True).pack(anchor='w', padx=T['space_lg'])
        self.label(self.sidebar, 'YOUR DATA. YOUR DEVICES.', size=8, muted=True).pack(anchor='w', padx=T['space_lg'], pady=(T['space_sm'], T['space_md']))
        self.nav = {}
        for title in ('Media library', 'Send to phone', 'Overview', 'Phone transfer', 'Create backup', 'Restore backup', 'Contacts', 'Apps', 'Backup manager', 'Activity', 'Connection help'):
            btn = self.button(self.sidebar, title, lambda p=title: self.show(p))
            btn.configure(pady=3)
            btn.pack(fill='x', padx=T['space_md'], pady=2)
            self.nav[title] = btn
        self.button(self.sidebar,'Companion Wi-Fi',self.open_companion).pack(fill='x',padx=T['space_md'],pady=3)
        self.label(self.sidebar, 'Powered by Tweest\nLOCAL FIRST · v1.16', muted=True, size=9).pack(side='bottom', anchor='w', padx=T['space_lg'], pady=T['space_lg'])
        self.right = tk.Frame(self, bg=T['bg'])
        self.right.grid(row=0, column=1, sticky='nsew', padx=T['space_xl'], pady=T['space_lg'])
        self.right.grid_rowconfigure(0, weight=1)
        self.right.grid_columnconfigure(0, weight=1)
        viewport = tk.Frame(self.right, bg=T['bg'])
        viewport.grid(row=0, column=0, sticky='nsew')
        viewport.grid_columnconfigure(0, weight=1)
        viewport.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, bg=T['bg'], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(viewport, orient='vertical', command=self.canvas.yview)
        self.main_scrollbar = scrollbar
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.content = tk.Frame(self.canvas, bg=T['bg'])
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self.resize_content)
        self.bind_all('<MouseWheel>', self.scroll_content)
        self.bind_all('<FocusIn>', self.reveal_focus)
        self.statusbox = tk.Frame(self.right, bg=T['surface'], padx=T['space_md'], pady=T['space_md'])
        self.statusbox.grid(row=1, column=0, sticky='ew', pady=(T['space_md'], 0))
        self.status = tk.StringVar(value='Ready · Choose a task to get started.')
        self.label(self.statusbox, 'SESSION STATUS', size=8, color=T['accent'], bold=True).pack(anchor='w')
        self.status_label = self.label(self.statusbox, '', muted=True)
        self.status_label.configure(textvariable=self.status, wraplength=730)
        self.status_label.pack(anchor='w', pady=T['space_sm'])
        self.progress = ttk.Progressbar(self.statusbox, maximum=1)
        self.progress.pack(fill='x')
        self.cancel_btn = self.button(self.statusbox, 'Cancel after current step', self.cancel_job)
        self.cancel_btn.pack(anchor='e', pady=(T['space_sm'], 0))
        self.cancel_btn.configure(state='disabled')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.show('Media library')
        from .file_drop import FileDrop
        try:
            self.file_drop = FileDrop(self, lambda paths:self.events.put(('drop_files',paths)))
        except OSError:
            self.file_drop = None  # File picker remains usable on managed desktops.
        self.after(100, self.poll)
        if getattr(sys, 'frozen', False) and home is None:
            from .desktop import ensure_shortcut
            threading.Thread(target=ensure_shortcut, args=(self.home,), daemon=True).start()

    def label(self, parent, text, size=None, muted=False, color=None, bold=False):
        label = tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color or (T['muted'] if muted else T['text']), font=(T['font'], size or T['body'], 'bold' if bold else 'normal'), justify='left', anchor='w')
        parent.bind('<Configure>', lambda event: label.configure(wraplength=max(100, event.width - T['space_lg'] * 2)) if event.widget == parent and label.winfo_exists() else None, add='+')
        return label

    def scroll_content(self, event):
        if event.widget.winfo_class() in ('Listbox', 'Text', 'TCombobox'):
            return
        if self.page == 'Media library' and hasattr(self, 'gallery'):
            self.gallery.scroll_media(event)
            return
        x, y = self.winfo_pointerxy()
        if self.canvas.winfo_rootx() <= x <= self.canvas.winfo_rootx() + self.canvas.winfo_width() and self.canvas.winfo_rooty() <= y <= self.canvas.winfo_rooty() + self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')

    def resize_content(self, event=None):
        self.canvas.itemconfigure(self.content_window, width=self.canvas.winfo_width(), height=self.canvas.winfo_height() if self.page in ('Media library', 'Apps', 'Contacts', 'Backup manager') else 0)

    def reveal_focus(self, event):
        widget = event.widget
        if not isinstance(widget,tk.Misc):
            return  # Native combobox popups can report a Tcl pathname, not a widget.
        if self.page == 'Media library' and hasattr(self, 'gallery'):
            self.gallery.reveal_focus(widget)
            return
        if str(widget).startswith(str(self.content) + '.'):
            top = widget.winfo_rooty() - self.content.winfo_rooty()
            visible_top = self.canvas.canvasy(0)
            height = self.canvas.winfo_height()
            if top < visible_top or top + widget.winfo_height() > visible_top + height:
                self.canvas.yview_moveto(max(0, top - height / 2) / max(1, self.content.winfo_height()))

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=T['accent'] if primary else T['raised'], fg=T['on_accent'] if primary else T['text'], activebackground=T['muted'], activeforeground=T['bg'], relief='flat', borderwidth=0, padx=T['space_md'], pady=T['space_sm'], cursor='hand2', anchor='w', highlightthickness=1, highlightbackground=T['border'], highlightcolor=T['accent'], disabledforeground=T['on_accent'] if primary else T['muted'])

    def heading(self, title, subtitle):
        self.label(self.content, 'TWIST MEDIABRIDGE  /  ' + self.page.upper(), size=8, color=T['accent'], bold=True).pack(anchor='w', pady=(0, T['space_md']))
        self.label(self.content, title, size=T['heading'], bold=True).pack(anchor='w')
        self.label(self.content, subtitle, muted=True).pack(anchor='w', pady=(T['space_sm'], T['space_lg']))

    def card(self, parent=None):
        frame = tk.Frame(parent or self.content, bg=T['surface'], padx=T['space_lg'], pady=T['space_md'])
        frame.pack(fill='x', pady=(0, T['space_md']))
        return frame

    def show(self, page):
        if self.busy:
            return
        self.page = page
        if page in ('Media library', 'Apps', 'Contacts', 'Backup manager'):
            self.statusbox.grid_remove()
            self.main_scrollbar.grid_remove()
        else:
            self.statusbox.grid()
            self.main_scrollbar.grid()
        self.active_controls = []
        for child in self.content.winfo_children():
            child.destroy()
        for title, btn in self.nav.items():
            btn.configure(bg=T['raised'] if title == page else T['surface'], fg=T['accent'] if title == page else T['text'])
        {'Media library': self.media_page, 'Send to phone': self.send_page, 'Overview': self.overview, 'Phone transfer': self.transfer_page, 'Create backup': self.backup_page,
         'Restore backup': self.restore_page, 'Backup manager': self.backup_manager_page, 'Contacts': lambda: self.phone_tools(False), 'Apps': lambda: self.phone_tools(True), 'Activity': self.activity_page, 'Connection help': self.help_page}[page]()
        self.canvas.yview_moveto(0)
        self.resize_content()

    def send_page(self):
        from .send_to_phone import SendToPhone
        self.send_panel = SendToPhone(self)

    def remember_backup(self, path):
        return self.catalog.add(path)

    def backup_manager_page(self):
        from .backup_manager import BackupManager
        self.backup_panel = BackupManager(self)

    def phone_tools(self, apps):
        from .phone_pages import phone_page
        phone_page(self, apps)

    def media_page(self):
        from .gallery import Gallery
        self.gallery = Gallery(self)
        self.gallery.pack(fill='both', expand=True)

    def overview(self):
        self.heading('Make room for your next device.', 'Copy shared files, keep a local backup, and restore with confidence.')
        hero = self.card()
        self.label(hero, 'One desktop. All your next moves.', size=20, bold=True).pack(anchor='w', pady=T['space_sm'])
        self.label(hero, 'Checksummed copies · Your original files stay in place', muted=True).pack(anchor='w', pady=T['space_sm'])
        row = tk.Frame(hero, bg=T['surface'])
        row.pack(fill='x', pady=T['space_md'])
        for text, page in (('Back up a device', 'Create backup'), ('Copy between devices', 'Phone transfer'), ('Restore a backup', 'Restore backup')):
            self.button(row, text, lambda p=page: self.show(p), primary=page == 'Create backup').pack(side='left', padx=(0, T['space_sm']))
        card = self.card()
        self.label(card, 'Built for files you can access', bold=True, size=15).pack(anchor='w')
        self.label(card, 'Photos, videos, music, documents and other shared files.\nAndroid USB access requires Google ADB and approval on your phone.\nYou can use a local folder or removable drive right away.', muted=True).pack(anchor='w', pady=T['space_md'])
        self.label(card, 'Contacts: exported vCard files. Apps: installation files only. iPhone, SMS, private app data and WhatsApp chats are unavailable.', color=T['danger'], size=10).pack(anchor='w')
        footer = self.card()
        self.label(footer, f'{len(self.endpoints)} sources available   /   {len(self.backup_records())} completed backups', color=T['accent'], bold=True).pack(anchor='w')
        self.button(footer, 'Connect a phone or folder →', lambda: self.show('Connection help')).pack(anchor='w', pady=(T['space_md'], 0))

    def endpoint_picker(self, title, variable):
        card = self.card()
        self.label(card, title.upper(), size=9, color=T['accent'], bold=True).pack(anchor='w', pady=(0, T['space_sm']))
        combo = ttk.Combobox(card, textvariable=variable, values=[e.label for e in self.endpoints], state='readonly', width=55)
        combo.pack(fill='x')
        self.active_controls.append((combo, 'readonly'))
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x', pady=(T['space_sm'], 0))
        for text, fn in (('Add folder / drive', lambda: self.add_folder(variable)), ('Refresh Android phones', self.refresh_devices)):
            btn = self.button(row, text, fn)
            btn.pack(side='left', padx=(0, T['space_sm']))
            self.active_controls.append((btn, 'normal'))
        if not self.endpoints:
            self.label(card, 'No source connected. Add a folder or connect and authorize an Android phone.', muted=True, size=9).pack(anchor='w', pady=(T['space_sm'], 0))

    def categories(self):
        card = self.card()
        self.label(card, 'CONTENT TO INCLUDE', size=9, color=T['accent'], bold=True).pack(anchor='w')
        self.selected = {}
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x', pady=T['space_sm'])
        for index, name in enumerate(CATEGORIES):
            variable = tk.BooleanVar(value=True)
            self.selected[name] = variable
            check = ttk.Checkbutton(row, text=name, variable=variable)
            check.grid(row=index // 3, column=index % 3, sticky='w', padx=(0, T['space_md']))
            self.active_controls.append((check, 'normal'))

    def transfer_page(self):
        self.heading('Move files to another device.', 'Source → destination. Existing different files are preserved and reported as conflicts.')
        self.source_var = tk.StringVar(value=self.endpoints[0].label if self.endpoints else '')
        self.target_var = tk.StringVar(value=self.endpoints[1].label if len(self.endpoints) > 1 else '')
        self.endpoint_picker('01  Source · copy from', self.source_var)
        self.endpoint_picker('02  Destination · copy to', self.target_var)
        self.categories()
        btn = self.button(self.content, 'Start verified copy →', self.start_transfer, primary=True)
        btn.pack(anchor='w')
        self.active_controls.append((btn, 'normal'))

    def backup_page(self):
        self.heading('Keep a copy close to home.', 'Create a local backup with a file manifest and SHA-256 integrity checks.')
        self.source_var = tk.StringVar(value=self.endpoints[0].label if self.endpoints else '')
        self.endpoint_picker('Source device or folder', self.source_var)
        card = self.card()
        self.label(card, 'BACKUP LIBRARY', size=9, color=T['accent'], bold=True).pack(anchor='w')
        path_label = self.label(card, str(self.library), muted=True, size=10)
        path_label.configure(wraplength=700)
        path_label.pack(anchor='w', pady=T['space_sm'])
        btn = self.button(card, 'Choose backup location', self.choose_library)
        btn.pack(anchor='w')
        self.active_controls.append((btn, 'normal'))
        self.categories()
        btn = self.button(self.content, 'Create verified backup →', self.start_backup, primary=True)
        btn.pack(anchor='w')
        self.active_controls.append((btn, 'normal'))

    def backup_records(self):
        records = []
        if self.library.is_dir():
            for child in self.library.iterdir():
                if child.is_dir():
                    try:
                        data = load_manifest(child)
                        records.append((child, data))
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
        return sorted(records, key=lambda r: r[0].name, reverse=True)

    def restore_page(self):
        self.heading('Bring your files back.', 'Only completed DeviceBridge backups are accepted. Integrity is checked before writing.')
        card = self.card()
        self.label(card, '01  CHOOSE A BACKUP', size=9, color=T['accent'], bold=True).pack(anchor='w')
        self.records = self.backup_records()
        self.record_labels = [f"{p.name} · {len(d['items'])} files" for p, d in self.records]
        self.record_var = tk.StringVar(value=self.record_labels[0] if self.record_labels else '')
        combo = ttk.Combobox(card, textvariable=self.record_var, values=self.record_labels, state='readonly', width=55)
        combo.pack(fill='x', pady=T['space_sm'])
        self.active_controls.append((combo, 'readonly'))
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x')
        for text, fn in (('Open backup folder…', self.import_backup), ('Change library…', self.choose_library)):
            btn = self.button(row, text, fn)
            btn.pack(side='left', padx=(0, T['space_sm']))
            self.active_controls.append((btn, 'normal'))
        if not self.records:
            self.label(card, 'No completed backups in this library yet.', muted=True).pack(anchor='w', pady=T['space_sm'])
        self.target_var = tk.StringVar(value=self.endpoints[0].label if self.endpoints else '')
        self.endpoint_picker('02  Restore destination', self.target_var)
        self.categories()
        btn = self.button(self.content, 'Verify backup & restore →', self.start_restore, primary=True)
        btn.pack(anchor='w')
        self.active_controls.append((btn, 'normal'))

    def history(self):
        try:
            return json.loads((self.home / 'activity.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []

    def activity_page(self):
        self.heading('A record of what happened.', 'Completed, partial, cancelled and failed operations are recorded locally.')
        box = self.card()
        text = tk.Text(box, height=18, bg=T['surface'], fg=T['text'], relief='flat', wrap='word', font=(T['font'], T['body']))
        text.pack(fill='both', expand=True)
        entries = self.history()
        text.insert('end', '\n\n'.join(f"{r['date']}   {r['task']}\n{r['summary']}" for r in reversed(entries[-30:])) or 'No operations yet. Your first result will appear here.')
        text.configure(state='disabled')
        if self.last_result:
            self.button(self.content, 'Save last detailed report…', self.save_report).pack(anchor='w')

    def help_page(self):
        self.heading('Connect with confidence.', 'Built-in Android tools. No separate SDK or Platform Tools download needed.')
        companion_card=self.card()
        self.label(companion_card,'COMPANION WI-FI · INCLUDING ANDROID 9',size=15,bold=True).pack(anchor='w')
        self.label(companion_card,'Install Twist Companion once. Share only approved folders and contacts over encrypted local Wi-Fi. No USB debugging or internet required. Existing USB and Android wireless debugging are still available.',muted=True).pack(fill='x',pady=8)
        self.button(companion_card,'Connect with phone companion',self.open_companion,True).pack(anchor='w')
        wireless_card = self.card()
        self.label(wireless_card, 'CONNECT OVER WI-FI', size=15, bold=True).pack(anchor='w')
        self.label(wireless_card, 'Android 11+: find nearby phones, choose yours and enter its pairing code. No IP typing in the normal flow; no internet needed. Android 9/10 normally need USB first.', muted=True, size=10).pack(fill='x', pady=T['space_sm'])
        wifi_button = self.button(wireless_card, 'Connect over Wi-Fi…', self.open_wireless, primary=True)
        wifi_button.pack(anchor='w')
        self.active_controls.append((wifi_button, 'normal'))
        card = self.card()
        self.label(card, 'ANDROID & SAMSUNG GALAXY', size=15, bold=True).pack(anchor='w')
        self.label(card, '1. On your phone, enable Developer options and USB debugging.\n2. Connect a USB data cable, unlock the phone and approve this computer.\n3. Click Refresh phones, then choose your connected device.', muted=True).pack(anchor='w', pady=T['space_md'])
        mode = 'Custom tools selected' if self.adb_mode == 'custom' else 'Automatic tools · ready'
        self.label(card, mode if self.adb else 'Tools missing · reopen the latest executable', size=10, bold=True).pack(anchor='w')
        self.label(card, 'Galaxy S series (including S21, S22 and S23 Ultra), Galaxy A and Galaxy Z use the same Android connection.\nThere is no model lock. Availability depends on Android permissions and accessible shared storage.\nCloud-only media, Gallery-only groups and Secure Folder are not accessible here.', muted=True, size=9).pack(anchor='w', pady=T['space_sm'])
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x', pady=T['space_sm'])
        for text, fn in (('Refresh phones', self.refresh_devices), ('Use built-in tools', self.use_builtin_adb), ('Custom adb.exe…', self.choose_adb)):
            b = self.button(row, text, fn)
            b.pack(side='left', padx=(0, T['space_sm']))
            self.active_controls.append((b, 'normal'))
        card = self.card()
        self.label(card, 'IF YOUR PHONE IS NOT DETECTED', size=15, bold=True).pack(anchor='w')
        self.label(card, 'Try another data cable or USB port, unlock the phone and approve USB debugging.\nA fresh Windows PC may need its manufacturer USB driver. This is separate from the built-in Android tools.', muted=True).pack(anchor='w', pady=T['space_sm'])
        self.button(card, 'Samsung USB driver ↗', lambda: __import__('webbrowser').open('https://developer.samsung.com/android-usb-driver')).pack(anchor='w')
        card = self.card()
        self.label(card, 'YOUR FILES, CONTACTS & APPS', size=15, bold=True).pack(anchor='w')
        self.label(card, 'Media uses shared folders such as DCIM, Pictures, Movies and Android/media.\nContacts: open Contacts → Enable contacts and allow access once on each phone.\nApps: back up and reinstall APKs; private app data is not included.\nLocal folders and drives can also be used. MTP entries under This PC are not folder paths.', muted=True, size=9).pack(anchor='w', pady=T['space_sm'])
        b = self.button(card, 'Add a local folder', self.add_folder)
        b.pack(anchor='w')
        self.active_controls.append((b, 'normal'))

    def open_wireless(self):
        if self.busy:
            return
        if not self.adb:
            self.use_builtin_adb()
        if not self.adb:
            messagebox.showinfo('Android tools missing', 'Reopen the latest executable to restore its built-in tools.')
            return
        existing = getattr(self, 'wireless_dialog', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        from .wireless_dialog import WirelessDialog
        self.wireless_dialog = WirelessDialog(self)

    def open_companion(self):
        if self.busy:return
        existing=getattr(self,'companion_dialog',None)
        if existing is not None and existing.winfo_exists():
            existing.lift();return
        from .companion_dialog import CompanionDialog
        self.companion_dialog=CompanionDialog(self)

    def use_builtin_adb(self):
        from .android_tools import resolve_adb
        self.adb_mode = 'automatic'
        self.adb = resolve_adb()
        self.persist()
        self.show(self.page)

    def open_adb_docs(self):
        import webbrowser
        webbrowser.open('https://developer.android.com/tools/releases/platform-tools')

    def persist(self):
        atomic_json(self.config_file, {**self.settings, 'library': str(self.library), 'adb': self.adb if self.adb_mode == 'custom' else '', 'adb_mode': self.adb_mode,
                    'folders': [str(e.root) for e in self.endpoints if isinstance(e, Folder)]})

    def add_folder(self, variable=None):
        path = filedialog.askdirectory(title='Choose a source or destination folder')
        if not path:
            return
        try:
            endpoint = Folder(path)
            if not any(e.key == endpoint.key for e in self.endpoints):
                self.endpoints.append(endpoint)
            self.persist()
            page = self.page
            previous_source = getattr(self, 'source_var', tk.StringVar()).get()
            previous_target = getattr(self, 'target_var', tk.StringVar()).get()
            is_target = variable is getattr(self, 'target_var', None)
            self.show(page)
            if hasattr(self, 'source_var'):
                self.source_var.set(endpoint.label if variable is not None and not is_target else previous_source)
            if hasattr(self, 'target_var'):
                self.target_var.set(endpoint.label if is_target else previous_target)
            self.status.set('Folder added. Choose it as a source or destination.')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot add folder', str(exc))

    def choose_library(self):
        folder = filedialog.askdirectory(title='Choose a backup library folder')
        if folder:
            self.library = Path(folder)
            self.persist()
            self.show(self.page)

    def import_backup(self):
        folder = filedialog.askdirectory(title='Choose a backup containing manifest.json')
        if folder:
            try:
                data = load_manifest(folder)
                self.records.append((Path(folder), data))
                label = f"{Path(folder).name} · {len(data['items'])} files"
                self.record_labels.append(label)
                self.record_var.set(label)
                self.status.set('Backup selected. Choose a destination and categories.')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                messagebox.showerror('Invalid backup', str(exc))

    def choose_adb(self):
        file = filedialog.askopenfilename(title='Choose Google Platform Tools adb.exe', filetypes=[('ADB executable', 'adb.exe')])
        if file:
            self.adb = file
            self.adb_mode = 'custom'
            self.persist()
            self.show(self.page)

    def refresh_devices(self):
        from .android_tools import resolve_adb
        self.adb = resolve_adb({'adb_mode': self.adb_mode, 'adb': self.adb})
        if not self.adb:
            messagebox.showinfo('Set up Android access', 'Reopen the latest Twist MediaBridge executable to use its built-in Android tools. See Connection help for advanced setup.')
            self.show('Connection help')
            return
        self.run('Device discovery', lambda report: discover(self.adb), self.devices_found, record=False)

    def devices_found(self, result):
        ready, blocked = result
        from .companion_link import retain_companions
        self.endpoints = retain_companions(self.endpoints,ready)
        from .engine import Android
        ready=[e for e in self.endpoints if isinstance(e,Android)]
        self.show(self.page)
        if ready:
            self.status.set(f'{len(ready)} Android phone(s) ready. Select the phone in the source or destination list.')
        elif 'unauthorized' in blocked:
            self.status.set('Phone detected · Unlock it and tap Allow USB debugging on the phone, then refresh again. If no prompt appears, reconnect the USB cable.')
        elif blocked:
            self.status.set(f"Phone connection blocked: {', '.join(blocked)}. Reconnect the cable, unlock the phone and refresh.")
        else:
            self.status.set('ADB is ready, but no phone was detected. Connect USB or use Connect over Wi-Fi in Connection help, then refresh.')

    def endpoint(self, variable):
        return next((e for e in self.endpoints if e.label == variable.get()), None)

    def choices(self):
        selected = {k for k, v in self.selected.items() if v.get()}
        if not selected:
            raise ValueError('Choose at least one content category.')
        return selected

    def start_backup(self):
        try:
            source, selected = self.endpoint(self.source_var), self.choices()
            if source is None:
                raise ValueError('Select a source first.')
            def work(report):
                result = backup(source, self.library, selected, self.cancel, report)
                if result['status'] == 'complete':
                    self.remember_backup(result['folder'])
                return result
            self.run('Backup', work)
        except ValueError as exc:
            messagebox.showinfo('Check your selection', str(exc))

    def start_transfer(self):
        try:
            from .engine import Android
            source, target, selected = self.endpoint(self.source_var), self.endpoint(self.target_var), self.choices()
            if source is None or target is None:
                raise ValueError('Select both a source and a destination.')
            self.run('Transfer', lambda report: transfer(source, target, selected, self.cancel, report,flatten=isinstance(source,Android) and isinstance(target,Folder)))
        except ValueError as exc:
            messagebox.showinfo('Check your selection', str(exc))

    def start_restore(self):
        try:
            if self.record_var.get() not in self.record_labels:
                raise ValueError('Select a completed backup first.')
            folder, _ = self.records[self.record_labels.index(self.record_var.get())]
            target, selected = self.endpoint(self.target_var), self.choices()
            if target is None:
                raise ValueError('Select a restore destination.')
            source = Folder(folder / 'files')
            self.run('Restore', lambda report: transfer(source, target, selected, self.cancel, report, backup_folder=folder))
        except (OSError, ValueError) as exc:
            messagebox.showinfo('Check your selection', str(exc))

    def run(self, task, fn, done=None, record=True):
        if self.busy:
            return
        self.busy = True
        self.current_task = task
        self.statusbox.grid()
        self.cancel.clear()
        self.progress['value'] = 0
        self.status.set(task + ' · preparing…')
        self.cancel_btn.configure(state='normal')
        for b in self.nav.values():
            b.configure(state='disabled')
        for widget, _ in self.active_controls:
            widget.configure(state='disabled')
        def worker():
            try:
                value = fn(lambda p, text: self.events.put(('progress', p, text)))
                self.events.put(('done', task, value, done, record))
            except Exception as exc:
                self.events.put(('error', task, str(exc), isinstance(exc, Cancelled), record))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'drop_files':
                    self.pending_drops.extend(event[1])
                elif event[0] == 'media_batch':
                    _, gallery, token, items = event
                    if gallery.alive:
                        gallery.update_scan_batch(token, items)
                elif event[0] == 'progress':
                    self.progress['value'], value = event[1:]
                    self.status.set(value)
                else:
                    self.busy = False
                    self.cancel_btn.configure(state='disabled')
                    for b in self.nav.values():
                        b.configure(state='normal')
                    for widget, state in self.active_controls:
                        if widget.winfo_exists():
                            widget.configure(state=state)
                    if event[0] == 'done':
                        _, task, result, done, record = event
                        if done:
                            done(result)
                        if record:
                            self.last_result = result
                            summary = f"{result['status'].upper()} · {result['copied']} files copied · {result.get('present', 0)} already present · {result['failed']} failed"
                            if 'requested' in result:summary+=f" · {result['requested']} selected in total"
                            self.status.set(summary + (' · See Activity for the report.' if result['failed'] else ''))
                            if self.page == 'Media library':
                                self.gallery.stats.set(summary + (' · Details in Activity.' if result['failed'] else ''))
                            self.record(task, summary)
                    else:
                        _, task, error, cancelled, record = event
                        summary = ('CANCELLED' if cancelled else 'FAILED') + ' · ' + error
                        self.status.set(summary)
                        if self.page == 'Backup manager' and hasattr(self, 'backup_panel'):
                            self.backup_panel.summary.set(summary)
                        if self.page in ('Apps', 'Contacts') and hasattr(self, 'phone_panel'):
                            self.phone_panel.summary.set(summary)
                        if self.page == 'Media library':
                            self.gallery.stats.set(summary)
                        if record:
                            self.last_result = {'status': 'cancelled' if cancelled else 'failed', 'error': error}
                            self.record(task, summary)
                    if self.page in ('Media library', 'Apps', 'Contacts', 'Backup manager'):
                        self.statusbox.grid_remove()
        except queue.Empty:
            pass
        except Exception:
            self.busy = False
            self.report_callback_exception(*sys.exc_info())
            self.status.set('Could not display the result. See errors.log in DeviceBridge-data.')
            if self.page == 'Media library':
                self.gallery.stats.set(self.status.get())
            for button in self.nav.values():
                button.configure(state='normal')
            self.cancel_btn.configure(state='disabled')
            for widget, state in self.active_controls:
                if widget.winfo_exists():
                    widget.configure(state=state)
        finally:
            if self.pending_drops and not self.busy:
                paths,self.pending_drops=self.pending_drops,[]
                if self.page != 'Send to phone':self.show('Send to phone')
                self.send_panel.add(paths)
            self.after(100, self.poll)

    def report_callback_exception(self, exc_type, value, traceback):
        import traceback as tb
        try:
            with (self.home / 'errors.log').open('a', encoding='utf-8') as log:
                log.write(datetime.now(timezone.utc).isoformat() + '\n')
                log.write(''.join(tb.format_exception(exc_type, value, traceback)))
        except OSError:
            pass

    def record(self, task, summary):
        rows = self.history()
        rows.append({'date': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'task': task, 'summary': summary})
        try:
            atomic_json(self.home / 'activity.json', rows[-200:])
        except OSError as exc:
            self.status.set(summary + ' · Could not save activity: ' + str(exc))

    def save_report(self):
        path = filedialog.asksaveasfilename(title='Save operation report', defaultextension='.json', filetypes=[('JSON report', '*.json')])
        if path:
            try:
                atomic_json(Path(path), self.last_result)
            except OSError as exc:
                messagebox.showerror('Report could not be saved', str(exc))

    def cancel_job(self):
        self.cancel.set()
        self.status.set('Cancellation requested. Waiting for the current step to stop…')
        self.cancel_btn.configure(state='disabled')

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation is running', 'Cancel the operation and wait for it to stop before closing.')
            return
        link=getattr(self,'companion_link',None)
        if link:link.close()
        self.destroy()


def main(start_page=None):
    try:
        app = App()
        if start_page == 'Send to phone':app.show(start_page)
        app.mainloop()
    except Exception:
        import traceback
        # A windowed executable otherwise hides startup errors.
        detail = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror('Twist MediaBridge could not start', detail)
        finally:
            raise

