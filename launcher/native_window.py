"""Frameless WebView2 shell with native resizing and work-area maximization."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading


class NativeFrame:
    """Keep the native resize/snap affordances while hiding Windows chrome."""
    def __init__(self, window):
        self.window = window
        self.handle = 0
        self._callback = None
        self._previous = None

    def install(self):
        if os.name != 'nt':
            return
        from System import Action
        native = self.window.native
        native.Invoke(Action(lambda: self._install_on_ui(native)))

    def _install_on_ui(self, form):
        from System.Windows.Forms import Padding
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        dwm = ctypes.WinDLL('dwmapi')
        handle = int(form.Handle.ToInt64())
        self.handle = handle
        result_type = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(result_type, wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM)
        get_long = user32.GetWindowLongPtrW
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t
        set_long = user32.SetWindowLongPtrW
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_long.restype = ctypes.c_ssize_t
        call = user32.CallWindowProcW
        call.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        call.restype = result_type
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.IsZoomed.argtypes = [wintypes.HWND]
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),
                        ('work',wintypes.RECT),('flags',wintypes.DWORD)]

        class MinMaxInfo(ctypes.Structure):
            _fields_ = [('reserved',wintypes.POINT),('max_size',wintypes.POINT),
                        ('max_position',wintypes.POINT),('min_track',wintypes.POINT),
                        ('max_track',wintypes.POINT)]

        def procedure(hwnd, message, wparam, lparam):
            try:
                if message == 0x83:  # WM_NCCALCSIZE: content occupies the whole window.
                    return 0
                if message == 0x24:  # WM_GETMINMAXINFO: maximize inside the monitor work area.
                    result = call(self._previous, hwnd, message, wparam, lparam)
                    monitor = user32.MonitorFromWindow(hwnd, 2)
                    info = MonitorInfo(); info.size = ctypes.sizeof(info)
                    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                        values = ctypes.cast(lparam, ctypes.POINTER(MinMaxInfo)).contents
                        values.max_position.x = info.work.left-info.monitor.left
                        values.max_position.y = info.work.top-info.monitor.top
                        values.max_size.x = info.work.right-info.work.left
                        values.max_size.y = info.work.bottom-info.work.top
                        scale = (user32.GetDpiForWindow(hwnd) or 96)/96
                        values.min_track.x = round(640*scale)
                        values.min_track.y = round(520*scale)
                    return result
                if message == 0x84 and not user32.IsZoomed(hwnd):  # WM_NCHITTEST
                    rect = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    x = ctypes.c_short(lparam & 0xffff).value
                    y = ctypes.c_short((lparam >> 16) & 0xffff).value
                    margin = max(5, round(6*(user32.GetDpiForWindow(hwnd) or 96)/96))
                    left, right = x < rect.left+margin, x >= rect.right-margin
                    top, bottom = y < rect.top+margin, y >= rect.bottom-margin
                    if top and left:return 13
                    if top and right:return 14
                    if bottom and left:return 16
                    if bottom and right:return 17
                    if left:return 10
                    if right:return 11
                    if top:return 12
                    if bottom:return 15
                if message == 0x86:  # WM_NCACTIVATE: don't paint a native caption.
                    return 1
            except Exception:
                pass
            return call(self._previous, hwnd, message, wparam, lparam)

        self._callback = callback_type(procedure)
        self._previous = set_long(handle, -4, ctypes.cast(self._callback, ctypes.c_void_p).value)
        if not self._previous:
            raise OSError(ctypes.get_last_error(), 'Could not install native window frame')
        # Preserve taskbar minimize/maximize, border resizing, Win+Arrow and Snap.
        style = get_long(handle, -16)
        set_long(handle, -16, style | 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000)
        user32.SetWindowPos.argtypes = [wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                                       ctypes.c_int,ctypes.c_int,wintypes.UINT]
        user32.SetWindowPos(handle, None, 0, 0, 0, 0, 0x0027)
        # WebView2 is a child HWND and consumes its own hit tests. Keep a slim
        # client margin owned by the Form so all eight native resize targets
        # remain reachable, including when the page contains a scrollbar.
        def update_margin(sender=None, event=None):
            margin = 0 if user32.IsZoomed(handle) else max(5, round(6*(user32.GetDpiForWindow(handle) or 96)/96))
            form.Padding = Padding(margin)
        self._update_margin = update_margin
        form.Resize += update_margin
        form.DpiChanged += update_margin
        update_margin()
        # Use the system corner preference when DWM supports it (Windows 11).
        preference = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(wintypes.HWND(handle), 33, ctypes.byref(preference), 4)


class NativeWindow:
    def __init__(self, server, home):
        self.server = server
        self.home = Path(home)
        self.window = None
        self.frame = None
        self.alive = False
        self.maximized = False
        self.events = threading.Event()

    def run(self):
        import webview
        webview.settings['ALLOW_FILE_URLS'] = False
        webview.settings['ALLOW_DOWNLOADS'] = False
        webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
        screens = webview.screens
        width = min(1280, max(640, screens[0].width-80)) if screens else 1280
        height = min(860, max(520, screens[0].height-80)) if screens else 860
        self.window = webview.create_window('艾尔之光 · 本地启动器', self.server.url,
            width=width, height=height, min_size=(640,520), frameless=True,
            easy_drag=False, shadow=True, resizable=True, background_color='#f3f7fa',
            text_select=True, zoomable=True)
        self.frame = NativeFrame(self.window)
        self.window.events.shown += self._shown
        self.window.events.closed += self._closed
        self.window.events.maximized += lambda: self._set_maximized(True)
        self.window.events.restored += lambda: self._set_maximized(False)
        self.alive = True
        webview.start(gui='edgechromium', private_mode=False,
                      storage_path=str(self.home/'webview'),
                      icon=str(Path(__file__).parent/'assets/launcher.ico'))

    def _shown(self):
        try:
            self.frame.install()
            status = dict(frameless=True, hwnd=self.frame.handle, width=self.window.width,
                          height=self.window.height, renderer='WebView2')
            (self.home/'native-window.json').write_text(json.dumps(status), encoding='utf8')
        except Exception as error:
            (self.home/'native-window-error.log').write_text(repr(error), encoding='utf8')
        self.events.set()

    def _closed(self):
        self.alive = False
        self.server.close_requested = True

    def _set_maximized(self, value):
        self.maximized = value

    def action(self, action):
        if not self.window or not self.alive:
            raise ValueError('原生窗口尚未准备好')
        if action == 'minimize': self.window.minimize()
        elif action == 'toggle_maximize':
            if self.maximized:self.window.restore()
            else:self.window.maximize()
        elif action == 'restore':
            self.window.restore();self.window.show()
        elif action == 'close':
            threading.Timer(.15, self.window.destroy).start()
        else:raise ValueError('未知窗口操作')
        return dict(maximized=self.maximized)
