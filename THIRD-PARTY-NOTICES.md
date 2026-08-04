# Third-party notices

Murmur itself is MIT (see `LICENSE`). It is built on other people's work, and
this file says whose, under what terms, and — because the two lists differ —
which of it actually ships inside the installer.

Licences below were read from the installed distributions' own metadata, not
from memory. If you are auditing this, `pip show -f <package>` and the
`.dist-info/METADATA` in your virtualenv are the authority, not this file.

## Shipped inside `Murmur-Setup-1.0.0.exe`

| Component | Licence | Notes |
|---|---|---|
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython/) | **LGPL-3.0** (or GPL-2.0 / GPL-3.0, at your option) | The whole user interface. See *Qt and the LGPL* below. |
| [shiboken6](https://doc.qt.io/qtforpython/shiboken6/) | **LGPL-3.0** (or GPL-2.0 / GPL-3.0) | PySide6's binding runtime. |
| [pynput](https://github.com/moses-palmer/pynput) | **LGPL-3.0** | Keyboard hook and synthetic input. |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Speech recognition. |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT | The inference engine underneath it. |
| [ONNX Runtime](https://onnxruntime.ai/) | MIT | Runs the Silero voice-activity model. |
| [tokenizers](https://github.com/huggingface/tokenizers) | Apache-2.0 | |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Apache-2.0 | Downloads the models on first run. |
| [sounddevice](https://python-sounddevice.readthedocs.io/) | MIT | |
| [PortAudio](https://www.portaudio.com/) | MIT | Bundled by sounddevice as a DLL. |
| [NumPy](https://numpy.org/) | BSD-3-Clause (with 0BSD, MIT, Zlib and CC0-1.0 parts) | |
| [tqdm](https://github.com/tqdm/tqdm) | MPL-2.0 and MIT | Arrives with faster-whisper. |
| [certifi](https://github.com/certifi/python-certifi) | MPL-2.0 | CA bundle for the model download. |
| [Python](https://www.python.org/) | PSF-2.0 | Frozen into the build by PyInstaller. |

[PyInstaller](https://pyinstaller.org/) (GPL-2.0-or-later **with a bootloader
exception**) builds the executable. The exception exists precisely so that the
applications it freezes do not inherit the GPL; PyInstaller is a build tool
here and no part of it is linked into Murmur's own code.

## Not shipped, but needed to run from source

| Component | Licence | Notes |
|---|---|---|
| [PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause, bundling **FFmpeg** (LGPL-2.1-or-later) | faster-whisper imports it to decode audio *files*. Murmur never hands it one — the microphone produces a NumPy array and `--file` is read with the standard library's `wave` module — so `rthook_no_pyav.py` stands a stub in its place and sixty megabytes of FFmpeg stay out of the installer. |

## Speech models

The Whisper weights are **MIT**, published by OpenAI and converted for
CTranslate2 by SYSTRAN. They are downloaded from Hugging Face on first use and
cached in `~\.cache\huggingface\hub`; they are not redistributed here and are
not part of any release asset.

The voice-activity model bundled with faster-whisper is
[Silero VAD](https://github.com/snakers4/silero-vad), **MIT**.

## The optional GPU pack

`Murmur-GPU-Pack.zip` is not in the installer and not in this repository. It is
built separately by `make_gpu_pack.py` and unpacked into
`%LOCALAPPDATA%\Murmur\gpu` by the Speed page. It is the one part of Murmur that
is not open source: the libraries in it are NVIDIA's, proprietary, and
redistributed as unmodified binaries taken from NVIDIA's own PyPI wheels.

Licences below were read from `.dist-info\licenses\License.txt` in the
virtualenv. All three wheels declare the same identifier,
`LicenseRef-NVIDIA-Proprietary`.

| Component | Licence | In the default pack |
|---|---|---|
| [cuBLAS](https://developer.nvidia.com/cublas) — `nvidia-cublas-cu12` 12.9.2.10 | **NVIDIA proprietary** — *License Agreement for NVIDIA Software Development Kits* (rel. 26 July 2018) with the *CUDA Toolkit Supplement* (rel. 16 August 2018) | `cublas64_12.dll`, `cublasLt64_12.dll` — 735 MB of the 1.6 GB. `nvblas64_12.dll` is left out. |
| [NVRTC](https://docs.nvidia.com/cuda/nvrtc/) — `nvidia-cuda-nvrtc-cu12` 12.9.86 | **NVIDIA proprietary** — the same two documents; both wheels ship a byte-identical `License.txt` | `nvrtc64_120_0.dll`, `nvrtc-builtins64_129.dll`. The alternate build `nvrtc64_120_0.alt.dll` is left out. |
| [cuDNN](https://developer.nvidia.com/cudnn) — `nvidia-cudnn-cu12` 9.24.0.43 | **NVIDIA proprietary** — a different, shorter agreement plus the *cuDNN Supplement*, both v. 28 January 2020 | Nine libraries: `cudnn64_9` and the `cudnn_cnn`, `cudnn_engines_precompiled`, `cudnn_engines_runtime_compiled`, `cudnn_engines_tensor_ir`, `cudnn_ext`, `cudnn_graph`, `cudnn_heuristic` and `cudnn_ops` DLLs. `cudnn_adv64_9.dll` is left out. |

The grant is narrow enough to be worth quoting rather than paraphrasing. You may
distribute the listed files "as incorporated in object code format into a
software application", provided "[y]our application must have material
additional functionality, beyond the included portions of the SDK" and "[t]he
distributable portions of the SDK shall only be accessed by your application"
(§1.1.2). Murmur appears to satisfy both — it is a dictation program, and the
libraries are reached through the search-path entry it adds at startup. Note
though that `murmur.py` also prepends the CUDA directories to the process `PATH`
(in `_register_cuda_dlls`, because `add_dll_directory` alone is not enough),
which child processes inherit; whether that remains consistent with "accessed
only by your application" is a question for counsel, not one this file settles.

The CUDA agreement adds, at §1.2, that "you may not distribute or sublicense the
SDK as a stand-alone product" — which is why the pack is an accessory to Murmur
and not a download offered on its own terms. That sentence is absent from the
cuDNN document. Both also say that "[u]nless you have an agreement with NVIDIA
for this purpose", you may not present an application built with the SDK as
sponsored or endorsed by NVIDIA. Murmur makes no such claim.

Because §1.2 also forbids removing "copyright or other proprietary notices",
`make_gpu_pack.py` packs each wheel's `License.txt` under `licenses/` and
`gpupack.install()` writes them to `%LOCALAPPDATA%\Murmur\gpu\licenses`. Earlier
builds packed only `*.dll` and extracted only `*.dll`, so the text was dropped at
both ends; if you rebuild an old pack, rebuild the installer logic with it.

Attachment B of the CUDA agreement lists third-party code carried inside the
Toolkit, including components compiled into cuBLAS: **Modified BSD** (Vasily
Volkov / Regents of the University of California; Davide Barbieri / University
of Rome Tor Vergata; The University of Tennessee; Jonathan Hogg / STFC),
**Apache-2.0** (Abdelfattah, Keyes and Ltaief / KAUST) and **MIT** (OpenAI).
Their binary-form attribution — and Apache-2.0's own NOTICE duty — is discharged
by shipping the full `License.txt`, which contains that attachment.

**Unresolved: the cuDNN file list.** The supplement inside the cuDNN 9.24 wheel
is dated January 2020 and names exactly one Windows library as distributable:
"the runtime files .so and .h, cudnn64_7.dll, and cudnn.lib". cuDNN 9 split that
single library into a dispatch stub plus the sub-libraries above, and
`cudnn64_9.dll` alone does nothing — `gpupack.py` requires `cudnn_graph64_9`,
`cudnn_ops64_9` and `cudnn_cnn64_9` as well. The text bundled in the wheel has
not caught up with the product it ships with, and it does not literally cover
eight of the nine files. The current
[cuDNN SLA](https://docs.nvidia.com/deeplearning/cudnn/sla/) and
[CUDA EULA](https://docs.nvidia.com/cuda/eula/) are the governing documents and
supersede the bundled copies; read them before publishing a pack. NVIDIA directs
questions of exactly this kind to `nvidia-compute-license-questions@nvidia.com`.

By the same reasoning the CUDA agreement's Attachment A (in the Toolkit
Supplement) names `cublas.dll`, `cublasLt.dll`, `nvrtc.dll` and
`nvrtc-builtins.dll`, while the wheels install the versioned Windows filenames
listed in the table. These are the same libraries under Windows' versioned
naming and NVIDIA's own wheels are the source, so the mapping is treated as
safe — but that is an inference, not something the document states.

## Qt and the LGPL

PySide6 and pynput are the only copyleft obligations in the list, and both are
*weak* copyleft: they attach to those libraries, not to Murmur's own source.
The README used to claim there was no copyleft here at all. That was wrong, and
it mattered, so this section is explicit about what the obligation is.

LGPL-3.0 §4 says that if you ship a work that links against the library, the
recipient must be able to replace that library with a modified version and
relink. For a PyInstaller build, three things satisfy it, and Murmur does all
three:

1. **The full source of this application is published**, under MIT, at
   <https://github.com/kaan7305/murmur-windows>. Anyone can rebuild it.
2. **The build is `onedir`, not `onefile`.** The Qt and pynput components sit
   next to the executable in `%LOCALAPPDATA%\Programs\Murmur` as ordinary
   importable files. Replacing one is a file copy; nothing has to be unpacked
   or patched to reach them.
3. **Neither library is modified.** They are installed from PyPI as published.

If you redistribute a modified Murmur, note that the same obligation follows
you: keep the LGPL components replaceable, and keep this file with it.

## The website

`site/index.html` sets [Inter](https://rsms.me/inter/) (SIL Open Font License
1.1, by Rasmus Andersson) as its interface face. The font is not embedded — the
page fetches it from Google Fonts at load time, which is a request to a third
party that a privacy-minded reader may reasonably want to know about, and the
only such request the page makes.

The hero image at `site/assets/speaker.jpg` was generated with an AI image model
by the author. It is not a photograph, and nobody real is depicted in it, so
there is no photographer and no subject to credit. Worth knowing if you fork
this: a purely machine-generated image may not attract copyright at all in some
jurisdictions, so treat the MIT grant over that one file as saying "do what you
like with it" rather than as a transfer of rights anyone could enforce.

## Scope of the MIT licence

MIT covers the source of this application and of its website: the Python, the
markup, the stylesheet, the drawn Murmur mark in `logo.py`, and the prose.

It does not, and cannot, cover two things that live inside those files:

1. **Third-party logos and trade dress.** `site/index.html` reproduces the marks
   of around forty products as inline SVG geometry — in the keyboard, in the
   logo wall, in the demo windows and in the destination switcher — together
   with the visual furniture of Slack, Gmail, Microsoft Word, Microsoft Excel,
   Microsoft OneNote, Google Chrome, Windows Terminal and the Windows 11
   taskbar, rendered in CSS. Those marks belong to their owners. Copying this
   repository does not convey any right to them.
2. **The NVIDIA libraries** in the optional GPU pack, which are proprietary and
   are covered by the section above. They are deliberately absent from this
   repository and from the installer.

If you fork Murmur, the code is yours to use under MIT. Replace the artwork.

## Trademarks

Murmur is not affiliated with, endorsed by or sponsored by any of the companies
below. Their names and marks appear on the website and in its demo for one
reason: to identify the applications Murmur types into, which is what the
product does. All marks are the property of their respective owners.

Adobe InDesign (Adobe); Atom, GitHub (GitHub / Microsoft); ChatGPT (OpenAI);
Claude, Claude Code (Anthropic); Cursor (Anysphere); Discord (Discord);
Evernote (Bending Spoons); Figma (Figma); Gmail, Google Chrome, Google Docs,
Google Meet (Google); Grammarly (Grammarly); iMessage (Apple); Jira (Atlassian);
Linear (Linear Orbit); Mendeley (Elsevier); Microsoft Excel, Microsoft OneNote,
Microsoft Outlook, Microsoft Word, Visual Studio Code, Windows, Windows
Terminal (Microsoft); Notion (Notion Labs); Obsidian (Dynalist); Overleaf
(Digital Science); PowerShell (Microsoft); Signal (Signal Technology
Foundation); Slack (Slack Technologies / Salesforce); Sublime Text (Sublime
HQ); Telegram (Telegram Messenger); Todoist (Doist); Warp (Warp Dev);
WhatsApp (Meta); Zoom (Zoom Communications); Zotero (Corporation for Digital
Scholarship).

NVIDIA, CUDA, cuDNN and GeForce RTX are trademarks of NVIDIA Corporation.
Whisper is OpenAI's; Qt is The Qt Company's.
