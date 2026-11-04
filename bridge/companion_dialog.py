"""Android 6+ companion Wi-Fi setup; independent from ADB pairing."""
import shutil
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk
from .theme import TOKENS as T
from .companion_link import Link, Companion, local_addresses
from .desktop import resource_path


class CompanionDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.link = getattr(app, 'companion_link', None)
        self.photo = None
        self.copied = None
        self.creation_lock=threading.Lock()
        self.title('Companion Wi-Fi · Twist MediaBridge')
        self.configure(bg=T['bg'])
        self.geometry('740x720')
        self.minsize(660, 650)
        self.protocol('WM_DELETE_WINDOW',self.close)
        body=tk.Frame(self,bg=T['bg'],padx=24,pady=20)
        body.pack(fill='both',expand=True)
        app.label(body,'Your Note8. Without a cable.',size=21,bold=True).pack(anchor='w')
        app.label(body,'Android 6+ · Same local network · No internet or USB debugging needed',muted=True,size=10).pack(anchor='w',pady=8)
        app.label(body,'Install Twist Companion on the phone once. Open it and choose your media folders / Contacts permission. Start pairing below, tap Scan PC QR in the phone companion, then approve Connect. Keep the companion open.',size=11).pack(fill='x',pady=8)
        row=tk.Frame(body,bg=T['bg']);row.pack(fill='x',pady=8)
        app.button(row,'Save phone app…',self.save_apk).pack(side='left')
        addresses=local_addresses()
        self.address=tk.StringVar(value=addresses[0] if addresses else '')
        ttk.Combobox(row,textvariable=self.address,values=addresses,state='readonly',width=17).pack(side='left',padx=12)
        self.start_button=app.button(row,'Start pairing',self.start,True)
        self.start_button.pack(side='left')
        self.qr=tk.Label(body,bg=T['surface'],fg=T['muted'],text='Your private pairing QR will appear here.',height=1)
        self.qr.pack(fill='both',expand=True,pady=8)
        self.status=tk.StringVar(value='Choose your PC’s Wi-Fi address. If there are several, use the same network as your phone.')
        label=app.label(body,'',size=10);label.configure(textvariable=self.status);label.pack(fill='x',pady=8)
        row=tk.Frame(body,bg=T['bg']);row.pack(fill='x')
        app.button(row,'Copy pairing link',self.copy_link).pack(side='left')
        app.button(row,'Disconnect',self.disconnect).pack(side='left',padx=10)
        app.button(row,'Done',self.close,True).pack(side='right')
        app.label(body,'USB and Android wireless debugging remain available. Companion: media transfer, approved-folder backups, contacts and APK backup. App installation/uninstallation still uses the existing debugging connections. If Windows asks, allow this app on your private network only.',muted=True,size=9).pack(fill='x',pady=(12,0))
        self.after(250,self.poll)

    def save_apk(self):
        chosen=filedialog.asksaveasfilename(parent=self,title='Save Android companion',initialfile='TwistCompanion.apk',defaultextension='.apk',filetypes=[('Android app','*.apk')])
        if chosen:
            try:
                shutil.copy2(resource_path('companion/TwistContactsBridge.apk'),chosen)
                self.status.set('Send this APK to your phone using Quick Share or another trusted method, then open it to install.')
            except OSError as error:
                messagebox.showerror('Cannot save companion',str(error),parent=self)

    def start(self):
        if self.app.busy:return
        self.disconnect()
        self.start_button.configure(state='disabled')
        self.status.set('Creating an encrypted local pairing session…')
        # Certificate creation runs outside the UI thread; Tk is touched only in poll.
        self.starting=True
        self.created=None
        address=self.address.get()
        def create():
            try: result=Link(address)
            except Exception as error:result=error
            with self.creation_lock:
                abandoned=not self.winfo_exists_safe()
                if not abandoned:self.created=result
            if abandoned and isinstance(result,Link):result.close()
        threading.Thread(target=create,daemon=True).start()

    def winfo_exists_safe(self):
        return not getattr(self,'closed',False)

    def copy_link(self):
        if self.link and not self.link.joined and time.monotonic()<self.link.deadline:
            self.copied=self.link.uri();self.clipboard_clear();self.clipboard_append(self.copied)
            self.status.set('Pairing link copied. Treat it as private. Paste into the phone companion if its camera cannot open the QR.')

    def clear_clipboard(self):
        if self.copied:
            try:
                if self.clipboard_get()==self.copied:self.clipboard_clear()
            except tk.TclError:pass
        self.copied=None

    def disconnect(self):
        if self.link:
            link=self.link;self.link=None
            threading.Thread(target=link.close,daemon=True).start()
        self.app.companion_link=None
        self.clear_clipboard()
        self.qr.configure(image='',text='Session ended. Start pairing to connect.',height=1)
        self.photo=None

    def poll(self):
        if not self.winfo_exists_safe():return
        if getattr(self,'starting',False) and self.created is not None:
            result=self.created;self.created=None;self.starting=False
            self.start_button.configure(state='normal')
            if isinstance(result,Exception):
                self.status.set('Cannot start local connection: '+str(result))
            else:
                self.link=result;self.app.companion_link=result
                import qrcode
                qr=qrcode.QRCode(box_size=3,border=4)
                qr.add_data(result.uri());qr.make(fit=True)
                image=qr.make_image(fill_color='black',back_color='white').convert('RGB')
                self.photo=ImageTk.PhotoImage(image)
                self.qr.configure(image=self.photo,text='',height=0)
        if self.link:
            if self.link.online():
                if not any(isinstance(e,Companion) and e.link is self.link for e in self.app.endpoints):
                    self.app.endpoints.append(Companion(self.link))
                    self.app.status.set(self.link.model+' connected through Companion Wi-Fi. Select it in Media library or Contacts.')
                    gallery=getattr(self.app,'gallery',None)
                    if gallery and gallery.alive:
                        gallery.refresh_choices();gallery.source_var.set(self.app.endpoints[-1].label);gallery.reset_source()
                    panel=getattr(self.app,'phone_panel',None)
                    if panel and panel.winfo_exists():
                        from .engine import Android
                        panel.combo.configure(values=[e.label for e in self.app.endpoints if isinstance(e,Android)])
                        panel.phone_var.set(self.app.endpoints[-1].label)
                self.qr.configure(image='',text='✓ '+self.link.model+' connected',height=1)
                self.photo=None;self.clear_clipboard()
                self.status.set('Connected. Choose this phone in Media library, Contacts, Apps or Create backup. Keep the phone companion open.')
            elif self.link.joined:
                self.status.set('Phone disconnected. Media and contacts are cleared when the connection is lost. Start pairing again to reconnect.')
            else:
                left=max(0,int(self.link.deadline-time.monotonic()))
                if left:
                    self.status.set(f'On the phone tap Scan PC QR in Twist Companion. Pairing expires in {left//60}:{left%60:02}.')
                else:
                    self.disconnect();self.status.set('Pairing expired. Start again for a fresh QR.')
        self.after(300,self.poll)

    def close(self):
        with self.creation_lock:
            self.closed=True
            created=getattr(self,'created',None)
            self.created=None
        if isinstance(created,Link):
            threading.Thread(target=created.close,daemon=True).start()
        self.clear_clipboard()
        if self.link and not self.link.online():self.disconnect()
        self.destroy()
