from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import queue
import threading
import tempfile
import shutil
from collections import OrderedDict
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import ImageTk

from .engine import Android, Folder, discover, transfer, Cancelled, adb_run
from .media import MediaCache, scan_media, album_counts, MEDIA_TYPES, play_frames, video_duration
from .theme import TOKENS as T
from .preview_canvas import PreviewCanvas
from .clipboard_image import image_payloads, put_image_on_clipboard
from .companion_link import phone_online, retain_companions


class Gallery(tk.Frame):
    def __init__(self, app):
        super().__init__(app.content, bg=T['bg'])
        self.app = app
        self.alive = True
        self.stop = threading.Event()
        self.media_cancel = threading.Event()
        self.jobs = queue.PriorityQueue()
        self.results = queue.Queue()
        self.sequence = 0
        self.generation = 0
        self.items = []
        self.chosen = set()
        self.selection_anchor = None
        self.album = None
        self.source = None
        self.index_ready = False
        self.scan_token = None
        self.photos = OrderedDict()
        self.cards = {}
        self.session_cache = Path(tempfile.mkdtemp(prefix='twist-media-'))
        self.cache = MediaCache(self.session_cache)
        self.preview = None
        self.preview_stop = threading.Event()
        self.heading()
        self.toolbar()
        self.build_browser()
        self.bind('<Destroy>', self.destroyed, add='+')
        for _ in range(3):
            threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.watch_connection, daemon=True).start()
        self.after(80, self.poll)

    def heading(self):
        a = self.app
        a.label(self, 'Albums & moments.', size=21, bold=True).pack(anchor='w', pady=(0, T['space_sm']))

    def control(self, parent, title, command, primary=False):
        button = self.app.button(parent, title, command, primary)
        self.app.active_controls.append((button, 'normal'))
        return button

    def toolbar(self):
        a = self.app
        card = tk.Frame(self, bg=T['surface'], padx=T['space_sm'], pady=T['space_sm'])
        card.pack(fill='x', pady=(0, T['space_sm']))
        self.source_var = tk.StringVar(value=next((e.label for e in a.endpoints if isinstance(e, Android)), ''))
        self.source_combo = ttk.Combobox(card, textvariable=self.source_var, values=[e.label for e in a.endpoints], state='readonly')
        self.source_combo.pack(side='left', fill='x', expand=True, padx=(0, 8))
        a.active_controls.append((self.source_combo, 'readonly'))
        self.source_combo.bind('<<ComboboxSelected>>', lambda event: self.reset_source())
        row = tk.Frame(card, bg=T['surface'])
        row.pack(side='right')
        for title, fn, primary in [('Load albums', self.load, True), ('Find phones', self.find_phones, False), ('Wi-Fi…', self.app.open_wireless, False), ('Local folder', self.add_source, False)]:
            self.control(row, title, fn, primary).pack(side='left', padx=(0, T['space_sm']))

    def build_browser(self):
        a = self.app
        self.stats = tk.StringVar(value='Connect a phone or choose a folder, then load your albums.')
        stats = a.label(self, '', muted=True)
        stats.configure(textvariable=self.stats)
        stats.pack(anchor='w', pady=(0, T['space_sm']))
        filters = tk.Frame(self, bg=T['bg'])
        filters.pack(fill='x', pady=(0, T['space_sm']))
        self.search = tk.StringVar()
        search = tk.Entry(filters, textvariable=self.search, bg=T['raised'], fg=T['text'], insertbackground=T['accent'], relief='flat', width=22)
        search.pack(side='left', fill='x', expand=True, ipady=T['space_sm'])
        search.insert(0, '')
        a.active_controls.append((search, 'normal'))
        self.search.trace_add('write', lambda *args: self.changed_filter())
        self.kind = tk.StringVar(value='Photos & videos')
        kind = ttk.Combobox(filters, textvariable=self.kind, values=['Photos & videos', 'Photos only', 'Videos only'], state='readonly', width=18)
        kind.pack(side='left', padx=(T['space_sm'], 0))
        kind.bind('<<ComboboxSelected>>', lambda event: self.changed_filter())
        a.active_controls.append((kind, 'readonly'))
        a.label(self, 'Click to preview · Ctrl+click to pick files · Shift+click for a range', muted=True, size=9).pack(anchor='w', pady=(0, T['space_sm']))
        split = tk.Frame(self, bg=T['bg'])
        split.pack(fill='both', expand=True)
        split.grid_columnconfigure(1, weight=1)
        split.grid_rowconfigure(0, weight=1)
        self.album_panel = tk.Frame(split, bg=T['surface'], padx=20, pady=24)
        self.album_panel.grid(row=0, column=0, sticky='ns', padx=(0, T['space_md']))
        a.label(self.album_panel, 'Your albums', size=9, color=T['accent'], bold=True).pack(anchor='w', padx=T['space_sm'])
        self.album_list = tk.Listbox(self.album_panel, bg=T['surface'], fg=T['text'], selectbackground=T['raised'], selectforeground=T['accent'], relief='flat', borderwidth=8, highlightthickness=0, width=22, height=5, font=(T['font'], 11), selectborderwidth=3, exportselection=False, activestyle='none')
        self.album_list.pack(fill='both', expand=True, pady=T['space_sm'])
        self.album_list.bind('<<ListboxSelect>>', self.choose_album)
        a.active_controls.append((self.album_list, 'normal'))
        self.control(self.album_panel, 'Select this album', self.select_album).pack(side='bottom', before=self.album_list, fill='x', pady=T['space_sm'])
        self.grid_area = tk.Frame(split, bg=T['bg'])
        self.grid_area.grid(row=0, column=1, sticky='nsew')
        viewport = tk.Frame(self.grid_area, bg=T['bg'])
        viewport.pack(fill='both', expand=True)
        self.thumb_canvas = tk.Canvas(viewport, bg=T['bg'], highlightthickness=0)
        self.thumb_canvas.pack(side='left', fill='both', expand=True)
        bar = ttk.Scrollbar(viewport, orient='vertical', command=self.thumb_canvas.yview)
        bar.pack(side='right', fill='y')
        self.scrollbar = bar
        self.thumb_canvas.configure(yscrollcommand=self.scrolled, yscrollincrement=36)
        self.tiles = tk.Frame(self.thumb_canvas, bg=T['bg'])
        self.tile_window = self.thumb_canvas.create_window((0, 0), window=self.tiles, anchor='nw')
        self.thumb_canvas.bind('<Configure>', self.layout_tiles)
        destination = tk.Frame(self, bg=T['surface'], padx=T['space_sm'], pady=T['space_sm'])
        destination.pack(side='bottom', fill='x', pady=(T['space_sm'], 0), before=split)
        self.destination = destination
        self.selection_text = tk.StringVar(value='0 items selected')
        selected = a.label(destination, '', bold=True)
        selected.configure(textvariable=self.selection_text)
        selected.pack(anchor='w', pady=(0, 4))
        self.target_var = tk.StringVar()
        self.target_combo = ttk.Combobox(destination, textvariable=self.target_var, state='readonly', values=[e.label for e in a.endpoints])
        self.target_combo.pack(side='left', fill='x', expand=True, padx=(0, 8))
        a.active_controls.append((self.target_combo, 'readonly'))
        actions = tk.Frame(destination, bg=T['surface'])
        actions.pack(side='right')
        self.control(actions, 'Save to…', self.add_target).pack(side='left', padx=(0, T['space_sm']))
        self.control(actions, 'Clear', self.clear_selection).pack(side='left')
        self.control(actions, 'Delete', self.delete_selected).pack(side='left', padx=8)
        self.control(actions, 'Transfer →', self.send, True).pack(side='right')
        self.render()

    def reset_source(self):
        self.media_cancel.set()
        self.media_cancel = threading.Event()
        self.preview_stop.set()
        if self.preview and self.preview.winfo_exists():
            self.preview.destroy()
        self.preview = None
        self.preview_local = None
        self.generation += 1
        self.photos.clear()
        for card, _, _ in self.cards.values():
            card.destroy()
        self.cards.clear()
        self.items = []
        self.chosen.clear()
        self.selection_anchor = None
        self.source = None
        self.index_ready = False
        self.scan_token = None
        self.album = None
        self.album_list.delete(0, 'end')
        self.stats.set('Source changed. Load albums to browse this device.')
        self.render()

    def find_phones(self):
        if not self.app.adb:
            messagebox.showinfo('Connect your phone', 'Configure adb.exe in Connection help first.', parent=self)
            return
        def done(result):
            phones, blocked = result
            self.app.endpoints = retain_companions(self.app.endpoints, phones)
            phones = [e for e in self.app.endpoints if isinstance(e, Android)]
            self.refresh_choices()
            if phones:
                self.source_var.set(phones[0].label)
                self.reset_source()
                self.stats.set('Phone ready. Click Load albums.')
            else:
                self.reset_source()
                self.source_var.set('')
                self.stats.set('No authorized phone. Unlock it and approve USB debugging, then find phones again.' if blocked else 'No phone found. Check USB debugging or use Wi-Fi… to pair/connect.')
        self.app.run('Find phones', lambda report: discover(self.app.adb), done, record=False)

    def refresh_choices(self):
        values = [e.label for e in self.app.endpoints]
        self.source_combo.configure(values=values)
        self.target_combo.configure(values=values)

    def folder(self):
        chosen = filedialog.askdirectory(title='Choose a media folder or transfer destination', parent=self)
        if not chosen:
            return None
        endpoint = Folder(chosen)
        if not any(e.key == endpoint.key for e in self.app.endpoints):
            self.app.endpoints.append(endpoint)
        self.app.persist()
        self.refresh_choices()
        return endpoint

    def add_source(self):
        endpoint = self.folder()
        if endpoint:
            self.source_var.set(endpoint.label)
            self.reset_source()
            self.load()

    def add_target(self):
        endpoint = self.folder()
        if endpoint:
            self.target_var.set(endpoint.label)

    def load(self):
        if self.app.busy:
            return
        source = self.app.endpoint(self.source_var)
        self.reset_source()
        if source is None:
            self.stats.set('Choose a source first, or click Find phones.')
            return
        self.media_cancel.set()
        self.media_cancel = threading.Event()
        self.generation += 1
        self.source = source
        self.index_ready = False
        self.items = []
        self.album_list.delete(0, 'end')
        self.album = None
        self.search.set('')
        self.kind.set('Photos & videos')
        self.chosen.clear()
        self.stats.set('Scanning media folders…')
        self.scan_token = object()
        token = self.scan_token
        def read(report):
            if isinstance(source, Android) and not phone_online(source, self.app.cancel,runner=adb_run):
                raise OSError('Phone is disconnected. Reconnect it before loading media.')
            return scan_media(source, self.app.cancel, report, lambda items: self.app.events.put(('media_batch', self, token, items)))
        def done(items):
            if self.scan_token is token and self.source is source:
                self.loaded(items)
        self.app.run('Read media albums', read, done, record=False)

    def update_scan_batch(self, token, items):
        if token is self.scan_token and self.alive:
            self.loaded(items, scanning=True)

    def loaded(self, items, scanning=False):
        if self.source is None or not self.alive:
            return
        self.index_ready = not scanning
        previous_albums = getattr(self, 'albums', [])
        previous_album = self.album
        sidebar_top = self.album_list.yview()[0]
        self.items = items
        self.albums = list(album_counts(items))
        if self.album not in self.albums:
            if previous_album in previous_albums and self.albums:
                # Prefer the next surviving album; at the end use the preceding one.
                index = previous_albums.index(previous_album)
                following = [name for name in previous_albums[index+1:] if name in self.albums]
                preceding = [name for name in previous_albums[:index] if name in self.albums]
                self.album = (following or preceding[-1:] or self.albums)[0]
            else:
                self.album = None
        self.album_list.delete(0, 'end')
        self.album_list.insert('end', f'All media   ·   {len(items):,}')
        counts = album_counts(items)
        for album in self.albums:
            self.album_list.insert('end', f'{PurePosixPath(album).name}   ·   {counts[album]:,}')
        selected_index = self.albums.index(self.album) + 1 if self.album else 0
        self.album_list.selection_set(selected_index)
        self.album_list.activate(selected_index)
        self.album_list.yview_moveto(sidebar_top)
        if previous_album != self.album:
            self.album_list.see(selected_index)
        summary = f'{len(items):,} photos & videos   ·   {len(self.albums)} albums'
        warnings = getattr(self.source, 'scan_warnings', [])
        if scanning:
            summary += ' · Still scanning…'
        elif warnings:
            summary += ' · ' + ' / '.join(warnings)
        elif not items:
            summary = 'No accessible photos or videos found in this source. Check the selected phone or folder.'
        self.stats.set(summary)
        self.render(reset=False)

    def choose_album(self, event=None):
        selection = self.album_list.curselection()
        if not selection:
            return
        index = selection[0]
        album = None if index == 0 else self.albums[index - 1]
        if album != self.album:
            self.album = album
            self.render()

    def filtered(self):
        query = self.search.get().strip().casefold()
        kind = self.kind.get()
        return [item for item in self.items if (self.album is None or item['album'] == self.album)
                and (not query or query in item['path'].casefold())
                and (kind == 'Photos & videos' or (kind == 'Photos only' and item['kind'] == 'Photos') or (kind == 'Videos only' and item['kind'] == 'Videos'))]

    def changed_filter(self):
        self.render()

    def render(self, reset=True):
        self.view_items = self.filtered()
        if reset:
            self.selection_anchor = None
            self.thumb_canvas.yview_moveto(0)
        self.visible_range = None
        self.paint_visible()

    def scrolled(self, first, last):
        self.scrollbar.set(first, last)
        if hasattr(self, 'view_items'):
            self.after_idle(self.paint_visible)

    def paint_visible(self):
        if not self.alive or not self.winfo_exists():
            return
        columns = max(1, self.thumb_canvas.winfo_width() // 140)
        items = self.view_items
        total_height = max(1, ((len(items) + columns - 1) // columns) * 166)
        extent = (self.thumb_canvas.winfo_width(), total_height)
        if getattr(self, 'extent', None) != extent:
            self.extent = extent
            self.thumb_canvas.configure(scrollregion=(0, 0, extent[0], total_height))
        first_row = max(0, int(self.thumb_canvas.canvasy(0)) // 166 - 1)
        start = first_row * columns
        end = min(len(items), (first_row + self.thumb_canvas.winfo_height() // 166 + 4) * columns)
        signature = (start, end, columns)
        if getattr(self, 'visible_range', None) == signature:
            return
        self.visible_range = signature
        self.thumb_canvas.coords(self.tile_window, 0, first_row * 166)
        self.thumb_canvas.itemconfigure(self.tile_window, height=max(166, ((end - start + columns - 1) // columns) * 166))
        generation = self.generation
        visible = items[start:end]
        names = {item['path'] for item in visible}
        for name in list(self.cards):
            if name not in names:
                self.cards.pop(name)[0].destroy()
        for widget in self.tiles.winfo_children():
            if not isinstance(widget, tk.Frame):
                widget.destroy()
        self.app.active_controls = [(w, state) for w, state in self.app.active_controls if w.winfo_exists()]
        if not visible:
            text = 'No matching media.' if self.items else ('No photos or videos found in this source.' if self.index_ready else 'Your albums will appear here.')
            self.app.label(self.tiles, text, muted=True, size=14).place(x=20, y=24)
        for index, item in enumerate(visible):
            name = item['path']
            x, y = ((start + index) % columns) * 140 + 4, (index // columns) * 166 + 4
            if name in self.cards:
                card, thumb, selected = self.cards[name]
                card.place_configure(x=x, y=y)
                selected.set(name in self.chosen)
                continue
            card = tk.Frame(self.tiles, bg=T['surface'], width=132, height=158)
            card.pack_propagate(False)
            card.place(x=((start + index) % columns) * 140 + 4, y=(index // columns) * 166 + 4, width=132, height=158)
            thumb = tk.Button(card, text='VIDEO' if item['kind'] == 'Videos' else 'Loading...', command=lambda i=item: self.open_preview(i), bg=T['raised'], fg=T['accent'], activebackground=T['surface'], relief='flat', cursor='hand2', takefocus=True, highlightthickness=1, highlightcolor=T['accent'], borderwidth=0)
            thumb.place(x=0, y=0, width=132, height=132)
            self.app.active_controls.append((thumb, 'normal'))
            label = tk.Label(card, text=PurePosixPath(name).name, font=(T['font'], 9), bg=T['surface'], fg=T['text'], anchor='w')
            label.place(x=5, y=134, width=122, height=22)
            selected = tk.BooleanVar(value=name in self.chosen)
            checkbox = ttk.Checkbutton(card, variable=selected, command=lambda n=name, v=selected: self.toggle(n, v))
            checkbox.place(relx=1, x=-4, y=4, anchor='ne')
            checkbox.bind('<Button-1>',lambda event,n=name,v=selected:self.select_media_click(n,event,v))
            checkbox.bind('<ButtonRelease-1>',lambda event:'break')
            # Modifier clicks on the tile also select, without opening its preview.
            for target in (card,thumb,label):
                for modifier in ('Control','Shift'):
                    target.bind(f'<{modifier}-Button-1>',lambda event,n=name,v=selected:self.select_media_click(n,event,v))
                    target.bind(f'<{modifier}-ButtonRelease-1>',lambda event:'break')
            self.app.active_controls.append((checkbox, 'normal'))
            if self.app.busy:
                thumb.configure(state='disabled')
                checkbox.configure(state='disabled')
            self.cards[name] = (card, thumb, selected)
            if name in self.photos:
                thumb.configure(image=self.photos[name], text='')
                thumb.image = self.photos[name]
                self.photos.move_to_end(name)
            elif self.source:
                row_y = ((start + index) // columns) * 166
                top = self.thumb_canvas.canvasy(0)
                priority = 10 if top <= row_y + 166 and row_y < top + self.thumb_canvas.winfo_height() else 20
                self.enqueue(priority, ('thumb', generation, item, thumb))
        self.selection_text.set(f'{len(self.chosen):,} items selected' + (f'  ·  {self.album}' if self.album else ''))

    def layout_tiles(self, event):
        self.thumb_canvas.itemconfigure(self.tile_window, width=event.width)
        self.visible_range = None
        self.paint_visible()

    def scroll_media(self, event):
        x, y = self.winfo_pointerxy()
        canvas = self.thumb_canvas
        if canvas.winfo_rootx() <= x <= canvas.winfo_rootx() + canvas.winfo_width() and canvas.winfo_rooty() <= y <= canvas.winfo_rooty() + canvas.winfo_height():
            canvas.yview_scroll(-int(event.delta / 120), 'units')

    def reveal_focus(self, widget):
        if str(widget).startswith(str(self.tiles) + '.'):
            top = widget.winfo_rooty() - self.tiles.winfo_rooty() + self.thumb_canvas.coords(self.tile_window)[1]
            visible = self.thumb_canvas.canvasy(0)
            height = self.thumb_canvas.winfo_height()
            if top < visible or top + widget.winfo_height() > visible + height:
                self.thumb_canvas.yview_moveto(max(0, top - height / 2) / max(1, self.extent[1]))

    def sync_media_selection(self):
        for name,(_,_,selected) in self.cards.items():
            selected.set(name in self.chosen)
        if self.preview and self.preview.winfo_exists():
            self.preview_chosen.set(self.preview_item['path'] in self.chosen)
        self.selection_text.set(f'{len(self.chosen):,} items selected' + (f'  ·  {self.album}' if self.album else ''))

    def select_media_click(self,name,event,variable):
        if self.app.busy:return 'break'
        if event.state & 0x0001:
            # Use the entire filtered order, including tiles not currently rendered.
            names = [row['path'] for row in self.view_items]
            if name not in names:return 'break'
            anchor = self.selection_anchor
            if anchor not in names:
                self.selection_anchor = anchor = name
            first,last = sorted((names.index(anchor),names.index(name)))
            self.chosen.update(names[first:last+1])
        else:
            # Normal checkbox and Ctrl clicks are additive individual toggles.
            if name in self.chosen:self.chosen.remove(name)
            else:self.chosen.add(name)
            self.selection_anchor = name
        variable.set(name in self.chosen)
        self.sync_media_selection()
        return 'break'

    def toggle(self, name, variable):
        if variable.get():
            self.chosen.add(name)
        else:
            self.chosen.discard(name)
        self.selection_anchor = name
        self.sync_media_selection()

    def select_album(self):
        if not self.items:
            return
        # Entire album; search/type filters do not hide selections.
        self.chosen.update(i['path'] for i in self.items if self.album is None or i['album'] == self.album)
        self.render(reset=False)

    def clear_selection(self):
        self.selection_anchor = None
        self.chosen.clear()
        self.render(reset=False)

    def send(self):
        if self.app.busy:
            return
        source = self.source
        target = self.app.endpoint(self.target_var)
        if source is None or not self.chosen or target is None:
            messagebox.showinfo('Choose what to send', 'Select media and a destination first.', parent=self)
            return
        chosen = set(self.chosen)
        def completed(result):
            failures=result.get('errors',[])
            if failures:
                details='\n\n'.join(f"{row['path']}: {row['error']}" for row in failures[:6])
                if len(failures)>6:details+=f'\n\n…and {len(failures)-6} more. Save the detailed report from Activity for the full list.'
                messagebox.showwarning('Some selected media were not exported',f"{result['copied']} copied · {result['present']} already present · {result['failed']} failed, out of {result.get('requested',len(chosen))} selected.\n\n"+details,parent=self)
        self.app.run('Selected media transfer', lambda report: transfer(source, target, MEDIA_TYPES, self.app.cancel, report, paths=chosen,flatten=isinstance(target,Folder)),completed)

    def delete_selected(self):
        if self.app.busy:
            return
        source = self.source
        if not isinstance(source, Android) or not self.chosen:
            messagebox.showinfo('Select phone media', 'Load a connected phone and select the photos or videos to delete.', parent=self)
            return
        names = sorted(self.chosen)
        details = '\n'.join(names[:8]) + ('\n…' if len(names) > 8 else '')
        if not messagebox.askyesno('Delete phone media?', f'Permanently delete {len(names)} selected photos/videos from this phone?\n\n{details}\n\nThis does not go to a recycle bin. Existing PC backups are retained.', parent=self):
            return
        from .delete_actions import delete_media
        def done(results):
            removed = {name for name, success, _ in results if success}
            self.items = [item for item in self.items if item['path'] not in removed]
            self.chosen.difference_update(removed)
            for name in removed:
                self.photos.pop(name, None)
            self.loaded(self.items)
            self.stats.set(f'{len(removed)} media files deleted · {len(results)-len(removed)} failed')
            if len(removed) != len(results):
                failed=[f'{name}: {detail}' for name,success,detail in results if not success]
                details='\n\n'.join(failed[:6])
                if len(failed)>6:details+=f'\n\n…and {len(failed)-6} more failures. Failed items remain selected.'
                messagebox.showwarning('Some files were not deleted',details,parent=self)
        self.app.run('Delete selected phone media', lambda report: delete_media(source, names, self.app.cancel, report), done, record=False)

    def enqueue(self, priority, task):
        self.sequence += 1
        self.jobs.put((priority, self.sequence, self.source, task, self.preview_stop if task[0] == 'preview' else self.media_cancel))

    def watch_connection(self):
        while not self.stop.wait(1):
            source = self.source
            if not isinstance(source, Android):
                continue
            try:
                online = phone_online(source, self.stop,runner=adb_run)
            except (OSError, TimeoutError, Cancelled):
                online = False
            if not online and not self.stop.is_set():
                self.results.put(('disconnected', source, None, None, None, None, None))

    def disconnected(self, source):
        if self.source is not source:
            return
        if self.app.busy:
            self.app.cancel.set()
        reason=source.link.disconnect_reason() if getattr(source,'kind','')=='companion' else 'Android debugging connection is unavailable.'
        self.reset_source()
        previous_cache = self.session_cache
        self.session_cache = Path(tempfile.mkdtemp(prefix='twist-media-'))
        self.cache = MediaCache(self.session_cache)
        threading.Thread(target=self.clean_cache, args=(previous_cache,), daemon=True).start()
        self.app.endpoints = [e for e in self.app.endpoints if e is not source]
        self.refresh_choices()
        self.source_var.set('')
        self.target_var.set('')
        self.stats.set('Phone disconnected. Media hidden. '+reason+' Reconnect and load albums again.')
        self.app.status.set('Phone disconnected. '+reason)

    @staticmethod
    def clean_cache(folder):
        import time
        for _ in range(10):
            shutil.rmtree(folder, ignore_errors=True)
            if not folder.exists():
                break
            time.sleep(.5)

    def worker(self):
        while not self.stop.is_set():
            try:
                _, _, source, task, cancel = self.jobs.get(timeout=.2)
            except queue.Empty:
                continue
            kind, generation, item, widget = task
            # Pause thumbnail work during transfers instead of losing queued jobs.
            while self.app.busy and getattr(self.app,'current_task','')!='Read media albums' and not self.stop.is_set() and not cancel.is_set():
                if kind=='thumb' and generation!=self.generation:break
                self.stop.wait(.1)
            if self.stop.is_set() or cancel.is_set() or (kind == 'thumb' and generation != self.generation):
                continue
            try:
                size = (132, 132) if kind == 'thumb' else ((2560,2560) if item['kind']=='Photos' else (1280,720))
                picture, local = self.cache.image(source, item['path'], cancel, size=size, thumbnail=kind == 'thumb', pad=False)
                self.results.put((kind, generation, item, widget, picture, local, None))
            except Exception as exc:
                if not self.stop.is_set():
                    self.results.put((kind, generation, item, widget, None, None, str(exc)))

    def open_preview(self, item):
        if self.app.busy:
            return
        if self.preview and self.preview.winfo_exists():
            self.close_preview()
        self.preview_items = list(self.filtered())
        self.preview_index = next((index for index,row in enumerate(self.preview_items) if row['path']==item['path']), -1)
        if self.preview_index < 0:
            self.preview_items = [item]; self.preview_index = 0
        dialog = tk.Toplevel(self)
        self.preview = dialog
        dialog.configure(bg=T['bg'])
        width = min(1280, max(700, dialog.winfo_screenwidth()-80))
        height = min(940, max(580, dialog.winfo_screenheight()-100))
        dialog.geometry(f'{width}x{height}')
        dialog.minsize(min(700,width), min(580,height))
        dialog.protocol('WM_DELETE_WINDOW', self.close_preview)
        self.preview_title = self.app.label(dialog, '', bold=True, size=16)
        self.preview_title.pack(anchor='w', padx=T['space_lg'], pady=T['space_md'])
        self.preview_album = self.app.label(dialog, '', muted=True, size=9)
        self.preview_album.pack(anchor='w', padx=T['space_lg'])
        area = tk.Frame(dialog,bg=T['bg'])
        area.pack(fill='both',expand=True,padx=T['space_md'],pady=T['space_md'])
        self.previous_button = self.app.button(area, '‹ Previous', lambda:self.navigate_preview(-1))
        self.previous_button.pack(side='left',padx=(0,8))
        self.next_button = self.app.button(area, 'Next ›', lambda:self.navigate_preview(1))
        self.next_button.pack(side='right',padx=(8,0))
        self.preview_image = PreviewCanvas(area)
        self.preview_image.pack(side='left',fill='both',expand=True)
        self.preview_timeline = timeline = tk.Frame(dialog,bg=T['bg'])
        self.video_time = tk.StringVar(value='0:00 / 0:00')
        self.seek_bar = tk.Scale(timeline, from_=0, to=1, resolution=.05,
            orient='horizontal', showvalue=False, bg=T['bg'], fg=T['text'],
            troughcolor=T['raised'], activebackground=T['accent'], highlightthickness=0,
            sliderlength=14, command=self.scrub_label, state='disabled')
        self.seek_bar.pack(side='left',fill='x',expand=True)
        time_label = self.app.label(timeline,'',muted=True,size=9)
        time_label.configure(textvariable=self.video_time); time_label.pack(side='right')
        self.seek_bar.bind('<ButtonPress-1>',self.begin_scrub)
        self.seek_bar.bind('<B1-Motion>',self.move_scrub)
        self.seek_bar.bind('<ButtonRelease-1>',self.end_scrub)
        self.seek_bar.bind('<KeyPress>',self.begin_key_scrub)
        self.seek_bar.bind('<KeyRelease>',self.end_key_scrub)
        self.preview_controls = controls = tk.Frame(dialog,bg=T['bg'])
        controls.pack(fill='x',padx=T['space_lg'],pady=T['space_md'])
        self.preview_chosen = tk.BooleanVar()
        check = ttk.Checkbutton(controls,text='Include in transfer',variable=self.preview_chosen,
            command=lambda:self.preview_toggle(self.preview_item))
        check.pack(side='left')
        self.play_button = self.app.button(controls,'Fit photo',self.play_preview,primary=True)
        self.play_button.pack(side='right')
        self.copy_button = self.app.button(controls,'Copy image',self.copy_preview_image)
        self.copy_button.pack(side='right',padx=(0,8))
        self.copy_button.configure(state='disabled')
        self.app.button(dialog,'Open in Windows app (video sound / full resolution)',self.open_external).pack(anchor='w',padx=T['space_lg'])
        self.preview_status = tk.StringVar()
        status = self.app.label(dialog,'',muted=True,size=9)
        status.configure(textvariable=self.preview_status); status.pack(anchor='w',padx=T['space_lg'],pady=T['space_sm'])
        def bind_keys(widget):
            # Bind before widget class handlers, including buttons and the timeline.
            widget.bind('<KeyPress-Left>',lambda event:self.navigate_preview(-1))
            widget.bind('<KeyPress-Right>',lambda event:self.navigate_preview(1))
            widget.bind('<Control-c>',lambda event:self.copy_preview_image())
            widget.bind('<Control-C>',lambda event:self.copy_preview_image())
            widget.bind('<KeyPress-space>',self.space_preview)
            widget.bind('<KeyRelease-space>',lambda event:'break')
            for child in widget.winfo_children():bind_keys(child)
        bind_keys(dialog)
        self.show_preview_item()
        self.preview_image.focus_set()

    def navigate_preview(self,step):
        if self.app.busy or not self.preview or not self.preview.winfo_exists():return 'break'
        index = self.preview_index + step
        if 0 <= index < len(self.preview_items):
            self.preview_index = index
            self.show_preview_item()
        return 'break'

    def show_preview_item(self):
        self.preview_stop.set()
        self.preview_stop = threading.Event()
        self.preview_token = object()
        item = self.preview_items[self.preview_index]
        self.preview_item = item; self.preview_local = None
        self.playing = False; self.scrubbing = False
        self.video_position = 0.; self.video_duration = 0.
        self.preview.title(PurePosixPath(item['path']).name+' · Twist MediaBridge preview')
        self.preview_title.configure(text=PurePosixPath(item['path']).name)
        self.preview_album.configure(text=f"{item['album']}  ·  {self.preview_index+1:,} / {len(self.preview_items):,}")
        self.previous_button.configure(state='normal' if self.preview_index>0 else 'disabled')
        self.next_button.configure(state='normal' if self.preview_index<len(self.preview_items)-1 else 'disabled')
        self.preview_chosen.set(item['path'] in self.chosen)
        self.preview_image.show_message('Loading preview locally…')
        self.play_button.configure(text='Play / pause preview' if item['kind']=='Videos' else 'Fit photo',state='disabled')
        self.seek_bar.configure(state='disabled',to=1); self.seek_bar.set(0)
        self.video_time.set('0:00 / 0:00')
        if item['kind']=='Videos':
            self.preview_timeline.pack(fill='x',padx=T['space_lg'],before=self.preview_controls)
        else:self.preview_timeline.pack_forget()
        self.copy_button.configure(state='disabled',text='Copy image')
        self.preview_status.set('Loading preview locally…')
        self.enqueue(0,('preview',self.preview_token,item,self.preview_image))

    def copy_preview_image(self):
        if not self.preview_local or self.preview_item['kind']!='Photos' or self.copy_button.cget('state')=='disabled':
            return 'break'
        token,local,widget = self.preview_token,self.preview_local,self.preview_image
        self.copy_button.configure(state='disabled',text='Copying…')
        self.preview_status.set('Preparing image for the clipboard…')
        def worker():
            try:
                payloads = image_payloads(local)
                self.results.put(('copy_image',token,None,widget,payloads,None,None))
            except Exception as exc:
                self.results.put(('copy_image',token,None,widget,None,None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        return 'break'

    def preview_toggle(self, item):
        self.toggle(item['path'], self.preview_chosen)
        # Refresh checkboxes when the preview closes; avoid repeating thumbnail work now.

    def play_preview(self):
        if not self.preview_local:
            return
        if self.preview_item['kind'] != 'Videos':
            self.preview_image.fit()
            return
        if self.scrubbing:return
        if getattr(self, 'playing', False):
            self.preview_stop.set()
            self.playing = False
            return
        if self.video_duration and self.video_position >= self.video_duration - .15:
            self.video_position = 0.
        self.start_video(self.video_position)

    def space_preview(self, event=None):
        self.play_preview()
        return 'break'

    def scrub_label(self, value):
        def stamp(seconds):
            seconds = max(0, int(float(seconds)))
            return f'{seconds//60}:{seconds%60:02d}'
        self.video_time.set(f'{stamp(value)} / {stamp(self.video_duration)}')

    def scrub_value(self, event):
        # Scale.coords gives handle centres at both limits, including theme insets.
        left = self.seek_bar.coords(0)[0]
        right = self.seek_bar.coords(self.video_duration)[0]
        return max(0., min(self.video_duration, (event.x-left) / max(1, right-left) * self.video_duration))

    def begin_scrub(self, event):
        if not self.video_duration:return 'break'
        self.resume_after_scrub = self.playing
        self.scrubbing = True
        self.preview_stop.set(); self.playing = False
        self.seek_bar.focus_set()
        self.seek_bar.set(self.scrub_value(event))
        return 'break'

    def move_scrub(self, event):
        if self.scrubbing:self.seek_bar.set(self.scrub_value(event))
        return 'break'

    def end_scrub(self, event):
        if self.scrubbing:
            self.seek_bar.set(self.scrub_value(event)); self.finish_scrub()
        return 'break'

    def begin_key_scrub(self, event):
        if event.keysym in ('Left', 'Right', 'Home', 'End', 'Prior', 'Next') and self.video_duration:
            if not self.scrubbing:
                self.resume_after_scrub = self.playing; self.scrubbing = True
                self.preview_stop.set(); self.playing = False

    def end_key_scrub(self, event):
        if event.keysym in ('Left', 'Right', 'Home', 'End', 'Prior', 'Next') and self.scrubbing:
            self.finish_scrub()

    def finish_scrub(self):
        self.scrubbing = False
        self.video_position = min(self.seek_bar.get(), max(0., self.video_duration-.1))
        self.start_video(self.video_position, single=not self.resume_after_scrub)

    def start_video(self, start, single=False):
        self.preview_stop.set()
        self.preview_stop = threading.Event()
        self.playing = not single
        stop, image_widget, local = self.preview_stop, self.preview_image, self.preview_local
        def worker():
            current = start
            try:
                def position(value):
                    nonlocal current
                    current = value
                def emit(frame):
                    if self.results.qsize() < 3:
                        self.results.put(('frame', stop, None, image_widget, frame, current, None))
                play_frames(local, stop, emit, start=start, position=position, single=single)
            except Exception as exc:
                self.results.put(('play_error', stop, None, image_widget, None, None, str(exc)))
            finally:
                self.results.put(('play_end', stop, None, image_widget, None, None, None))
        threading.Thread(target=worker, daemon=True).start()

    def probe_video(self, local, widget):
        token = self.preview_token
        def worker():
            try:
                seconds = video_duration(local)
                self.results.put(('video_info', token, None, widget, None, seconds, None))
            except Exception as exc:
                self.results.put(('video_info', token, None, widget, None, 0., str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def open_external(self):
        if self.preview_local and Path(self.preview_local).exists():
            try:
                os.startfile(self.preview_local)
            except OSError as exc:
                messagebox.showerror('Cannot open media', str(exc), parent=self.preview)

    def close_preview(self):
        self.preview_stop.set()
        self.playing = False
        if self.preview:
            self.preview.destroy()
        self.preview = None
        self.preview_token = None
        self.preview_local = None
        self.preview_items = []
        self.render(reset=False)

    def poll(self):
        if not self.alive:
            return
        try:
            while True:
                kind, generation, item, widget, picture, local, error = self.results.get_nowait()
                if kind == 'disconnected':
                    self.disconnected(generation)
                    continue
                if kind == 'thumb' and generation != self.generation:
                    continue
                if kind in ('preview','video_info','copy_image') and generation is not getattr(self,'preview_token',None):
                    continue
                cached_photo = None
                if kind == 'thumb' and picture is not None:
                    cached_photo = ImageTk.PhotoImage(picture)
                    self.photos[item['path']] = cached_photo
                    self.photos.move_to_end(item['path'])
                    while len(self.photos) > 512:
                        self.photos.popitem(last=False)
                if not widget.winfo_exists():
                    continue
                if kind in ('frame', 'play_error', 'play_end') and generation is not self.preview_stop:
                    continue
                if kind == 'copy_image':
                    self.copy_button.configure(state='normal',text='Copy image')
                    try:
                        if error:raise OSError(error)
                        put_image_on_clipboard(picture,int(self.preview.winfo_id()))
                        self.preview_status.set('Image copied. Press Ctrl+V in WhatsApp or another app to paste.')
                    except OSError as exc:
                        self.preview_status.set('Image could not be copied. Please try again.')
                        messagebox.showerror('Cannot copy image',str(exc),parent=self.preview)
                elif kind == 'video_info':
                    self.video_duration = local
                    self.seek_bar.configure(to=max(.1,local), state='normal' if local else 'disabled')
                    self.scrub_label(self.video_position)
                    if error:self.preview_status.set('Timeline unavailable; Open in Windows app is available.')
                elif kind == 'play_end':
                    self.playing = False
                elif kind == 'play_error':
                    self.preview_status.set(error)
                elif picture is not None:
                    if kind == 'frame' and local is not None:
                        self.video_position = local
                        if not self.scrubbing:
                            self.seek_bar.set(local); self.scrub_label(local)
                    if kind in ('preview', 'frame'):
                        widget.set_picture(picture)
                    else:
                        photo = cached_photo or ImageTk.PhotoImage(picture)
                        widget.configure(image=photo, text='', height=0)
                        widget.image = photo
                    if kind == 'preview':
                        self.preview_local = local
                        if item['kind'] == 'Videos':self.probe_video(local, widget)
                        self.play_button.configure(state='normal')
                        self.copy_button.configure(state='normal' if item['kind']=='Photos' else 'disabled')
                        self.preview_status.set(f"{item['kind']} · Preview ready" + (' · Muted playback' if item['kind'] == 'Videos' else ''))
                elif error:
                    if kind == 'thumb':
                        widget.configure(text='▶  Click for video preview' if item['kind'] == 'Videos' else 'Click to preview', height=5)
                    else:
                        widget.show_message('Preview unavailable\n' + error)
                        self.preview_status.set('The file may still be transferred even if a preview is unavailable.')
        except queue.Empty:
            pass
        self.after(80, self.poll)

    def destroyed(self, event):
        if event.widget == self:
            self.alive = False
            self.stop.set()
            self.media_cancel.set()
            self.preview_stop.set()
            # Delayed cleanup lets cancelled ADB/FFmpeg operations release files.
            threading.Thread(target=self.clean_cache, args=(self.session_cache,), daemon=True).start()
