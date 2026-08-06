# Murmur

Press a key, speak, and the text lands wherever your cursor already is.

Everything runs on this machine. The audio never leaves it, there's no account,
no API key, and no per-minute cost. There is exactly one exception and it is
worth being straight about: the first run downloads the speech model itself.
After that you can pull the network cable out and never plug it back in.

![Murmur's main window: a sidebar of Home, Models library, Language, Sound,
Speed and History, and a Home page showing words-per-minute, words this week,
and a checklist for getting started](docs/screenshot.png)

## Use it

**[Download the installer](https://github.com/kaan7305/murmur-windows/releases/latest)**
— `Murmur-Setup-1.0.0.exe`, 67 MB. It appears in the Start menu once installed.
Nothing else is needed: no Python, no virtualenv, no administrator rights. It
installs per-user into `%LOCALAPPDATA%\Programs\Murmur`.

```
SHA-256  83c008031d908d39fb7b5390cac23484aff69a5233deee3483b4a7a2a74a2682
```

### What it needs

| | |
|---|---|
| Windows | 10 version 1809 or later, or Windows 11 |
| Processor | 64-bit Intel or AMD. **Not ARM64** — see below |
| Memory | 4 GB. The model is held in memory while Murmur runs, so Large v3 wants 8 GB |
| Disk | about 1 GB: 260 MB for the app, 480 MB for the default model |
| Network | once, on first run, to fetch the model. Never again |
| Graphics card | optional. An NVIDIA card makes it faster; nothing needs one |

ARM64 machines — Snapdragon X and the other Copilot+ laptops — are not
supported. The frozen build would run under x64 emulation slowly enough to be
worse than useless, so the installer declines rather than disappoint you. If
that is your machine, running from source is the route that works today.

**First run downloads about 480 MB**, the Small model, from Hugging Face. It
happens once, in the background, and Murmur is unusable until it finishes, so
start it before you need it rather than during a meeting.

**Windows will warn you the first time.** The installer is not code-signed, so
SmartScreen shows *"Windows protected your PC"* and hides the run button behind
**More info → Run anyway**. That warning means "this file has no certificate and
few people have downloaded it yet" — not "this file is malicious". A signing
certificate costs a few hundred pounds a year, which is not something a free
tool has, so the honest answer is to tell you rather than to hide it.

**One scanner out of sixty-eight disagrees**, and it is worth saying which and
why rather than leaving you to find it.
[VirusTotal reads this exact file](https://www.virustotal.com/gui/file/83c008031d908d39fb7b5390cac23484aff69a5233deee3483b4a7a2a74a2682)
— the hash above — as 1/68. The one detection is DeepInstinct, an enterprise
tool that classifies files with a machine-learning model rather than signatures,
and its verdict is a bare "malicious" with no malware family named, which is
what a guess looks like standing next to a match. It is reacting to the shape of
the file: an Inno Setup installer is a small loader with a compressed payload
appended to it, and structurally that is also what a dropper is. The other
sixty-seven engines do not flag it.

If you would rather not take that on trust, don't: the whole program is in this
repository, `build.bat` produces the installer from it, and running from source
skips the installer altogether.

To run from source instead:

```
setup.bat     once, to install dependencies
run.bat       to start it
```

| Key | Does |
|---|---|
| `Ctrl+Space` | start listening; press again to stop and paste |
| `Esc` | discard the recording without transcribing |
| `F10` | quit |

The dictation shortcut is a setting — the setup guide offers to change it, and
it is stored in `config.json`.

**The shortcut is swallowed**, so the window you are dictating into does not act
on it as well. Without that, Ctrl+Space starts dictating *and* opens autocomplete
in every editor, and F9 dictates *and* toggles a breakpoint — which is why most
dictation tools end up recommending a shortcut nobody would otherwise press.

That cuts both ways, and there is one case where it will bite you. **If you type
Chinese, Japanese or Korean, rebind the shortcut before anything else.**
`Ctrl+Space` is the standard Windows IME on/off toggle, and Murmur swallowing it
means you lose IME switching everywhere until you change it.

## How it compares

Windows already dictates, and there are other Whisper front-ends. Where Murmur
is not the right answer:

| | Use that instead when |
|---|---|
| **Win+H**, built into Windows | You are happy with it. It is already there, it is free, and it needs no install. On a Copilot+ machine it runs on the NPU and is fast. |
| **Dragon** and other paid tools | You need voice *commands* and editing by voice, or a medical or legal vocabulary. Murmur only types what you say. |
| **Other Whisper front-ends** | You are on macOS or Linux — Murmur is Windows-only — or you want a signed installer today. |

Where Murmur is different: it works offline on an ordinary machine with no NPU
and no Microsoft account; it swallows its own shortcut so the app underneath
does not also act on it; it lets you pick the model, so you can trade speed
against accuracy; and it pastes per-application, because the shortcut that
pastes into a terminal is not the one that pastes into Word.

Being straight about the rest: the installer is unsigned, there is no ARM64
build, and while Whisper handles 99 languages the Small model that ships by
default is noticeably weaker outside English — set a larger model if you dictate
in another language.

`hotkeys.py` does this with a low-level keyboard hook. pynput's own
`GlobalHotKeys` cannot: it can suppress an event, but only from inside the hook
filter, and suppressing there raises an exception that unwinds before the event
reaches pynput's own matching — so the key is swallowed and the shortcut stops
working. The matching therefore happens in `hotkeys.py`, under one rule: the
shortcut's key while its modifiers are held is swallowed, and nothing else ever
is. Escape is deliberately exempt — it cancels a recording but still reaches
whatever else wanted it.

If that hook ever throws, Windows' dispatcher swallows the error and delivers
the key normally: the worst case is a shortcut that stops working, never a
keyboard that stops typing.

Leave it running in the background. Put the cursor where you want text, press
the hotkey, talk, press it again. The transcript is pasted into whatever window
has focus — Google Docs, Sheets, the browser address bar, a terminal, anything.

## First run

The first launch opens a five-screen setup guide rather than the main window:
where Murmur lives once the window is closed, whether the microphone is being
heard, where transcription happens, and finally the shortcut — which it asks you
to actually press and watch your own words appear in a box.

That last screen is the point of the whole thing. Nobody believes dictation
works until they have seen it work once, and the box has focus, so the text
arrives there by exactly the path it will use everywhere else.

Reopen it any time from the tray menu, or run `Murmur.exe --guide`.

## Always available

Nothing can start Murmur *with* the shortcut. The shortcut is a system-wide
keyboard hook and a hook needs a process to live in, so until Murmur is running
there is nobody listening for Ctrl+Space. Two settings on the Sound page close
that gap:

**Start Murmur when I sign in** writes `HKCU\...\Run` with `--hidden`, so it
comes back into the tray at sign-in with no window and the shortcut works from
the moment the desktop appears. The installer offers the same thing as a
checkbox; both write the same value, so they cannot disagree. `startup.py` also
doubles as a hand switch — `python startup.py` / `python startup.py off` — for
when there is no window open to tick.

**Keep a small Murmur pill on screen** floats a dot-sized pill above other
windows: proof it is running, a reminder of the key when pointed at, and
something to click for anyone who has not memorised the shortcut yet. Drag it
anywhere and the position is remembered; right-click it for the tray menu. It
hides itself while recording, since the full pill is then saying the same thing
louder, and — like the recording pill — it carries `WS_EX_NOACTIVATE`, so
clicking it never takes focus from the window that is about to be pasted into.

## How it works

Your voice is captured at 16kHz and turned into a log-Mel spectrogram — a
picture of which frequencies were loud when. Whisper's encoder reads that
picture; its decoder is a language model that writes text one token at a time,
attending to both the audio and the words it has already written.

That decoder is why punctuation and capitalisation come out right without being
asked, and why the model picks the correct homophone from context. It's also why
it will invent a plausible sentence out of pure silence, so a voice-activity
filter gates it: no speech detected, no text produced.

## Measured speed

4.0s dictation-length clip on an NVIDIA GPU. All configurations
transcribed the test sentence correctly; only the latency differs.

| Model | Precision | Time | vs realtime |
|---|---|---|---|
| large-v3 | float16 | 4.50s | 0.9x |
| large-v3 | int8_float16 | 3.62s | 1.1x |
| **small** | **int8_float16** | **0.85s** | **4.7x** |

`small` is the default because the others make you wait roughly as long as you
spoke, which ruins the feel of dictating.

**Without the GPU pack**, which is how the installer ships, the same clip takes
2.6s on CPU — 1.5x realtime. Slower than the card, still
faster than speaking, and it needs no 1.6 GB download. Those two figures are
measured cold, on the first transcription after loading, which is what someone
pressing the shortcut for the first time actually experiences; the table above
is warmed.

**Why large-v3 is slow here, and it isn't your GPU.** CTranslate2 4.8.1 ships no
native kernels for Blackwell (`sm_120`), so it runs JIT-compiled PTX instead.
The card sits pinned at 100% utilisation and 4 GB of VRAM while delivering a
fraction of what it should. Verified with `nvidia-smi` during inference — the
work is genuinely on the GPU, just running unoptimised code.

Two ways out when you want `large-v3` quality:

- Wait for CTranslate2 to add `sm_120` kernels, then flip `MODEL` back
- Switch the backend to whisper.cpp with CUDA built for `sm_120`, which does
  support the architecture natively

## Building the installer

```
build.bat            Murmur-Setup-1.0.0.exe   (67 MB)
build.bat --gpu      also Murmur-GPU-Pack.zip (1.6 GB)
```

Needs `pyinstaller` in the virtualenv and Inno Setup 6
(`winget install JRSoftware.InnoSetup`). The build refuses to package a program
that fails `Murmur.exe --selftest`, which loads the model and transcribes a
synthesised clip — a frozen build breaks in ways a source checkout cannot, and
that check catches it before an installer exists.

**Why the graphics libraries are a separate download.** cuBLAS and cuDNN are
1.6 GB, roughly twenty-five times the installer, and they do nothing at all
without an NVIDIA card. Bundling them would mean most people downloading 1.7 GB
to use 67 MB of it. Instead the installer ships the CPU build, and the Speed
page inside the app installs the pack for whoever has a card to run it on. It
unpacks to `%LOCALAPPDATA%\Murmur\gpu`, so it needs no administrator rights and
survives reinstalling Murmur itself.

`PACK_URL` at the top of `gpupack.py` ships empty, so the Speed page offers two
buttons: *Download the pack*, which opens the releases page, and *Choose the
downloaded file*, which asks for the zip on disk. A file picker on its own would
be a dead end for anyone who does not already have the archive, which is why the
way to get it comes first. Fill `PACK_URL` in once the file sits somewhere the
app can fetch it from directly, and the main button downloads it in place,
leaving *Install from a file* as the quieter route for whoever already has it.

`make_gpu_pack.py` leaves out three libraries the wheels ship — `cudnn_adv`,
the alternate NVRTC build and `nvblas`, together about 350 MB — because
CTranslate2 running Whisper never calls them. `--full` includes everything if a
card ever turns out to disagree.

## Language, and why you should set it

Whisper will detect the language for you, and on dictation-length audio it is
not good at it. Detection reads the opening seconds and commits; a wrong guess
does not produce a translation, it produces confident nonsense, because the
decoder picks the wrong vocabulary and then writes fluently in it.

Same 8-second clip of English:

| Language setting | Time | Result |
|---|---|---|
| Detect automatically | 1.88s | correct |
| **English (named)** | **0.73s** | correct |
| Turkish (deliberately wrong) | 13.23s | degraded — "Mermr transcribes" |

Naming the language is 2.6x faster, because the detection pass is skipped
entirely. Getting it wrong is both far slower and worse. There is no case in
which leaving it on automatic is the better option if you know what you speak.

Which is why the language is also in the tray and pill menu, not only on the
Language page. Advice to always name the language is worth nothing to someone
who speaks two of them if naming it costs opening a window mid-sentence. The
menu lists the languages actually dictated in, most recent first, and that list
builds itself — the second time you choose Turkish it is one right-click away,
and languages you never use never appear.

## Vocabulary

Names, product names and jargon are the words a speech model cannot get from
sound alone — it has no reason to prefer "Murmur" over "murmur" or "Mermur".
The Language page takes a list of them.

This is passed to faster-whisper as `hotwords`, not `initial_prompt`. Both reach
the decoder through the same `sot_prev` mechanism, but `hotwords` is independent
of `condition_on_previous_text` (which Murmur turns off) and faster-whisper
truncates it to fit the prompt window rather than letting it silently corrupt
the context.

It works, and it is a bias rather than a rule. The sample clip says the
product's own name, and the model writes it as `murmur`; with `Murmur` on the
list it writes `Murmur`, reproducibly. A word that sounds nothing like what was
said still will not appear.

About sixty words fit in the window Whisper reserves for this. Past that,
faster-whisper trims the list, so the interface says how many will fit rather
than letting the extra entries do nothing silently.

## Corrections

Vocabulary leans on what the model *hears*. Corrections fix what it *writes*,
which is a different problem: `github` comes out lowercase every time, and an
address comes out as "name at example dot com". The model heard both perfectly
well, so no amount of biasing the audio side changes either.

A correction is a pair — what it writes, what you wanted — applied to the
finished transcript, in order, so a later rule can act on what an earlier one
produced. Matching is whole-word and ignores capitalisation, because the first
rule anyone writes turns `at` into `@` and must not touch "attention".

Two cases take the space in front with them. A replacement starting with
punctuation is one: `comma` → `,` would otherwise give "hello , world". An
empty replacement is the other, which is how filler words are dropped —
without it, deleting the `um` from "I um think" leaves two spaces behind.

Deliberately not regular expressions. The people who need this are fixing the
spelling of their own surname, and a syntax error in a settings box that
silently stopped all dictation would be a poor trade for power nobody asked
for.

## When it mishears

`small` is fast enough to feel instant and wrong often enough to notice. Until
now the only recourse was to say the whole thing again.

The last clip stays in memory, so the newest card in History offers to run it
through a larger model — whichever is already downloaded, so pressing it never
starts a 3 GB download you did not ask for. English-only weights are skipped
unless English is the named language, since distil-large-v3 would transcribe
Turkish into fluent nonsense, which is the exact failure the retry exists to
undo.

The result is **not** pasted. The window dictated into a minute ago may be
anything by now, and typing into whatever has focus is not a correction, it is
a new problem. It replaces the text on the card and goes to the clipboard.

One clip is kept, not a session's worth: this is a second chance, not a
recording of your day.

## Choosing a microphone

The picker in the header and the one on the Sound page are the same control and
write the same setting; changing either updates the other.

Windows makes this less simple than it sounds. Every microphone is exposed
through three or four driver families — MME, DirectSound, WASAPI, WDM-KS — so a
raw device listing shows each one several times under several spellings, and
MME, which is the family that opens most reliably, truncates names at 31
characters. `input_devices()` collapses the duplicates: the name comes from
whichever driver spells it out in full, and the index from whichever driver
opens it best, so the name you read and the device that gets opened are
deliberately allowed to come from different rows. WDM-KS entries are dropped
entirely — PortAudio cannot open them in the mode used here, so offering one
would only produce a device that fails when selected.

The choice is stored by name, not by index, because indices shift as devices are
plugged and unplugged. A microphone that has gone missing is shown as *not
connected* and recording falls back to the system default rather than failing.

## What Murmur counts

The Home page reports the last seven days from `stats.json`, so the numbers mean
something on a Monday morning rather than resetting with every launch. Only
totals are kept — word counts, seconds of speech, and which applications were
dictated into. No transcript, and no text of any kind, is ever written there.

*Saved this week* compares those words against typing them at 40 words per
minute. That figure is an assumption, not a measurement of you, which is why the
caption says so on hover.

The History page is the one exception, and it is off by default. Transcripts
live in memory and are gone when Murmur quits unless *keep these after Murmur
closes* is ticked, at which point they go to `history.json` beside the config —
on this computer, sent nowhere, and emptied by the Clear button on the same
page. Kept in its own file so that clearing your transcripts does not also
throw away a year of counters.

## Text size

Every size in the interface is a number somebody chose while looking at their
own screen. The Sound page multiplies all of them at once — window, tray menu
and pill together — for when Murmur specifically is the thing you are leaning
in to read. When *everything* is too small, Windows' own display scaling is the
better answer and Murmur follows it already.

It applies on restart. Qt copies a font into a widget when the widget is built,
so changing it live would resize half the window and leave the rest, which
looks like a fault rather than a setting.

## What lives where

| Path | Holds |
|---|---|
| `%LOCALAPPDATA%\Programs\Murmur` | the program; removed by the uninstaller |
| `%LOCALAPPDATA%\Murmur` | `config.json`, `stats.json`, `history.json` if kept, the log, the GPU pack |
| `~\.cache\huggingface\hub` | the speech models |

Nothing mutable sits next to the executable, so a standard user can change
settings and install the GPU pack without being prompted for a password. The
uninstaller asks before deleting the second one and never touches the third —
re-downloading three gigabytes of model weights because someone reinstalled the
app would be rude.

## Configuration

Everything worth changing is at the top of `murmur.py`.

| Setting | Notes |
|---|---|
| `HOTKEY_DICTATE` | the default only; pynput syntax, e.g. `<ctrl>+<space>` |
| `MODEL` | `large-v3` (best, ~3 GB), `distil-large-v3` (faster, English), `small` (runs anywhere) |
| `DEVICE` | `cuda`, falls back to CPU automatically if no GPU is visible |
| `LANGUAGE` | `None` autodetects; setting `"en"` is faster and more accurate |
| `PASTE_OVERRIDES` | per-app paste shortcuts, for consoles that don't use Ctrl+V |

## Two things Windows won't let it do

**Elevated windows.** If a window is running as Administrator, a normal-privilege
app cannot send keystrokes to it — Windows blocks synthetic input across
integrity levels. Run Murmur as admin too, or don't dictate into elevated
windows. There's no way around this from user space.

**Consoles that don't paste with Ctrl+V.** Windows Terminal is fine. Some legacy
consoles want Ctrl+Shift+V — add them to `PASTE_OVERRIDES`. Also note that
pasting multi-line text into a shell will *execute* it, since newlines act as
Enter.

## Checking it works

```
run.bat --devices          list microphones, confirm the right one is default
run.bat --file sample.wav  transcribe a file, no mic needed; prints a speed figure
python selftest.py         clipboard, focus detection, audio, CUDA
```

## Licence

**MIT** — see `LICENSE`. Original work, not derived from any other
application's source.

The dependencies are a mix, and two of them are copyleft: **PySide6 (Qt)** and
**pynput** are both LGPL-3.0. That is *weak* copyleft — it attaches to those
libraries, not to Murmur's code, and MIT is a normal licence to publish
alongside them — but it is not nothing, and an earlier version of this section
claimed there was no copyleft here at all. There is. `THIRD-PARTY-NOTICES.md`
lists every component, what it is licensed under, whether it ships inside the
installer, and what the LGPL actually asks of anyone redistributing the build.

Whisper's weights, `faster-whisper` and CTranslate2 are MIT, as this section
always said.

MIT covers the code and the prose, not everything the files contain. The
website reproduces the logos and window furniture of around forty products to
show where Murmur types; those marks belong to their owners, and copying this
repository conveys no right to them. And the optional GPU pack is NVIDIA's
proprietary CUDA, cuBLAS and cuDNN libraries — which is why it is neither in
this repository nor in the installer, and why it is fetched separately. The
image at the top of the website was generated with an AI model rather than
photographed; nobody real is in it. `THIRD-PARTY-NOTICES.md` sets out both
carve-outs and what NVIDIA's terms permit. Fork the code freely; replace the
artwork.
