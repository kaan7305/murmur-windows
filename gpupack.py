"""The optional GPU pack: cuBLAS, cuDNN and NVRTC, installed after the fact.

These libraries are two gigabytes and are useless without an NVIDIA card, so
bundling them would triple the download for the people who benefit least. They
are shipped as a separate archive instead, fetched only when there is a card to
run them on.

The pack unpacks flat into LOCALAPPDATA/Murmur/gpu/bin, which murmur.py adds to
the DLL search path at startup. Nothing is written near the program itself, so
none of this needs administrator rights.
"""
from __future__ import annotations

import json
import shutil
import zipfile

import paths

# Where a hosted pack lives. Left empty on purpose: fill it in when the archive
# is published somewhere, and the in-app button becomes a one-click download.
# Until then the same button asks for the file on disk, so the feature works
# with no server at all.
PACK_URL = ""

PACK_VERSION = "1"

# The libraries CTranslate2 resolves by name at inference time. Checked after
# unpacking so a truncated archive is caught here rather than mid-transcription.
REQUIRED = ["cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll",
            "cudnn_graph64_9.dll", "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll"]


class PackError(Exception):
    pass


def state() -> str:
    """One of:

    ready      the GPU is usable right now
    available  there is a card, but the libraries are missing
    none       no NVIDIA card, so the pack would do nothing
    """
    import murmur as core
    if core.cuda_usable():
        return "ready"
    return "available" if core.has_nvidia_gpu() else "none"


def installed_size() -> float:
    """Gigabytes on disk, 0.0 if not installed."""
    d = paths.gpu_dir()
    if not d.is_dir():
        return 0.0
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / (1024 ** 3)


def download(url: str, dest, progress=None, cancel=None) -> None:
    """Stream `url` to `dest`, calling progress(done, total) as it goes.

    Written to a .part file and renamed at the end, so an interrupted download
    can never be mistaken for a complete one.
    """
    import urllib.request

    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Murmur"})
    with urllib.request.urlopen(req, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(part, "wb") as f:
            while True:
                if cancel is not None and cancel():
                    f.close()
                    part.unlink(missing_ok=True)
                    raise PackError("Cancelled.")
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    part.replace(dest)


def install(archive, progress=None) -> None:
    """Unpack an archive into the GPU directory and mark it complete.

    The manifest is written last and is the only thing gpu_installed() looks at,
    so a crash partway through leaves the pack correctly reported as absent
    rather than half-present.
    """
    target = paths.gpu_dir()
    binaries = target / "bin"
    paths.gpu_manifest().unlink(missing_ok=True)
    shutil.rmtree(binaries, ignore_errors=True)
    binaries.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(archive) as z:
            members = [m for m in z.infolist()
                       if not m.is_dir() and m.filename.lower().endswith(".dll")]
            if not members:
                raise PackError("That archive contains no libraries - is it the "
                                "right file?")
            for i, m in enumerate(members, 1):
                # Flatten: the archive may carry the wheel's nested layout, and
                # a single directory is one entry on the DLL search path.
                name = m.filename.rsplit("/", 1)[-1]
                with z.open(m) as src, open(binaries / name, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if progress:
                    progress(i, len(members))
    except zipfile.BadZipFile:
        raise PackError("That file is not a valid archive.")

    missing = [n for n in REQUIRED if not (binaries / n).is_file()]
    if missing:
        shutil.rmtree(binaries, ignore_errors=True)
        raise PackError("The pack is incomplete - missing "
                        + ", ".join(missing[:3]))

    paths.gpu_manifest().write_text(json.dumps({
        "version": PACK_VERSION,
        "files": len(members),
        "bytes": sum(f.stat().st_size for f in binaries.iterdir()),
    }, indent=2), encoding="utf-8")


def remove() -> None:
    paths.gpu_manifest().unlink(missing_ok=True)
    shutil.rmtree(paths.gpu_dir(), ignore_errors=True)
