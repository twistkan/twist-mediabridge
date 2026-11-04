"""Publish image pixels to the Windows clipboard; no file-path paste dependency."""
import ctypes
from ctypes import wintypes
import io
import os
import time
from PIL import Image, ImageOps


def image_payloads(path):
    """Read the full local photo, applying camera orientation without editing it."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
    png = io.BytesIO(); image.save(png,format='PNG',compress_level=1)
    rgb = Image.new('RGB',image.size,'white'); rgb.paste(image,mask=image.getchannel('A'))
    bmp = io.BytesIO(); rgb.save(bmp,format='BMP')
    return bmp.getvalue()[14:], png.getvalue()


def put_image_on_clipboard(payloads,owner):
    if os.name != 'nt':raise OSError('Image clipboard sharing requires Windows.')
    user = ctypes.WinDLL('user32',use_last_error=True)
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    user.OpenClipboard.argtypes=[wintypes.HWND]; user.OpenClipboard.restype=wintypes.BOOL
    user.EmptyClipboard.argtypes=[]; user.EmptyClipboard.restype=wintypes.BOOL
    user.CloseClipboard.argtypes=[]; user.CloseClipboard.restype=wintypes.BOOL
    user.SetClipboardData.argtypes=[wintypes.UINT,wintypes.HANDLE]; user.SetClipboardData.restype=wintypes.HANDLE
    user.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR]; user.RegisterClipboardFormatW.restype=wintypes.UINT
    kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t]; kernel.GlobalAlloc.restype=wintypes.HGLOBAL
    kernel.GlobalLock.argtypes=[wintypes.HGLOBAL]; kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HGLOBAL]; kernel.GlobalUnlock.restype=wintypes.BOOL
    kernel.GlobalFree.argtypes=[wintypes.HGLOBAL]; kernel.GlobalFree.restype=wintypes.HGLOBAL
    formats=[8,user.RegisterClipboardFormatW('PNG')]  # CF_DIB plus alpha-capable PNG.
    allocated=[]; opened=False
    try:
        for format_id,data in zip(formats,payloads):
            if not format_id:continue
            handle=kernel.GlobalAlloc(0x0002,len(data))
            if not handle:raise ctypes.WinError(ctypes.get_last_error())
            allocated.append([format_id,handle])
            pointer=kernel.GlobalLock(handle)
            if not pointer:raise ctypes.WinError(ctypes.get_last_error())
            try:ctypes.memmove(pointer,data,len(data))
            finally:kernel.GlobalUnlock(handle)
        for _ in range(5):
            if user.OpenClipboard(owner):opened=True; break
            time.sleep(.01)
        if not opened:raise OSError('The clipboard is busy. Please try Copy image again.')
        if not user.EmptyClipboard():raise ctypes.WinError(ctypes.get_last_error())
        for format_id,handle in allocated:
            if user.SetClipboardData(format_id,handle):
                # Ownership transfers to Windows; these handles must not be freed.
                for entry in allocated:
                    if entry[1]==handle:entry[1]=None; break
            elif format_id==8:raise ctypes.WinError(ctypes.get_last_error())
            # DIB remains usable even if the optional PNG format is rejected.
    finally:
        if opened:user.CloseClipboard()
        for _,handle in allocated:
            if handle:kernel.GlobalFree(handle)
