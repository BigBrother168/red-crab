# -*- coding: utf-8 -*-
"""What every part of the Win32 shim shares: the last error, one table of handles, how arguments arrive, and how a
call that is not there yet says so.  Standard library only.

Arguments are Python values, not C ones: _api(...) in clawd_pet.pyw sets restype and argtypes on these plain
functions, which is allowed and changes nothing.  So an argument is what the caller wrote: an int, None, a str, a
ctypes instance (c_void_p(h)), ctypes.byref(x) (the object is arg._obj), a pointer (.contents), an array, or a
structure passed by value.  Structures are read and written by field name, never by Windows' byte layout (LONG is
c_long, 8 bytes here).  Results are plain ints: BOOL 1 or 0, handles non-zero ints from the one table below."""
import ctypes
import sys
import threading
import traceback

ERROR_SUCCESS = 0
ERROR_FILE_NOT_FOUND = 2
ERROR_INVALID_HANDLE = 6
ERROR_INVALID_PARAMETER = 87
ERROR_CALL_NOT_IMPLEMENTED = 120
ERROR_ALREADY_EXISTS = 183
ERROR_INVALID_WINDOW_HANDLE = 1400
ERROR_INVALID_MENU_HANDLE = 1401
ERROR_CANNOT_FIND_WND_CLASS = 1407
ERROR_CLASS_ALREADY_EXISTS = 1410
ERROR_CLASS_DOES_NOT_EXIST = 1411
ERROR_POPUP_ALREADY_ACTIVE = 1446

MESSAGES = {
    ERROR_SUCCESS: "The operation completed successfully.",
    ERROR_FILE_NOT_FOUND: "The system cannot find the file specified.",
    ERROR_INVALID_HANDLE: "The handle is invalid.",
    ERROR_INVALID_PARAMETER: "The parameter is incorrect.",
    ERROR_CALL_NOT_IMPLEMENTED: "This function is not supported on this system.",
    ERROR_ALREADY_EXISTS: "Cannot create a file when that file already exists.",
    ERROR_INVALID_WINDOW_HANDLE: "Invalid window handle.",
    ERROR_INVALID_MENU_HANDLE: "Invalid menu handle.",
    ERROR_CANNOT_FIND_WND_CLASS: "Cannot find window class.",
    ERROR_CLASS_ALREADY_EXISTS: "Class already exists.",
    ERROR_CLASS_DOES_NOT_EXIST: "Class does not exist.",
    ERROR_POPUP_ALREADY_ACTIVE: "Popup menu already active.",
}

_HANDLE_FIRST = 0x10000      # far from 0, from 1 (HWND_BOTTOM) and from the small ids the program uses
_HANDLE_STEP = 4
_WORD = 1 << 64

# --------------------------------------------------------------------------- the last error
_tls = threading.local()


def get_last_error():
    """The calling thread's last error, as ctypes.get_last_error() gives it on Windows."""
    return getattr(_tls, "value", 0)


def set_last_error(value):
    """-> the value it had (as ctypes.set_last_error)."""
    old = get_last_error()
    _tls.value = int(value)
    return old


def fail(code, result=0):
    """A failed call: the last error is code, the result what such a call returns (mostly 0)."""
    set_last_error(code)
    return result


# --------------------------------------------------------------------------- handles
_table = {}
_next = [_HANDLE_FIRST]
_lock = threading.Lock()


def new_handle(obj):
    """A handle for obj, never used before in this process."""
    with _lock:
        h = _next[0]
        _next[0] += _HANDLE_STEP
        _table[h] = obj
    return h


def lookup(h, kind=None):
    """The object of handle h (of class kind), or None."""
    obj = _table.get(handle(h))
    if obj is None or (kind is not None and not isinstance(obj, kind)):
        return None
    return obj


def release(h):
    """Forget handle h: -> its object, or None."""
    with _lock:
        return _table.pop(handle(h), None)


def objects(kind):
    """All live objects of class kind, oldest first."""
    with _lock:
        items = sorted(_table.items())
    return [obj for _, obj in items if isinstance(obj, kind)]


def window(h):
    """The window record of hwnd h, or None (window records say so with is_window)."""
    obj = _table.get(handle(h))
    return obj if getattr(obj, "is_window", False) else None


# --------------------------------------------------------------------------- arguments
def number(v):
    """An integer argument as an int: None is 0, a ctypes value its .value."""
    if v is None:
        return 0
    if isinstance(v, ctypes._SimpleCData):
        v = v.value
        if v is None:
            return 0
    return int(v)


def handle(v):
    """A handle (or other pointer-sized value) as an int: None and NULL are 0, and c_void_p(-1).value comes back
    as -1 (HWND_TOPMOST and friends are negative)."""
    v = number(v)
    if v >= _WORD >> 1:
        v -= _WORD
    return v


def deref(arg):
    """What a pointer argument points to (ctypes.byref(x) -> x, a pointer -> .contents, a structure passed as it
    is -> itself), or None for NULL."""
    if arg is None:
        return None
    if type(arg).__name__ == "CArgObject":
        return arg._obj
    if isinstance(arg, ctypes._Pointer):
        return arg.contents if arg else None
    return arg


def text(v):
    """A string argument (str, c_wchar_p, a unicode buffer) as str, or None."""
    if v is None or isinstance(v, str):
        return v
    value = getattr(v, "value", v)
    return value if value is None or isinstance(value, str) else str(value)


def pack(lo, hi):
    """MAKELPARAM / MAKEWPARAM: two 16-bit halves, each of which may be negative."""
    return ((int(hi) & 0xFFFF) << 16) | (int(lo) & 0xFFFF)


# --------------------------------------------------------------------------- telling
_told = set()


def say(msg):
    """One line on stderr (if there is one: a windowless start may have none)."""
    if sys.stderr is None:
        return
    try:
        sys.stderr.write("clawd_mac.win32: %s\n" % msg)
        sys.stderr.flush()
    except Exception:
        pass


def report(where):
    """An exception inside an AppKit callback: told on stderr, never raised into AppKit (which would abort)."""
    say("error in %s\n%s" % (where, traceback.format_exc().rstrip()))


def not_yet(name, result=0):
    """A Win32 function that a later step brings to macOS: until then it fails as a Win32 call fails (result, last
    error 120) and says so on stderr, the first time only."""
    def call(*args):
        if name not in _told:
            _told.add(name)
            say("%s is not there yet on macOS" % name)
        set_last_error(ERROR_CALL_NOT_IMPLEMENTED)
        return result
    call.__name__ = name
    return call


def no_meaning(name, result=0):
    """A function of a DLL that has no meaning on macOS (imm32, shcore, ...): fails quietly, last error 120."""
    def call(*args):
        set_last_error(ERROR_CALL_NOT_IMPLEMENTED)
        return result
    call.__name__ = name
    return call
