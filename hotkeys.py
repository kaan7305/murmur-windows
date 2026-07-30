"""A global shortcut that the focused application does not also receive.

pynput's own GlobalHotKeys cannot do this. It hears the key, but so does
everything else, so pressing Ctrl+Space to dictate inside an editor also opens
autocomplete, and F9 inside a debugger also toggles a breakpoint. pynput can
suppress events - but only from inside the low-level hook filter, and
suppressing there raises an exception that unwinds before the event ever reaches
GlobalHotKeys' own matching. Suppress the key and the shortcut stops working.

So the matching happens here instead. One low-level hook, one rule:

    the shortcut's key, while its modifiers are held  ->  fire, and swallow it
    anything else                                     ->  pass through untouched

Nothing else is ever suppressed, which bounds what a mistake in here can cost.
And should this raise, Windows' hook dispatcher swallows the error and delivers
the event normally: the failure mode is a shortcut that stops working, never a
keyboard that stops typing.
"""
from __future__ import annotations

import ctypes

from pynput import keyboard

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
DOWN = (WM_KEYDOWN, WM_SYSKEYDOWN)
UP = (WM_KEYUP, WM_SYSKEYUP)

VK_ESCAPE = 0x1B

# What to ask GetAsyncKeyState about for each modifier. Deliberately the
# side-agnostic codes: pynput reports <shift> as VK_LSHIFT, and someone holding
# the right-hand Shift means the same thing by it.
MODIFIER_VKS = {
    "ctrl": (0x11,), "ctrl_l": (0x11,), "ctrl_r": (0x11,),
    "alt": (0x12,), "alt_l": (0x12,), "alt_r": (0x12,), "alt_gr": (0x12,),
    "shift": (0x10,), "shift_l": (0x10,), "shift_r": (0x10,),
    "cmd": (0x5B, 0x5C), "cmd_l": (0x5B,), "cmd_r": (0x5C,),
}

_u32 = ctypes.WinDLL("user32", use_last_error=True)


def _key_vk(key) -> int | None:
    """The virtual key code pynput means by a parsed hotkey component.

    Letters and digits arrive as a character with no code attached, and their
    virtual key code is the uppercase character - that is how Windows numbers
    them.
    """
    if isinstance(key, keyboard.Key):
        return key.value.vk
    if key.vk is not None:
        return key.vk
    if key.char:
        return ord(key.char.upper())
    return None


def combo_from_event(key: int, modifiers, text: str) -> tuple:
    """Turn a Qt key press into a shortcut pynput can register.

    Returns (combo, None) or (None, reason). Lives here rather than in either
    of the two widgets that capture shortcuts, because the rules - what counts
    as a usable key, why a bare letter cannot be one - are a property of the
    hotkey system and not of any particular dialog.
    """
    from PySide6 import QtCore

    if key in (QtCore.Qt.Key_Control, QtCore.Qt.Key_Alt, QtCore.Qt.Key_Shift,
               QtCore.Qt.Key_Meta, QtCore.Qt.Key_AltGr):
        return None, ""            # a modifier alone; still waiting

    parts = []
    if modifiers & QtCore.Qt.ControlModifier:
        parts.append("<ctrl>")
    if modifiers & QtCore.Qt.AltModifier:
        parts.append("<alt>")
    if modifiers & QtCore.Qt.ShiftModifier:
        parts.append("<shift>")
    if modifiers & QtCore.Qt.MetaModifier:
        parts.append("<cmd>")

    named = {
        QtCore.Qt.Key_Space: "<space>", QtCore.Qt.Key_Tab: "<tab>",
        QtCore.Qt.Key_Return: "<enter>", QtCore.Qt.Key_Enter: "<enter>",
        QtCore.Qt.Key_Backspace: "<backspace>",
        QtCore.Qt.Key_Insert: "<insert>", QtCore.Qt.Key_Delete: "<delete>",
        QtCore.Qt.Key_Home: "<home>", QtCore.Qt.Key_End: "<end>",
        QtCore.Qt.Key_PageUp: "<page_up>",
        QtCore.Qt.Key_PageDown: "<page_down>",
    }
    if QtCore.Qt.Key_F1 <= key <= QtCore.Qt.Key_F24:
        main = f"<f{key - QtCore.Qt.Key_F1 + 1}>"
    elif key in named:
        main = named[key]
    elif text and text.isalnum():
        main = text.lower()
    else:
        return None, "That key cannot be used - try another"

    # A shortcut with no modifier fires every time the key is touched, in every
    # application. Function keys are the exception: nothing types them.
    if not parts and not main.startswith("<f"):
        return None, "Needs Ctrl, Alt or Shift - try again"

    parts.append(main)
    return "+".join(parts), None


class GlobalHotkey:
    """Watches for one shortcut and hides it from everything else.

    on_trigger fires once per press, not once per auto-repeat, and runs on the
    hook thread - so it must hand off rather than do work. on_escape, if given,
    fires on Escape and does *not* swallow it: Escape means too much elsewhere
    to take away from every other application on the machine.
    """

    def __init__(self, combo: str, on_trigger, on_escape=None) -> None:
        parts = keyboard.HotKey.parse(combo)      # raises ValueError if invalid
        self.combo = combo
        self._on_trigger = on_trigger
        self._on_escape = on_escape
        self._listener = None
        self._held = False

        self._modifier_vks: list[tuple] = []
        self._main_vk: int | None = None
        for part in parts:
            name = part.name if isinstance(part, keyboard.Key) else None
            if name in MODIFIER_VKS:
                self._modifier_vks.append(MODIFIER_VKS[name])
            else:
                self._main_vk = _key_vk(part)

        if self._main_vk is None:
            raise ValueError(f"{combo!r} has no key to press, only modifiers")

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=None, on_release=None, win32_event_filter=self._filter)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # ── the hook ────────────────────────────────────────────────────────────

    def _modifiers_held(self) -> bool:
        # The high bit of GetAsyncKeyState is "down right now". The low bit is
        # "pressed since last asked", which would report keys released seconds
        # ago and is not what is being asked.
        return all(
            any(_u32.GetAsyncKeyState(vk) & 0x8000 for vk in group)
            for group in self._modifier_vks
        )

    def _filter(self, msg, data) -> bool:
        vk = data.vkCode

        if vk == VK_ESCAPE:
            if msg in DOWN and self._on_escape is not None:
                self._on_escape()
            return False

        if vk != self._main_vk:
            return False

        if msg in DOWN:
            if self._modifiers_held():
                if not self._held:      # ignore the auto-repeat storm
                    self._held = True
                    self._on_trigger()
                self._listener.suppress_event()
        elif msg in UP:
            # Only swallow the release of a press that was itself swallowed,
            # so no application is left holding a key down that never came up.
            if self._held:
                self._held = False
                self._listener.suppress_event()
        return False
