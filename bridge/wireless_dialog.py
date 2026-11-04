"""A local-only, two-step wireless connection assistant."""
import queue
import threading
import textwrap
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from .engine import Android, Folder, Cancelled
from .theme import TOKENS as T
from . import wireless


class WirelessDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('Twist MediaBridge · Connect over Wi-Fi')
        self.configure(bg=T['bg'])
        self.geometry('780x710')
        self.minsize(720, 690)
        self.transient(app)
        self.grab_set()
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.running = False
        self.status_kind = 'idle'
        self.controls = []
        self.nearby_rows = {}
        self.selected_candidate = None
        self.manual_visible = False
        self.qr_window = None
        self.qr_photo = None
        self.qr_session = None
        self.pair_address = tk.StringVar()
        self.code = tk.StringVar()
        self.connect_address = tk.StringVar()
        self.status = tk.StringVar(value='Open the phone pairing-code screen, then click Find nearby phones. No address typing needed.')
        self.connections = {e.label: e.serial for e in app.endpoints
                            if isinstance(e, Android) and hasattr(e,'serial') and wireless.wireless_serial(e.serial)}
        self.selected = tk.StringVar(value=next(iter(self.connections), ''))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Escape>', lambda event: self.close())
        self.bind('<Destroy>', lambda event: self.cancel.set() if event.widget is self else None)
        self.body = tk.Frame(self, bg=T['bg'], padx=T['space_lg'], pady=T['space_md'])
        self.body.pack(fill='both', expand=True)
        self.footer = footer = tk.Frame(self.body, bg=T['bg'])
        footer.pack(side='bottom', fill='x')
        label = app.label(footer, '', size=10, color=T['success'])
        label.configure(textvariable=self.status)
        label.pack(fill='x', pady=T['space_sm'])
        app.label(footer, 'Keep Wireless debugging on during transfers. Guest Wi-Fi, VPNs or router isolation can block local connections. To revoke trust, Forget this computer on the phone. Pairing codes are never saved.', size=9, muted=True).pack(fill='x')
        app.button(footer, 'Cancel / Close', self.close).pack(anchor='e', pady=T['space_sm'])
        canvas_row = tk.Frame(self.body, bg=T['bg'])
        canvas_row.pack(fill='both', expand=True)
        canvas = tk.Canvas(canvas_row, bg=T['bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_row, command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=T['bg'])
        window = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta / 120), 'units'))
        self.body = inner
        app.label(self.body, 'Your phone. Without the cable.', size=21, bold=True).pack(anchor='w')
        app.label(self.body, 'Android 11+ · Same local Wi-Fi · Internet access is not required', size=10, color=T['accent']).pack(anchor='w', pady=T['space_sm'])
        app.label(self.body, 'No phone notification is sent. For a six-digit code, open Wireless debugging → Pair device with pairing code ON THE PHONE. Keep that screen open. QR pairing is a separate option.', muted=True, size=10).pack(fill='x', pady=(0, T['space_sm']))
        card = self.card()
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x', pady=(0, T['space_sm']))
        self.button(row, 'Find nearby phones', self.start_find, True).pack(side='left')
        self.button(row, 'Pair with QR code', self.start_qr).pack(side='left', padx=T['space_sm'])
        app.button(row, 'Phone setup help', self.phone_help).pack(side='right')
        listing = tk.Frame(card, bg=T['surface'])
        listing.pack(fill='both', expand=True)
        app.style.configure('Nearby.Treeview', background=T['list_bg'], fieldbackground=T['list_bg'],
                            foreground=T['text'], rowheight=T['space_md'] * 2, borderwidth=0)
        app.style.configure('Nearby.Treeview.Heading', background=T['raised'], foreground=T['text'], padding=T['space_sm'])
        app.style.map('Nearby.Treeview', background=[('selected', T['list_selected'])], foreground=[('selected', T['text'])])
        self.nearby_tree = ttk.Treeview(listing, columns=('phone', 'state'), show='headings', height=3, selectmode='browse', style='Nearby.Treeview')
        self.nearby_tree.heading('phone', text='Nearby Android phones')
        self.nearby_tree.heading('state', text='Next step')
        self.nearby_tree.column('phone', width=380, minwidth=200)
        self.nearby_tree.column('state', width=150, minwidth=110)
        self.nearby_tree.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(listing, command=self.nearby_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.nearby_tree.configure(yscrollcommand=scrollbar.set)
        self.nearby_tree.bind('<<TreeviewSelect>>', self.choose_candidate)
        self.nearby_tree.bind('<Button-1>', lambda event: 'break' if self.running else None)
        self.nearby_tree.bind('<KeyPress>', lambda event: 'break' if self.running else None)
        self.nearby_tree.bind('<Double-1>', lambda event: self.start_selected_connect() if not self.running else None)
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x', pady=(T['space_sm'], 0))
        app.label(row, 'Pairing code', size=10).pack(side='left', padx=(0, T['space_sm']))
        self.pin_entry = self.entry(row, self.code, secret=True)
        self.pin_entry.pack(side='left', fill='x', expand=True, ipady=T['space_sm'])
        self.button(row, 'Pair using code', self.start_auto_pair, True).pack(side='left', padx=T['space_sm'])
        self.button(row, 'Connect selected', self.start_selected_connect).pack(side='left')
        self.action_status = app.label(card, '', size=10, color=T['accent'])
        self.action_status.configure(textvariable=self.status)
        self.action_status.pack(fill='x', pady=(T['space_sm'], 0))
        self.activity = ttk.Progressbar(card, mode='indeterminate')
        self.activity.pack(fill='x', pady=(T['space_sm'], 0))
        app.label(card, 'Already paired? Select your phone and Connect selected. Unpaired phones may show a device identifier until connected.', size=9, muted=True).pack(fill='x', pady=(T['space_sm'], 0))
        self.manual_toggle = self.button(self.body, 'Advanced manual connection ▸', self.toggle_manual)
        self.manual_toggle.pack(anchor='w', pady=(0, T['space_sm']))
        self.manual = tk.Frame(self.body, bg=T['bg'])
        card = self.card(self.manual)
        app.label(card, '1  PAIR ONCE', bold=True).pack(anchor='w')
        app.label(card, 'Tap “Pair device with pairing code” on the phone. Keep that popup open.', size=10, muted=True).pack(anchor='w', pady=T['space_sm'])
        form = tk.Frame(card, bg=T['surface'])
        form.pack(fill='x')
        self.field(form, 'Pairing IP address:port', self.pair_address, 0)
        self.field(form, 'Six-digit code', self.code, 1, secret=True)
        self.button(form, 'Pair phone', self.start_pair).grid(row=1, column=2, padx=(T['space_sm'], 0), sticky='e')
        card = self.card(self.manual)
        app.label(card, '2  CONNECT', bold=True).pack(anchor='w')
        app.label(card, 'Close the pairing popup. Copy “IP address & Port” from the main Wireless debugging screen. This port is usually different.', size=10, muted=True).pack(fill='x', pady=T['space_sm'])
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x')
        app.label(row, 'Connection IP address:port', size=10).pack(anchor='w')
        self.entry(row, self.connect_address).pack(side='left', fill='x', expand=True, ipady=T['space_sm'])
        self.button(row, 'Connect', self.start_connect, True).pack(side='left', padx=(T['space_sm'], 0))
        card = self.card()
        app.label(card, 'DISCONNECT A WI-FI DEVICE', bold=True, size=10).pack(anchor='w', pady=(0, T['space_sm']))
        row = tk.Frame(card, bg=T['surface'])
        row.pack(fill='x')
        box = ttk.Combobox(row, textvariable=self.selected, values=list(self.connections), state='readonly')
        box.pack(side='left', fill='x', expand=True)
        self.controls.append((box, 'readonly'))
        self.button(row, 'Disconnect', self.start_disconnect).pack(side='left', padx=(T['space_sm'], 0))
        self.timer = self.after(100, self.poll)

    def card(self, parent=None):
        card = tk.Frame(parent or self.body, bg=T['surface'], padx=T['space_md'], pady=T['space_sm'])
        card.pack(fill='x', pady=(0, T['space_sm']))
        return card

    def entry(self, parent, variable, secret=False):
        entry = tk.Entry(parent, textvariable=variable, bg=T['raised'], fg=T['text'],
                         insertbackground=T['accent'], relief='flat', show='•' if secret else '')
        self.controls.append((entry, 'normal'))
        return entry

    def field(self, parent, label, variable, column, secret=False):
        parent.grid_columnconfigure(column, weight=1)
        self.app.label(parent, label, size=10).grid(row=0, column=column, sticky='w', padx=(0, T['space_sm']))
        self.entry(parent, variable, secret).grid(row=1, column=column, sticky='ew', ipady=T['space_sm'], padx=(0, T['space_sm']))

    def button(self, parent, text, fn, primary=False):
        button = self.app.button(parent, text, fn, primary)
        self.controls.append((button, 'normal'))
        return button

    def launch(self, name, work):
        if self.running:
            return
        self.running = True
        self.cancel.clear()
        self.status_kind = 'working'
        self.action_status.configure(fg=T['accent'])
        self.status.set(name + '…')
        self.activity.start()
        for control, _ in self.controls:
            control.configure(state='disabled')
        def worker():
            try:
                self.events.put((name, work(), None))
            except Cancelled:
                self.events.put((name, None, 'Cancelled.'))
            except wireless.PairingRequired as exc:
                self.events.put(('needs_pairing', None, str(exc)))
            except (OSError, ValueError, TimeoutError) as exc:
                self.events.put((name, None, str(exc)))
            except Exception:
                # Never send raw process output or pairing secrets to UI logs.
                self.events.put((name, None, 'Connection failed. Check the phone settings and try again.'))
        threading.Thread(target=worker, daemon=True).start()

    def toggle_manual(self):
        self.manual_visible = not self.manual_visible
        if self.manual_visible:
            self.manual.pack(fill='x', after=self.manual_toggle)
        else:
            self.manual.pack_forget()
        self.manual_toggle.configure(text='Advanced manual connection ▾' if self.manual_visible else 'Advanced manual connection ▸')

    def phone_help(self):
        messagebox.showinfo('Open the pairing screen on your phone',
            'Android 11 or newer is required for cable-free PIN pairing.\n\n'
            'OPPO / ColorOS: Settings → Additional settings (or System settings) → Developer options. '
            'Open Wireless debugging by tapping its name, not only its on/off switch. '
            'Then tap Pair device with pairing code.\n\n'
            'If Developer options is hidden: Settings → About phone → Version, then tap Version number '
            '(or Build number) seven times. Enter the phone lock code if asked.\n\n'
            'You can also search phone Settings for Wireless debugging. If that screen is absent on your '
            'phone software, this app cannot enable it remotely. Keep using USB where available.\n\n'
            'Finding a phone is not the same as pairing. An unpaired phone will not automatically '
            'show an approval notification when the PC tries to connect.', parent=self)

    def start_find(self):
        if self.running:
            return
        self.code.set('')
        self.nearby_rows.clear()
        self.selected_candidate = None
        self.nearby_tree.delete(*self.nearby_tree.get_children())
        self.launch('Finding phones', lambda: wireless.nearby(self.app.adb, self.cancel))

    def start_qr(self):
        if self.running:
            return
        from . import qr_pairing
        from PIL import ImageTk
        session = qr_pairing.new_session()
        self.qr_session = session
        window = self.qr_window = tk.Toplevel(self)
        window.title('Twist MediaBridge · Scan to pair')
        window.configure(bg=T['bg'])
        window.geometry('520x650')
        window.minsize(520, 650)
        window.transient(self)
        window.grab_set()
        window.protocol('WM_DELETE_WINDOW', self.cancel_qr)
        window.bind('<Escape>', lambda event: self.cancel_qr())
        body = tk.Frame(window, bg=T['bg'], padx=T['space_lg'], pady=T['space_md'])
        body.pack(fill='both', expand=True)
        self.app.button(body, 'Cancel QR pairing', self.cancel_qr).pack(side='bottom', anchor='e', pady=T['space_sm'])
        self.app.label(body, 'Scan to connect.', size=21, bold=True).pack(anchor='w')
        self.app.label(body, 'On the phone: Wireless debugging → Pair device with QR code. Scan this screen using that scanner. A normal camera may not pair the phone.', size=10, muted=True).pack(fill='x', pady=T['space_md'])
        self.qr_photo = ImageTk.PhotoImage(qr_pairing.image(session))
        tk.Label(body, image=self.qr_photo, bg=T['bg']).pack(pady=T['space_sm'])
        self.app.label(body, 'Local network only · Expires in 5 minutes\nNo PIN or IP typing. Keep this window open.', size=10, muted=True).pack(fill='x', pady=T['space_sm'])
        label = self.app.label(body, '', size=10, color=T['accent'])
        label.configure(textvariable=self.status)
        label.pack(fill='x', pady=T['space_sm'])
        self.launch('QR pairing · scan the code on your phone', lambda: qr_pairing.pair_session(self.app.adb, session, self.cancel,
                    lambda text: self.events.put(('progress', text, None))))

    def cancel_qr(self):
        self.cancel.set()
        self.clear_qr()
        self.status.set('Cancelling QR pairing…')
        self.grab_set()

    def clear_qr(self):
        if self.qr_window is not None and self.qr_window.winfo_exists():
            self.qr_window.destroy()
        self.qr_window = self.qr_photo = self.qr_session = None

    def choose_candidate(self, event=None):
        if self.running:
            return
        selection = self.nearby_tree.selection()
        candidate = self.nearby_rows.get(selection[0]) if selection else None
        if candidate is self.selected_candidate:
            return  # Repeated Treeview events must not erase errors or a typed PIN.
        self.selected_candidate = candidate
        self.status_kind = 'idle'
        self.code.set('')
        if self.selected_candidate:
            self.status.set('Enter the code shown on this phone and Pair & connect.' if self.selected_candidate['pair_address']
                            else 'Already paired? Connect selected. Otherwise open Pair device with pairing code on this phone, enter its code here and Pair & connect.')

    def start_auto_pair(self):
        if self.running:
            return
        row = self.selected_candidate
        if not row:
            self.status.set('Find nearby phones, then select the phone you want to pair.')
            return
        code = self.code.get()
        self.code.set('')
        if not code:
            self.prompt_pairing('Open the code screen on your phone.')
            return
        self.launch('Pairing & connecting', lambda: wireless.pair_and_connect(self.app.adb, dict(row), code, self.cancel,
                    lambda text: self.events.put(('progress', text, None))))

    def start_selected_connect(self):
        if self.running:
            return
        row = self.selected_candidate
        if not row:
            self.status.set('Find nearby phones, then select a phone first.')
            return
        if self.code.get().strip():
            self.start_auto_pair()
            return
        self.code.set('')
        self.launch('Connecting selected', lambda: wireless.connect_candidate(self.app.adb, dict(row), self.cancel))

    def prompt_pairing(self, reason):
        self.status_kind = 'pairing_required'
        row = self.selected_candidate
        if not row:
            self.status.set('Select the phone you want to pair first.')
            return
        self.launch('Waiting for phone code screen', lambda: wireless.wait_for_pin_server(self.app.adb, dict(row), self.cancel,
                    report=lambda text: self.events.put(('progress', text, None))))

    def enter_phone_code(self, row):
        self.selected_candidate.update(row)
        self.status.set('Phone code screen detected. Enter the six-digit code displayed there. Keep that phone popup open.')
        prompt = ('The selected phone is now advertising its pairing-code screen.\n\n'
                    'Read the six-digit code on that phone screen and enter it below. '
                    'Keep the phone popup open until pairing finishes.\n\n'
                    'This code is generated on the phone, not sent as a notification by the PC.')
        prompt = '\n\n'.join(textwrap.fill(paragraph, width=68) for paragraph in prompt.split('\n\n'))
        code = simpledialog.askstring('Pair this phone', prompt,
                    parent=self, show='•')
        self.grab_set()
        if code is not None:
            self.code.set(code.strip())
            self.start_auto_pair()
        else:
            self.status.set('Phone detected, but pairing is not complete. On the phone open Pair device with pairing code, enter its code here and Pair & connect.')

    def start_pair(self):
        address, code = self.pair_address.get(), self.code.get()
        self.code.set('')
        self.launch('Pairing', lambda: wireless.pair(self.app.adb, address, code, self.cancel))

    def start_connect(self):
        address = self.connect_address.get()
        self.launch('Connecting', lambda: wireless.connect(self.app.adb, address, self.cancel))

    def start_disconnect(self):
        serial = self.connections.get(self.selected.get())
        if not serial:
            self.status.set('No Wi-Fi connection selected. USB connections are left alone.')
            return
        self.launch('Disconnecting', lambda: wireless.disconnect(self.app.adb, serial, self.cancel))

    def poll(self):
        try:
            name, result, error = self.events.get_nowait()
        except queue.Empty:
            self.timer = self.after(100, self.poll)
            return
        if name == 'progress':
            self.status.set(result)
            self.timer = self.after(100, self.poll)
            return
        self.running = False
        self.activity.stop()
        self.activity['value'] = 0
        is_qr = name.startswith('QR pairing')
        if is_qr:
            self.clear_qr()
            self.grab_set()
            if self.cancel.is_set():
                error = 'Cancelled.'
        for control, state in self.controls:
            control.configure(state=state)
        if name == 'needs_pairing':
            self.prompt_pairing(error)
        elif error:
            self.status_kind = 'error'
            self.action_status.configure(fg=T['danger'])
            self.status.set(error)
            if (name in ('Connecting selected', 'Connecting', 'Pairing & connecting', 'Pairing', 'Waiting for phone code screen') or is_qr) and error != 'Cancelled.':
                messagebox.showerror('Wi-Fi connection not completed', error, parent=self)
        elif name == 'Finding phones':
            for index, row in enumerate(result):
                key = str(index)
                self.nearby_rows[key] = row
                state = 'Connected' if row['connected_serial'] else ('Code screen detected' if row['pair_address'] else 'Open code screen on phone')
                self.nearby_tree.insert('', 'end', iid=key, values=(row['label'], state))
            self.status.set(f'{len(result)} phone(s) found. Select your phone.' if result else
                            'No phone advertised yet after ADB and direct local discovery. Toggle Wireless debugging off/on on the phone, keep its pairing screen open and find again. Same Wi-Fi alone is not enough; guest networks/firewalls may block discovery.')
        elif name == 'Pairing':
            self.status.set(result)
            self.app.status.set('Wi-Fi phone paired. Complete Connect using the main Wireless debugging port.')
        elif name == 'Waiting for phone code screen':
            self.enter_phone_code(result)
        elif name in ('Connecting', 'Pairing & connecting', 'Connecting selected') or is_qr:
            if name == 'Connecting':
                address = wireless.endpoint(self.connect_address.get())
            else:
                result, address = result
            phones, _ = result
            phones.sort(key=lambda phone: phone.serial != address)
            from .companion_link import retain_companions
            self.app.endpoints = retain_companions(self.app.endpoints,phones)
            self.close()
            self.app.show('Media library')
            self.app.gallery.stats.set('Wi-Fi phone connected. Click Load albums. Keep Wireless debugging enabled on the phone.')
            self.app.status.set('Wi-Fi connected · local network only; no internet required.')
            return
        elif name == 'Disconnecting':
            self.app.endpoints = [e for e in self.app.endpoints if not isinstance(e, Android) or getattr(e,'serial',None) != result]
            # Destroying/rebuilding the media page also clears private previews.
            page = self.app.page
            self.close()
            self.app.show(page)
            self.app.status.set('Wi-Fi phone disconnected. To revoke pairing, Forget this computer on the phone.')
            return
        self.timer = self.after(100, self.poll)

    def close(self):
        self.cancel.set()
        self.clear_qr()
        self.code.set('')
        if getattr(self, 'timer', None):
            self.after_cancel(self.timer)
        self.grab_release()
        self.destroy()
