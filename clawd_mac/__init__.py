# -*- coding: utf-8 -*-
"""Red Crab on macOS.

The pets are a Win32 program (ctypes all the way down).  On macOS the Win32 calls they make are served by this
package instead of Windows, so the program itself stays one program:

  win32.py    the user32 / kernel32 / shell32 / gdi32 subset the pets use, over AppKit (PyObjC).  install() puts
              ctypes.WinDLL, ctypes.windll, ctypes.WINFUNCTYPE, ctypes.WinError and ctypes.get_last_error in place
              (only where ctypes has none), so the entry scripts call it once, before anything else.
  gdiplus.py  the GDI+ flat-API subset (sign boards, live scaling, clawd_scale.py), over Quartz only (no AppKit,
              so it also runs without a window server).
  lock.py     named single-instance locks: what a named mutex is on Windows.
  system.py   the rest of what differs: where the saves live, the UI language, start at login (a LaunchAgent),
              finding and stopping the pet's process.

Nothing in here is imported on Windows.
"""
