import tkinter as tk
from tkinter import ttk, messagebox
from .duplicates import find_duplicates, validate_removals
from .theme import TOKENS as T


def show_review(panel):
    if panel.app.busy:
        return
    if not panel.rows:
        panel.summary.set('Load contacts before finding duplicates.')
        return
    if getattr(panel, 'duplicate_window', None) and panel.duplicate_window.winfo_exists():
        panel.duplicate_window.lift()
        return
    groups = find_duplicates(panel.rows)
    if not groups:
        messagebox.showinfo('Duplicate contacts', 'No shared full phone numbers or matching names were found.', parent=panel)
        return
    dialog = tk.Toplevel(panel)
    panel.duplicate_window = dialog
    dialog.title('Review possible duplicate contacts · Twist MediaBridge')
    dialog.configure(bg=T['bg'])
    dialog.geometry('1000x650')
    dialog.minsize(820,560)
    dialog.transient(panel.app)
    dialog.grab_set()
    dialog.bind('<Escape>',lambda event:dialog.destroy())
    pad = T['space_md']
    panel.app.label(dialog,'Review possible duplicates',size=20,bold=True).pack(anchor='w',padx=pad,pady=pad)
    panel.app.label(dialog,'A shared number can belong to different people. Name-only matches are suggestions. All contacts start as Keep.',muted=True,size=10).pack(fill='x',padx=pad,pady=(0,pad))
    removed = set()
    body = tk.Frame(dialog,bg=T['bg'])
    body.pack(fill='both',expand=True,padx=pad)
    left = tk.Frame(body,bg=T['surface'])
    left.pack(side='left',fill='y',padx=(0,pad))
    listing = tk.Listbox(left,width=29,bg=T['list_bg'],fg=T['text'],selectbackground=T['list_selected'],selectforeground=T['text'],exportselection=False,relief='flat')
    listing.pack(side='left',fill='both',expand=True)
    bar = ttk.Scrollbar(left,command=listing.yview)
    bar.pack(side='right',fill='y')
    listing.configure(yscrollcommand=bar.set)
    for group in groups:
        listing.insert('end',f"{group['match']} · {len(group['rows'])} contacts")
    right=tk.Frame(body,bg=T['bg'])
    right.pack(fill='both',expand=True)
    reason=tk.StringVar()
    label=panel.app.label(right,'',color=T['accent'],bold=True,size=10)
    label.configure(textvariable=reason)
    label.pack(fill='x',pady=(0,T['space_sm']))
    area=tk.Frame(right,bg=T['surface'])
    area.pack(fill='both',expand=True)
    tree=ttk.Treeview(area,columns=('action','name','numbers'),show='headings',style='Phone.Treeview',selectmode='browse')
    for col,text,width in [('action','Click to change',125),('name','Contact',200),('numbers','Phone numbers',230)]:
        tree.heading(col,text=text)
        tree.column(col,width=width,minwidth=80)
    tree.pack(side='left',fill='both',expand=True)
    scroll=ttk.Scrollbar(area,command=tree.yview)
    scroll.pack(side='right',fill='y')
    tree.configure(yscrollcommand=scroll.set)
    tree.tag_configure('keep',foreground=T['success'])
    tree.tag_configure('remove',foreground=T['danger'])
    summary=tk.StringVar()
    def current():
        return groups[listing.curselection()[0] if listing.curselection() else 0]
    def render(event=None):
        group=current()
        reason.set(group['reason']+' · '+group['match'])
        tree.delete(*tree.get_children())
        for row in group['rows']:
            marked=row['id'] in removed
            tree.insert('','end',iid=row['id'],values=('Remove (review)' if marked else '✓ Keep',row['name'],row.get('detail','')),tags=('remove' if marked else 'keep',))
        summary.set(f'{len(groups)} matching groups · {len(removed)} contacts marked for review')
    def toggle(key):
        if not key:return
        if key in removed:removed.remove(key)
        else:removed.add(key)
        render()
        tree.focus(key)
    tree.bind('<Button-1>',lambda event:toggle(tree.identify_row(event.y)))
    tree.bind('<space>',lambda event:toggle(tree.focus()))
    listing.bind('<<ListboxSelect>>',render)
    def keep_only():
        key=tree.focus()
        if not key:
            messagebox.showinfo('Choose a contact','Click a contact row first, then choose Keep highlighted only.',parent=dialog)
            return
        removed.update(row['id'] for row in current()['rows'] if row['id']!=key)
        removed.discard(key)
        render()
    controls=tk.Frame(dialog,bg=T['surface'],padx=pad,pady=pad)
    controls.pack(side='bottom',fill='x',padx=pad,pady=pad,before=body)
    label=panel.app.label(controls,'',muted=True,size=10)
    label.configure(textvariable=summary)
    label.pack(anchor='w',pady=(0,T['space_sm']))
    panel.app.button(controls,'Keep highlighted only',keep_only).pack(side='left')
    def reset():
        removed.clear()
        render()
    panel.app.button(controls,'Keep all',reset).pack(side='left',padx=T['space_sm'])
    def apply():
        try:validate_removals(groups,removed)
        except ValueError as exc:
            messagebox.showinfo('Keep a contact',str(exc),parent=dialog)
            return
        panel.chosen=set(removed)
        panel.render()
        panel.summary.set(f'{len(removed)} possible duplicates selected. Back up or review them before using Delete selected. Nothing has been deleted.')
        dialog.destroy()
    panel.app.button(controls,'Select marked contacts',apply,True).pack(side='right')
    listing.selection_set(0)
    render()
