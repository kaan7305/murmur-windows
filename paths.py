"""Where Murmur keeps its files.

An installed copy lives under Programs in LOCALAPPDATA, a directory the
installer owns: an upgrade overwrites what it finds there and an uninstall
removes it. So nothing mutable may sit beside the executable: config, logs and
the optional GPU pack all go to the Murmur folder in LOCALAPPDATA. A source
checkout uses the same layout, so there is one code path to reason about rather
than two.
"""
from __future__ import annotations

import os
import pathlib
import sys

FROZEN = getattr(sys, "frozen", False)


def app_dir() -> pathlib.Path:
    """The directory the program was launched from - not ours to write to."""
    if FROZEN:
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent


def resource(name: str) -> pathlib.Path:
    """A read-only file shipped inside the build.

    PyInstaller unpacks bundled data to a temporary directory and points
    sys._MEIPASS at it; in a onedir build that is the _internal folder.
    """
    base = getattr(sys, "_MEIPASS", None)
    return pathlib.Path(base) / name if base else app_dir() / name


def data_dir() -> pathlib.Path:
    """Everything Murmur writes. Created on first access."""
    root = os.environ.get("LOCALAPPDATA")
    base = pathlib.Path(root) if root else pathlib.Path.home() / "AppData" / "Local"
    d = base / "Murmur"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> pathlib.Path:
    return data_dir() / "config.json"


def log_file() -> pathlib.Path:
    return data_dir() / "murmur.log"


def gpu_dir() -> pathlib.Path:
    """Where the optional CUDA pack is unpacked to."""
    return data_dir() / "gpu"


def gpu_manifest() -> pathlib.Path:
    return gpu_dir() / "manifest.json"


def gpu_installed() -> bool:
    """True once a complete pack has been unpacked.

    The manifest is written last, so a download interrupted halfway leaves the
    directory present but unmarked and the next launch treats it as absent.
    """
    return gpu_manifest().is_file()
