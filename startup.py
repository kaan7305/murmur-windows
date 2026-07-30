"""Whether Murmur comes back on its own after a sign-in.

Worth being clear about why this exists at all: nothing can launch Murmur *on*
the shortcut. The shortcut is a system-wide keyboard hook, and a hook needs a
process to live in - until Murmur is running there is nobody listening for
Ctrl+Space, so there is nothing to launch it. Starting hidden at sign-in is the
whole answer. The tray icon appears, the hook goes on, and from then on the
shortcut works without anyone ever opening a window.

HKCU\\...\\Run rather than a shortcut in the Startup folder: no file to go
stale, no elevation needed, and it is the same value the installer's "Start
Murmur when I sign in" checkbox writes - so the installer and the in-app
setting cannot end up disagreeing about the answer.
"""
from __future__ import annotations

import pathlib
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Murmur"
FLAG = "--hidden"   # boot to the tray, not to a window nobody asked for


def _installed_exe() -> pathlib.Path | None:
    """The installed copy, if there is one.

    Matters when Murmur is being run from a source checkout on a machine that
    also has it installed: the thing that should come back at sign-in is the
    installed application, not whichever virtualenv happened to be active.
    """
    import os

    root = os.environ.get("LOCALAPPDATA")
    for base in ([pathlib.Path(root)] if root else []) + [
            pathlib.Path.home() / "AppData" / "Local"]:
        exe = base / "Programs" / "Murmur" / "Murmur.exe"
        if exe.is_file():
            return exe
    return None


def command() -> str:
    """The exact command line to register."""
    import paths

    if paths.FROZEN:
        return f'"{pathlib.Path(sys.executable)}" {FLAG}'

    installed = _installed_exe()
    if installed is not None:
        return f'"{installed}" {FLAG}'

    # A source checkout: pythonw, so no console window flashes up at sign-in.
    py = pathlib.Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    script = pathlib.Path(__file__).resolve().parent / "app.py"
    return f'"{pyw if pyw.is_file() else py}" "{script}" {FLAG}'


def _stored() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE)
    except OSError:
        return None
    return value or None


def is_enabled() -> bool:
    return _stored() is not None


def set_enabled(on: bool) -> None:
    """Add or remove the entry. Raises OSError if the registry refuses."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE)
            except FileNotFoundError:
                pass


def repair() -> None:
    """Correct an entry that points at a copy which is no longer there.

    Reinstalling elsewhere, or moving the folder, leaves a Run value aimed at
    nothing: Murmur then silently stops coming back at sign-in and the setting
    still reads as on. Only ever rewrites an entry that already exists, so it
    can never switch the feature on behind the user's back.
    """
    stored = _stored()
    if stored is None:
        return
    target = stored.split('"')[1] if stored.startswith('"') else stored.split(" ")[0]
    if pathlib.Path(target).is_file():
        return
    try:
        set_enabled(True)
    except OSError:
        pass


if __name__ == "__main__":   # a hand switch, for when there is no window open
    want = "off" not in sys.argv[1:]
    set_enabled(want)
    print(f"Start at sign-in: {'on' if is_enabled() else 'off'}")
    print(f"  {_stored() or '(no entry)'}")
