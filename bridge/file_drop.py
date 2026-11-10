"""Windows Explorer file drops, using the built-in Shell API (no extra runtime)."""
import ctypes
from ctypes import wintypes as W
import sys


class FileDrop:
    def __init__(self, root, receive):
        self.hwnd = None
        if sys.platform != 'win32':
            return
        self.shell = ctypes.WinDLL('shell32', use_last_error=True)
        self.controls = ctypes.WinDLL('comctl32', use_last_error=True)
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.GetAncestor.argtypes = [W.HWND, W.UINT]
        user.GetAncestor.restype = W.HWND
        self.shell.DragAcceptFiles.argtypes = [W.HWND, W.BOOL]
        self.shell.DragQueryFileW.argtypes = [W.HANDLE, W.UINT, W.LPWSTR, W.UINT]
        self.shell.DragQueryFileW.restype = W.UINT
        self.shell.DragFinish.argtypes = [W.HANDLE]
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT,
                                          W.WPARAM, W.LPARAM, ctypes.c_size_t, ctypes.c_size_t)
        self.controls.SetWindowSubclass.argtypes = [W.HWND, callback_type, ctypes.c_size_t, ctypes.c_size_t]
        self.controls.SetWindowSubclass.restype = W.BOOL
        self.controls.RemoveWindowSubclass.argtypes = [W.HWND, callback_type, ctypes.c_size_t]
        self.controls.DefSubclassProc.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        self.controls.DefSubclassProc.restype = ctypes.c_ssize_t

        def procedure(hwnd, message, wparam, lparam, identity, data):
            if message == 0x233:  # WM_DROPFILES; Windows owns this handle until DragFinish.
                try:
                    paths = []
                    for index in range(self.shell.DragQueryFileW(wparam, 0xffffffff, None, 0)):
                        size = self.shell.DragQueryFileW(wparam, index, None, 0)
                        buffer = ctypes.create_unicode_buffer(size + 1)
                        self.shell.DragQueryFileW(wparam, index, buffer, size + 1)
                        paths.append(buffer.value)
                    receive(paths)  # Queue only; do not call Tk from a native callback.
                finally:
                    self.shell.DragFinish(wparam)
                return 0
            if message == 0x82:  # WM_NCDESTROY
                self.controls.RemoveWindowSubclass(hwnd, self.callback, 1)
                self.hwnd = None
            return self.controls.DefSubclassProc(hwnd, message, wparam, lparam)

        self.callback = callback_type(procedure)  # Keep alive for the entire window lifetime.
        root.update_idletasks()
        hwnd = user.GetAncestor(root.winfo_id(), 2)  # GA_ROOT: Tk's Windows wrapper.
        if not self.controls.SetWindowSubclass(hwnd, self.callback, 1, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = hwnd
        self.shell.DragAcceptFiles(hwnd, True)
