"""Murmur's main window: a sidebar and a stack of pages."""
from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtWidgets

import history
import hotkeys
import logo
import murmur as core
import stats as stats_mod
import startup
import theme
from theme import (ACCENT, ACCENT_WASH, BG, GOOD, INK, INK_MID, INK_SOFT,
                   LINE, LINE_SOFT, SCALES, SURFACE, Button, Card, Label, font,
                   nav_icon)


def scroll_area(inner: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    area = QtWidgets.QScrollArea()
    area.setWidget(inner)
    area.setWidgetResizable(True)
    area.setFrameShape(QtWidgets.QFrame.NoFrame)
    area.setStyleSheet(
        f"QScrollArea{{background:{BG};}} QWidget{{background:{BG};}}"
        f"QScrollBar:vertical{{background:transparent;width:10px;margin:4px;}}"
        f"QScrollBar::handle:vertical{{background:#D5D5DC;border-radius:5px;"
        f"min-height:40px;}} QScrollBar::add-line,QScrollBar::sub-line{{height:0;}}")
    return area


def page_header(title: str, subtitle: str) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    lay.addWidget(Label(title, 20, 700, INK))
    sub = Label(subtitle, 11.5, 400, INK_SOFT)
    sub.setWordWrap(True)
    lay.addWidget(sub)
    return w


# ── the microphone picker ──────────────────────────────────────────────────

class DeviceSelector(QtWidgets.QComboBox):
    """Choose the microphone, and have that choice actually take effect.

    Every instance writes the same setting and reloads the others, because the
    picker exists twice - once in the header, once on the Sound page - and two
    controls disagreeing about which microphone is in use is worse than having
    only one of them.
    """

    #: every live selector, so a change in one is reflected in the rest
    _instances: list["DeviceSelector"] = []

    changed = QtCore.Signal()

    def __init__(self, compact: bool = True) -> None:
        super().__init__()
        self.setFont(font(11 if compact else 11.5))
        self.setMinimumHeight(28 if compact else 36)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._compact = compact
        if compact:
            self.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                               QtWidgets.QSizePolicy.Fixed)
        else:
            self.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.setStyleSheet(
            f"QComboBox{{border:1px solid {'transparent' if compact else LINE};"
            f"border-radius:8px;padding:3px 8px;background:transparent;"
            f"color:{INK_MID};}}"
            f"QComboBox:hover{{background:#F1F1F4;}}"
            f"QComboBox::drop-down{{border:none;width:20px;}}"
            f"QComboBox QAbstractItemView{{border:1px solid {LINE};"
            f"background:{SURFACE};color:{INK};padding:4px;"
            f"selection-background-color:{ACCENT_WASH};selection-color:{INK};"
            f"outline:0;}}"
            if compact else
            f"QComboBox{{border:1px solid {LINE};border-radius:9px;"
            f"padding:6px 12px;background:{SURFACE};color:{INK};}}"
            f"QComboBox::drop-down{{border:none;width:26px;}}"
            f"QComboBox QAbstractItemView{{border:1px solid {LINE};"
            f"background:{SURFACE};color:{INK};"
            f"selection-background-color:{ACCENT_WASH};selection-color:{INK};"
            f"outline:0;}}")
        DeviceSelector._instances.append(self)
        self.destroyed.connect(lambda: self._forget())
        self.reload()
        self.currentIndexChanged.connect(self._on_pick)

    def _forget(self) -> None:
        if self in DeviceSelector._instances:
            DeviceSelector._instances.remove(self)

    # Qt sizes a combo box to its widest entry, which for a list of Windows
    # audio devices is a fifty-character string nobody selected. In the header
    # that leaves a wide box with the chosen name floating at its left edge,
    # reading as though the microphone were part of the page title. Size to
    # what is actually showing instead.

    MAX_COMPACT_WIDTH = 300

    def sizeHint(self) -> QtCore.QSize:
        hint = super().sizeHint()
        if not self._compact:
            return hint
        width = self.fontMetrics().horizontalAdvance(self.currentText()) + 46
        return QtCore.QSize(min(width, self.MAX_COMPACT_WIDTH), hint.height())

    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint() if self._compact else super().minimumSizeHint()

    def _fit(self, label: str) -> str:
        """Windows audio device names run to seventy characters and say the
        same thing after the first thirty. Shortened with an ellipsis in the
        header, where a name cut off mid-word looks like a rendering fault;
        the full name is on the tooltip and on the Sound page."""
        if not self._compact or len(label) <= 36:
            return label
        return label[:35].rstrip() + "…"

    def reload(self) -> None:
        """Rebuild the list without letting the rebuild look like a choice."""
        self.blockSignals(True)
        self.clear()
        saved = core.load_config().get("device")

        self.addItem("System default", "")
        for d in core.input_devices():
            label = f"{d['name']}   (default)" if d["default"] else d["name"]
            self.addItem(self._fit(label), d["name"])
            self.setItemData(self.count() - 1, d["name"],
                             QtCore.Qt.ToolTipRole)

        wanted = 0
        if saved:
            for i in range(self.count()):
                if self.itemData(i) == saved:
                    wanted = i
                    break
            else:
                # Saved but not present: keep it visible and say so, rather
                # than silently jumping the selection to something else.
                self.addItem(f"{saved}   (not connected)", saved)
                wanted = self.count() - 1
        self.setCurrentIndex(wanted)
        self.setToolTip(self.currentData() or "The microphone Windows prefers")
        self.blockSignals(False)
        self.updateGeometry()       # the width follows the selected name

    def _on_pick(self, _index: int) -> None:
        cfg = core.load_config()
        cfg["device"] = self.currentData() or ""
        core.save_config(cfg)
        self.setToolTip(self.currentData() or "The microphone Windows prefers")
        self.updateGeometry()
        for other in DeviceSelector._instances:
            if other is not self:
                other.reload()
        self.changed.emit()


# ── home ───────────────────────────────────────────────────────────────────

class StatTile(QtWidgets.QWidget):
    def __init__(self, value: str, caption: str) -> None:
        super().__init__()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.value = Label(value, 21, 700, INK)
        lay.addWidget(self.value)
        self.caption = Label(caption, 10.5, 400, INK_SOFT)
        lay.addWidget(self.caption)


class ActionRow(QtWidgets.QWidget):
    """One line of the Get started list: a glyph, a heading, and what it does.

    Clickable when there is somewhere to go. The keys on the right are the
    live shortcut, not a picture of one, so this stays true after someone
    changes it.
    """

    clicked = QtCore.Signal()

    def __init__(self, glyph: str, title: str, body: str,
                 keys: list | None = None, target: bool = True) -> None:
        super().__init__()
        self.setObjectName("row")
        self._target = target
        if target:
            self.setCursor(QtCore.Qt.PointingHandCursor)
        self._restyle(False)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 9, 10, 9)
        row.setSpacing(14)

        art = QtWidgets.QLabel()
        art.setPixmap(row_glyph(glyph))
        art.setFixedWidth(26)
        art.setAlignment(QtCore.Qt.AlignCenter)
        art.setStyleSheet("background:transparent;")
        row.addWidget(art, 0, QtCore.Qt.AlignVCenter)

        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(Label(title, 13.5, 600, INK))
        # No empty second line. A blank label still claims its height, which is
        # how rows that lost their explanatory text kept the hole it left.
        if body:
            sub = Label(body, 11.5, 400, INK_SOFT)
            sub.setWordWrap(True)
            col.addWidget(sub)
        row.addLayout(col, 1)

        self._row = row
        self._keys_at = row.count()
        self._keys: list[QtWidgets.QWidget] = []
        self.set_keys(keys or [])

    def set_keys(self, names: list) -> None:
        for k in getattr(self, "_keys", []):
            self._row.removeWidget(k)
            k.deleteLater()
        self._keys = []
        for i, name in enumerate(names):
            cap = Label(name, 10.5, 600, INK_MID)
            cap.setAlignment(QtCore.Qt.AlignCenter)
            cap.setStyleSheet(
                f"color:{INK_MID};background:#F1F1F4;border:1px solid {LINE};"
                f"border-radius:6px;padding:4px 9px;")
            self._row.insertWidget(self._keys_at + i, cap,
                                   0, QtCore.Qt.AlignVCenter)
            self._keys.append(cap)

    def _restyle(self, hover: bool) -> None:
        bg = "#F4F4F7" if (hover and self._target) else "transparent"
        self.setStyleSheet(
            f"QWidget#row{{background:{bg};border-radius:10px;}}")

    def enterEvent(self, _e) -> None:
        self._restyle(True)

    def leaveEvent(self, _e) -> None:
        self._restyle(False)

    def mousePressEvent(self, _e) -> None:
        if self._target:
            self.clicked.emit()


def row_glyph(kind: str, size: int = 22) -> QtGui.QPixmap:
    """The small line drawings down the left of the Get started list."""
    ratio = 2
    pix = QtGui.QPixmap(size * ratio, size * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(QtGui.QColor(INK_MID), 1.7, QtCore.Qt.SolidLine,
                        QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
    c = size / 2
    if kind == "record":
        p.drawEllipse(QtCore.QPointF(c, c), 8, 8)
        p.setBrush(QtGui.QColor(INK_MID))
        p.drawEllipse(QtCore.QPointF(c, c), 3.4, 3.4)
    elif kind == "keyboard":
        p.drawRoundedRect(QtCore.QRectF(c - 9, c - 6, 18, 12), 2.5, 2.5)
        for x in (-5, -1, 3):
            p.drawLine(QtCore.QPointF(c + x, c - 2), QtCore.QPointF(c + x, c - 2))
        p.drawLine(QtCore.QPointF(c - 4, c + 3), QtCore.QPointF(c + 4, c + 3))
    elif kind == "mic":
        p.drawRoundedRect(QtCore.QRectF(c - 3, c - 9, 6, 11), 3, 3)
        p.drawArc(QtCore.QRectF(c - 6.5, c - 4, 13, 11), 180 * 16, 180 * 16)
        p.drawLine(QtCore.QPointF(c, c + 6), QtCore.QPointF(c, c + 9))
    elif kind == "globe":
        p.drawEllipse(QtCore.QPointF(c, c), 8.5, 8.5)
        p.drawEllipse(QtCore.QPointF(c, c), 3.6, 8.5)   # the meridian
        p.drawLine(QtCore.QPointF(c - 8.5, c), QtCore.QPointF(c + 8.5, c))
    elif kind == "model":
        for i, h in enumerate((4, 8, 6)):
            x = c - 6 + i * 6
            p.drawLine(QtCore.QPointF(x, c - h), QtCore.QPointF(x, c + h))
    elif kind == "bolt":
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(INK_MID))
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(c + 1.5, c - 9), QtCore.QPointF(c - 6, c + 1),
            QtCore.QPointF(c - 1, c + 1), QtCore.QPointF(c - 1.5, c + 9),
            QtCore.QPointF(c + 6, c - 1), QtCore.QPointF(c + 1, c - 1),
        ]))
    p.end()
    return pix


class HomePage(QtWidgets.QWidget):
    #: name of the page a Get started row wants opened. A name rather than an
    #: index: indices shift the moment a page is added, and did.
    navigate = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        inner = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(30, 24, 30, 30)
        lay.setSpacing(18)

        # What the week looked like. Kept on disk, so these are not four zeroes
        # that reset every time the application is restarted.
        stats = Card(padding=20)
        srow = QtWidgets.QHBoxLayout()
        srow.setSpacing(0)
        self.t_speed = StatTile("0 WPM", "Average speed")
        self.t_words = StatTile("0", "Words this week")
        self.t_apps = StatTile("0", "Apps used")
        self.t_saved = StatTile("0 min", "Saved this week")
        self.t_saved.caption.setToolTip(
            f"Time these words would have taken to type at "
            f"{stats_mod.TYPING_WPM:.0f} words per minute, less the time spent "
            f"dictating them.")
        for i, tile in enumerate((self.t_speed, self.t_words,
                                  self.t_apps, self.t_saved)):
            srow.addWidget(tile, 1)
            if i < 3:
                sep = QtWidgets.QFrame()
                sep.setFrameShape(QtWidgets.QFrame.VLine)
                sep.setStyleSheet(f"color:{LINE_SOFT};")
                srow.addWidget(sep)
        stats.body().addLayout(srow)
        lay.addWidget(stats)

        lay.addWidget(Label("Get started", 15, 700, INK))

        rows = Card(padding=10)
        rows.body().setSpacing(2)
        self.row_record = ActionRow(
            "record", "Start recording",
            "Put the cursor anywhere, press the shortcut, and speak.",
            core.hotkey_label(), target=False)
        rows.body().addWidget(self.row_record)

        for glyph, title, page in [
            ("keyboard", "Change the shortcut", "Sound"),
            ("globe", "Set your language", "Language"),
            ("mic", "Choose your microphone", "Sound"),
            ("model", "Pick a model", "Models library"),
            ("bolt", "Use the graphics card", "Speed"),
        ]:
            row = ActionRow(glyph, title, "")
            row.clicked.connect(lambda p=page: self.navigate.emit(p))
            rows.body().addWidget(row)
        lay.addWidget(rows)

        privacy = Card(padding=18)
        prow = QtWidgets.QHBoxLayout()
        prow.setSpacing(12)
        dot = QtWidgets.QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{GOOD};border-radius:4px;")
        prow.addWidget(dot, 0, QtCore.Qt.AlignVCenter)
        note = Label("Everything runs on this computer.", 11.5, 400, INK_MID)
        note.setWordWrap(True)
        prow.addWidget(note, 1)
        privacy.body().addLayout(prow)
        lay.addWidget(privacy)

        lay.addStretch(1)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(inner))
        self.refresh()

    def refresh_hotkey(self) -> None:
        self.row_record.set_keys(core.hotkey_label())

    def refresh(self, *_ignored) -> None:
        """Redraw the week's figures. Takes and ignores arguments so the old
        per-session call sites keep working."""
        s = stats_mod.summary()
        self.t_speed.value.setText(f"{s['wpm']} WPM")
        self.t_words.value.setText(f"{s['words']:,}")
        self.t_apps.value.setText(str(s["apps"]))
        self.t_saved.value.setText(stats_mod.format_saved(s["saved_minutes"]))


# ── models ─────────────────────────────────────────────────────────────────

class ModelCard(Card):
    """One row: name, what it costs you, what it gives you, and the button.

    Deliberately a row and not a panel. Choosing between six models means
    comparing them, and you cannot compare things you have to scroll between.
    """

    chosen = QtCore.Signal(str)

    def __init__(self, name: str, meta: dict, current: bool) -> None:
        super().__init__(padding=13)
        self.name = name
        if current:
            self.setStyleSheet(
                f"QFrame#card{{background:{SURFACE};border:1.6px solid {ACCENT};"
                f"border-radius:14px;}}")

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(18)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(1)
        title = Label(meta["title"], 14, 700, ACCENT if current else INK)
        left.addWidget(title)
        left.addWidget(Label(meta["note"], 11.5, 400, INK_SOFT))
        row.addLayout(left, 1)

        for value in (meta["size"], meta["lang"]):
            col = Label(value, 11.5, 500, INK_MID)
            col.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
            col.setFixedWidth(104)
            row.addWidget(col)

        downloaded = core.is_downloaded(name)
        self.btn = Button(
            "In use" if current else ("Use" if downloaded else "Download"),
            "ghost")
        self.btn.setEnabled(not current)
        self.btn.setFixedWidth(104)
        self.btn.clicked.connect(lambda: self.chosen.emit(self.name))
        row.addWidget(self.btn)
        self.body().addLayout(row)


class ModelsPage(QtWidgets.QWidget):
    model_changed = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._inner = QtWidgets.QWidget()
        self._lay = QtWidgets.QVBoxLayout(self._inner)
        self._lay.setContentsMargins(30, 22, 30, 24)
        self._lay.setSpacing(8)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(self._inner))
        self.reload()

    def reload(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


        current = core.resolve_model()
        for name, meta in core.MODELS.items():
            card = ModelCard(name, meta, name == current)
            card.chosen.connect(self._choose)
            self._lay.addWidget(card)

        used = sum(core.disk_used(n) for n in core.MODELS)
        self._lay.addWidget(Label(f"{used:.1f} GB on disk", 10.5, 400, INK_SOFT))
        self._lay.addStretch(1)

    def _choose(self, name: str) -> None:
        cfg = core.load_config()
        cfg["model"] = name
        core.save_config(cfg)
        self.model_changed.emit(name)
        self.reload()


# ── sound ──────────────────────────────────────────────────────────────────

class LevelBar(QtWidgets.QWidget):
    """Live input meter, so you can see the microphone is working."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(10)
        self._level = 0.0
        self._peak = 0.0
        t = QtCore.QTimer(self)
        t.timeout.connect(self._decay)
        t.start(60)

    def set_level(self, v: float) -> None:
        self._level = max(0.0, min(1.0, v))
        self._peak = max(self._peak, self._level)
        self.update()

    def _decay(self) -> None:
        self._level *= 0.72
        self._peak *= 0.985
        self.update()

    def paintEvent(self, _e) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        r = self.rect()
        p.setBrush(QtGui.QColor("#ECECF0"))
        p.drawRoundedRect(r, 5, 5)
        if self._level > 0.01:
            w = int(r.width() * self._level)
            colour = "#E8483A" if self._level > 0.92 else ACCENT
            p.setBrush(QtGui.QColor(colour))
            p.drawRoundedRect(QtCore.QRect(0, 0, w, r.height()), 5, 5)
        if self._peak > 0.02:
            x = int(r.width() * self._peak)
            p.setBrush(QtGui.QColor(INK_SOFT))
            p.drawRect(QtCore.QRect(max(0, x - 2), 0, 2, r.height()))


class ShortcutField(QtWidgets.QPushButton):
    """Click, then press the combination you want.

    The same capture rules as the setup guide - they live in hotkeys.py, so
    this and the guide cannot drift apart on what counts as a usable key.
    """

    captured = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFont(font(11.5, 600))
        self.setMinimumHeight(36)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._listening = False
        self.clicked.connect(self._listen)
        self.refresh()

    def refresh(self) -> None:
        self._listening = False
        self.setText("  ".join(core.hotkey_label()))
        self.setStyleSheet(
            f"QPushButton{{border:1px solid {LINE};border-radius:9px;"
            f"padding:6px 16px;background:{SURFACE};color:{INK};}}"
            f"QPushButton:hover{{border-color:{ACCENT};}}")

    def _listen(self) -> None:
        self._listening = True
        self.setText("Press the keys you want ...")
        self.setStyleSheet(
            f"QPushButton{{border:1.5px solid {ACCENT};border-radius:9px;"
            f"padding:6px 16px;background:{ACCENT_WASH};color:{INK};}}")
        self.setFocus()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if not self._listening:
            super().keyPressEvent(event)
            return
        if event.key() == QtCore.Qt.Key_Escape:
            self.refresh()
            return
        combo, reason = hotkeys.combo_from_event(
            event.key(), event.modifiers(), event.text())
        if combo:
            self.captured.emit(combo)
            self.refresh()
        elif reason:
            self.setText(reason)


class SoundPage(QtWidgets.QWidget):
    test_toggled = QtCore.Signal(bool)
    hotkey_changed = QtCore.Signal(str)
    pill_toggled = QtCore.Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        inner = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(30, 26, 30, 30)
        lay.setSpacing(14)


        key = Card()
        key.body().addWidget(Label("Dictation shortcut", 12.5, 600, INK))
        krow = QtWidgets.QHBoxLayout()
        krow.setSpacing(12)
        self.shortcut = ShortcutField()
        self.shortcut.captured.connect(self.hotkey_changed.emit)
        krow.addWidget(self.shortcut)
        khint = Label("Press once to start, again to stop.", 10.5, 400, INK_SOFT)
        krow.addWidget(khint, 1)
        key.body().addLayout(krow)
        lay.addWidget(key)

        dev = Card()
        dev.body().addWidget(Label("Input device", 12.5, 600, INK))
        self.device_box = DeviceSelector(compact=False)
        dev.body().addWidget(self.device_box)

        meter_row = QtWidgets.QHBoxLayout()
        meter_row.setSpacing(12)
        self.test_btn = Button("Test microphone", "ghost")
        self.test_btn.setCheckable(True)
        self.test_btn.toggled.connect(self._on_test)
        meter_row.addWidget(self.test_btn)
        self.meter = LevelBar()
        meter_row.addWidget(self.meter, 1)
        dev.body().addLayout(meter_row)
        self.hint = Label("Press Test and speak — the bar should move.",
                          10.5, 400, INK_SOFT)
        dev.body().addWidget(self.hint)
        lay.addWidget(dev)

        # Without an explicit colour the label inherits the card's palette and
        # renders white on white - invisible.
        check_css = f"""
            QCheckBox {{ color:{INK}; background:transparent; spacing:9px;
                         padding:3px 0; }}
            QCheckBox::indicator {{ width:17px; height:17px; }}
            QCheckBox::indicator:unchecked {{
                border:1.5px solid #C6C6CE; border-radius:5px;
                background:{SURFACE}; }}
            QCheckBox::indicator:checked {{
                border:1.5px solid {ACCENT}; border-radius:5px;
                background:{ACCENT}; }}
        """

        fb = Card()
        fb.body().addWidget(Label("Feedback", 12.5, 600, INK))
        self.beeps = QtWidgets.QCheckBox(
            "Play a sound when recording starts, stops, and text is pasted")
        self.beeps.setFont(font(11.5))
        self.beeps.setStyleSheet(check_css)
        self.beeps.setChecked(core.beeps_enabled())
        self.beeps.toggled.connect(lambda v: self._save("beeps", v))
        fb.body().addWidget(self.beeps)

        self.restore_clip = QtWidgets.QCheckBox(
            "Put the previous clipboard contents back after pasting")
        self.restore_clip.setFont(font(11.5))
        self.restore_clip.setStyleSheet(check_css)
        self.restore_clip.setChecked(core.load_config().get("restore_clip", True))
        self.restore_clip.toggled.connect(
            lambda v: self._save("restore_clip", v))
        fb.body().addWidget(self.restore_clip)
        lay.addWidget(fb)

        # ── on screen and at sign-in ──
        # Both answer the same question - "is Murmur there when I need it" -
        # so they sit in one card rather than being filed under Feedback.
        av = Card()
        av.body().addWidget(Label("Always available", 12.5, 600, INK))

        self.pill = QtWidgets.QCheckBox(
            "Keep a small Murmur pill on screen — click it to dictate")
        self.pill.setFont(font(11.5))
        self.pill.setStyleSheet(check_css)
        self.pill.setChecked(core.pill_enabled())
        self.pill.toggled.connect(self.pill_toggled.emit)
        av.body().addWidget(self.pill)
        av.body().addWidget(Label("Drag it anywhere; right-click for the menu.",
                                  10.5, 400, INK_SOFT))

        self.startup = QtWidgets.QCheckBox("Start Murmur when I sign in")
        self.startup.setFont(font(11.5))
        self.startup.setStyleSheet(check_css)
        self.startup.setChecked(startup.is_enabled())
        self.startup.toggled.connect(self._set_startup)
        av.body().addWidget(self.startup)
        self.startup_hint = Label(
            "Starts hidden in the tray, so the shortcut works without opening "
            "a window.", 10.5, 400, INK_SOFT)
        av.body().addWidget(self.startup_hint)
        lay.addWidget(av)

        # ── text size ──
        # Every point size in this app is a number somebody picked on their own
        # screen. This is the one control that says the reader gets a vote.
        ts = Card()
        ts.body().addWidget(Label("Text size", 12.5, 600, INK))
        srow = QtWidgets.QHBoxLayout()
        srow.setSpacing(8)
        current = float(core.load_config().get("text_scale", 1.0))
        self.scale_group = QtWidgets.QButtonGroup(self)
        for label, value in SCALES:
            btn = QtWidgets.QRadioButton(label)
            btn.setFont(font(11.5))
            btn.setStyleSheet(check_css.replace("QCheckBox", "QRadioButton")
                              .replace("border-radius:5px", "border-radius:9px"))
            btn.setChecked(abs(value - current) < 0.01)
            btn.toggled.connect(
                lambda on, v=value: self._set_scale(v) if on else None)
            self.scale_group.addButton(btn)
            srow.addWidget(btn)
        srow.addStretch(1)
        ts.body().addLayout(srow)
        self.scale_hint = Label("Applies to the window, the tray menu and the "
                                "pill.", 10.5, 400, INK_SOFT)
        ts.body().addWidget(self.scale_hint)
        lay.addWidget(ts)

        lay.addStretch(1)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(inner))
        self.reload_devices()

    def _save(self, key: str, value) -> None:
        cfg = core.load_config()
        cfg[key] = value
        core.save_config(cfg)

    def _set_scale(self, value: float) -> None:
        """Save the text size, and say plainly that it needs a restart.

        Qt copies a font into a widget when it is set, so nothing already on
        screen would change. Half a window resizing while the rest stayed put
        would look like a bug; saying so costs one relaunch and no confusion.
        """
        self._save("text_scale", value)
        self.scale_hint.setText(
            "Saved. Quit Murmur from the tray menu and start it again to see "
            "the new size."
            if abs(value - theme.SCALE) > 0.01 else
            "Applies to the window, the tray menu and the pill.")

    def _set_startup(self, on: bool) -> None:
        """Write the Run entry, and say so if Windows would not take it.

        A checkbox that ticks but changes nothing is worse than no checkbox:
        the machine is then rebooted on the strength of a promise Murmur never
        made. If the write fails the tick goes back, without re-entering here.
        """
        try:
            startup.set_enabled(on)
        except OSError as e:
            self.startup.blockSignals(True)
            self.startup.setChecked(not on)
            self.startup.blockSignals(False)
            self.startup_hint.setText(f"Windows would not save that setting: {e}")
            return
        self.startup_hint.setText(
            "Murmur will start hidden in the tray when you sign in."
            if on else "Murmur will only run when you open it.")

    def _on_test(self, on: bool) -> None:
        self.test_btn.setText("Stop test" if on else "Test microphone")
        self.hint.setText("Speak now — the bar should move." if on
                          else "Press Test and speak — the bar should move.")
        self.test_toggled.emit(on)

    def reload_devices(self) -> None:
        """Re-read the microphone list. DeviceSelector owns the listing now;
        this remains because the window still asks for a refresh when it is
        shown, and a microphone may have been plugged in since."""
        self.device_box.reload()

    def refresh_hotkey(self) -> None:
        self.shortcut.refresh()


# ── language and vocabulary ────────────────────────────────────────────────

class WordChip(QtWidgets.QFrame):
    """One vocabulary entry, with a way to take it back off the list."""

    removed = QtCore.Signal(str)

    def __init__(self, word: str) -> None:
        super().__init__()
        self.word = word
        self.setObjectName("chip")
        self.setStyleSheet(
            f"QFrame#chip{{background:#F1F1F4;border:1px solid {LINE};"
            f"border-radius:13px;}}")
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(11, 4, 5, 4)
        row.setSpacing(4)
        row.addWidget(Label(word, 11, 500, INK))

        x = QtWidgets.QPushButton("×")
        x.setCursor(QtCore.Qt.PointingHandCursor)
        x.setFixedSize(18, 18)
        x.setFont(font(12, 600))
        x.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{INK_SOFT};"
            f"border-radius:9px;}}"
            f"QPushButton:hover{{background:#E2E2E7;color:{INK};}}")
        x.clicked.connect(lambda: self.removed.emit(self.word))
        row.addWidget(x)


class RuleRow(QtWidgets.QFrame):
    """One correction: what the model writes, and what it should have written."""

    removed = QtCore.Signal(str)

    def __init__(self, find: str, into: str) -> None:
        super().__init__()
        self.find = find
        self.setObjectName("rule")
        self.setStyleSheet(
            f"QFrame#rule{{background:#F7F7F9;border:1px solid {LINE_SOFT};"
            f"border-radius:9px;}}")
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(11, 5, 5, 5)
        row.setSpacing(8)

        row.addWidget(Label(find, 11.5, 500, INK))
        row.addWidget(Label("→", 11.5, 400, INK_SOFT))
        # An empty replacement is a real rule - it is how "um" and "you know"
        # come out of a transcript - but a blank space on the row reads as the
        # interface having lost something.
        row.addWidget(Label(into or "removed", 11.5,
                            500 if into else 400,
                            INK if into else INK_SOFT))
        row.addStretch(1)

        x = QtWidgets.QPushButton("×")
        x.setCursor(QtCore.Qt.PointingHandCursor)
        x.setFixedSize(20, 20)
        x.setFont(font(12, 600))
        x.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{INK_SOFT};"
            f"border-radius:10px;}}"
            f"QPushButton:hover{{background:#E2E2E7;color:{INK};}}")
        x.clicked.connect(lambda: self.removed.emit(self.find))
        row.addWidget(x)


class FlowLayout(QtWidgets.QLayout):
    """Lays widgets left to right and wraps, like text.

    Qt has no such layout built in, and a vocabulary is a set of short chips of
    wildly varying width - a grid would leave ragged holes and a single row
    would run off the edge.
    """

    def __init__(self, parent=None, spacing: int = 7) -> None:
        super().__init__(parent)
        self._items: list = []
        self._space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QtCore.QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._layout(rect, test=False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect, test: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._space
                line_height = 0
            if not test:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x += hint.width() + self._space
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class LanguagePage(QtWidgets.QWidget):
    """What language is being spoken, and which words to expect in it."""

    changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        inner = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(30, 26, 30, 30)
        lay.setSpacing(14)


        # ── spoken language ──
        card = Card()
        card.body().addWidget(Label("Spoken language", 12.5, 600, INK))
        self.lang = QtWidgets.QComboBox()
        self.lang.setFont(font(11.5))
        self.lang.setMinimumHeight(36)
        self.lang.setMaxVisibleItems(18)
        self.lang.setStyleSheet(
            f"QComboBox{{border:1px solid {LINE};border-radius:9px;"
            f"padding:6px 12px;background:{SURFACE};color:{INK};}}"
            f"QComboBox::drop-down{{border:none;width:26px;}}"
            f"QComboBox QAbstractItemView{{border:1px solid {LINE};"
            f"background:{SURFACE};color:{INK};"
            f"selection-background-color:{ACCENT_WASH};selection-color:{INK};"
            f"outline:0;}}")
        self.lang.addItem("Detect automatically", "")
        for code, name in core.all_languages():
            self.lang.addItem(f"{name}   ({code})", code)
        saved = core.load_config().get("language") or ""
        for i in range(self.lang.count()):
            if self.lang.itemData(i) == saved:
                self.lang.setCurrentIndex(i)
                break
        self.lang.currentIndexChanged.connect(self._save_language)
        card.body().addWidget(self.lang)

        lay.addWidget(card)

        # ── vocabulary ──
        vocab = Card()
        top = QtWidgets.QHBoxLayout()
        top.addWidget(Label("Vocabulary", 12.5, 600, INK))
        top.addStretch(1)
        self.count_label = Label("", 10.5, 400, INK_SOFT)
        top.addWidget(self.count_label)
        vocab.body().addLayout(top)

        add_row = QtWidgets.QHBoxLayout()
        add_row.setSpacing(9)
        self.entry = QtWidgets.QLineEdit()
        self.entry.setFont(font(11.5))
        self.entry.setMinimumHeight(36)
        self.entry.setPlaceholderText("Add a word")
        self.entry.setStyleSheet(
            f"QLineEdit{{border:1px solid {LINE};border-radius:9px;"
            f"padding:6px 12px;background:{SURFACE};color:{INK};}}"
            f"QLineEdit:focus{{border:1.5px solid {ACCENT};}}")
        self.entry.returnPressed.connect(self._add)
        add_row.addWidget(self.entry, 1)
        add_btn = Button("Add", "ghost")
        add_btn.clicked.connect(self._add)
        add_row.addWidget(add_btn)
        vocab.body().addLayout(add_row)

        self.chips_holder = QtWidgets.QWidget()
        # The scroll area paints every plain QWidget inside it the page colour,
        # which puts a grey band behind the chips in the middle of a white card.
        self.chips_holder.setStyleSheet("background:transparent;")
        self.chips = FlowLayout(self.chips_holder)
        vocab.body().addWidget(self.chips_holder)

        self.empty = Label("Names, jargon, anything spelled unusually.",
                           11, 400, INK_SOFT)
        self.empty.setWordWrap(True)
        vocab.body().addWidget(self.empty)

        lay.addWidget(vocab)

        # ── output rules ──
        # Vocabulary leans on what the model hears; this fixes what it writes.
        # Two cards rather than one, because confusing them wastes prompt space
        # on words that were never misheard in the first place.
        rules = Card()
        rules.body().addWidget(Label("Corrections", 12.5, 600, INK))

        rule_row = QtWidgets.QHBoxLayout()
        rule_row.setSpacing(9)
        self.rule_find = QtWidgets.QLineEdit()
        self.rule_find.setPlaceholderText("What it writes")
        self.rule_into = QtWidgets.QLineEdit()
        self.rule_into.setPlaceholderText("What you wanted")
        for box in (self.rule_find, self.rule_into):
            box.setFont(font(11.5))
            box.setMinimumHeight(36)
            box.setStyleSheet(
                f"QLineEdit{{border:1px solid {LINE};border-radius:9px;"
                f"padding:6px 12px;background:{SURFACE};color:{INK};}}"
                f"QLineEdit:focus{{border:1.5px solid {ACCENT};}}")
            box.returnPressed.connect(self._add_rule)
            rule_row.addWidget(box, 1)
        rule_add = Button("Add", "ghost")
        rule_add.clicked.connect(self._add_rule)
        rule_row.addWidget(rule_add)
        rules.body().addLayout(rule_row)

        self.rules_holder = QtWidgets.QWidget()
        self.rules_holder.setStyleSheet("background:transparent;")
        self.rules_list = QtWidgets.QVBoxLayout(self.rules_holder)
        self.rules_list.setContentsMargins(0, 0, 0, 0)
        self.rules_list.setSpacing(5)
        rules.body().addWidget(self.rules_holder)

        self.rules_empty = Label(
            "Whole words, any capitalisation. Applied in order, after each "
            "dictation.", 11, 400, INK_SOFT)
        self.rules_empty.setWordWrap(True)
        rules.body().addWidget(self.rules_empty)
        lay.addWidget(rules)

        lay.addStretch(1)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(inner))
        self.reload_words()
        self.reload_rules()

    # ── actions ─────────────────────────────────────────────────────────────

    def _save_language(self) -> None:
        # set_language rather than a plain save: it also keeps the recently
        # used list the tray menu offers, so a language chosen here is in the
        # quick menu next time without being configured twice.
        core.set_language(self.lang.currentData() or "")
        self.changed.emit()

    def refresh_language(self) -> None:
        """Re-read the setting, for when it was changed from the tray menu."""
        saved = core.load_config().get("language") or ""
        for i in range(self.lang.count()):
            if self.lang.itemData(i) == saved:
                self.lang.blockSignals(True)
                self.lang.setCurrentIndex(i)
                self.lang.blockSignals(False)
                return

    def _add(self) -> None:
        word = self.entry.text().strip()
        if not word:
            return
        words = core.vocabulary()
        # Case-insensitive: adding "Anthropic" when "anthropic" is already
        # there gains nothing and costs prompt space.
        if word.lower() in {w.lower() for w in words}:
            self.entry.clear()
            return
        words.append(word)
        self._store(words)
        self.entry.clear()

    def _remove(self, word: str) -> None:
        self._store([w for w in core.vocabulary() if w != word])

    def _store(self, words: list) -> None:
        cfg = core.load_config()
        cfg["vocabulary"] = words
        core.save_config(cfg)
        self.reload_words()
        self.changed.emit()

    def reload_words(self) -> None:
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        words = core.vocabulary()
        for word in words:
            chip = WordChip(word)
            chip.removed.connect(self._remove)
            self.chips.addWidget(chip)
        self.chips_holder.setVisible(bool(words))
        self.empty.setVisible(not words)

        self._set_count(words)

    # ── corrections ─────────────────────────────────────────────────────────

    def _add_rule(self) -> None:
        find = self.rule_find.text().strip()
        into = self.rule_into.text().strip()
        if not find:
            return
        # Replacing a word with exactly itself is the one rule guaranteed to do
        # nothing. Compared case-sensitively on purpose: "github" to "GitHub"
        # differs only in case and is the most useful rule on the page.
        if find == into:
            self.rule_find.clear()
            self.rule_into.clear()
            return
        rules = [r for r in core.replacements() if r[0].lower() != find.lower()]
        rules.append((find, into))
        self._store_rules(rules)
        self.rule_find.clear()
        self.rule_into.clear()
        self.rule_find.setFocus()

    def _remove_rule(self, find: str) -> None:
        self._store_rules([r for r in core.replacements() if r[0] != find])

    def _store_rules(self, rules: list) -> None:
        cfg = core.load_config()
        cfg["replacements"] = [[f, t] for f, t in rules]
        core.save_config(cfg)
        self.reload_rules()

    def reload_rules(self) -> None:
        while self.rules_list.count():
            item = self.rules_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rules = core.replacements()
        for find, into in rules:
            row = RuleRow(find, into)
            row.removed.connect(self._remove_rule)
            self.rules_list.addWidget(row)
        self.rules_holder.setVisible(bool(rules))

    def _set_count(self, words: list) -> None:
        advised = core.VOCABULARY_ADVISED
        if not words:
            self.count_label.setText("")
        elif len(words) <= advised:
            self.count_label.setText(f"{len(words)} of {advised}")
        else:
            # Not an error: faster-whisper trims the list itself. But the words
            # past the cut do nothing, and silently ignoring them would look
            # like the feature not working.
            self.count_label.setText(
                f"{len(words)} — only the first {advised} are used")


# ── speed / GPU pack ───────────────────────────────────────────────────────

class PackWorker(QtCore.QThread):
    """Fetches and unpacks the GPU libraries off the interface thread.

    It is one and a half gigabytes; doing any of it on the main thread would
    freeze the window for minutes and Windows would offer to kill it.
    """
    progress = QtCore.Signal(int, str)      # percent, caption
    finished_ok = QtCore.Signal()
    failed = QtCore.Signal(str)

    def __init__(self, source: str, is_url: bool) -> None:
        super().__init__()
        self.source = source
        self.is_url = is_url
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        import pathlib
        import tempfile

        import gpupack
        temp = None
        try:
            archive = self.source
            if self.is_url:
                temp = pathlib.Path(tempfile.gettempdir()) / "murmur-gpu-pack.zip"

                def on_bytes(done: int, total: int) -> None:
                    pct = int(done * 100 / total) if total else 0
                    self.progress.emit(
                        pct, f"Downloading  {done / 1024**3:.2f} GB"
                             + (f" of {total / 1024**3:.2f} GB" if total else ""))

                gpupack.download(self.source, temp, on_bytes,
                                 cancel=lambda: self._cancel)
                archive = str(temp)

            gpupack.install(archive, lambda i, n: self.progress.emit(
                int(i * 100 / n), f"Installing  {i} of {n} libraries"))
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass


class SpeedPage(QtWidgets.QWidget):
    """Turning on the graphics card, which is an opt-in download.

    The CUDA maths libraries are 1.6 GB and do nothing without an NVIDIA card,
    so shipping them to everybody would have tripled the installer for the
    people they cannot help. They live here instead.
    """
    changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self._worker = None
        self._inner = QtWidgets.QWidget()
        self._lay = QtWidgets.QVBoxLayout(self._inner)
        self._lay.setContentsMargins(30, 26, 30, 30)
        self._lay.setSpacing(14)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(self._inner))
        self.reload()

    # ── rendering ───────────────────────────────────────────────────────────

    def reload(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        import gpupack
        state = gpupack.state()


        card = Card(padding=20)
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(Label("Graphics acceleration", 14, 700, INK))
        top.addStretch(1)
        # State as a word in the ordinary type colour. It was a coloured word
        # inside a coloured box, one wash per state, which is a lot of paint
        # for three possible values.
        top.addWidget(Label({"ready": "On", "available": "Off"}.get(state, "—"),
                            12, 600, GOOD if state == "ready" else INK_MID))
        card.body().addLayout(top)

        body = Label(self._explain(state), 11.5, 400, INK_SOFT)
        body.setWordWrap(True)
        card.body().addWidget(body)

        # Progress, hidden until something is running.
        self.bar = QtWidgets.QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(
            f"QProgressBar{{background:#ECECF0;border:none;border-radius:3px;}}"
            f"QProgressBar::chunk{{background:{ACCENT};border-radius:3px;}}")
        self.bar.hide()
        card.body().addWidget(self.bar)
        self.note = Label("", 10.5, 400, INK_MID)
        self.note.hide()
        card.body().addWidget(self.note)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        if state == "ready":
            size = Label(f"{gpupack.installed_size():.1f} GB installed",
                         10.5, 400, INK_SOFT)
            row.insertWidget(0, size)
            self.remove_btn = Button("Remove", "ghost")
            self.remove_btn.clicked.connect(self._remove)
            row.addWidget(self.remove_btn)
        elif state == "available":
            # With no download URL configured, choosing the file is the only
            # route, so it becomes the primary button rather than the quiet
            # alternative to one that cannot work.
            if gpupack.PACK_URL:
                self.file_btn = Button("Install from a file", "ghost")
                self.file_btn.clicked.connect(
                    lambda: self._install(from_file=True))
                row.addWidget(self.file_btn)
                self.install_btn = Button("Enable graphics acceleration",
                                          "primary")
                self.install_btn.clicked.connect(lambda: self._install())
                row.addWidget(self.install_btn)
            else:
                self.install_btn = Button("Install the GPU pack", "primary")
                self.install_btn.clicked.connect(
                    lambda: self._install(from_file=True))
                row.addWidget(self.install_btn)
        card.body().addLayout(row)
        self._lay.addWidget(card)

        self._lay.addStretch(1)

    def _explain(self, state: str) -> str:
        if state == "ready":
            return "Transcription is running on the graphics card."
        if state == "available":
            import gpupack
            return ("An NVIDIA card is here but the CUDA libraries are not. "
                    + ("About 1.6 GB to download." if gpupack.PACK_URL
                       else "Point Murmur at Murmur-GPU-Pack.zip. 1.6 GB."))
        return "No NVIDIA card, so there is nothing to turn on."

    def _facts(self, state: str) -> QtWidgets.QWidget:
        card = Card(padding=20)
        card.body().addWidget(Label("What this changes", 12.5, 600, INK))
        for head, text in [
            ("Speed, not accuracy",
             "The same model produces the same words either way. The card only "
             "makes them arrive sooner."),
            ("Bigger models become practical",
             "Medium and Large are slow enough on a processor to interrupt the "
             "flow of dictating. On a card they stop being a trade-off."),
            ("Nothing else changes",
             "Audio still never leaves the machine, and there is still no "
             "account and no per-minute cost."),
        ]:
            card.body().addWidget(Label(head, 11.5, 600, INK_MID))
            b = Label(text, 11, 400, INK_SOFT)
            b.setWordWrap(True)
            card.body().addWidget(b)
        return card

    # ── actions ─────────────────────────────────────────────────────────────

    def _install(self, from_file: bool = False) -> None:
        import gpupack
        source, is_url = gpupack.PACK_URL, True
        if from_file or not gpupack.PACK_URL:
            source, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Choose the GPU pack", "", "GPU pack (*.zip)")
            if not source:
                return
            is_url = False

        for btn in ("install_btn", "file_btn"):
            if hasattr(self, btn):
                getattr(self, btn).setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        self.note.setText("Starting ...")
        self.note.show()

        self._worker = PackWorker(source, is_url)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, pct: int, caption: str) -> None:
        self.bar.setValue(pct)
        self.note.setText(caption)

    def _on_done(self) -> None:
        self.reload()
        self.changed.emit()
        QtWidgets.QMessageBox.information(
            self, "Murmur",
            "Graphics acceleration is installed.\n\nRestart Murmur to start "
            "using it - the libraries are loaded when the program starts.")

    def _on_failed(self, message: str) -> None:
        self.reload()
        QtWidgets.QMessageBox.warning(
            self, "Murmur", f"Could not install the GPU pack.\n\n{message}")

    def _remove(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self, "Murmur",
            "Remove the graphics libraries?\n\nMurmur will go back to running "
            "on the processor when it next starts.")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        import gpupack
        gpupack.remove()
        self.reload()
        self.changed.emit()


# ── history ────────────────────────────────────────────────────────────────

class HistoryEntry(Card):
    """One transcript, with a way to copy it and - if it is the newest one and
    a better model exists - a way to have it heard again."""

    redo = QtCore.Signal()

    def __init__(self, text: str, meta: str, stamp: str) -> None:
        super().__init__(padding=15)
        self.text = text
        top = QtWidgets.QHBoxLayout()
        top.addWidget(Label(stamp, 10, 600, INK_SOFT))
        top.addStretch(1)
        self.redo_btn = Button("Redo", "quiet")
        self.redo_btn.clicked.connect(self.redo.emit)
        self.redo_btn.hide()
        top.addWidget(self.redo_btn)
        self.copy_btn = Button("Copy", "quiet")
        self.copy_btn.clicked.connect(lambda: core.clipboard_set(self.text))
        top.addWidget(self.copy_btn)
        self.body().addLayout(top)

        self.body_label = Label(text, 12.5, 400, INK)
        self.body_label.setWordWrap(True)
        self.body().addWidget(self.body_label)
        self.meta_label = Label(meta, 10, 400, INK_SOFT)
        self.body().addWidget(self.meta_label)

    def set_text(self, text: str, meta: str) -> None:
        self.text = text
        self.body_label.setText(text)
        self.meta_label.setText(meta)

    def offer_redo(self, model: str | None) -> None:
        self.redo_btn.setText(f"Redo with {model}" if model else "Redo")
        self.redo_btn.setEnabled(True)
        self.redo_btn.setVisible(bool(model))

    def redo_running(self, model: str) -> None:
        self.redo_btn.setText(f"Listening again with {model} ...")
        self.redo_btn.setEnabled(False)


class HistoryPage(QtWidgets.QWidget):
    """What was dictated, this session or since the setting was turned on."""

    redo_requested = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self._inner = QtWidgets.QWidget()
        self._lay = QtWidgets.QVBoxLayout(self._inner)
        self._lay.setContentsMargins(30, 26, 30, 30)
        self._lay.setSpacing(12)

        # The setting sits on the page it governs rather than under Sound.
        # Someone deciding whether their words should be written to disk is
        # looking at their words when the question occurs to them.
        head = Card(padding=15)
        hrow = QtWidgets.QHBoxLayout()
        self.keep = QtWidgets.QCheckBox("Keep these after Murmur closes")
        self.keep.setFont(font(11.5))
        self.keep.setStyleSheet(f"""
            QCheckBox {{ color:{INK}; background:transparent; spacing:9px; }}
            QCheckBox::indicator {{ width:17px; height:17px; }}
            QCheckBox::indicator:unchecked {{
                border:1.5px solid #C6C6CE; border-radius:5px;
                background:{SURFACE}; }}
            QCheckBox::indicator:checked {{
                border:1.5px solid {ACCENT}; border-radius:5px;
                background:{ACCENT}; }}
        """)
        self.keep.setChecked(history.enabled())
        self.keep.toggled.connect(self._set_keep)
        hrow.addWidget(self.keep)
        hrow.addStretch(1)
        self.clear_btn = Button("Clear", "quiet")
        self.clear_btn.clicked.connect(self._clear)
        hrow.addWidget(self.clear_btn)
        head.body().addLayout(hrow)
        self.note = Label("", 10.5, 400, INK_SOFT)
        self.note.setWordWrap(True)
        head.body().addWidget(self.note)
        self._lay.addWidget(head)

        self.empty = Card(padding=30)
        e = QtWidgets.QVBoxLayout()
        e.setSpacing(4)
        e.addWidget(Label("Nothing yet", 13, 600, INK_MID),
                    0, QtCore.Qt.AlignHCenter)
        self.empty.body().addLayout(e)
        self._lay.addWidget(self.empty)
        self._lay.addStretch(1)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area(self._inner))

        self._latest: HistoryEntry | None = None
        self._entries: list[HistoryEntry] = []
        self._restore()
        self._refresh_note()

    # ── the list ────────────────────────────────────────────────────────────

    def _restore(self) -> None:
        """Put saved transcripts back on the page, oldest inserted first so the
        newest ends up on top exactly as a live one would."""
        for saved in reversed(history.load()):
            self._insert(saved.get("text", ""), saved.get("meta", ""),
                         saved.get("stamp", ""), latest=False)

    def _insert(self, text: str, meta: str, stamp: str,
                latest: bool = True) -> HistoryEntry:
        self.empty.hide()
        entry = HistoryEntry(text, meta, stamp)
        entry.redo.connect(self.redo_requested.emit)
        self._lay.insertWidget(1, entry)
        self._entries.insert(0, entry)
        if latest:
            self._latest = entry
        return entry

    def add(self, text: str, meta: str) -> None:
        # Only one card may offer a retry, and it is this one from now on.
        if self._latest is not None:
            self._latest.redo_btn.hide()
        self._insert(text, meta, time.strftime("%H:%M:%S"))

    def offer_redo(self, model: str | None) -> None:
        if self._latest is not None:
            self._latest.offer_redo(model)

    def redo_started(self, model: str) -> None:
        if self._latest is not None:
            self._latest.redo_running(model)

    def redo_finished(self) -> None:
        if self._latest is not None:
            self._latest.offer_redo(core.better_model())

    def replace_latest(self, text: str, meta: str) -> None:
        if self._latest is not None:
            self._latest.set_text(text, meta)
            # The clip has now been through the better model. Offering the same
            # retry again would only spend another minute reaching the same
            # answer.
            self._latest.redo_btn.hide()

    # ── the setting ─────────────────────────────────────────────────────────

    def _set_keep(self, on: bool) -> None:
        cfg = core.load_config()
        cfg["keep_history"] = on
        core.save_config(cfg)
        if on:
            # Everything already on screen predates the setting. Writing it out
            # now is what someone ticking the box means, and losing this
            # session's transcripts to a setting meant to preserve them would
            # be a strange way to start.
            for entry in reversed(self._entries):
                history.add(entry.text, entry.meta_label.text())
        else:
            history.clear()
        self._refresh_note()

    def _clear(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self, "Murmur",
            "Clear the history?\n\nThe transcripts on this page are removed, "
            "and the saved file with them.")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        history.clear()
        for entry in self._entries:
            entry.setParent(None)
            entry.deleteLater()
        self._entries.clear()
        self._latest = None
        self.empty.show()
        self._refresh_note()

    def _refresh_note(self) -> None:
        self.note.setText(
            "Saved on this computer, in Murmur's own folder. Nothing is sent "
            "anywhere." if self.keep.isChecked() else
            "Kept until you quit. Never written to disk.")


# ── shell ──────────────────────────────────────────────────────────────────

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Murmur")
        self.resize(1000, 700)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(f"QMainWindow{{background:{BG};}}")

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        lay = QtWidgets.QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QtWidgets.QWidget()
        side.setFixedWidth(228)
        side.setStyleSheet(
            f"background:#EFEFF3;border-right:1px solid {LINE};")
        slay = QtWidgets.QVBoxLayout(side)
        slay.setContentsMargins(14, 20, 14, 16)
        slay.setSpacing(12)

        brand = QtWidgets.QHBoxLayout()
        brand.setSpacing(9)
        mark = QtWidgets.QLabel()
        mark.setPixmap(logo.mark_pixmap(26, INK))
        mark.setStyleSheet("background:transparent;")
        brand.addWidget(mark)
        brand.addWidget(Label("Murmur", 15.5, 700, INK))
        brand.addStretch(1)
        slay.addLayout(brand)

        self.nav = QtWidgets.QListWidget()
        self.nav.setIconSize(QtCore.QSize(28, 28))
        self.nav.setSpacing(1)
        self.nav.setFont(font(12))
        self.nav.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.nav.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.nav.setStyleSheet(f"""
            QListWidget{{background:transparent;border:none;outline:0;}}
            QListWidget::item{{padding:8px 10px;border-radius:9px;
                margin-bottom:2px;color:{INK};}}
            QListWidget::item:selected{{background:{SURFACE};color:{INK};}}
            QListWidget::item:hover:!selected{{background:rgba(0,0,0,0.045);}}
        """)
        slay.addWidget(self.nav, 1)

        # A quiet card at the foot of the sidebar: what is loaded, and the one
        # promise worth repeating.
        badge = QtWidgets.QFrame()
        # Scoped by name: an unqualified rule here is inherited by the labels
        # inside, and each of them grows its own rounded border.
        badge.setObjectName("badge")
        badge.setStyleSheet(
            f"QFrame#badge{{background:{SURFACE};border:1px solid {LINE};"
            f"border-radius:11px;}}")
        blay = QtWidgets.QVBoxLayout(badge)
        blay.setContentsMargins(12, 10, 12, 10)
        blay.setSpacing(2)
        brow = QtWidgets.QHBoxLayout()
        brow.setSpacing(7)
        dot = QtWidgets.QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background:{GOOD};border-radius:3px;")
        brow.addWidget(dot, 0, QtCore.Qt.AlignVCenter)
        self.side_model = Label("small", 11.5, 700, INK)
        brow.addWidget(self.side_model)
        brow.addStretch(1)
        blay.addLayout(brow)
        self.side_device = Label("Runs entirely on this computer",
                                 9.5, 400, INK_SOFT)
        blay.addWidget(self.side_device)
        slay.addWidget(badge)
        lay.addWidget(side)

        # ── right hand side: a slim header, then the pages ──
        right = QtWidgets.QWidget()
        rlay = QtWidgets.QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)

        header = QtWidgets.QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background:{SURFACE};border-bottom:1px solid {LINE};")
        hlay = QtWidgets.QHBoxLayout(header)
        hlay.setContentsMargins(20, 0, 16, 0)
        hlay.setSpacing(10)

        mark = QtWidgets.QLabel()
        mark.setPixmap(logo.tile_pixmap(24))
        mark.setStyleSheet("background:transparent;")
        hlay.addWidget(mark, 0, QtCore.Qt.AlignVCenter)
        self.header_title = Label("Home", 13, 700, INK)
        hlay.addWidget(self.header_title, 0, QtCore.Qt.AlignVCenter)
        hlay.addStretch(1)

        # The microphone belongs here rather than buried on a settings page:
        # it is the one setting worth changing mid-sentence, when you have just
        # heard yourself come out muffled and know why.
        #
        # Both of these are added with an explicit alignment. Left to itself a
        # combo box expands to swallow the stretch above - which reads as the
        # microphone being left-aligned next to the page title - and a label
        # stretches to the full 52px header and has its rounded ends clipped.
        self.header_mic = DeviceSelector()
        hlay.addWidget(self.header_mic, 0, QtCore.Qt.AlignVCenter)
        self.header_model = Label("small", 11, 500, INK_MID)
        hlay.addWidget(self.header_model, 0, QtCore.Qt.AlignVCenter)
        rlay.addWidget(header)

        self.pages = QtWidgets.QStackedWidget()
        rlay.addWidget(self.pages, 1)
        lay.addWidget(right, 1)

        self.home = HomePage()
        self.models = ModelsPage()
        self.language = LanguagePage()
        self.sound = SoundPage()
        self.speed = SpeedPage()
        self.history = HistoryPage()

        self._titles = ["Home", "Models library", "Language", "Sound",
                        "Speed", "History"]
        for label, glyph, page in [
            ("Home", "home", self.home),
            ("Models library", "models", self.models),
            ("Language", "language", self.language),
            ("Sound", "sound", self.sound),
            ("Speed", "speed", self.speed),
            ("History", "history", self.history),
        ]:
            item = QtWidgets.QListWidgetItem(nav_icon(glyph), label)
            item.setSizeHint(QtCore.QSize(0, 46))
            self.nav.addItem(item)
            self.pages.addWidget(page)

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.currentRowChanged.connect(
            lambda i: self.header_title.setText(self._titles[i]))
        self.home.navigate.connect(
            lambda name: self.nav.setCurrentRow(self._titles.index(name))
            if name in self._titles else None)
        self.nav.setCurrentRow(0)

        self.status = Label("Ready.",
                            10.5, 400, INK_MID)
        bar = self.statusBar()
        bar.addWidget(self.status)
        bar.setStyleSheet(
            f"QStatusBar{{background:{SURFACE};border-top:1px solid {LINE};"
            f"padding:3px 12px;}} QStatusBar::item{{border:none;}}")
        self.refresh_side_note()

    def show_page(self, name: str) -> None:
        """Bring a named page to the front, for links from outside the window."""
        if name in self._titles:
            self.nav.setCurrentRow(self._titles.index(name))

    def refresh_hotkey(self) -> None:
        """Push a changed shortcut everywhere it is shown."""
        self.home.refresh_hotkey()
        self.sound.refresh_hotkey()

    def refresh_side_note(self) -> None:
        name = core.resolve_model()
        self.side_model.setText(name)
        self.header_model.setText(name)
        # Kept short: the sidebar badge is 200px wide and clips without mercy.
        self.side_device.setText("Using the graphics card" if core.cuda_usable()
                                 else "Using the processor")
        self.header_mic.reload()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Closing hides to the tray; Murmur has to stay listening."""
        event.ignore()
        self.hide()
