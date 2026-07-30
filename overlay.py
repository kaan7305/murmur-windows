"""The recording pill: a floating panel that appears while Murmur listens.

The hard requirement is that it must never take focus. Whatever the user was
typing into has to stay focused, because that is where the transcript gets
pasted a moment later.

Dark on purpose. It appears over whatever is already on screen - an editor, a
terminal, a video call - and a bright panel there reads as a dialog demanding an
answer rather than as a transient indicator.
"""
from __future__ import annotations

import collections
import ctypes

from PySide6 import QtCore, QtGui, QtWidgets

CARD_BG = QtGui.QColor(28, 28, 31, 246)
CARD_EDGE = QtGui.QColor(255, 255, 255, 26)
INK = QtGui.QColor(245, 245, 247)
INK_SOFT = QtGui.QColor(154, 154, 162)
WAVE = QtGui.QColor(232, 232, 236)


def deny_activation(widget: QtWidgets.QWidget) -> None:
    """Belt and braces on top of WA_ShowWithoutActivating: WS_EX_NOACTIVATE
    tells Windows this window must never become the foreground one, so the app
    the user was typing into keeps focus and receives the paste.

    Both floating windows depend on this, and the pill depends on it hardest:
    it is the one you click, and a click that stole focus would move the paste
    target to Murmur itself.
    """
    try:
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = int(widget.winId())
        u32 = ctypes.windll.user32
        cur = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           cur | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        pass


class Waveform(QtWidgets.QWidget):
    """A mirrored bar meter fed by the audio callback.

    Levels arrive far faster than the eye needs, so they are kept in a ring
    buffer and the widget repaints on its own timer instead of per sample.

    At rest every bar collapses to a dot rather than to nothing: a flat line
    reads as "broken", a row of dots reads as "listening, hearing silence".
    """

    BARS = 68

    def __init__(self, parent=None, colour: QtGui.QColor | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(58)
        self._colour = colour or WAVE
        self._levels: collections.deque[float] = collections.deque(
            [0.0] * self.BARS, maxlen=self.BARS)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(33)  # ~30fps

    def push(self, level: float) -> None:
        self._levels.append(max(0.0, min(1.0, level)))

    def reset(self) -> None:
        self._levels.extend([0.0] * self.BARS)

    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        n = len(self._levels)
        if not n:
            return
        slot = w / n
        bar_w = max(2.0, slot * 0.44)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self._colour)
        for i, level in enumerate(self._levels):
            amp = max(bar_w / 2, level * (h * 0.46))
            x = i * slot + (slot - bar_w) / 2
            p.drawRoundedRect(
                QtCore.QRectF(x, mid - amp, bar_w, amp * 2),
                bar_w / 2, bar_w / 2)


class KeyHint(QtWidgets.QLabel):
    """A small keycap, e.g. the 'Ctrl' and 'Space' next to Record."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 5px;
                padding: 2px 7px;
                color: #D8D8DE;
                font-size: 11px;
                font-weight: 600;
            }
        """)


class RecordingOverlay(QtWidgets.QWidget):
    stop_requested = QtCore.Signal()
    cancel_requested = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool            # keeps it off the taskbar and alt-tab
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setFixedSize(560, 138)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 18)   # room for the shadow

        card = QtWidgets.QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(f"""
            QFrame#card {{
                background: rgba({CARD_BG.red()},{CARD_BG.green()},
                                 {CARD_BG.blue()},0.97);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 16px;
            }}
        """)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 10)
        shadow.setColor(QtGui.QColor(0, 0, 0, 130))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        inner = QtWidgets.QVBoxLayout(card)
        inner.setContentsMargins(18, 12, 18, 12)
        inner.setSpacing(6)

        # The waveform and any message occupy the same space: the meter answers
        # "is it hearing me", the message answers "what happened", and they are
        # never both the useful thing to show.
        self.stack = QtWidgets.QStackedLayout()
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.wave = Waveform(card)
        self.message = QtWidgets.QLabel("")
        self.message.setAlignment(QtCore.Qt.AlignCenter)
        self.message.setStyleSheet(
            f"color:rgb({INK_SOFT.red()},{INK_SOFT.green()},{INK_SOFT.blue()});"
            f"background:transparent;font-size:13px;")
        self.stack.addWidget(self.wave)
        self.stack.addWidget(self.message)
        holder = QtWidgets.QWidget()
        holder.setLayout(self.stack)
        holder.setStyleSheet("background:transparent;")
        inner.addWidget(holder)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(7)

        self.device_label = QtWidgets.QLabel("Default")
        self.device_label.setStyleSheet(
            f"color:rgb({INK_SOFT.red()},{INK_SOFT.green()},{INK_SOFT.blue()});"
            f"font-size:12px;background:transparent;")
        row.addWidget(self._mic_icon())
        row.addWidget(self.device_label)
        row.addStretch(1)

        self.stop_btn = self._flat_button("Stop")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        row.addWidget(self.stop_btn)
        self._caps: list[KeyHint] = []
        self._caps_at = row.count()
        row.addSpacing(12)

        self.cancel_btn = self._flat_button("Close")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        row.addWidget(self.cancel_btn)
        row.addWidget(KeyHint("Esc"))

        self._row = row
        inner.addLayout(row)
        self.set_hotkey(["Ctrl", "Space"])

    # ── pieces ──────────────────────────────────────────────────────────────

    def set_hotkey(self, caps: list[str]) -> None:
        """Show the keys that actually stop the recording, whatever they are."""
        for cap in self._caps:
            self._row.removeWidget(cap)
            cap.deleteLater()
        self._caps = []
        for i, name in enumerate(caps):
            cap = KeyHint(name)
            self._row.insertWidget(self._caps_at + i, cap)
            self._caps.append(cap)

    def _mic_icon(self) -> QtWidgets.QLabel:
        pix = QtGui.QPixmap(16, 16)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(INK_SOFT, 1.4))
        p.drawRoundedRect(QtCore.QRectF(5.5, 2, 5, 8), 2.5, 2.5)
        p.drawArc(QtCore.QRectF(3.5, 6, 9, 7), 180 * 16, 180 * 16)
        p.drawLine(QtCore.QPointF(8, 12.5), QtCore.QPointF(8, 14.5))
        p.end()
        lbl = QtWidgets.QLabel()
        lbl.setPixmap(pix)
        lbl.setStyleSheet("background: transparent;")
        return lbl

    def _flat_button(self, text: str) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setFlat(True)
        b.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: #E4E4E9; font-size: 12.5px; padding: 3px 2px;
            }
            QPushButton:hover { color: #FFFFFF; }
        """)
        return b

    # ── behaviour ───────────────────────────────────────────────────────────

    def set_device(self, name: str) -> None:
        self.device_label.setText(name[:46])

    def push_level(self, level: float) -> None:
        self.wave.push(level)

    def show_centred(self) -> None:
        self.wave.reset()
        self.stack.setCurrentWidget(self.wave)
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.bottom() - self.height() - 90,
        )
        self.show()
        self.raise_()
        self._deny_activation()

    def flash(self, text: str, msec: int = 1600) -> None:
        """Say something and then get out of the way.

        Used for the outcomes that produce no text - silence, a clip too short -
        which otherwise leave the pill vanishing with no explanation of why
        nothing was pasted.
        """
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)
        self.show()
        self.raise_()
        self._deny_activation()
        QtCore.QTimer.singleShot(msec, self.hide)

    def _deny_activation(self) -> None:
        deny_activation(self)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancel_requested.emit()
        else:
            super().keyPressEvent(event)


# ── the idle pill ──────────────────────────────────────────────────────────

class Dots(QtWidgets.QWidget):
    """The waveform at rest: the same row of dots the recording pill shows when
    it is hearing silence, which is exactly what Murmur is doing while it waits
    for the shortcut. Same shape at rest and in use, so the pill growing into
    the recording panel reads as one object rather than two."""

    COUNT = 6

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._lift = 0.0        # 0 at rest, 1 when the pointer is over the pill
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.valueChanged.connect(self._on_step)

    def _on_step(self, v) -> None:
        self._lift = float(v)
        self.update()

    def set_lifted(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._lift)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        slot = w / self.COUNT
        bar_w = 3.0
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(WAVE)
        # Hovering raises the middle bars a little: enough to say "this is a
        # control", not so much that it looks like it started listening.
        shape = (0.35, 0.75, 1.0, 0.85, 0.6, 0.3)
        for i in range(self.COUNT):
            amp = bar_w / 2 + self._lift * shape[i] * (h * 0.30)
            x = i * slot + (slot - bar_w) / 2
            p.drawRoundedRect(QtCore.QRectF(x, mid - amp, bar_w, amp * 2),
                              bar_w / 2, bar_w / 2)


class IdlePill(QtWidgets.QWidget):
    """A small always-there handle, floating above other windows.

    It answers the question the tray icon answers badly - is Murmur running,
    and where do I press - without occupying a corner of the screen the size of
    a dialog. Click it to dictate, drag it anywhere, right-click for the menu.

    It hides itself while recording: the full pill takes over then, and two
    Murmur panels on screen at once would be one too many.
    """

    clicked = QtCore.Signal()
    menu_requested = QtCore.Signal(QtCore.QPoint)
    moved = QtCore.Signal(int, int)

    PAD = 13                    # room for the shadow to fall into
    CARD = QtCore.QSize(76, 30)
    DRAG_SLOP = 4               # a click with a shaky hand is still a click

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        # An open hand, not a pointing finger. The pill was draggable from the
        # start and nobody could tell: a finger says "press me here", and a
        # thing that says press-me-here reads as fixed in place. The hand says
        # pick me up, and closes while you are carrying it.
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setFixedSize(self.CARD.width() + self.PAD * 2,
                          self.CARD.height() + self.PAD * 2)
        self.setWindowOpacity(0.72)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("pill")
        self.card.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._style(hover=False)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        inner = QtWidgets.QVBoxLayout(self.card)
        inner.setContentsMargins(14, 8, 14, 8)
        self.dots = Dots(self.card)
        inner.addWidget(self.dots)

        self._press: QtCore.QPoint | None = None
        self._origin: QtCore.QPoint | None = None
        self._dragged = False
        self.set_hotkey(["Ctrl", "Space"])

    def _style(self, hover: bool) -> None:
        edge = 0.22 if hover else 0.10
        self.card.setStyleSheet(f"""
            QFrame#pill {{
                background: rgba({CARD_BG.red()},{CARD_BG.green()},
                                 {CARD_BG.blue()},0.97);
                border: 1px solid rgba(255,255,255,{edge});
                border-radius: {self.CARD.height() // 2}px;
            }}
        """)

    def set_hotkey(self, caps: list[str]) -> None:
        self.setToolTip(
            f"Murmur - press {' + '.join(caps)} to dictate\n"
            f"Click to start, drag to move, right-click for the menu")

    # ── placement ───────────────────────────────────────────────────────────

    def place(self, saved: tuple[int, int] | None = None) -> None:
        """Put the pill back where it was left, or somewhere sensible.

        A saved position is only honoured if it still lands on a screen: an
        external monitor that has been unplugged since would otherwise strand
        the pill in space, with no way to get it back short of editing the
        config file by hand.
        """
        if saved is not None:
            point = QtCore.QPoint(int(saved[0]), int(saved[1]))
            screen = QtGui.QGuiApplication.screenAt(
                point + QtCore.QPoint(self.width() // 2, self.height() // 2))
            if screen is not None:
                self.move(self._on_screen(point))
                return
        area = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.center().x() - self.width() // 2,
                  area.bottom() - self.height() - 10)

    def _on_screen(self, point: QtCore.QPoint) -> QtCore.QPoint:
        """Keep the pill catchable.

        Dragged against an edge it may hang off it - that is the user's call,
        and one corner of the screen is a perfectly good place to park it. What
        it may not do is go so far that there is nothing left to grab: an
        unreachable pill can only be recovered by editing config.json, which is
        not a thing anyone should have to discover.

        Clamped against the whole virtual desktop rather than one screen, so it
        can still be carried across to a second monitor.
        """
        span = QtCore.QRect()
        for screen in QtGui.QGuiApplication.screens():
            span = span.united(screen.availableGeometry())
        grab = self.CARD.height()          # roughly a thumb's worth of pill
        x = max(span.left() - self.width() + grab + self.PAD,
                min(point.x(), span.right() - grab - self.PAD))
        y = max(span.top() - self.PAD,
                min(point.y(), span.bottom() - grab - self.PAD))
        return QtCore.QPoint(x, y)

    # ── mouse ───────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragged = False
            self.setCursor(QtCore.Qt.ClosedHandCursor)
        elif event.button() == QtCore.Qt.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._press is None or self._origin is None:
            return
        delta = event.globalPosition().toPoint() - self._press
        if not self._dragged and delta.manhattanLength() < self.DRAG_SLOP:
            return
        self._dragged = True
        self.move(self._on_screen(self._origin + delta))

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return
        self._press = self._origin = None
        self.setCursor(QtCore.Qt.OpenHandCursor)
        if self._dragged:
            self.moved.emit(self.x(), self.y())
        else:
            self.clicked.emit()

    def enterEvent(self, _event) -> None:
        self.setWindowOpacity(1.0)
        self._style(hover=True)
        self.dots.set_lifted(True)

    def leaveEvent(self, _event) -> None:
        self.setWindowOpacity(0.72)
        self._style(hover=False)
        self.dots.set_lifted(False)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.raise_()
        deny_activation(self)
