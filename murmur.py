"""Murmur - press a key, speak, and the text lands wherever your cursor is.

Original implementation. Nothing here is derived from another project's source.

    Ctrl+Space   start listening / stop and transcribe
    F10          quit

Everything runs locally: the audio never leaves the machine and there is no
API key or account involved.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import functools
import os
import queue
import re
import sys
import threading
import time

# Must be set before huggingface_hub is imported.
# Hub 1.x routes large files through the Xet CDN by default; that endpoint
# drops sustained transfers here (WinError 10054) while ordinary API calls
# succeed, so multi-GB model downloads fail. The classic CDN works fine.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def beeps_enabled() -> bool:
    """Whether to make a noise when recording starts and stops.

    Off by default. The beeps date from when Murmur was a console program and
    the only way to tell it had heard the keypress was to listen for one. The
    application answers that question better and more quietly: the recording
    pill appears, and the tray icon turns red. Two square-wave tones on every
    single dictation is a lot of noise to pay for information already on screen.

    Still a setting, on the Sound page, for anyone dictating without looking.
    """
    return load_config().get("beeps", False)


def pill_enabled() -> bool:
    """Whether the small floating pill sits on screen while Murmur waits.

    On by default. The tray icon is the conventional answer to "is it running",
    and it is a poor one: it is 16 pixels, usually hidden behind the overflow
    arrow, and it tells someone who has just installed a dictation program
    nothing about how to start dictating. The pill is visible, says which key
    to press when pointed at, and can be clicked by anyone who has not yet
    memorised the shortcut. Off for anyone who wants the screen back.
    """
    return load_config().get("pill", True)


def pill_position() -> tuple[int, int] | None:
    """Where the pill was last dragged to, if it has been moved."""
    pos = load_config().get("pill_pos")
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        try:
            return int(pos[0]), int(pos[1])
        except (TypeError, ValueError):
            return None
    return None


def beep(kind: str) -> None:
    """Audible feedback, when it has been asked for.

    The setting is checked here rather than at each call site: there are eight
    of them across two entry points, and one of them forgetting would be a bug
    nobody notices until it is making noise on somebody else's machine.
    """
    if not beeps_enabled():
        return
    try:
        import winsound
        tones = {
            "start": [(880, 90)],              # rising: now listening
            "stop": [(660, 80)],               # falling: captured, working
            "done": [(880, 70), (1175, 90)],   # two-note: text is in
            "empty": [(300, 200)],             # low buzz: nothing heard
        }
        for freq, ms in tones.get(kind, []):
            winsound.Beep(freq, ms)
    except Exception:
        pass


def _cuda_search_paths() -> list:
    """Directories that might hold cuBLAS and cuDNN, best candidate first.

    Two ways they arrive. An installed copy gets them from the optional GPU
    pack, unpacked flat into LOCALAPPDATA. A source checkout gets them from the
    pip wheels, which scatter them across site-packages/nvidia/*/bin.
    """
    import pathlib
    import site

    import paths

    found = [paths.gpu_dir() / "bin"]
    for p in site.getsitepackages():
        found.extend((pathlib.Path(p) / "nvidia").glob("*/bin"))
    found.extend((pathlib.Path(__file__).parent / ".venv" / "Lib"
                  / "site-packages" / "nvidia").glob("*/bin"))
    return [d for d in found if d.is_dir()]


def _register_cuda_dlls() -> None:
    """Make those directories loadable. Without this the model loads fine and
    then fails on the first encode with 'Library cublas64_12.dll is not
    found'."""
    found = [str(d) for d in _cuda_search_paths()]
    for d in found:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass

    # add_dll_directory alone is not enough: CTranslate2 resolves cuBLAS
    # lazily with a plain LoadLibrary, which searches PATH and ignores the
    # directories registered above.
    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dlls()


def cuda_usable() -> bool:
    """Whether inference can actually run on the GPU right now.

    Asking CTranslate2 for a device count is not enough on its own: it answers
    from the driver, which is present on any machine with an NVIDIA card, and
    returns 1 even when none of the maths libraries are installed. Believing it
    means choosing the GPU and then dying at the first encode. The honest test
    is whether cuBLAS itself loads.
    """
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0:
            return False
    except Exception:
        return False
    try:
        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cudnn64_9.dll")
        return True
    except OSError:
        return False


def has_nvidia_gpu() -> bool:
    """A card is present, whether or not the maths libraries are. This is what
    decides if the GPU pack is worth offering."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False

import numpy as np
import sounddevice as sd
from pynput import keyboard

# The Windows console defaults to cp1252, which cannot encode most of what a
# multilingual model will hand back - printing a Turkish transcript would
# otherwise raise UnicodeEncodeError and take the app down with it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────── configuration ──

# pynput syntax: named keys need angle brackets (<space>, <f9>, <cmd>); plain
# characters do not (q). Getting this wrong raises ValueError at startup.
#
# Deliberately NOT Ctrl+Alt: on Turkish (and most European) layouts AltGr is
# delivered by Windows as a synthetic Ctrl+Alt, so Ctrl+Alt combinations fire
# unreliably - typically once, then not again.
#
# Ctrl+Space is the default because it is what people who dictate already have
# in their fingers. It is not free of conflicts - it opens autocomplete in most
# editors and switches input method with a CJK IME installed - and pynput cannot
# swallow a key without swallowing every key, so the focused application sees it
# too. That is what HOTKEY_DICTATE being a setting is for; the setup guide
# offers to change it.
HOTKEY_DICTATE = "<ctrl>+<space>"
HOTKEY_QUIT = "<f10>"


def resolve_hotkey() -> str:
    """The dictation hotkey: whatever was chosen, or the default above."""
    return load_config().get("hotkey") or HOTKEY_DICTATE


def hotkey_label(combo: str | None = None) -> list:
    """A hotkey as the keycaps to draw for it: '<ctrl>+<space>' -> [Ctrl, Space].

    The interface shows this in three places and none of them want angle
    brackets, so the translation lives here rather than in each of them.
    """
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Win",
             "space": "Space", "enter": "Enter", "tab": "Tab", "esc": "Esc",
             "caps_lock": "Caps", "backspace": "Backspace"}
    caps = []
    for part in (combo or resolve_hotkey()).split("+"):
        part = part.strip().strip("<>")
        caps.append(names.get(part, part.upper()))
    return caps

# Measured on this machine (RTX 5070 Ti Laptop, 4.0s clip, see README):
#   large-v3 float16       0.9x realtime   <- too slow to dictate with
#   large-v3 int8_float16  1.1x realtime
#   small    int8_float16  4.7x realtime   <- responsive
# CTranslate2 4.8.1 has no native kernels for Blackwell (sm_120) and falls back
# to JIT-compiled PTX: the GPU sits at 100% but delivers a fraction of what it
# should. Until that lands upstream, the smaller model is the honest choice.
MODEL = os.environ.get("MURMUR_MODEL", "small")  # small / distil-large-v3 / large-v3
DEVICE = "cuda"                 # falls back to CPU automatically if unavailable
COMPUTE_TYPE = "int8_float16"   # "int8" on CPU
LANGUAGE = None           # None = autodetect; "en" is faster and more accurate

SAMPLE_RATE = 16_000      # what Whisper expects
MAX_SECONDS = 300         # a hard stop so a forgotten session can't eat all RAM

# Apps whose paste shortcut isn't Ctrl+V. Process name (lowercase) -> keys.
# Legacy consoles are the usual offenders; add to taste.
PASTE_OVERRIDES: dict[str, str] = {
    # "conhost.exe": "ctrl+shift+v",
}

# ─────────────────────────────────────────────────────────────── the models ──
# All Whisper weights are MIT licensed and hosted by Hugging Face, so every one
# of these can be offered freely and none of them cost anything to distribute.
# Download sizes are approximate.

MODELS: dict[str, dict] = {
    "tiny": {
        "title": "Tiny", "params": "39M", "size": "75 MB",
        "lang": "99 languages", "note": "Answers instantly",
    },
    "base": {
        "title": "Base", "params": "74M", "size": "145 MB",
        "lang": "99 languages", "note": "Fast, still rough",
    },
    "small": {
        "title": "Small", "params": "244M", "size": "480 MB",
        "lang": "99 languages", "note": "Faster than you speak",
    },
    "distil-large-v3": {
        "title": "Distil Large v3", "params": "756M", "size": "1.5 GB",
        "lang": "English only", "note": "Large's accuracy, half the wait",
    },
    "medium": {
        "title": "Medium", "params": "769M", "size": "1.5 GB",
        "lang": "99 languages", "note": "Better with names and noise",
    },
    "large-v3": {
        "title": "Large v3", "params": "1550M", "size": "3.1 GB",
        "lang": "99 languages", "note": "The most accurate, and the slowest",
    },
}

CONFIG_PATH = None  # set in main(); kept next to this file


def _config_path():
    import paths
    return paths.config_file()


def load_config() -> dict:
    import json

    path = _config_path()
    if not path.is_file():
        return {}
    try:
        # utf-8-sig, not utf-8: Notepad and PowerShell both put a byte order
        # mark at the front of a file they save, and json.loads treats that
        # mark as a syntax error. Reading it as plain utf-8 meant one edit in
        # Notepad silently discarded every setting - the shortcut, the chosen
        # model, whether the setup guide had been seen - and the file still
        # looked perfectly correct to whoever opened it.
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        # Silence here is what made the bug above so hard to see: settings
        # simply stopped applying, with nothing anywhere saying why.
        print(f"  config.json could not be read ({e}); using defaults")
        return {}


def save_config(cfg: dict) -> None:
    import json
    _config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def resolve_model() -> str:
    """Environment beats saved config beats the built-in default."""
    return os.environ.get("MURMUR_MODEL") or load_config().get("model") or MODEL


def better_model(current: str | None = None) -> str | None:
    """The model worth retrying a misheard dictation with, or None.

    Bigger, in the order the models are listed, which is the order they get
    slower and more accurate in. A model already on disk is preferred over a
    better one that is not, because "redo this" should not mean "download 3 GB
    first" unless there is nothing else to offer.

    English-only weights are skipped unless English is the named language.
    distil-large-v3 is more accurate than small at everything except the one
    thing that matters here - it would transcribe Turkish into confident
    nonsense, which is exactly the failure the retry exists to fix.
    """
    current = current or resolve_model()
    names = list(MODELS)
    candidates = names[names.index(current) + 1:] if current in names else names
    if resolve_language() != "en":
        candidates = [n for n in candidates
                      if "English" not in MODELS[n].get("lang", "")]
    if not candidates:
        return None
    downloaded = [n for n in candidates if is_downloaded(n)]
    return downloaded[-1] if downloaded else candidates[-1]


# ── language ───────────────────────────────────────────────────────────────
# Whisper knows a hundred languages and will guess which one it is hearing.
# On a dictation-length clip that guess is unreliable: there is not much audio
# to go on, and a wrong guess does not produce a mistranslation - it produces
# confident nonsense, because the decoder commits to the wrong vocabulary and
# writes fluent text in it. Naming the language removes the guess and is
# measurably faster, since the detection pass is skipped.

# The ones worth putting at the top of a list. Everything Whisper supports is
# still offered underneath; this is only about what someone scrolls past.
COMMON_LANGUAGES = [
    ("tr", "Turkish"), ("en", "English"), ("de", "German"), ("fr", "French"),
    ("es", "Spanish"), ("it", "Italian"), ("nl", "Dutch"), ("pt", "Portuguese"),
    ("ru", "Russian"), ("ar", "Arabic"), ("zh", "Chinese"),
    ("ja", "Japanese"), ("ko", "Korean"),
]


def all_languages() -> list:
    """(code, name) for every language the model supports, common ones first."""
    try:
        from faster_whisper.tokenizer import _LANGUAGE_CODES
        codes = set(_LANGUAGE_CODES)
    except Exception:
        codes = {c for c, _ in COMMON_LANGUAGES}

    out = [(c, n) for c, n in COMMON_LANGUAGES if c in codes]
    seen = {c for c, _ in out}
    try:
        import locale
        names = {}
        for c in sorted(codes - seen):
            names[c] = c.upper()
        out.extend(sorted(names.items(), key=lambda kv: kv[1]))
    except Exception:
        out.extend((c, c.upper()) for c in sorted(codes - seen))
    return out


def resolve_language():
    """The language to decode in, or None to let the model guess."""
    return load_config().get("language") or LANGUAGE


#: How many languages the quick menu offers before it is just the full list
#: again. Four covers everyone who switches; a longer menu is a worse menu.
QUICK_LANGUAGES = 4


def recent_languages() -> list:
    """Language codes most recently dictated in, newest first.

    Kept so the menu can offer the two or three languages someone actually
    speaks without asking them to configure a list. Naming the language is
    2.6x faster than letting the model detect it and far more accurate, but
    only if changing it does not mean opening a window mid-sentence.
    """
    saved = load_config().get("recent_languages") or []
    out = []
    for code in saved:
        if isinstance(code, str) and code and code not in out:
            out.append(code)
    return out[:QUICK_LANGUAGES]


def set_language(code: str | None) -> None:
    """Switch the spoken language and remember it as recently used.

    Detect-automatically is stored as the setting but never enters the recent
    list: it is not a language, and a menu offering it twice is a menu that
    looks broken.
    """
    code = code or ""
    cfg = load_config()
    cfg["language"] = code
    if code:
        recent = [c for c in recent_languages() if c != code]
        cfg["recent_languages"] = [code] + recent[:QUICK_LANGUAGES - 1]
    save_config(cfg)


def language_name(code) -> str:
    if not code:
        return "Detect automatically"
    for c, name in all_languages():
        if c == code:
            return name
    return code.upper()


# ── vocabulary ─────────────────────────────────────────────────────────────

def vocabulary() -> list:
    """Words the model should lean towards: names, jargon, product names."""
    words = load_config().get("vocabulary") or []
    return [w.strip() for w in words if w and w.strip()]


def hotwords():
    """The vocabulary as the single string faster-whisper wants, or None.

    This biases the decoder, it does not constrain it: a word on the list is
    made more likely, not guaranteed, and one that sounds nothing like what was
    said still will not appear. Worth being clear about, because "custom
    vocabulary" sounds like a dictionary lookup and behaves like a nudge.

    faster-whisper truncates this to half the prompt window itself, so a long
    list degrades quietly rather than failing - but the words past the cut have
    no effect, which is why the interface says how many will fit.
    """
    words = vocabulary()
    return ", ".join(words) if words else None


#: Roughly how many words fit in the prompt window Whisper reserves for this.
#: Half of 224 tokens, and a proper noun is rarely one token, so this is a
#: deliberately conservative figure to advise people with.
VOCABULARY_ADVISED = 60


# ── output rules ───────────────────────────────────────────────────────────
# Vocabulary biases what the decoder hears. This fixes what it writes, which
# is a different problem: "github" comes out lowercase every time, an address
# comes out as "kaan at gmail dot com", and no amount of biasing the audio
# side changes either, because the model heard those perfectly well.
#
# A rule is a pair - what it writes, what you wanted - applied to the finished
# transcript. Deliberately not regular expressions: the people who need this
# are fixing the spelling of their own surname, and a syntax error in a
# settings box that silently stops all dictation would be a poor trade for
# power nobody asked for.


def replacements() -> list:
    """The output rules, as (find, replace) pairs."""
    raw = load_config().get("replacements") or []
    out = []
    for item in raw:
        # Stored as two-element lists because JSON has no tuples. Anything
        # else in the file is somebody's hand edit, and skipping it beats
        # taking the whole config down over one malformed row.
        if isinstance(item, (list, tuple)) and len(item) == 2:
            find, into = str(item[0]).strip(), str(item[1])
            if find:
                out.append((find, into))
    return out


#: Characters that belong tight against the word in front of them. A phrase
#: spoken aloud carries a space before it - "kaan at gmail dot com", "hello
#: comma world" - and replacing only the phrase leaves that space stranded:
#: "kaan @gmail.com", "hello , world". These are the replacements where the
#: space was part of what was being said.
ATTACHING = ",.!?;:)]}%@"


@functools.lru_cache(maxsize=256)
def _rule_pattern(find: str, eat_space: bool = False):
    """Whole-word, case-insensitive.

    Whole-word because a rule turning "at" into "@" must not touch "attention",
    and that is the first rule anyone writes. The boundaries are only applied
    at ends that are actually word characters, since \\b next to punctuation
    means the opposite of what it looks like and would stop a rule for "..."
    from ever matching.

    eat_space extends the match backwards over the space in front, for the
    replacements that should sit against the previous word rather than after
    a gap. It cannot swallow a word: the boundary still has to hold, so a rule
    for "at" matches " at" and never "kaanat".
    """
    left = r"\b" if find[:1].isalnum() else ""
    right = r"\b" if find[-1:].isalnum() else ""
    lead = r"[ \t]*" if eat_space else ""
    return re.compile(lead + left + re.escape(find) + right, re.IGNORECASE)


def apply_rules(text: str) -> str:
    """Run the output rules over a finished transcript.

    Rules are applied in order and to the result of the previous one, so a
    later rule can act on what an earlier one produced. That is worth knowing
    when writing them and is why the interface keeps them in a visible order
    rather than a set.
    """
    for find, into in replacements():
        # Deleting a word takes the space with it, or "I um think" becomes
        # "I  think"; punctuation takes it for the reason above.
        eat_space = not into or into[0] in ATTACHING
        # A function as the replacement, not a string: re.sub reads \1 and \g
        # in a string replacement as group references, so a rule replacing
        # something with "\1" would raise mid-dictation. Returning the text
        # from a callable makes it literal, which is the only thing a rule
        # here is ever meant to be.
        text = _rule_pattern(find, eat_space).sub(lambda _m, r=into: r, text)
    return text


# ── the microphone ─────────────────────────────────────────────────────────

def _device_key(name: str) -> str:
    """A form of the name the different drivers can be compared on.

    MME truncates device names at 31 characters, so the same microphone is
    "Microphone Array (Intel(R) Smart" under one driver and "Microphone Array
    (Intel(R) Smart Sound Technology)" under another. Comparing the truncated
    form is the only way to tell they are the same thing.
    """
    return name.strip().lower()[:30]


# Which driver family to open a microphone through, best first. WDM-KS is
# absent on purpose: it is a kernel-streaming interface, it names devices things
# like "Microphone Array 1 ()", and PortAudio cannot open it in the blocking
# mode used here - picking one from a list would simply fail.
HOST_API_RANK = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}


def input_devices() -> list[dict]:
    """The microphones, one entry each.

    Windows exposes every microphone through several driver families, so the
    raw listing shows each one three or four times under three or four
    spellings - and MME, which is the one that opens most reliably, truncates
    names at 31 characters. So the entries are collapsed per microphone, taking
    the fullest name from whichever driver spells it out and the index from
    whichever driver opens it best. The name you read and the device that gets
    opened need not come from the same row.
    """
    try:
        default_index = sd.default.device[0]
        devices = sd.query_devices()
    except Exception:
        return []

    default_key = None
    if isinstance(default_index, int) and 0 <= default_index < len(devices):
        default_key = _device_key(devices[default_index]["name"])

    best: dict[str, dict] = {}
    for index, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        try:
            api = sd.query_hostapis(d["hostapi"])["name"]
        except Exception:
            continue
        if api not in HOST_API_RANK:
            continue
        name = d["name"].strip()
        # Not microphones: routing endpoints PortAudio lists alongside them,
        # which record silence and confuse anyone who picks one.
        if name.lower().startswith(("microsoft sound mapper",
                                    "primary sound capture")):
            continue

        key = _device_key(name)
        rank = HOST_API_RANK[api]
        entry = best.setdefault(key, {"name": name, "index": index,
                                      "rank": rank, "default": False})
        if len(name) > len(entry["name"]):
            entry["name"] = name          # the fullest spelling
        if rank < entry["rank"]:
            entry["index"], entry["rank"] = index, rank
        if key == default_key:
            entry["default"] = True

    return [{k: v for k, v in e.items() if k != "rank"}
            for e in best.values()]


def resolve_device():
    """The device index to record from, or None for whatever Windows prefers.

    Returns None when the saved microphone is gone rather than raising: a
    headset unplugged since yesterday should cost you the preference, not the
    ability to dictate.
    """
    saved = load_config().get("device")
    if not saved:
        return None
    key = _device_key(saved)
    for d in input_devices():
        if _device_key(d["name"]) == key:
            return d["index"]
    return None


def device_label() -> str:
    """What to show as the microphone in use."""
    saved = load_config().get("device")
    if saved:
        key = _device_key(saved)
        for d in input_devices():
            if _device_key(d["name"]) == key:
                return d["name"]
        return f"{saved} (not connected)"
    for d in input_devices():
        if d["default"]:
            return f"{d['name']} (default)"
    try:
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return "No microphone found"


def is_downloaded(name: str) -> bool:
    import pathlib
    cache = pathlib.Path.home() / ".cache" / "huggingface" / "hub"
    d = cache / f"models--Systran--faster-whisper-{name}"
    return d.is_dir() and any(d.rglob("model.bin"))


def disk_used(name: str) -> float:
    import pathlib
    cache = pathlib.Path.home() / ".cache" / "huggingface" / "hub"
    d = cache / f"models--Systran--faster-whisper-{name}"
    if not d.is_dir():
        return 0.0
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / (1024 ** 3)

# ─────────────────────────────────────────────────────────────── clipboard ──
# Done with ctypes rather than a dependency: it's a dozen calls and it means
# one less wheel to ship when this gets packaged.

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

#: How long to leave the dictation on the clipboard before putting the previous
#: contents back. This is a race against the target application actually reading
#: the clipboard, and there is no signal for "the paste happened" short of owning
#: the clipboard and rendering it lazily. 0.35s was too tight: a loaded machine,
#: an Electron window or an RDP session can take longer, and losing that race
#: means the app pastes whatever the user copied *before* dictating. For anyone
#: with a password manager open that is the worst thing this program could do.
#: Nobody notices a clipboard restored a second later.
RESTORE_DELAY = 1.5

#: Windows reads these registered formats to decide what may be done with a
#: clipboard entry. They are split because the two questions are not the same
#: one.
#:
#: The cloud clipboard syncs between a user's machines through Microsoft's
#: servers, so dictated text is always excluded from it: a program whose whole
#: claim is that nothing leaves this computer cannot quietly post every sentence
#: you speak to a server.
NEVER_LEAVE_MACHINE = ("CanUploadToCloudClipboard",)

#: The local history is the user's own machine, so this one is conditional. It
#: applies only while the clipboard is being used as transport - when Murmur is
#: about to put the previous contents back. Someone who has turned that restore
#: off has asked for the dictation to stay on the clipboard, and keeping it out
#: of Win+V would then be working against them rather than protecting them.
KEEP_OUT_OF_HISTORY = ("ExcludeClipboardContentFromMonitorProcessing",
                       "CanIncludeInClipboardHistory")

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

u32.OpenClipboard.argtypes = [wt.HWND]
u32.OpenClipboard.restype = wt.BOOL
u32.GetClipboardData.argtypes = [wt.UINT]
u32.GetClipboardData.restype = wt.HANDLE
u32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
u32.SetClipboardData.restype = wt.HANDLE
u32.RegisterClipboardFormatW.argtypes = [wt.LPCWSTR]
u32.RegisterClipboardFormatW.restype = wt.UINT
u32.GetClipboardSequenceNumber.restype = wt.DWORD
k32.GlobalLock.argtypes = [wt.HGLOBAL]
k32.GlobalLock.restype = wt.LPVOID
k32.GlobalUnlock.argtypes = [wt.HGLOBAL]
k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = wt.HGLOBAL

# Handles are 64-bit; without an explicit restype ctypes assumes c_int and
# silently truncates them, which fails in ways that look like permissions bugs.
u32.GetForegroundWindow.restype = wt.HWND
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.GetWindowThreadProcessId.restype = wt.DWORD
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
k32.QueryFullProcessImageNameW.restype = wt.BOOL
k32.CloseHandle.argtypes = [wt.HANDLE]


def _open_clipboard(attempts: int = 40) -> bool:
    """The clipboard is a single global lock; other apps hold it briefly.

    The budget is deliberately about a second rather than the 0.2s it used to
    be. Losing this lock is not cosmetic - the dictation is dropped and the only
    complaint is a print() that the windowed build has no console to show - and
    0.2s turned out to be short enough to lose on an otherwise idle machine.
    """
    for _ in range(attempts):
        if u32.OpenClipboard(None):
            return True
        time.sleep(0.025)
    return False


def clipboard_get() -> str | None:
    if not _open_clipboard():
        return None
    try:
        handle = u32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = k32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            k32.GlobalUnlock(handle)
    finally:
        u32.CloseClipboard()


_formats: dict[str, int] = {}


def _format_id(name: str) -> int:
    """RegisterClipboardFormatW, memoised. The same name always maps to the
    same id for the lifetime of the session, so asking twice is wasted work."""
    if name not in _formats:
        _formats[name] = u32.RegisterClipboardFormatW(name)
    return _formats[name]


def _dword_handle(value: int):
    """A movable global holding a single DWORD, which is what the privacy
    marker formats expect as their payload."""
    handle = k32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(wt.DWORD))
    if not handle:
        return None
    ptr = k32.GlobalLock(handle)
    ctypes.memmove(ptr, ctypes.byref(wt.DWORD(value)), ctypes.sizeof(wt.DWORD))
    k32.GlobalUnlock(handle)
    return handle


def clipboard_set(text: str, marks: tuple[str, ...] = ()) -> bool:
    """Put text on the clipboard, optionally with marker formats attached.

    `marks` names the registered formats to set alongside the text - see
    NEVER_LEAVE_MACHINE and KEEP_OUT_OF_HISTORY. Nothing is marked by default,
    because restoring whatever the user had on the clipboard before must not
    reclassify it: that content is theirs and was never ours to relabel.
    """
    if not _open_clipboard():
        return False
    try:
        u32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        handle = k32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = k32.GlobalLock(handle)
        ctypes.memmove(ptr, buf, size)
        k32.GlobalUnlock(handle)
        # On success the system owns this memory - do not free it.
        if not u32.SetClipboardData(CF_UNICODETEXT, handle):
            return False

        # Best effort by design: an older Windows that does not know a format
        # simply registers the name and ignores the data, and a failure here
        # must never cost the user their paste.
        for name in marks:
            marker = _dword_handle(0)
            if marker:
                u32.SetClipboardData(_format_id(name), marker)
        return True
    finally:
        u32.CloseClipboard()


# ────────────────────────────────────────────────────────── foreground app ──

def foreground_process() -> str:
    """Lowercased exe name of whatever window has focus, or ''."""
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        n = wt.DWORD(512)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        k32.CloseHandle(h)
    return ""


# ───────────────────────────────────────────────────────────────── pasting ──

kb = keyboard.Controller()

_KEYS = {
    "ctrl": keyboard.Key.ctrl,
    "shift": keyboard.Key.shift,
    "alt": keyboard.Key.alt,
}


def _release_modifiers() -> None:
    """The hotkey's own modifiers may still be physically held down; if we
    paste while Alt is down the target app sees Ctrl+Alt+V instead."""
    for key in (keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.shift,
                keyboard.Key.cmd):
        try:
            kb.release(key)
        except Exception:
            pass


def paste(text: str) -> None:
    combo = PASTE_OVERRIDES.get(foreground_process(), "ctrl+v")
    *mods, final = combo.split("+")

    previous = clipboard_get()
    restoring = previous is not None and load_config().get("restore_clip", True)
    marks = NEVER_LEAVE_MACHINE + (KEEP_OUT_OF_HISTORY if restoring else ())
    if not clipboard_set(text, marks):
        print("  ! could not write to clipboard; is another app holding it?")
        return
    ours = u32.GetClipboardSequenceNumber()

    _release_modifiers()
    time.sleep(0.08)  # let the modifier release register before we press again

    for m in mods:
        kb.press(_KEYS[m])
    kb.press(final)
    kb.release(final)
    for m in reversed(mods):
        kb.release(_KEYS[m])

    # Give the target app time to actually read the clipboard before we put the
    # old contents back - see RESTORE_DELAY for why it is as long as it is. The
    # Sound page can turn this off, for anyone who would rather the dictation
    # stayed on the clipboard to paste again.
    if not restoring:
        return

    time.sleep(RESTORE_DELAY)

    # If anything else wrote to the clipboard while we waited - the user copied
    # something, another program pushed to it - that write is newer than ours,
    # and restoring now would silently destroy it. The sequence number is the
    # only cheap way to notice; it moves on every clipboard update and not on a
    # read, so unchanged means nobody has touched it since we did.
    if u32.GetClipboardSequenceNumber() != ours:
        return
    clipboard_set(previous)


# ─────────────────────────────────────────────────────────────── recording ──

class Recorder:
    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self.active = False

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"  audio: {status}")
        self._frames.append(indata.copy())

    def start(self) -> None:
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=self._callback,
        )
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
        audio = np.concatenate(self._frames, axis=0).flatten()
        return audio[: MAX_SECONDS * SAMPLE_RATE]


# ──────────────────────────────────────────────────────────────────── main ──

def load_model(name: str | None = None):
    from faster_whisper import WhisperModel

    name = name or resolve_model()
    device, compute = DEVICE, COMPUTE_TYPE
    if device == "cuda" and not cuda_usable():
        if has_nvidia_gpu():
            print("  GPU found but the CUDA libraries are missing - running on "
                  "CPU. Install the GPU pack to use the card.")
        else:
            print("  no CUDA device visible - falling back to CPU (slower)")
        device, compute = "cpu", "int8"

    if not is_downloaded(name):
        meta = MODELS.get(name, {})
        print(f"downloading {name} ({meta.get('size', 'unknown size')}) - once only")
    print(f"loading {name} on {device} ({compute}) ...")
    t0 = time.time()
    model = WhisperModel(name, device=device, compute_type=compute)
    print(f"  ready in {time.time() - t0:.1f}s")
    return model


def transcribe(model, audio: np.ndarray) -> str:
    segments, _ = model.transcribe(
        audio,
        language=resolve_language(),
        # Names and jargon the decoder should lean towards. Passed as hotwords
        # rather than initial_prompt: hotwords is applied through the same
        # mechanism but is independent of condition_on_previous_text, which is
        # off below, and faster-whisper truncates it to fit the prompt window
        # instead of silently corrupting it.
        hotwords=hotwords(),
        # Beam search buys almost nothing on dictation-length clips (measured:
        # 4.50s vs 4.43s on large-v3) and costs latency, so take the greedy path.
        beam_size=1,
        # Silero VAD. Whisper is a language model at heart and will happily
        # invent a sentence out of silence; gating on speech stops that.
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,
    )
    # Rules run here rather than at the paste, so the --file path, the setup
    # guide and the history all see the same text the window would have got.
    return apply_rules(" ".join(s.text.strip() for s in segments).strip())


def _sample_clip() -> np.ndarray | None:
    """A known phrase to time models against. Synthesised with the speech voice
    every Windows install already has, so this needs no bundled audio file."""
    import subprocess
    import wave

    import paths

    path = paths.data_dir() / "_bench_sample.wav"
    if not path.exists():
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{path}'); "
            "$s.Speak('Send the quarterly report to the finance team by Friday.'); "
            "$s.Dispose()"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           check=True, capture_output=True, timeout=90)
        except Exception as e:
            print(f"  could not synthesise a test clip: {e}")
            return None

    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        rate = w.getframerate()
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != SAMPLE_RATE:
        idx = np.linspace(0, len(a) - 1, int(len(a) * SAMPLE_RATE / rate))
        a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    return a


def benchmark() -> int:
    """Time every downloaded model on this machine, so the choice is made from
    measurements rather than from a table someone wrote on other hardware."""
    audio = _sample_clip()
    if audio is None:
        return 1
    secs = len(audio) / SAMPLE_RATE

    have = [n for n in MODELS if is_downloaded(n)]
    if not have:
        print("  no models downloaded yet. Try:  run.bat --model small")
        return 1

    print(f"\n  timing {len(have)} model(s) on a {secs:.1f}s clip\n")
    print(f"  {'model':<18}{'time':>9}{'speed':>10}   transcript")
    print("  " + "-" * 78)
    for name in have:
        try:
            model = load_model(name)
            transcribe(model, audio)                    # warm the kernels
            t0 = time.time()
            text = transcribe(model, audio)
            took = time.time() - t0
            print(f"  {name:<18}{took:8.2f}s{secs / took:9.1f}x   "
                  f"{text[:44]}")
            del model
        except Exception as e:
            print(f"  {name:<18}   failed: {type(e).__name__}: {str(e)[:40]}")
    print(f"\n  Higher speed is better; anything under 1x means you wait "
          f"longer than you spoke.\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Murmur - local voice to text")
    ap.add_argument("--devices", action="store_true",
                    help="list input devices and exit")
    ap.add_argument("--file", metavar="WAV",
                    help="transcribe a wav file and exit (no mic needed)")
    ap.add_argument("--models", action="store_true",
                    help="list the available speech models and exit")
    ap.add_argument("--model", metavar="NAME",
                    help="switch to a model (downloads it if needed) and remember it")
    ap.add_argument("--benchmark", action="store_true",
                    help="time every downloaded model on this machine")
    args = ap.parse_args()

    if args.models:
        current = resolve_model()
        print(f"\n  {'':2}{'model':<18}{'params':<9}{'download':<11}"
              f"{'language':<15}{'on disk':<10}notes")
        print("  " + "-" * 92)
        for name, meta in MODELS.items():
            mark = "->" if name == current else "  "
            have = f"{disk_used(name):.1f} GB" if is_downloaded(name) else "-"
            print(f"  {mark}{name:<18}{meta['params']:<9}{meta['size']:<11}"
                  f"{meta['lang']:<15}{have:<10}{meta['note']}")
        print(f"\n  '->' is in use. Switch with:  run.bat --model <name>")
        print(f"  Models download on demand from Hugging Face and are free "
              f"(MIT licensed).\n")
        return 0

    if args.model:
        if args.model not in MODELS:
            print(f"unknown model {args.model!r}. Choose one of: "
                  f"{', '.join(MODELS)}")
            return 2
        meta = MODELS[args.model]
        if not is_downloaded(args.model):
            print(f"{args.model} is not downloaded yet ({meta['size']}). Fetching ...")
        load_model(args.model)          # downloads and verifies it actually loads
        cfg = load_config()
        cfg["model"] = args.model
        save_config(cfg)
        print(f"\n  now using {args.model} ({meta['params']}, {meta['lang']})")
        print(f"  saved to config.json - restart Murmur to use it\n")
        return 0

    if args.benchmark:
        return benchmark()

    if args.devices:
        print(sd.query_devices())
        print(f"\ndefault input: {sd.query_devices(kind='input')['name']}")
        return 0

    model = load_model()

    if args.file:
        import wave
        with wave.open(args.file, "rb") as w:
            raw = w.readframes(w.getnframes())
            rate = w.getframerate()
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if rate != SAMPLE_RATE:
            idx = np.linspace(0, len(audio) - 1,
                              int(len(audio) * SAMPLE_RATE / rate))
            audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
        t0 = time.time()
        text = transcribe(model, audio)
        secs = len(audio) / SAMPLE_RATE
        took = time.time() - t0
        print(f"\n{text}\n")
        print(f"  {secs:.1f}s of audio in {took:.2f}s  ({secs / took:.1f}x realtime)")
        return 0

    recorder = Recorder()
    jobs: queue.Queue[np.ndarray] = queue.Queue()
    stopping = threading.Event()

    def worker() -> None:
        while not stopping.is_set():
            try:
                audio = jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            secs = len(audio) / SAMPLE_RATE
            if secs < 0.3:
                print("  too short, ignoring")
                beep("empty")
                continue
            print("  transcribing ...")
            t0 = time.time()
            text = transcribe(model, audio)
            took = time.time() - t0
            if not text:
                print("  nothing heard (silence, or the mic picked up nothing)")
                beep("empty")
                continue
            print(f'  "{text}"')
            print(f"  {secs:.1f}s in {took:.2f}s ({secs / took:.1f}x realtime)")
            target = foreground_process() or "?"
            paste(text)
            print(f"  pasted into {target}")
            beep("done")

    threading.Thread(target=worker, daemon=True).start()

    def toggle() -> None:
        if recorder.active:
            audio = recorder.stop()
            print(f"stopped   {len(audio) / SAMPLE_RATE:.1f}s captured")
            beep("stop")
            jobs.put(audio)
        else:
            recorder.start()
            print(f"listening ...  speak now, press {dictate} again to stop")
            beep("start")

    def quit_app() -> None:
        print("bye")
        stopping.set()
        quit_listener.stop()

    # Fail with something readable rather than a traceback out of pynput.
    dictate = resolve_hotkey()
    for label, combo in (("HOTKEY_DICTATE", dictate),
                         ("HOTKEY_QUIT", HOTKEY_QUIT)):
        try:
            keyboard.HotKey.parse(combo)
        except ValueError as e:
            print(f"\n  {label} = {combo!r} is not valid: unknown key {e}")
            print("  Named keys need angle brackets: <space>, <f9>, <enter>.")
            print("  Plain characters do not: q, 1, .\n")
            return 2

    print(f"\n  {dictate}   dictate (press once to start, again to stop)")
    print(f"  {HOTKEY_QUIT}       quit\n")

    # The dictation key is swallowed so the window being dictated into does not
    # also act on it; quit is left alone, since taking a function key away from
    # the whole machine to end a console session would be rude.
    from hotkeys import GlobalHotkey

    dictate_hotkey = GlobalHotkey(dictate, toggle)
    dictate_hotkey.start()
    try:
        with keyboard.GlobalHotKeys({HOTKEY_QUIT: quit_app}) as quit_listener:
            quit_listener.join()
    finally:
        dictate_hotkey.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
