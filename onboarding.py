"""The setup guide shown the first time Murmur runs.

Five screens, under a minute. It exists because the two things most likely to
make someone give up happen before they ever dictate a word: they close the
window and think they have quit the program, and they press the shortcut into an
application that was not listening. Both are fixed by being told once.

The last screen is the important one - it does not describe the shortcut, it
makes the user press it and watch their own words appear. Nobody trusts
dictation until they have seen it work once.
"""
from __future__ import annotations

import ctypes

from PySide6 import QtCore, QtGui, QtWidgets

import hotkeys
import logo
import murmur as core
from overlay import Waveform
from theme import (D_ACCENT, D_BG, D_INK, D_INK_MID, D_INK_SOFT, D_LINE,
                   D_SURFACE, D_SURFACE_HI, DarkButton, KeyCap, StepBar, font)


def dark_label(text: str, size: float, weight: int, colour: str,
               wrap: bool = True) -> QtWidgets.QLabel:
    lab = QtWidgets.QLabel(text)
    lab.setFont(font(size, weight))
    lab.setStyleSheet(f"color:{colour};background:transparent;")
    lab.setWordWrap(wrap)
    return lab


def centred(widget: QtWidgets.QWidget, width: int) -> QtWidgets.QHBoxLayout:
    """Centre a paragraph at a readable measure.

    setMaximumWidth is not enough: a wrapping QLabel inside a stretch sandwich
    is given its own sizeHint, which for wrapped text is far narrower than the
    maximum, so the text ends up in a thin column down the middle.
    """
    widget.setFixedWidth(width)
    if isinstance(widget, QtWidgets.QLabel):
        widget.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    row.addWidget(widget)
    row.addStretch(1)
    return row


# ── the illustration on the tray screen ────────────────────────────────────

def tray_illustration(width: int = 430) -> QtGui.QPixmap:
    """A drawing of the Windows tray with Murmur's icon in it, and an arrow.

    Drawn rather than screenshotted so it stays sharp at any scaling and does
    not go stale when Windows changes its own tray.
    """
    h = 150
    ratio = 2
    pix = QtGui.QPixmap(width * ratio, h * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)

    # The taskbar strip: light, because the Windows tray is light even when the
    # rest of the desktop is dark, and pretending otherwise would be unhelpful.
    # Two bands - a dimmer sliver of desktop above, the tray itself below.
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor("#C9D0DC"))
    p.drawRoundedRect(QtCore.QRectF(0, 74, width, 54), 10, 10)
    p.setBrush(QtGui.QColor("#EDF0F5"))
    p.drawRoundedRect(QtCore.QRectF(0, 88, width, 40), 10, 10)
    p.drawRect(QtCore.QRectF(0, 88, width, 20))

    icon_y = 106
    x = 30.0
    ink = QtGui.QColor("#3A3F49")

    # the chevron that reveals hidden icons
    p.setPen(QtGui.QPen(ink, 1.8, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    p.drawLine(QtCore.QPointF(x - 6, icon_y + 2), QtCore.QPointF(x, icon_y - 4))
    p.drawLine(QtCore.QPointF(x, icon_y - 4), QtCore.QPointF(x + 6, icon_y + 2))
    x += 40

    # Murmur itself, the thing the arrow points at
    murmur_x = x
    p.drawPixmap(QtCore.QPointF(x - 11, icon_y - 11), logo.tile_pixmap(22))
    x += 42

    # a couple of ordinary neighbours, so it reads as a tray and not as a button
    p.setPen(QtGui.QPen(ink, 1.7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    p.drawArc(QtCore.QRectF(x - 9, icon_y - 7, 18, 16), 30 * 16, 120 * 16)
    p.drawArc(QtCore.QRectF(x - 5, icon_y - 3, 10, 10), 30 * 16, 120 * 16)
    p.setBrush(ink)
    p.drawEllipse(QtCore.QPointF(x, icon_y + 5), 1.4, 1.4)
    x += 40

    p.setBrush(ink)
    p.setPen(QtCore.Qt.NoPen)
    speaker = QtGui.QPolygonF([
        QtCore.QPointF(x - 7, icon_y - 2), QtCore.QPointF(x - 3, icon_y - 2),
        QtCore.QPointF(x + 1, icon_y - 7), QtCore.QPointF(x + 1, icon_y + 7),
        QtCore.QPointF(x - 3, icon_y + 2), QtCore.QPointF(x - 7, icon_y + 2),
    ])
    p.drawPolygon(speaker)
    p.setPen(QtGui.QPen(ink, 1.5))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawArc(QtCore.QRectF(x + 2, icon_y - 6, 9, 12), -60 * 16, 120 * 16)
    x += 42

    p.setPen(QtGui.QPen(ink, 1.5))
    p.drawRoundedRect(QtCore.QRectF(x - 9, icon_y - 5, 17, 10), 2.5, 2.5)
    p.setBrush(ink)
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(QtCore.QRectF(x - 7.5, icon_y - 3.5, 12, 7), 1.5, 1.5)
    p.drawRoundedRect(QtCore.QRectF(x + 8.5, icon_y - 2, 2, 4), 1, 1)

    # the clock, right-aligned the way the real one is
    p.setPen(QtGui.QColor("#3A3F49"))
    p.setFont(font(9))
    p.drawText(QtCore.QRectF(width - 110, icon_y - 14, 90, 14),
               QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, "3:59 PM")
    p.drawText(QtCore.QRectF(width - 110, icon_y, 90, 14),
               QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, "2026-07-26")

    # the arrow
    red = QtGui.QColor("#F04A34")
    p.setPen(QtGui.QPen(red, 4.5, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    p.drawLine(QtCore.QPointF(murmur_x, 14), QtCore.QPointF(murmur_x, 56))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(red)
    # The tip stops above the icon rather than on it - an arrow overlapping the
    # thing it points at hides the thing it points at.
    p.drawPolygon(QtGui.QPolygonF([
        QtCore.QPointF(murmur_x, 72),
        QtCore.QPointF(murmur_x - 9, 54),
        QtCore.QPointF(murmur_x + 9, 54),
    ]))
    p.end()
    return pix


# ── the model choice ───────────────────────────────────────────────────────

class ChoiceCard(QtWidgets.QFrame):
    """One of the two tiles on the model screen."""

    clicked = QtCore.Signal(str)

    def __init__(self, key: str, title: str, note: str, glyph: str,
                 enabled: bool = True) -> None:
        super().__init__()
        self.key = key
        self.enabled_choice = enabled
        self._selected = False
        # Scoped by object name: an unqualified QFrame rule in a stylesheet is
        # inherited by every child, and the labels inside would each grow their
        # own border.
        self.setObjectName("choice")
        self.setFixedSize(196, 186)
        self.setCursor(QtCore.Qt.PointingHandCursor if enabled
                       else QtCore.Qt.ArrowCursor)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(4)

        art = QtWidgets.QLabel()
        art.setPixmap(self._glyph(glyph, enabled))
        art.setAlignment(QtCore.Qt.AlignCenter)
        art.setStyleSheet("background:transparent;")
        lay.addWidget(art, 1)

        self.title = dark_label(title, 14, 700,
                                D_ACCENT if enabled else D_INK_SOFT)
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.title)

        sub = dark_label(note, 10.5, 500, D_INK_SOFT)
        sub.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(sub)
        self._restyle()

    def _glyph(self, kind: str, enabled: bool) -> QtGui.QPixmap:
        size, ratio = 74, 2
        pix = QtGui.QPixmap(size * ratio, size * ratio)
        pix.setDevicePixelRatio(ratio)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        colour = QtGui.QColor(D_ACCENT if enabled else "#5A5A62")
        p.setPen(QtGui.QPen(colour, 3.0, QtCore.Qt.SolidLine,
                            QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        c = size / 2
        if kind == "cloud":
            # Filled rather than outlined: three overlapping circles stroked
            # individually read as a Venn diagram, and united they leave seams
            # where the shapes meet. A silhouette has neither problem.
            path = QtGui.QPainterPath()
            # Winding, not the default odd-even: with odd-even every place two
            # circles overlap cancels out and the cloud comes out full of holes.
            path.setFillRule(QtCore.Qt.WindingFill)
            path.addEllipse(QtCore.QPointF(c - 11, c + 1), 11, 11)
            path.addEllipse(QtCore.QPointF(c + 2, c - 6), 15, 15)
            path.addEllipse(QtCore.QPointF(c + 15, c + 2), 10, 10)
            path.addRect(QtCore.QRectF(c - 22, c + 1, 37, 11))
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(colour)
            p.drawPath(path)
        else:
            # a processor: a square with legs, which is what "on this machine"
            # looks like to anyone who has seen a motherboard
            p.drawRoundedRect(QtCore.QRectF(c - 15, c - 15, 30, 30), 5, 5)
            p.drawRoundedRect(QtCore.QRectF(c - 6, c - 6, 12, 12), 2, 2)
            for i in (-8, 0, 8):
                p.drawLine(QtCore.QPointF(c + i, c - 15),
                           QtCore.QPointF(c + i, c - 22))
                p.drawLine(QtCore.QPointF(c + i, c + 15),
                           QtCore.QPointF(c + i, c + 22))
                p.drawLine(QtCore.QPointF(c - 15, c + i),
                           QtCore.QPointF(c - 22, c + i))
                p.drawLine(QtCore.QPointF(c + 15, c + i),
                           QtCore.QPointF(c + 22, c + i))
        p.end()
        return pix

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self._restyle()

    def _restyle(self) -> None:
        border = D_ACCENT if self._selected else D_LINE
        width = "2px" if self._selected else "1px"
        self.setStyleSheet(
            f"QFrame#choice{{background:{D_SURFACE if self._selected else D_BG};"
            f"border:{width} solid {border};border-radius:14px;}}")

    def mousePressEvent(self, _e) -> None:
        if self.enabled_choice:
            self.clicked.emit(self.key)


# ── changing the shortcut ──────────────────────────────────────────────────

class HotkeyCatcher(QtWidgets.QLabel):
    """Press the combination you want; it becomes the shortcut.

    Typing a shortcut into a text box means inventing a syntax and then
    explaining it. Catching the actual keypress means there is nothing to
    explain and nothing to get wrong.
    """

    captured = QtCore.Signal(str)
    cancelled = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__("Press the keys you want ...")
        self.setFont(font(12, 600))
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumHeight(44)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setStyleSheet(
            f"color:{D_INK};background:{D_SURFACE_HI};"
            f"border:1.5px solid {D_ACCENT};border-radius:10px;padding:8px;")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            return
        combo, reason = hotkeys.combo_from_event(
            event.key(), event.modifiers(), event.text())
        if combo:
            self.captured.emit(combo)
        elif reason:
            self.setText(reason)


# ── the screens ────────────────────────────────────────────────────────────

class Step(QtWidgets.QWidget):
    """A screen: a heading, some body, and up to three buttons underneath."""

    title = ""
    subtitle = ""
    progress = 0.0

    def __init__(self, guide: "Onboarding") -> None:
        super().__init__()
        self.guide = guide
        self.setStyleSheet(f"background:{D_BG};")
        self.lay = QtWidgets.QVBoxLayout(self)
        self.lay.setContentsMargins(38, 30, 38, 26)
        self.lay.setSpacing(10)
        self.build()

    def build(self) -> None:
        ...

    def on_enter(self) -> None:
        ...

    def on_leave(self) -> None:
        ...

    def heading(self, title: str, subtitle: str = "") -> None:
        self.lay.addWidget(dark_label(title, 26, 800, D_INK))
        if subtitle:
            sub = dark_label(subtitle, 12.5, 400, D_INK_MID)
            self.lay.addWidget(sub)


class WelcomeStep(Step):
    progress = 0.0

    def build(self) -> None:
        self.lay.setContentsMargins(38, 38, 38, 26)
        self.lay.addStretch(3)
        t = dark_label("Welcome to Murmur", 30, 800, D_INK)
        t.setAlignment(QtCore.Qt.AlignCenter)
        self.lay.addWidget(t)

        s = dark_label("We'll set it up and make sure it works the way you "
                       "want.", 13, 400, D_INK_MID)
        self.lay.addLayout(centred(s, 400))

        self.lay.addSpacing(12)
        e = dark_label("Estimated time: less than a minute", 11.5, 400,
                       D_INK_SOFT)
        e.setAlignment(QtCore.Qt.AlignCenter)
        self.lay.addWidget(e)
        self.lay.addStretch(4)

        go = DarkButton("Get Started")
        go.clicked.connect(self.guide.next_step)
        self.lay.addWidget(go)

        free = dark_label("Free, and it stays that way. Nothing you say leaves "
                          "this computer.", 10.5, 400, D_INK_SOFT)
        free.setAlignment(QtCore.Qt.AlignCenter)
        self.lay.addWidget(free)


class TrayStep(Step):
    progress = 0.25

    def build(self) -> None:
        self.heading(
            "Murmur lives in the tray",
            "Closing the window does not quit it. Murmur keeps listening for "
            "the shortcut from the system tray, at the bottom right of your "
            "screen.")

        art = QtWidgets.QLabel()
        art.setPixmap(tray_illustration())
        art.setAlignment(QtCore.Qt.AlignCenter)
        art.setStyleSheet("background:transparent;")
        self.lay.addSpacing(14)
        self.lay.addWidget(art)

        self.hint = dark_label("", 11.5, 400, D_INK_SOFT)
        self.hint.hide()
        self.lay.addWidget(self.hint)
        self.lay.addStretch(1)

        self.ok = DarkButton("Got it")
        self.ok.clicked.connect(self.guide.next_step)
        self.lay.addWidget(self.ok)

        self.lost = DarkButton("I can't find it", "muted")
        self.lost.clicked.connect(self._explain)
        self.lay.addWidget(self.lost)

    def _explain(self) -> None:
        self.hint.setText(
            "Windows hides new tray icons by default. Click the ^ arrow at the "
            "left of the tray to see them, then drag Murmur down onto the "
            "taskbar to keep it visible.")
        self.hint.show()
        self.lost.hide()


class MicStep(Step):
    progress = 0.5

    def build(self) -> None:
        self.heading("Let's test your microphone",
                     "Speak, and see whether the bars react. Nothing is "
                     "recorded or kept.")

        self.device = QtWidgets.QComboBox()
        self.device.setFont(font(11.5))
        self.device.setMinimumHeight(38)
        self.device.setStyleSheet(f"""
            QComboBox{{border:1px solid {D_LINE};border-radius:9px;
                padding:6px 12px;background:{D_SURFACE};color:{D_INK};}}
            QComboBox::drop-down{{border:none;width:26px;}}
            QComboBox QAbstractItemView{{border:1px solid {D_LINE};
                background:{D_SURFACE};color:{D_INK};
                selection-background-color:{D_SURFACE_HI};outline:0;}}""")
        self.lay.addSpacing(10)
        self.lay.addWidget(self.device)

        self.wave = Waveform(colour=QtGui.QColor(D_ACCENT))
        self.wave.setMinimumHeight(96)
        self.lay.addStretch(1)
        self.lay.addWidget(self.wave)
        self.lay.addStretch(1)

        self.note = dark_label("", 11, 400, D_INK_SOFT)
        self.note.setAlignment(QtCore.Qt.AlignCenter)
        self.lay.addWidget(self.note)

        go = DarkButton("Continue")
        go.clicked.connect(self.guide.next_step)
        self.lay.addWidget(go)

    def on_enter(self) -> None:
        self.device.clear()
        try:
            import sounddevice as sd
            default = sd.query_devices(kind="input")["name"]
            self.device.addItem(f"{default}   (system default)")
            seen = {default}
            for d in sd.query_devices():
                if d["max_input_channels"] > 0 and d["name"] not in seen:
                    seen.add(d["name"])
                    self.device.addItem(d["name"])
        except Exception as e:
            self.device.addItem(f"No input devices found: {e}")
        self.note.setText("No movement? Pick a different input above.")
        self.guide.mic_test.emit(True)

    def on_leave(self) -> None:
        self.guide.mic_test.emit(False)

    def push_level(self, level: float) -> None:
        self.wave.push(level)


class ModelStep(Step):
    progress = 0.75

    def build(self) -> None:
        self.heading(
            "Where the transcription happens",
            "Murmur runs the speech model on this computer. Your voice is "
            "never uploaded, there is no account, and there is nothing to pay.")

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(14)
        row.addStretch(1)
        self.local = ChoiceCard("local", "Local", "Free forever", "chip", True)
        self.cloud = ChoiceCard("cloud", "Cloud", "Coming soon", "cloud", False)
        for card in (self.local, self.cloud):
            card.clicked.connect(self._choose)
            row.addWidget(card)
        row.addStretch(1)
        self.lay.addSpacing(16)
        self.lay.addLayout(row)
        self.local.set_selected(True)

        self.lay.addSpacing(14)
        note = dark_label(
            "A cloud option is planned for machines too slow to run the model "
            "well, and it will be the only part that ever costs money. "
            "Everything local stays free.", 11, 400, D_INK_SOFT)
        self.lay.addLayout(centred(note, 470))
        self.lay.addStretch(1)

        go = DarkButton("Continue")
        go.clicked.connect(self.guide.next_step)
        self.lay.addWidget(go)

    def _choose(self, key: str) -> None:
        self.local.set_selected(key == "local")
        self.cloud.set_selected(key == "cloud")


class ShortcutStep(Step):
    progress = 1.0

    def build(self) -> None:
        self.heading("Try the shortcut")

        self.press_row = QtWidgets.QHBoxLayout()
        self.press_row.setSpacing(6)
        self.press_row.addWidget(dark_label("Press", 12.5, 400, D_INK_MID))
        self._caps: list[QtWidgets.QWidget] = []
        self.press_row.addStretch(1)
        self.lay.addLayout(self.press_row)

        self.change = DarkButton("Change shortcut", "link")
        self.change.clicked.connect(self._start_capture)
        self.lay.addWidget(self.change, 0, QtCore.Qt.AlignLeft)

        self.catcher = HotkeyCatcher()
        self.catcher.captured.connect(self._apply_hotkey)
        self.catcher.cancelled.connect(self._end_capture)
        self.catcher.hide()
        self.lay.addWidget(self.catcher)

        self.box = QtWidgets.QTextEdit()
        self.box.setPlaceholderText(
            'Say "This is my first recording with Murmur"')
        self.box.setFont(font(13))
        self.box.setMinimumHeight(190)
        self.box.setStyleSheet(
            f"QTextEdit{{background:{D_BG};color:{D_INK};"
            f"border:1.5px solid {D_ACCENT};border-radius:12px;padding:14px;}}")
        self.lay.addSpacing(8)
        self.lay.addWidget(self.box, 1)

        self.state = dark_label("", 11, 400, D_INK_SOFT)
        self.lay.addWidget(self.state)

        self.done = DarkButton("Complete setup")
        self.done.setEnabled(False)
        self.done.clicked.connect(self.guide.finish)
        self.lay.addWidget(self.done)

        self.skip = DarkButton("Skip this and finish", "quiet")
        self.skip.clicked.connect(self.guide.finish)
        self.lay.addWidget(self.skip)
        self._render_caps()

    def _render_caps(self) -> None:
        for cap in self._caps:
            self.press_row.removeWidget(cap)
            cap.deleteLater()
        self._caps = []
        widgets = [KeyCap(name, accent=True)
                   for name in core.hotkey_label()]
        # No wrapping: a line that breaks between the keycaps and the verb
        # leaves the caps floating next to nothing.
        widgets.append(dark_label("to start recording, and again to stop",
                                  12.5, 400, D_INK_MID, wrap=False))
        for i, w in enumerate(widgets):
            self.press_row.insertWidget(1 + i, w)
            self._caps.append(w)

    def _start_capture(self) -> None:
        self.catcher.setText("Press the keys you want ...")
        self.catcher.show()
        self.catcher.setFocus()
        self.change.hide()

    def _end_capture(self) -> None:
        self.catcher.hide()
        self.change.show()
        self.box.setFocus()

    def _apply_hotkey(self, combo: str) -> None:
        self.guide.hotkey_changed.emit(combo)
        self._end_capture()
        self._render_caps()

    def on_enter(self) -> None:
        self.box.setFocus()
        self.state.setText(self.guide.hint)

    def set_hint(self, text: str) -> None:
        self.state.setText(text)

    def on_transcribed(self, text: str) -> None:
        """The transcript is pasted into the box by the ordinary paste path -
        the box has focus, so it arrives there like it would anywhere else.
        This only has to notice that it worked."""
        self.state.setText("That is exactly how it works everywhere else.")
        self.done.setEnabled(True)
        self.skip.hide()


# ── the window ─────────────────────────────────────────────────────────────

class Onboarding(QtWidgets.QWidget):
    mic_test = QtCore.Signal(bool)
    hotkey_changed = QtCore.Signal(str)
    completed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Murmur setup")
        self.setWindowIcon(logo.app_icon())
        self.resize(680, 760)
        self.setMinimumSize(620, 700)
        self.setStyleSheet(f"background:{D_BG};")
        self.hint = ""

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.bar = StepBar()
        holder = QtWidgets.QWidget()
        holder.setStyleSheet(f"background:{D_BG};")
        hl = QtWidgets.QVBoxLayout(holder)
        hl.setContentsMargins(38, 20, 38, 0)
        hl.addWidget(self.bar)
        lay.addWidget(holder)
        self.bar_holder = holder

        self.stack = QtWidgets.QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.steps = [WelcomeStep(self), TrayStep(self), MicStep(self),
                      ModelStep(self), ShortcutStep(self)]
        for step in self.steps:
            self.stack.addWidget(step)
        self._index = 0
        self._show_index(0)
        self._dark_title_bar()

    # ── navigation ──────────────────────────────────────────────────────────

    def _show_index(self, index: int) -> None:
        self.steps[self._index].on_leave()
        self._index = index
        step = self.steps[index]
        self.stack.setCurrentWidget(step)
        self.bar.set_fraction(step.progress)
        # The welcome screen has nothing behind it, so a progress bar reading
        # zero would only say "this will take a while".
        self.bar_holder.setVisible(index > 0)
        step.on_enter()

    def next_step(self) -> None:
        if self._index + 1 < len(self.steps):
            self._show_index(self._index + 1)

    def finish(self) -> None:
        self.steps[self._index].on_leave()
        cfg = core.load_config()
        cfg["onboarded"] = True
        core.save_config(cfg)
        self.completed.emit()
        self.close()

    # ── things the application feeds in ─────────────────────────────────────

    def push_level(self, level: float) -> None:
        for step in self.steps:
            if isinstance(step, MicStep):
                step.push_level(level)

    def on_transcribed(self, text: str) -> None:
        self.steps[-1].on_transcribed(text)

    def set_hint(self, text: str) -> None:
        self.hint = text
        if self._index == len(self.steps) - 1:
            self.steps[-1].set_hint(text)

    def refresh_hotkey(self) -> None:
        self.steps[-1]._render_caps()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Closing the guide early still counts as having seen it; nobody wants
        to be walked through setup twice."""
        self.steps[self._index].on_leave()
        cfg = core.load_config()
        if not cfg.get("onboarded"):
            cfg["onboarded"] = True
            core.save_config(cfg)
            self.completed.emit()
        super().closeEvent(event)

    def _dark_title_bar(self) -> None:
        """Windows draws the title bar, not Qt, and it draws it light unless
        told otherwise - a white strip above a black window."""
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass
