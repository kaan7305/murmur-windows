"""One place for colour, type and the small reusable pieces."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

# ── palette ────────────────────────────────────────────────────────────────
BG = "#F6F6F8"
SURFACE = "#FFFFFF"
LINE = "#E6E6EA"
LINE_SOFT = "#F0F0F3"
INK = "#16161A"
INK_MID = "#55555E"
INK_SOFT = "#8A8A94"
ACCENT = "#4F46E5"
ACCENT_DARK = "#4338CA"
ACCENT_WASH = "#EEF0FE"
GOOD = "#0F8A4D"
GOOD_WASH = "#E9F6EF"
WARN = "#B45309"
WARN_WASH = "#FDF3E3"

# ── dark palette ───────────────────────────────────────────────────────────
# Used by the setup guide and the recording pill, both of which sit on top of
# whatever the user is doing rather than inside the main window. Dark keeps them
# from flashing a bright rectangle over a dim screen, and reads as an overlay
# rather than as another document window.
D_BG = "#141416"
D_SURFACE = "#232326"
D_SURFACE_HI = "#2C2C30"
D_LINE = "#38383D"
D_INK = "#FFFFFF"
D_INK_MID = "#B4B4BC"
D_INK_SOFT = "#87878F"
D_ACCENT = "#74B7F8"
D_ACCENT_HI = "#8DC5FA"
D_ON_ACCENT = "#0B1620"      # near-black; the accent is too light for white
D_MUTED_BTN = "#28414F"      # the quiet second choice under a primary button
D_MUTED_BTN_HI = "#31505F"

TIER_COLOUR = {
    "Fastest": ("#0F8A4D", GOOD_WASH),
    "Fast": ("#0F8A4D", GOOD_WASH),
    "Recommended": (ACCENT, ACCENT_WASH),
    "Accurate": ("#7C3AED", "#F3EDFE"),
    "Most accurate": (WARN, WARN_WASH),
}


# ── text size ──────────────────────────────────────────────────────────────
# Every size in this file and the pages is a point size somebody chose while
# looking at their own screen. This multiplies all of them at once, so a person
# who finds the interface small can say so once instead of losing an argument
# with it. Windows' own display scaling is the right answer when everything is
# too small; this is for when only Murmur is.

#: What the sizes in the code are written against.
SCALE = 1.0

#: Offered on the Sound page. Keep the labels short - they are radio buttons,
#: not documentation.
SCALES = [("Normal", 1.0), ("Large", 1.15), ("Larger", 1.3), ("Largest", 1.5)]


def set_scale(value: float) -> None:
    """Set the multiplier. Call before any widget is built.

    Nothing re-reads this: a QFont is copied into a widget when it is set, so
    changing the scale after the window exists leaves every existing label at
    its old size. The setting therefore says it applies on restart, which is
    honest and costs one relaunch, rather than half-applying and looking broken.
    """
    global SCALE
    try:
        SCALE = min(2.0, max(0.8, float(value)))
    except (TypeError, ValueError):
        SCALE = 1.0


def font(size: float, weight: int = 400) -> QtGui.QFont:
    size = size * SCALE
    f = QtGui.QFont("Segoe UI Variable Display", int(size))
    if not QtGui.QFontInfo(f).exactMatch():
        f = QtGui.QFont("Segoe UI", int(size))
    f.setPointSizeF(size)
    f.setWeight(QtGui.QFont.Weight(weight))
    return f


class Label(QtWidgets.QLabel):
    def __init__(self, text: str = "", size: float = 12.5, weight: int = 400,
                 colour: str = INK, parent=None) -> None:
        super().__init__(text, parent)
        self.setFont(font(size, weight))
        self.setStyleSheet(f"color:{colour}; background:transparent;")


class Card(QtWidgets.QFrame):
    """A white panel with a hairline border - the base of every page."""

    def __init__(self, parent=None, padding: int = 20, radius: int = 14) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"QFrame#card{{background:{SURFACE};border:1px solid {LINE};"
            f"border-radius:{radius}px;}}")
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(padding, padding, padding, padding)
        self._lay.setSpacing(10)

    def body(self) -> QtWidgets.QVBoxLayout:
        return self._lay


class Pill(QtWidgets.QLabel):
    """A small status chip: Recommended, Downloaded, English only."""

    def __init__(self, text: str, fg: str = INK_MID, bg: str = "#F1F1F4",
                 parent=None) -> None:
        super().__init__(text, parent)
        self.setFont(font(9.5, 600))
        self.setStyleSheet(
            f"color:{fg}; background:{bg}; border-radius:8px;"
            f"padding:3px 9px;")
        self.setAlignment(QtCore.Qt.AlignCenter)


class Button(QtWidgets.QPushButton):
    def __init__(self, text: str, kind: str = "primary", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFont(font(10.5, 600))
        self.setMinimumHeight(32)
        styles = {
            "primary": f"""
                QPushButton{{background:{ACCENT};color:#fff;border:none;
                    border-radius:8px;padding:6px 18px;}}
                QPushButton:hover{{background:{ACCENT_DARK};}}
                QPushButton:disabled{{background:#ECECEF;color:{INK_SOFT};}}""",
            "ghost": f"""
                QPushButton{{background:transparent;color:{INK};
                    border:1px solid {LINE};border-radius:8px;padding:6px 18px;}}
                QPushButton:hover{{background:#F4F4F7;}}
                QPushButton:disabled{{color:{INK_SOFT};}}""",
            "quiet": f"""
                QPushButton{{background:transparent;color:{INK_MID};
                    border:none;border-radius:8px;padding:6px 10px;}}
                QPushButton:hover{{background:#F1F1F4;color:{INK};}}""",
        }
        self.setStyleSheet(styles.get(kind, styles["primary"]))


class DarkButton(QtWidgets.QPushButton):
    """The full-width buttons of the setup guide.

    Three kinds, in descending loudness: the thing to do, the thing to do
    instead, and the way out that should not compete with either.
    """

    def __init__(self, text: str, kind: str = "primary", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFont(font(13, 600))
        self.setMinimumHeight(52)
        styles = {
            "primary": f"""
                QPushButton{{background:{D_ACCENT};color:{D_ON_ACCENT};
                    border:none;border-radius:12px;padding:10px 20px;}}
                QPushButton:hover{{background:{D_ACCENT_HI};}}
                QPushButton:disabled{{background:#2A3138;color:#5C626A;}}""",
            "muted": f"""
                QPushButton{{background:{D_MUTED_BTN};color:{D_INK};
                    border:none;border-radius:12px;padding:10px 20px;}}
                QPushButton:hover{{background:{D_MUTED_BTN_HI};}}""",
            "quiet": f"""
                QPushButton{{background:transparent;color:{D_INK_SOFT};
                    border:none;padding:6px 12px;}}
                QPushButton:hover{{color:{D_INK_MID};}}""",
            "link": f"""
                QPushButton{{background:transparent;color:{D_ACCENT};
                    border:none;padding:2px 0;text-align:left;}}
                QPushButton:hover{{color:{D_ACCENT_HI};}}""",
        }
        self.setStyleSheet(styles.get(kind, styles["primary"]))
        if kind in ("quiet", "link"):
            self.setMinimumHeight(24)
            self.setFont(font(11.5, 600 if kind == "link" else 400))


class KeyCap(QtWidgets.QLabel):
    """One key, drawn as a key: Ctrl, Space, Esc."""

    def __init__(self, text: str, accent: bool = False, parent=None) -> None:
        super().__init__(text, parent)
        self.setFont(font(10.5, 600))
        self.setAlignment(QtCore.Qt.AlignCenter)
        if accent:
            self.setStyleSheet(
                f"color:{D_ON_ACCENT};background:{D_ACCENT};border-radius:6px;"
                f"padding:4px 10px;")
        else:
            self.setStyleSheet(
                f"color:{D_INK_MID};background:{D_SURFACE_HI};"
                f"border:1px solid {D_LINE};border-radius:6px;padding:3px 9px;")


class StepBar(QtWidgets.QWidget):
    """The progress line across the top of the setup guide.

    Drawn rather than styled because the reference has a soft glow spilling past
    the end of the filled section, and a QProgressBar cannot paint outside its
    own chunk.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self._fraction = 0.0
        self._shown = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._ease)
        self._timer.start(16)

    def set_fraction(self, value: float) -> None:
        self._fraction = max(0.0, min(1.0, value))

    def _ease(self) -> None:
        if abs(self._shown - self._fraction) < 0.002:
            self._shown = self._fraction
            return
        self._shown += (self._fraction - self._shown) * 0.18
        self.update()

    def paintEvent(self, _e) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        h = 4.0
        y = (self.height() - h) / 2

        p.setBrush(QtGui.QColor(D_SURFACE_HI))
        p.drawRoundedRect(QtCore.QRectF(0, y, self.width(), h), h / 2, h / 2)

        w = self.width() * self._shown
        if w <= 0:
            return
        # The glow: the same bar drawn twice more, fatter and nearly clear.
        for spread, alpha in ((5.0, 34), (2.5, 70)):
            c = QtGui.QColor(D_ACCENT)
            c.setAlpha(alpha)
            p.setBrush(c)
            p.drawRoundedRect(
                QtCore.QRectF(0, y - spread / 2, w, h + spread),
                (h + spread) / 2, (h + spread) / 2)
        p.setBrush(QtGui.QColor(D_ACCENT))
        p.drawRoundedRect(QtCore.QRectF(0, y, w, h), h / 2, h / 2)


GRADIENTS = {
    "home": ("#FF9A56", "#F2703A"),
    "models": ("#6366F1", "#8B5CF6"),
    "language": ("#F2B23A", "#E08A18"),
    "sound": ("#34C77B", "#12A05C"),
    "speed": ("#38BDF8", "#0EA5E9"),
    "history": ("#A78BFA", "#7C3AED"),
}


def nav_icon(glyph: str, colour: str = "", size: int = 34) -> QtGui.QIcon:
    """A gradient squircle with a drawn glyph - no icon files needed."""
    a, b = GRADIENTS.get(glyph, (colour or "#8A8A94", colour or "#6B6B70"))
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtCore.Qt.NoPen)
    grad = QtGui.QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QtGui.QColor(a))
    grad.setColorAt(1.0, QtGui.QColor(b))
    p.setBrush(QtGui.QBrush(grad))
    p.drawRoundedRect(QtCore.QRectF(0, 0, size, size), size * 0.28, size * 0.28)

    p.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 1.9,
                        QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    c = size / 2
    if glyph == "home":
        p.drawLine(QtCore.QPointF(c - 7, c), QtCore.QPointF(c, c - 6))
        p.drawLine(QtCore.QPointF(c, c - 6), QtCore.QPointF(c + 7, c))
        p.drawLine(QtCore.QPointF(c - 4.5, c), QtCore.QPointF(c - 4.5, c + 6))
        p.drawLine(QtCore.QPointF(c + 4.5, c), QtCore.QPointF(c + 4.5, c + 6))
        p.drawLine(QtCore.QPointF(c - 4.5, c + 6), QtCore.QPointF(c + 4.5, c + 6))
    elif glyph == "models":
        for i, h in enumerate((5, 9, 6.5)):
            x = c - 6 + i * 6
            p.drawLine(QtCore.QPointF(x, c - h), QtCore.QPointF(x, c + h))
    elif glyph == "sound":
        p.drawArc(QtCore.QRectF(c - 5, c - 7, 10, 11), 180 * 16, 180 * 16)
        p.drawLine(QtCore.QPointF(c, c + 4), QtCore.QPointF(c, c + 7))
        p.setBrush(QtGui.QColor("#FFFFFF"))
        p.drawRoundedRect(QtCore.QRectF(c - 2.5, c - 8, 5, 8), 2.5, 2.5)
    elif glyph == "language":
        # A globe: outline, equator, and one meridian drawn as an ellipse seen
        # edge-on, which is what makes a circle read as a sphere.
        p.drawEllipse(QtCore.QPointF(c, c), 8, 8)
        p.drawEllipse(QtCore.QPointF(c, c), 3.4, 8)
        p.drawLine(QtCore.QPointF(c - 8, c), QtCore.QPointF(c + 8, c))
    elif glyph == "speed":
        # A lightning bolt, for the page that makes things faster.
        p.setBrush(QtGui.QColor("#FFFFFF"))
        p.setPen(QtCore.Qt.NoPen)
        bolt = QtGui.QPolygonF([
            QtCore.QPointF(c + 2.5, c - 8), QtCore.QPointF(c - 5.5, c + 1),
            QtCore.QPointF(c - 0.5, c + 1), QtCore.QPointF(c - 2.5, c + 8),
            QtCore.QPointF(c + 5.5, c - 1), QtCore.QPointF(c + 0.5, c - 1),
        ])
        p.drawPolygon(bolt)
    elif glyph == "history":
        p.drawEllipse(QtCore.QPointF(c, c), 7, 7)
        p.drawLine(QtCore.QPointF(c, c - 3.5), QtCore.QPointF(c, c))
        p.drawLine(QtCore.QPointF(c, c), QtCore.QPointF(c + 3.5, c + 1.5))
    p.end()
    return QtGui.QIcon(pix)
