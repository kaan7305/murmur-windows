"""Transcripts kept across restarts, when that has been asked for.

Off by default, and the default is the point. Everything else Murmur writes
down is a total - words, seconds, the names of applications - and none of it
can reconstruct anything anybody said. This file is the exception: it holds
the actual text. So it is opt-in, it says on the page that it is on, and there
is a button to empty it.

Kept separate from stats.json for the same reason. Someone deleting their
transcripts should not lose a year of counters to do it, and someone reading
the stats file should not find prose in it.
"""
from __future__ import annotations

import json
import time

import paths

#: How many transcripts to keep. Enough to find the thing you dictated this
#: morning and lost; not so many that the file becomes an archive nobody
#: decided to keep. Oldest are dropped first.
LIMIT = 300


def enabled() -> bool:
    import murmur as core
    return bool(core.load_config().get("keep_history", False))


def _path():
    return paths.data_dir() / "history.json"


def load() -> list:
    """Saved transcripts, newest first. Empty when the setting is off."""
    if not enabled():
        return []
    try:
        data = json.loads(_path().read_text(encoding="utf-8-sig"))
    except Exception:
        # A history that will not parse is not worth an error message. The
        # page simply starts empty, and the next dictation writes a good file.
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("text")][:LIMIT]


def add(text: str, meta: str) -> None:
    """Record one transcript, if saving is on.

    Reads the file, prepends, writes it back. That is O(file) per dictation
    and would be the wrong shape for a log; at 300 entries of a sentence each
    it is a few tens of kilobytes, and it keeps newest-first ordering free.
    """
    if not enabled() or not text:
        return
    entries = load()
    entries.insert(0, {"text": text, "meta": meta,
                       "stamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    _write(entries[:LIMIT])


def replace_latest(text: str, meta: str) -> None:
    """Correct the newest entry after a retry with a better model.

    The corrected text replaces the original rather than being added beside
    it. Two entries for one thing said once would make the history a record of
    Murmur's attempts instead of a record of what was dictated.
    """
    if not enabled() or not text:
        return
    entries = load()
    if not entries:
        return
    entries[0] = {**entries[0], "text": text, "meta": meta}
    _write(entries)


def clear() -> None:
    """Empty the history, and remove the file rather than leaving it blank.

    A user who presses Clear means the text should be gone, not replaced with
    an empty list in a file still sitting on disk under the same name.
    """
    try:
        _path().unlink(missing_ok=True)
    except OSError:
        _write([])


def _write(entries: list) -> None:
    try:
        _path().write_text(json.dumps(entries, indent=1, ensure_ascii=False),
                           encoding="utf-8")
    except OSError:
        pass        # never interrupt a dictation over a file that will not save
