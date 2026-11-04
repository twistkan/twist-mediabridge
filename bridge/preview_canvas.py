"""Resizable native media canvas; keeps source pixels for subsequent resizes."""
import tkinter as tk
from PIL import Image, ImageTk
from .theme import TOKENS as T


class PreviewCanvas(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=T['bg'], highlightthickness=0, width=1, height=1)
        self.picture = None
        self.image = None
        self.resize_job = None
        self.art = self.create_image(0, 0, anchor='center')
        self.message = self.create_text(0, 0, fill=T['muted'], justify='center', text='Loading preview locally…\nLarge videos can take a moment.')
        self.bind('<Configure>', self.resized)
        self.bind('<Destroy>', self.disposed)

    def disposed(self, event):
        if event.widget is self and self.resize_job:
            self.after_cancel(self.resize_job); self.resize_job = None
        if event.widget is self:self.picture = None; self.image = None

    def resized(self, event=None):
        self.coords(self.message, self.winfo_width()/2, self.winfo_height()/2)
        self.itemconfigure(self.message, width=max(100, self.winfo_width()-40))
        if self.resize_job:self.after_cancel(self.resize_job)
        self.resize_job = self.after(60, self.fit)

    def set_picture(self, picture):
        self.picture = picture
        self.itemconfigure(self.message, text='')
        self.fit()

    def show_message(self, text):
        self.picture = None; self.image = None
        self.itemconfigure(self.art, image='')
        self.itemconfigure(self.message, text=text)
        self.resized()

    def fit(self):
        if self.resize_job:
            self.after_cancel(self.resize_job); self.resize_job = None
        if self.picture is None:return
        width, height = max(1,self.winfo_width()), max(1,self.winfo_height())
        scale = min(width/self.picture.width, height/self.picture.height)
        size = (max(1,round(self.picture.width*scale)), max(1,round(self.picture.height*scale)))
        resized = self.picture.resize(size, Image.Resampling.LANCZOS)
        self.image = ImageTk.PhotoImage(resized)
        self.itemconfigure(self.art, image=self.image)
        self.coords(self.art, width/2, height/2)
