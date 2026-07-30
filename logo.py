"""The Murmur mark.

Three waveform bars, and then the fourth stroke is a text caret: the sound
turns into a cursor. That is the whole product in one shape.

Everything is drawn in code, so there are no asset files to lose and the mark
is sharp at any size and any DPI.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui

INK = "#16161A"
ACCENT_A = "#6366F1"   # indigo
ACCENT_B = "#8B5CF6"   # violet


def draw_mark(p: QtGui.QPainter, box: QtCore.QRectF, colour: QtGui.QColor) -> None:
    """Draw the mark to fill `box`. Designed on a 64x64 grid and scaled."""
    p.save()
    p.translate(box.left(), box.top())
    s = box.width() / 64.0
    p.scale(s, s)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(colour)

    mid = 32.0
    bar_w = 6.0
    # Three bars, low-high-low: a murmur rather than a shout.
    for x, h in ((13.0, 16.0), (24.0, 30.0), (35.0, 21.0)):
        p.drawRoundedRect(
            QtCore.QRectF(x, mid - h / 2, bar_w, h), bar_w / 2, bar_w / 2)

    # The caret. A stem with serifs top and bottom, the way a text cursor is
    # drawn - so the eye reads "typing" where it expected a fourth bar.
    stem_w, stem_h = 5.0, 30.0
    x = 47.0
    p.drawRoundedRect(
        QtCore.QRectF(x, mid - stem_h / 2, stem_w, stem_h), 2.5, 2.5)
    serif_w, serif_h = 15.0, 4.6
    sx = x + stem_w / 2 - serif_w / 2
    for y in (mid - stem_h / 2 - serif_h * 0.35, mid + stem_h / 2 - serif_h * 0.65):
        p.drawRoundedRect(
            QtCore.QRectF(sx, y, serif_w, serif_h), serif_h / 2, serif_h / 2)
    p.restore()


def mark_pixmap(size: int, colour: str = INK) -> QtGui.QPixmap:
    """The bare mark, no tile. For the sidebar wordmark and the tray."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    draw_mark(p, QtCore.QRectF(0, 0, size, size), QtGui.QColor(colour))
    p.end()
    return pix


def tile_pixmap(size: int, a: str = ACCENT_A, b: str = ACCENT_B) -> QtGui.QPixmap:
    """The app icon: the mark in white on a gradient squircle."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)

    grad = QtGui.QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QtGui.QColor(a))
    grad.setColorAt(1.0, QtGui.QColor(b))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QBrush(grad))
    # ~22% corner radius is the platform squircle proportion.
    p.drawRoundedRect(QtCore.QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    inset = size * 0.19
    draw_mark(p, QtCore.QRectF(inset, inset, size - inset * 2, size - inset * 2),
              QtGui.QColor("#FFFFFF"))
    p.end()
    return pix


def tray_pixmap(size: int, recording: bool = False) -> QtGui.QPixmap:
    """Tray icon. Turns red while listening so the state is visible at a glance."""
    if recording:
        return tile_pixmap(size, "#F0563E", "#E8483A")
    return tile_pixmap(size)


def app_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(tile_pixmap(s))
    return icon


def write_ico(path: str) -> None:
    """A multi-resolution .ico, for the executable, the installer and the
    shortcut.

    Assembled by hand rather than through QImageWriter, which writes a single
    image per file. Windows picks the entry matching the size it is drawing, so
    a one-size icon looks soft everywhere except that size - and the 16px taskbar
    and 256px file view are both places people actually see it. Each entry is a
    PNG, which every Windows since Vista reads.
    """
    import struct

    sizes = [16, 24, 32, 48, 64, 128, 256]
    blobs = []
    for s in sizes:
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.WriteOnly)
        tile_pixmap(s).save(buf, "PNG")
        blobs.append(bytes(buf.data()))

    offset = 6 + 16 * len(sizes)          # header, then one entry per image
    directory = b""
    for s, blob in zip(sizes, blobs):
        # 256 is stored as 0: the field is one byte and 256 does not fit.
        directory += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32,
                                 len(blob), offset)
        offset += len(blob)

    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        f.write(directory)
        for blob in blobs:
            f.write(blob)
