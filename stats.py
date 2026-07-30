"""What Murmur has done, remembered across restarts.

Counters that reset every launch say nothing - the number is always small and
always about the last ten minutes. These are kept per day in LOCALAPPDATA, which
makes "this week" answerable and keeps the file small enough to never need
pruning logic: a year of heavy use is a few hundred lines of JSON.

Only totals are stored. No transcript, and no text of any kind, ever reaches
this file - the names of applications dictated into are the most specific thing
in it, and those are what make "apps used" mean anything.
"""
from __future__ import annotations

import datetime
import json

import paths

# What "saved this week" is measured against. Sustained prose typing for an
# average office worker sits around here; it is a stated assumption rather than
# a measurement of you, which is why the interface says so next to the number.
TYPING_WPM = 40.0


def _today() -> str:
    return datetime.date.today().isoformat()


def _path():
    return paths.data_dir() / "stats.json"


def load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8-sig"))
    except Exception:
        return {"days": {}}


def _save(data: dict) -> None:
    try:
        _path().write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass        # a statistic is never worth interrupting a dictation for


def record(words: int, spoken_seconds: float, app: str) -> None:
    """Add one finished dictation."""
    data = load()
    day = data.setdefault("days", {}).setdefault(
        _today(), {"words": 0, "spoken": 0.0, "sessions": 0, "apps": []})
    day["words"] += words
    day["spoken"] += spoken_seconds
    day["sessions"] += 1
    if app and app not in day["apps"]:
        day["apps"].append(app)
    _save(data)


def _recent(days: int = 7) -> list[dict]:
    cutoff = datetime.date.today() - datetime.timedelta(days=days - 1)
    out = []
    for key, day in load().get("days", {}).items():
        try:
            if datetime.date.fromisoformat(key) >= cutoff:
                out.append(day)
        except ValueError:
            continue
    return out


def summary() -> dict:
    """The four figures on the Home page.

    speed is words per minute of *speech*, which is what the microphone
    measured, not a guess. saved compares that against typing the same words at
    TYPING_WPM, and is deliberately floored at zero rather than showing a
    negative number on the day someone dictates one word and pauses.
    """
    week = _recent()
    words = sum(d.get("words", 0) for d in week)
    spoken = sum(d.get("spoken", 0.0) for d in week)
    apps = {a for d in week for a in d.get("apps", [])}

    minutes_spoken = spoken / 60.0
    wpm = words / minutes_spoken if minutes_spoken > 0.05 else 0.0
    saved = max(0.0, words / TYPING_WPM - minutes_spoken)

    total = load().get("days", {})
    return {
        "wpm": round(wpm),
        "words": words,
        "apps": len(apps),
        "saved_minutes": saved,
        "sessions": sum(d.get("sessions", 0) for d in week),
        "words_all_time": sum(d.get("words", 0) for d in total.values()),
    }


def format_saved(minutes: float) -> str:
    if minutes < 1:
        return "0 min"
    if minutes < 60:
        return f"{minutes:.0f} min"
    hours = minutes / 60
    return f"{hours:.1f} hr" if hours < 10 else f"{hours:.0f} hr"
