# Contributing

## Setting up from source

Windows, with Python 3.10 or newer on `PATH`.

```
git clone https://github.com/kaan7305/murmur-windows.git
cd murmur-windows
setup.bat
```

`setup.bat` creates `.venv` and installs `requirements.txt` into it: faster-whisper,
PySide6, sounddevice, numpy and pynput. A few hundred megabytes, once. ctranslate2,
huggingface_hub, tokenizers and onnxruntime are not listed because faster-whisper
brings them, and pinning them here would mean holding a second opinion about
versions it already has one on.

The speech model is not part of that. It downloads from Hugging Face on the first
transcription, into `~\.cache\huggingface\hub`. The default `small` is a few
hundred megabytes; `large-v3` is about 3 GB.

## Running it

```
run.bat                     the windowed application
run.bat --devices           list microphones and show which is default
run.bat --file sample.wav   transcribe a file, no microphone needed
run.bat --model small       switch model, downloading it if necessary
```

With no arguments `run.bat` starts `app.py`, which is the application. With
arguments it runs `murmur.py`, the console version, and holds the window open
afterwards so the output can be read.

## Running the self test

```
.venv\Scripts\python.exe selftest.py
```

Clipboard round trip, foreground process detection, an input device, and CUDA.
Nothing in it needs a microphone or a voice. The two CUDA checks fail on a
machine with no NVIDIA card or no GPU pack, and that is the expected result
there rather than a bug.

There is a second and different self test inside the application:

```
.venv\Scripts\python.exe app.py --selftest
```

That one loads the model and transcribes a synthesised clip, which is the part
that breaks in a frozen build and cannot break in a source checkout. It writes
its result to `%LOCALAPPDATA%\Murmur\selftest.txt` because a windowed executable
has nowhere to print, and `build.bat` refuses to package a build that fails it.

## pyinstaller is missing from the dependency list

`build.bat` runs `"%PY%" -m PyInstaller`, but pyinstaller appears in neither
`requirements.txt` nor `setup.bat`. A fresh clone that runs `setup.bat` and then
`build.bat` therefore fails at step 2 of 4 with `No module named PyInstaller`.
Install it into the virtualenv by hand:

```
.venv\Scripts\python.exe -m pip install pyinstaller
```

Building the installer also needs Inno Setup 6, which is a program rather than a
Python package: `winget install JRSoftware.InnoSetup`.

## House style

Comments say why, not what. `paths.py` and `hotkeys.py` are the reference: each
opens with the reason the file exists, and the comments inside explain the
decisions that the code cannot. A comment restating the line below it is noise.

Anything that appears on screen is governed by `DESIGN.md`, which is stricter
than it looks. Sentence case, no exclamation marks, and every string has to earn
its place by answering a question the user is asking at that moment.
