"""Shared image indicators: a real green tick in every checkbutton."""
from PIL import Image, ImageDraw, ImageTk


def install_ticks(app):
    images = []
    for selected, disabled in ((False, False), (True, False), (False, True), (True, True)):
        image = Image.new('RGBA', (72, 72))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 67, 67), radius=16,
                               fill='#152e2b' if selected else '#211b45',
                               outline='#64eda9' if selected and not disabled else '#a39ac9', width=5)
        if selected:
            draw.line((20, 36, 31, 47, 53, 23), fill='#64eda9' if not disabled else '#a39ac9', width=8, joint='curve')
        images.append(ImageTk.PhotoImage(image.resize((24, 24), Image.Resampling.LANCZOS)))
    app.tick_images = images
    app.style.element_create('Twist.Check.indicator', 'image', images[0],
                             ('disabled', 'selected', images[3]), ('disabled', images[2]),
                             ('selected', images[1]), sticky='')
    app.style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
        ('Twist.Check.indicator', {'side': 'left', 'sticky': ''}),
        ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
            ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
    app.style.configure('TCheckbutton', padding=4)
