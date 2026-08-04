"""Build the optional GPU pack from the libraries pip put in the virtualenv.

    python make_gpu_pack.py            the tested subset
    python make_gpu_pack.py --full     every DLL the wheels ship

The wheels install two gigabytes, and CTranslate2 running Whisper touches only
some of it. The default list is what survived being removed one at a time and
re-tested; --full is the escape hatch if a card turns out to need something this
machine did not.

The result is dist/Murmur-GPU-Pack.zip, holding the libraries under bin/ and
each wheel's licence under licenses/. It is not compressed further than the DLLs
already are - they are mostly incompressible machine code, and ZIP_DEFLATE on
1.6 GB costs minutes to save a few percent.

Everything in bin/ is NVIDIA's, proprietary, and redistributed unmodified under
terms that permit it only as part of an application and forbid stripping the
notices. That is why the licences are packed too, why gpupack.install() keeps
them, and why the pack is an accessory to Murmur rather than a download offered
on its own. See THIRD-PARTY-NOTICES.md, which also records what is unresolved
about the cuDNN file list.
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


def license_files() -> dict[str, pathlib.Path]:
    """Each NVIDIA wheel's License.txt, keyed by the distribution it came from.

    These libraries are proprietary. NVIDIA's terms permit redistributing them
    inside an application but forbid removing their notices, and the licence
    text lives in the wheel's .dist-info rather than next to the DLLs - so a
    pack built from `nvidia/*/bin` alone strips it, which is what this one did
    until now. Packing without them is refused rather than warned about,
    because a warning is a thing you scroll past.
    """
    roots = [pathlib.Path(p) for p in site.getsitepackages()]
    roots.append(pathlib.Path(__file__).parent / ".venv" / "Lib"
                 / "site-packages")

    found: dict[str, pathlib.Path] = {}
    for root in roots:
        for info in sorted(root.glob("nvidia_*.dist-info")):
            for rel in ("licenses/License.txt", "License.txt", "LICENSE"):
                src = info / rel
                if src.is_file():
                    # nvidia_cublas_cu12-12.9.2.10.dist-info -> nvidia_cublas_cu12
                    found.setdefault(info.name.split("-")[0], src)
                    break
    return found


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

    licences = license_files()
    if not licences:
        print("No NVIDIA License.txt found in any nvidia_*.dist-info.\n"
              "Refusing to build a pack that would ship their libraries with "
              "their licence stripped. Reinstall the wheels with pip so the\n"
              "dist-info directories are present.")
        return 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    total = sum(f.stat().st_size for f in files.values())
    print(f"packing {len(files)} libraries, {total / 1024**3:.2f} GB\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for name, src in sorted(files.items()):
            print(f"  {src.stat().st_size / 1024**2:8.1f} MB  {name}")
            z.write(src, f"bin/{name}")
        for dist, src in sorted(licences.items()):
            z.write(src, f"licenses/{dist}/License.txt")

    print(f"\n  + {len(licences)} licence file(s): "
          + ", ".join(sorted(licences)))
    print(f"\n  -> {out}  ({out.stat().st_size / 1024**3:.2f} GB)")
    if not args.full:
        print(f"     {len(SKIP)} libraries left out; --full includes them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
