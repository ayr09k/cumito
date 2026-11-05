"""
Teclas multimedia del teclado (▶︎⏸ ⏭ ⏮): controlan Cumito aunque la ventana
no esté al frente. Solo en Windows. Si otra app ya se quedó con una tecla,
esa simplemente no se toma (no se rompe nada).
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
KEYS = {1: (0xB3, "play_pause"), 2: (0xB0, "next"), 3: (0xB1, "prev")}


class MediaKeys(QAbstractNativeEventFilter):
    def __init__(self, app, window, on_key):
        super().__init__()
        self.app, self.window, self.on_key = app, window, on_key
        self.active = False
        self._hwnd = None
        self.taken = []

    def start(self):
        if sys.platform != "win32" or self.active:
            return
        import ctypes
        self._hwnd = int(self.window.winId())
        user32 = ctypes.windll.user32
        self.taken = []
        for hid, (vk, name) in KEYS.items():
            if user32.RegisterHotKey(self._hwnd, hid, MOD_NOREPEAT, vk):
                self.taken.append(name)
        self.app.installNativeEventFilter(self)
        self.active = True

    def stop(self):
        if not self.active:
            return
        import ctypes
        for hid in KEYS:
            ctypes.windll.user32.UnregisterHotKey(self._hwnd, hid)
        self.app.removeNativeEventFilter(self)
        self.active = False

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG", "windows_generic_MSG"):
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam in KEYS:
                    self.on_key(KEYS[msg.wParam][1])
                    return True, 0
        except Exception:
            pass
        return False, 0
