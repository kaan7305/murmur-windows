"""Murmur, as an actual application: tray icon, window, setup guide and the
recording overlay.

Threading shape, which is the thing to keep straight here:

  Qt main thread   owns every widget; nothing else may touch them
  pynput thread    delivers the hotkey
  PortAudio thread delivers microphone frames
  worker thread    runs the model so the interface never freezes

Everything crossing into the interface goes through a Qt signal.
"""
from __future__ import annotations

import queue
import sys
import threading
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

# Two copies of Murmur both answer the hotkey, both record, and both paste,
# which looks exactly like the app transcribing twice. One instance only.
SINGLETON = "murmur-single-instance"


_LOCK_HANDLE = None  # module-level so the mutex lives as long as the process


def claim_single_instance() -> bool:
    """Take an OS-level named mutex. True if we are the one true instance.

    A socket probe is not enough on its own: two copies launched in the same
    instant both find no server, both continue, and the second one's
    removeServer() call evicts the first. CreateMutexW is atomic, so exactly
    one caller can ever win regardless of timing.
    """
    global _LOCK_HANDLE
    import ctypes
    from ctypes import wintypes

    ERROR_ALREADY_EXISTS = 183
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE

    handle = k32.CreateMutexW(None, True, f"Local\\{SINGLETON}")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    _LOCK_HANDLE = handle
    return True


def ask_running_instance_to_show() -> None:
    """Best effort nudge so a second launch surfaces the window already open."""
    sock = QtNetwork.QLocalSocket()
    sock.connectToServer(SINGLETON)
    if sock.waitForConnected(400):
        sock.write(b"show")
        sock.waitForBytesWritten(400)
        sock.disconnectFromServer()

import history
import logo
import murmur as core
import startup
import stats
from hotkeys import GlobalHotkey
from overlay import IdlePill, RecordingOverlay
from theme import font, set_scale
from ui import MainWindow

# Type size for the tray and pill menu. Windows' own default is 9pt, which is
# small for a menu opened from a floating pill rather than from a menu bar.
# One number, here, because it is the thing most likely to want adjusting.
MENU_PT = 20.0


def tray_icon(active: bool = False) -> QtGui.QIcon:
    """The Murmur mark, red while listening so the state reads at a glance."""
    icon = QtGui.QIcon()
    for s in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(logo.tray_pixmap(s, recording=active))
    return icon


class Bridge(QtCore.QObject):
    """Signals are the only sanctioned route from a worker into the interface."""
    level = QtCore.Signal(float)
    started = QtCore.Signal()
    stopped = QtCore.Signal(float)
    transcribed = QtCore.Signal(str, float, float, str)
    redone = QtCore.Signal(str, float, str)
    failed = QtCore.Signal(str)
    status = QtCore.Signal(str)


class Murmur(QtCore.QObject):
    def __init__(self, app: QtWidgets.QApplication) -> None:
        super().__init__()
        self.app = app
        self.bridge = Bridge()
        self.model = None
        self.words = 0
        self.sessions = 0
        self.cancelled = False
        self._testing = False
        self.guide = None            # the setup guide, built on first request

        self.window = MainWindow()
        self.overlay = RecordingOverlay()
        self.pill = IdlePill()
        self.recorder = LevelRecorder(self.bridge)
        # (audio, model to use) - None means the loaded one. A retry goes
        # through the same queue as a dictation so two transcriptions can
        # never run at once and fight over the card.
        self.jobs: queue.Queue[tuple] = queue.Queue()
        # The last clip, kept so a mishearing can be retried with a better
        # model instead of said again. One clip only: this is a second chance,
        # not a recording of the day.
        self._last_audio: np.ndarray | None = None
        self._redoing = False

        self._build_tray()
        self._connect()
        self._claim_singleton()
        # An entry pointing at a copy that has moved would silently stop
        # bringing Murmur back at sign-in, while the setting still read as on.
        startup.repair()
        self.pill.place(core.pill_position())
        self._sync_pill()

        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._load_model, daemon=True).start()
        self._start_hotkeys()

    # ── wiring ──────────────────────────────────────────────────────────────

    def _build_tray(self) -> None:
        self.tray = QtWidgets.QSystemTrayIcon(tray_icon(), self.app)
        self.tray.setToolTip("Murmur")
        menu = QtWidgets.QMenu()
        # Setting the font rather than a stylesheet leaves Qt to work the row
        # heights out from it, and keeps the menu looking like a Windows menu
        # in both light and dark rather than like a repainted imitation.
        menu.setFont(font(MENU_PT))
        self.act_state = menu.addAction("Loading model ...")
        self.act_state.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Open Murmur", self._show_window)
        self.act_dictate = menu.addAction("Dictate now", self.toggle)

        # Language belongs in this menu and not only on a settings page.
        # Naming the language is 2.6x faster than letting Whisper detect it and
        # far more accurate - but only if switching costs one right-click. Made
        # to rebuild on every open, since the setting also changes from the
        # window and a menu quietly disagreeing with the app is worse than no
        # menu at all.
        self.lang_menu = menu.addMenu("Language")
        self.lang_menu.setFont(font(MENU_PT))
        self.lang_menu.aboutToShow.connect(self._fill_language_menu)

        menu.addAction("Setup guide", self.show_guide)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._show_window()
            if r == QtWidgets.QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _claim_singleton(self) -> None:
        """Listen for a second launch so it can raise this window instead of
        starting a rival copy. removeServer clears a stale socket left behind
        by a crash."""
        QtNetwork.QLocalServer.removeServer(SINGLETON)
        self.server = QtNetwork.QLocalServer(self)
        self.server.newConnection.connect(self._second_instance)
        self.server.listen(SINGLETON)

    def _second_instance(self) -> None:
        conn = self.server.nextPendingConnection()
        if conn:
            conn.disconnectFromServer()
        self._show_window()

    def _connect(self) -> None:
        b = self.bridge
        b.level.connect(self.overlay.push_level)
        b.started.connect(self._on_started)
        b.stopped.connect(self._on_stopped)
        b.transcribed.connect(self._on_transcribed)
        b.redone.connect(self._on_redone)
        b.failed.connect(self._on_failed)
        b.status.connect(self.window.set_status)
        self.overlay.stop_requested.connect(self.toggle)
        self.overlay.cancel_requested.connect(self.cancel)
        self.pill.clicked.connect(self.toggle)
        self.pill.menu_requested.connect(self._pill_menu)
        self.pill.moved.connect(self._pill_moved)
        self.window.models.model_changed.connect(self._switch_model)
        self.window.sound.test_toggled.connect(self._mic_test)
        self.window.sound.pill_toggled.connect(self._pill_setting)
        self.window.sound.hotkey_changed.connect(self._change_hotkey)
        self.window.history.redo_requested.connect(self._redo_last)
        self.window.speed.changed.connect(self.window.refresh_side_note)
        # While the Sound page is testing, feed its meter as well as the pill.
        b.level.connect(self._route_level)

    def _route_level(self, v: float) -> None:
        if self._testing:
            self.window.sound.meter.set_level(v)

    def _mic_test(self, on: bool) -> None:
        """Live input meter, so a silent microphone is obvious before you
        discover it by dictating into nothing."""
        self._testing = on
        if on:
            if not self.recorder.active:
                try:
                    self.recorder.start()
                except Exception as e:
                    self.window.set_status(f"Could not open the microphone: {e}")
                    self._testing = False
                    self.window.sound.test_btn.setChecked(False)
        else:
            if self.recorder.active:
                self.recorder.stop()

    # ── the idle pill ───────────────────────────────────────────────────────

    def _sync_pill(self) -> None:
        """One place that decides whether the pill is on screen.

        Shown when it is switched on and Murmur is idle; hidden while recording,
        because the full pill is standing in the same place saying the same
        thing louder. Recording state changes from three directions - hotkey,
        pill, tray - so working it out here beats a show() and a hide() at each.
        """
        if core.pill_enabled() and not self.recorder.active:
            self.pill.show()
            self.pill.raise_()
        else:
            self.pill.hide()

    def _pill_setting(self, on: bool) -> None:
        cfg = core.load_config()
        cfg["pill"] = on
        core.save_config(cfg)
        self._sync_pill()

    def _pill_moved(self, x: int, y: int) -> None:
        cfg = core.load_config()
        cfg["pill_pos"] = [x, y]
        core.save_config(cfg)

    def _pill_menu(self, point: QtCore.QPoint) -> None:
        menu = self.tray.contextMenu()
        if menu is not None:
            menu.popup(point)

    # ── language ────────────────────────────────────────────────────────────

    def _fill_language_menu(self) -> None:
        """Detect, then the languages actually dictated in, then the full list.

        The recent list is built from use rather than configured. Someone who
        speaks two languages should not have to declare that anywhere - the
        second time they choose Turkish it is in the menu, and the choice they
        never make never clutters it.
        """
        self.lang_menu.clear()
        current = core.load_config().get("language") or ""
        group = QtGui.QActionGroup(self.lang_menu)
        group.setExclusive(True)

        def entry(code: str, label: str) -> None:
            act = self.lang_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(code == current)
            act.triggered.connect(lambda _=False, c=code: self._set_language(c))
            group.addAction(act)

        entry("", "Detect automatically")
        recent = core.recent_languages()
        # The language in use is always offered, even on the first run when
        # nothing has been used yet and the recent list is empty.
        if current and current not in recent:
            recent = [current] + recent
        if recent:
            self.lang_menu.addSeparator()
            for code in recent:
                entry(code, core.language_name(code))
        self.lang_menu.addSeparator()
        self.lang_menu.addAction("More languages ...", self._open_languages)

    def _set_language(self, code: str) -> None:
        core.set_language(code)
        self.window.language.refresh_language()
        self.window.set_status(f"Dictating in {core.language_name(code)}.")

    def _open_languages(self) -> None:
        self._show_window()
        self.window.show_page("Language")

    def _start_hotkeys(self, combo: str | None = None) -> None:
        """Register the dictation hotkey, replacing any previous one.

        Called again whenever the shortcut is changed. pynput has no way to
        rebind a live listener, so the old one is stopped and a new one started;
        anything holding a reference to the old listener would keep a dead
        thread alive, hence the single attribute.
        """
        combo = combo or core.resolve_hotkey()

        def trigger() -> None:
            # Called on the keyboard hook thread; touching a widget from here
            # would be a crash, and holding the hook up would make Windows drop
            # it. Hand straight over to the Qt thread and return.
            QtCore.QMetaObject.invokeMethod(
                self, "toggle", QtCore.Qt.QueuedConnection)

        def escape() -> None:
            if self.recorder.active:
                QtCore.QMetaObject.invokeMethod(
                    self, "cancel", QtCore.Qt.QueuedConnection)

        try:
            listener = GlobalHotkey(combo, trigger, escape)
        except ValueError:
            # A saved shortcut that no longer parses would otherwise take the
            # whole application down at startup, with the fix locked inside the
            # window it just failed to open.
            self.bridge.failed.emit(
                f"The shortcut {combo!r} is not valid - using "
                f"{core.HOTKEY_DICTATE} instead.")
            combo = core.HOTKEY_DICTATE
            listener = GlobalHotkey(combo, trigger, escape)

        old = getattr(self, "listener", None)
        if old is not None:
            old.stop()
        self.listener = listener
        self.listener.start()

        caps = core.hotkey_label(combo)
        self.overlay.set_hotkey(caps)
        self.pill.set_hotkey(caps)
        self.window.refresh_hotkey()
        self.tray.setToolTip(f"Murmur - press {' + '.join(caps)} to dictate")
        self.act_dictate.setText(f"Dictate now ({' + '.join(caps)})")

    def _change_hotkey(self, combo: str) -> None:
        cfg = core.load_config()
        cfg["hotkey"] = combo
        core.save_config(cfg)
        self._start_hotkeys(combo)
        if self.guide is not None:
            self.guide.refresh_hotkey()

    # ── setup guide ─────────────────────────────────────────────────────────

    def show_guide(self) -> None:
        """Open the setup guide, building it the first time it is asked for."""
        from onboarding import Onboarding

        if self.guide is None:
            self.guide = Onboarding()
            self.guide.mic_test.connect(self._mic_test)
            self.guide.hotkey_changed.connect(self._change_hotkey)
            self.guide.completed.connect(self._guide_done)
            self.bridge.level.connect(self.guide.push_level)
        self.guide.set_hint(
            "Ready when you are." if self.model is not None
            else "Still loading the speech model - one moment.")
        self.guide.show()
        self.guide.raise_()
        self.guide.activateWindow()

    def _guide_done(self) -> None:
        self._show_window()

    # ── model ───────────────────────────────────────────────────────────────

    def _load_model(self, name: str | None = None) -> None:
        try:
            self.bridge.status.emit(f"Loading {name or core.resolve_model()} ...")
            self.model = core.load_model(name)
            caps = " + ".join(core.hotkey_label())
            self.bridge.status.emit(f"Ready. Press {caps} anywhere to dictate.")
            if self.guide is not None:
                self.guide.set_hint("Ready when you are.")
            self.act_state.setText(f"Ready - {core.resolve_model()}")
            self.window.refresh_side_note()
            self.window.home.refresh()
        except Exception as e:
            self.bridge.failed.emit(f"Could not load the model: {e}")

    def _switch_model(self, name: str) -> None:
        self.model = None
        self.act_state.setText(f"Loading {name} ...")
        threading.Thread(target=self._load_model, args=(name,),
                         daemon=True).start()

    # ── recording lifecycle ─────────────────────────────────────────────────

    @QtCore.Slot()
    def toggle(self) -> None:
        # The mic test holds the same stream open; end it before dictating,
        # otherwise F9 would read as "stop" and discard a recording that
        # never started.
        if self._testing:
            self.window.sound.test_btn.setChecked(False)

        if self.recorder.active:
            audio = self.recorder.stop()
            self.overlay.hide()
            self._sync_pill()
            if self.cancelled:
                self.cancelled = False
                self.bridge.status.emit("Cancelled.")
                return
            self.bridge.stopped.emit(len(audio) / core.SAMPLE_RATE)
            self._last_audio = audio
            self.jobs.put((audio, None))
        else:
            if self.model is None:
                self.bridge.status.emit("Still loading the model, one moment ...")
                return
            self.cancelled = False
            self.overlay.set_device(core.device_label())
            try:
                self.recorder.start()
            except Exception as e:
                # A microphone that will not open is the one failure the pill
                # cannot report, because there is nothing to show it over.
                self.bridge.failed.emit(f"Could not open the microphone: {e}")
                return
            self._sync_pill()          # the full pill takes over from here
            self.overlay.show_centred()
            self.bridge.started.emit()

    @QtCore.Slot()
    def cancel(self) -> None:
        if not self.recorder.active:
            return
        self.cancelled = True
        self.toggle()

    def _on_started(self) -> None:
        self.tray.setIcon(tray_icon(active=True))
        self.window.set_status("Listening ...")
        core.beep("start")

    def _on_stopped(self, secs: float) -> None:
        self.tray.setIcon(tray_icon())
        self.window.set_status(f"Captured {secs:.1f}s, transcribing ...")
        core.beep("stop")

    def _on_transcribed(self, text: str, secs: float, took: float,
                        target: str) -> None:
        self.words += len(text.split())
        self.sessions += 1
        speed = f"{secs / took:.1f}x" if took else "-"
        # Totals only, and on disk, so the Home page can answer "this week"
        # rather than "since you last started the program".
        stats.record(len(text.split()), secs, target)
        self.window.home.refresh()
        meta = f"{secs:.1f}s in {took:.2f}s ({speed}) - pasted into {target}"
        self.window.history.add(text, meta)
        history.add(text, meta)
        # Only the newest entry can be retried, because only its audio is
        # still in memory. Offering the button on older cards would be a
        # promise the process cannot keep.
        self.window.history.offer_redo(core.better_model())
        self.window.set_status(f'Pasted into {target}  -  "{text[:60]}"')
        if self.guide is not None and self.guide.isVisible():
            self.guide.on_transcribed(text)
        core.beep("done")

    def _redo_last(self) -> None:
        """Run the last clip through a better model, on request."""
        name = core.better_model()
        if self._last_audio is None or not name:
            return
        if self._redoing:
            return
        if not core.is_downloaded(name):
            # Nothing is downloaded behind the user's back. 3 GB arriving
            # unannounced because they pressed a button labelled "redo" is
            # not a correction anybody asked for.
            self.window.set_status(
                f"{name} is not downloaded yet - get it from the models "
                f"library and the retry will use it.")
            self._show_window()
            self.window.show_page("Models library")
            return
        self._redoing = True
        self.window.history.redo_started(name)
        self.window.set_status(f"Transcribing that again with {name} ...")
        self.jobs.put((self._last_audio, name))

    def _on_redone(self, text: str, took: float, name: str) -> None:
        self._redoing = False
        if not text:
            self.window.history.redo_finished()
            return
        meta = f"redone with {name} in {took:.2f}s - copied to the clipboard"
        self.window.history.replace_latest(text, meta)
        history.replace_latest(text, meta)
        self.window.set_status(
            f'{name} heard: "{text[:60]}"  -  copied to the clipboard.')

    def _on_failed(self, message: str) -> None:
        self.window.set_status(message)
        # A tray balloon for something the user is standing in front of is the
        # wrong instrument: it appears in the corner, after a delay, and steals
        # attention from where they were looking. The pill is already there.
        if self.overlay.isVisible() or not self.window.isVisible():
            self.overlay.flash(message)
        else:
            self.tray.showMessage("Murmur", message,
                                  QtWidgets.QSystemTrayIcon.Warning, 4000)

    # ── worker ──────────────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            audio, redo_with = self.jobs.get()
            if redo_with:
                self._redo_job(audio, redo_with)
                continue
            secs = len(audio) / core.SAMPLE_RATE
            if secs < 0.3 or self.model is None:
                self.bridge.failed.emit("Too short - nothing to transcribe.")
                continue
            try:
                t0 = time.time()
                text = core.transcribe(self.model, audio)
                took = time.time() - t0
            except Exception as e:
                self.bridge.failed.emit(f"Transcription failed: {e}")
                continue
            if not text:
                self.bridge.failed.emit("Nothing heard - only silence.")
                core.beep("empty")
                continue
            target = core.foreground_process() or "?"
            core.paste(text)
            self.bridge.transcribed.emit(text, secs, took, target)

    def _redo_job(self, audio: np.ndarray, name: str) -> None:
        """Transcribe the last clip again with a larger model.

        The model is loaded, used and dropped rather than kept: large-v3 is
        3 GB of weights to hold for a button pressed once in a while, and the
        model in use has to stay loaded so the next dictation is not made to
        wait for this one.

        The result is not pasted. The window that was dictated into minutes
        ago may be anything by now, and silently typing into whatever has
        focus is not a correction, it is a new problem. It goes to the
        clipboard, which is where a correction is useful.
        """
        try:
            t0 = time.time()
            model = core.load_model(name)
            text = core.transcribe(model, audio)
            took = time.time() - t0
            del model
        except Exception as e:
            self.bridge.failed.emit(f"Could not redo that with {name}: {e}")
            self.bridge.redone.emit("", 0.0, "")
            return
        if not text:
            self.bridge.failed.emit(f"{name} heard nothing in that clip either.")
            self.bridge.redone.emit("", 0.0, "")
            return
        core.clipboard_set(text)
        self.bridge.redone.emit(text, took, name)

    # ── window / quit ───────────────────────────────────────────────────────

    def _show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self) -> None:
        try:
            self.listener.stop()
        except Exception:
            pass
        self.app.quit()


class LevelRecorder:
    """Recorder that also reports a level for the waveform."""

    def __init__(self, bridge: Bridge) -> None:
        self.bridge = bridge
        self._frames: list[np.ndarray] = []
        self._stream = None
        self.active = False

    def _callback(self, indata, frames, time_info, status) -> None:
        self._frames.append(indata.copy())
        # Root mean square, scaled so ordinary speech fills most of the meter.
        rms = float(np.sqrt(np.mean(np.square(indata))))
        self.bridge.level.emit(min(1.0, rms * 9.0))

    def start(self) -> None:
        import sounddevice as sd
        self._frames = []
        # device=None means whatever Windows considers the default, which is
        # also what resolve_device() falls back to when the chosen microphone
        # has been unplugged.
        self._stream = sd.InputStream(
            samplerate=core.SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=1024, device=core.resolve_device(),
            callback=self._callback)
        self._stream.start()
        self.active = True

    def stop(self) -> np.ndarray:
        self.active = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()


def _make_output_safe() -> None:
    """Under a windowed interpreter sys.stdout is None, and any print() then
    raises. Point both streams at a log file so diagnostics survive and no
    stray print can take the app down."""
    import paths
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log = open(paths.log_file(), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
    except Exception:
        import io
        sys.stdout = sys.stdout or io.StringIO()
        sys.stderr = sys.stderr or io.StringIO()


def _hide_console() -> None:
    """Run under python.exe (whose window creation is reliable) but hide the
    console, so Murmur looks like an ordinary windowed app."""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)   # SW_HIDE
    except Exception:
        pass


def selftest() -> int:
    """Prove a build works without a microphone or a human.

    A packaged application fails differently from a source checkout: a data file
    the spec forgot, a DLL that never got collected, an import satisfied in the
    virtualenv and missing here. None of that shows up until something reaches
    for it, so this reaches for all of it - the model, the tokeniser, the
    voice-activity network, the clipboard - and transcribes a known clip.

    Results go to a file because a windowed executable has nowhere to print.
    """
    import paths

    lines: list[str] = []
    ok = True

    def check(label: str, fn):
        nonlocal ok
        try:
            lines.append(f"  PASS  {label}: {fn()}")
        except Exception as e:
            ok = False
            lines.append(f"  FAIL  {label}: {type(e).__name__}: {e}")

    lines.append(f"Murmur selftest - frozen={paths.FROZEN}")
    lines.append(f"  app  {paths.app_dir()}")
    lines.append(f"  data {paths.data_dir()}")

    import murmur as core

    check("numpy", lambda: __import__("numpy").__version__)
    check("ctranslate2", lambda: __import__("ctranslate2").__version__)
    check("sounddevice", lambda: __import__("sounddevice").get_portaudio_version()[1])
    check("onnxruntime", lambda: __import__("onnxruntime").__version__)
    check("gpu state", lambda: __import__("gpupack").state())
    check("clipboard", lambda: core.clipboard_set("murmur selftest") and "wrote")

    # The real test: load the model and transcribe. Uses whatever the machine
    # ended up choosing, so the GPU path is exercised when the pack is present.
    def transcribe_clip():
        import time

        import numpy as np
        audio = core._sample_clip()
        if audio is None:
            raise RuntimeError("could not synthesise a clip")
        model = core.load_model()
        t0 = time.time()
        text = core.transcribe(model, audio)
        took = time.time() - t0
        secs = len(audio) / core.SAMPLE_RATE
        if not text:
            raise RuntimeError("transcribed to nothing")
        return f'{secs:.1f}s in {took:.2f}s ({secs / took:.1f}x) "{text[:60]}"'

    check("transcribe", transcribe_clip)

    lines.append("PASSED" if ok else "FAILED")
    (paths.data_dir() / "selftest.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    _make_output_safe()
    if "--selftest" in sys.argv:
        return selftest()
    if "--console" not in sys.argv:
        _hide_console()
    app = QtWidgets.QApplication(sys.argv)
    # Before any widget exists: a font is copied into a widget when it is set,
    # so a scale applied later would only reach whatever was built after it.
    set_scale(core.load_config().get("text_scale", 1.0))
    app.setApplicationName("Murmur")
    app.setQuitOnLastWindowClosed(False)   # closing the window keeps the tray
    app.setWindowIcon(logo.app_icon())

    if not claim_single_instance():
        ask_running_instance_to_show()
        print("Murmur is already running; raised the existing window.")
        return 0

    murmur = Murmur(app)

    # First run goes to the setup guide instead of the main window. Someone who
    # has just installed a dictation program does not want a dashboard, they
    # want to know which key to press.
    first_run = not core.load_config().get("onboarded")
    if "--guide" in sys.argv or (first_run and "--hidden" not in sys.argv):
        murmur.show_guide()
    elif "--hidden" not in sys.argv:
        murmur.window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
