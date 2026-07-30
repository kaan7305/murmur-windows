"""Build the optional GPU pack from the libraries pip put in the virtualenv.

    python make_gpu_pack.py            the tested subset
    python make_gpu_pack.py --full     every DLL the wheels ship

The wheels install two gigabytes, and CTranslate2 running Whisper touches only
some of it. The default list is what survived being removed one at a time and
re-tested; --full is the escape hatch if a card turns out to need something this
machine did not.

The result is dist/Murmur-GPU-Pack.zip. It is not compressed further than the
DLLs already are - they are mostly incompressible machine code, and ZIP_DEFLATE
on 1.6 GB costs minutes to save a few percent.
"""
from __future__ import annotations

import argparse
import pathlib
import site
import sys
import zipfile

# Left out of the default pack, with the reason, so this is a decision rather
# than an oversight:
#
#   cudnn_adv64_9.dll         257 MB  recurrent and multi-head attention
#                                     primitives; CTranslate2 implements
#                                     attention itself and never calls them
#   nvrtc64_120_0.alt.dll      86 MB  an alternate JIT compiler build, loaded
#                                     only when the primary one is absent
#   nvblas64_12.dll                    a BLAS shim for Fortran callers
SKIP = {"cudnn_adv64_9.dll", "nvrtc64_120_0.alt.dll", "nvblas64_12.dll"}


def source_dirs() -> list[pathlib.Path]:
    roots = [pathlib.Path(p) / "nvidia" for p in site.getsitepackages()]
    roots.append(pathlib.Path(__file__).parent / ".venv" / "Lib"
                 / "site-packages" / "nvidia")
    return [d for r in roots for d in r.glob("*/bin") if d.is_dir()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", action="store_true",
                    help="include every DLL, not just the tested subset")
    ap.add_argument("-o", "--out", default="dist/Murmur-GPU-Pack.zip")
    args = ap.parse_args()

    dirs = source_dirs()
    if not dirs:
        print("No CUDA libraries found. Install them first:\n"
              "  .venv\\Scripts\\pip install nvidia-cublas-cu12 "
              "nvidia-cudnn-cu12 nvidia-cuda-nvrtc-cu12")
        return 1

    files: dict[str, pathlib.Path] = {}
    for d in dirs:
        for dll in sorted(d.glob("*.dll")):
            if not args.full and dll.name in SKIP:
                continue
            files.setdefault(dll.name, dll)   # first directory wins

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    total = sum(f.stat().st_size for f in files.values())
    print(f"packing {len(files)} libraries, {total / 1024**3:.2f} GB\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for name, src in sorted(files.items()):
            print(f"  {src.stat().st_size / 1024**2:8.1f} MB  {name}")
            z.write(src, f"bin/{name}")

    print(f"\n  -> {out}  ({out.stat().st_size / 1024**3:.2f} GB)")
    if not args.full:
        print(f"     {len(SKIP)} libraries left out; --full includes them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
