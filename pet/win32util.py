import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def idle_seconds():
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    tick = ctypes.windll.kernel32.GetTickCount()
    return max(0, (tick - info.dwTime) / 1000.0)


def foreground_hwnd():
    return user32.GetForegroundWindow()


def window_title(hwnd):
    if not hwnd:
        return ""
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value or ""


def window_rect(hwnd):
    if not hwnd:
        return None
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def is_window_visible(hwnd):
    return bool(hwnd) and bool(user32.IsWindowVisible(hwnd))
