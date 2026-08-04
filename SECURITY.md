# Security

## Supported version

| Version | Fixes |
|---|---|
| 1.0.0, the current release | yes |
| anything older | no |

There is one release and one maintainer. Fixes go into the next release rather
than being backported, so "supported" means the newest installer and `main` in
this repository.

## Reporting a vulnerability

Report it privately through GitHub Security Advisories: the **Security** tab of
this repository, then **Report a vulnerability**. The direct link is
`https://github.com/kaan7305/murmur-windows/security/advisories/new`. The report
stays between you and the maintainer until there is a fix.

Please do not open a public issue for anything that could be used against
someone running Murmur today. The bug form is for defects that are already
visible to whoever hit them.

What makes a report actionable: the Murmur version, the Windows version, what an
attacker has to be able to do already, and what they gain by it. A proof of
concept helps. A scanner's output on its own usually does not.

Expect a first reply within about seven days. That is one person working in
their own time, so it is an expectation and not a service level. If a week
passes in silence, send a reminder through the same advisory. Confirmed reports
are published as an advisory alongside the fix, crediting you unless you would
rather not be named.

## What Murmur touches

Murmur runs unprivileged, has no account, no server and no network service. Four
parts of it are worth reading before anything else.

**A low-level keyboard hook.** `hotkeys.py` installs a `WH_KEYBOARD_LL` hook
through pynput, so every keystroke on the machine passes through Murmur's filter
while it is running, whatever window has focus. The filter matches one shortcut
and suppresses only that key while its modifiers are held. Everything else is
passed through untouched, and Escape is never swallowed. Keys are not recorded,
stored or forwarded. It is still a keyboard hook, and its correctness is the
most security-relevant thing in this codebase.

**Synthetic keystrokes.** After transcribing, `paste()` in `murmur.py` presses
Ctrl+V, or a per-application override, into whichever window has focus. The text
lands wherever the cursor is, including a shell, where multi-line text executes
as it arrives. Windows blocks synthetic input from a normal process into an
elevated window, so an unelevated Murmur cannot type into one.

**The clipboard.** Pasting reads the current clipboard contents so they can be
put back, replaces them with the transcript, and restores the original 1.5
seconds later if nothing else has written to the clipboard meanwhile.

The transcript is always marked to stay off the cloud clipboard, which would
otherwise sync it through Microsoft's servers to the user's other machines. It
is additionally kept out of the local Win+V history whenever the restore is on,
which is the default. Turning the restore off is a request to leave the
dictation on the clipboard, and something left on the clipboard on purpose
belongs in the history like anything else — so in that configuration the
transcript is retained by Windows locally. The restored contents are never
re-marked either way, because they were never Murmur's to reclassify.

**A first-run download over HTTPS.** The speech model is fetched by
`huggingface_hub` from `Systran/faster-whisper-<name>` on Hugging Face into
`~\.cache\huggingface\hub`, on the first transcription and not again. Integrity
is whatever the hub and TLS provide. The optional GPU pack is a separate zip of
NVIDIA libraries, either chosen from disk or downloaded, unpacked into
`%LOCALAPPDATA%\Murmur\gpu`; it is treated as untrusted input, and archive
member names are checked before anything is written.

Everything Murmur writes lives in `%LOCALAPPDATA%\Murmur`: `config.json`,
`stats.json` (counts and the names of applications dictated into, never text),
`murmur.log`, and `history.json` only when saving transcripts has been switched
on, which it is not by default.

## The installer is not signed

Releases carry no code-signing certificate, so SmartScreen warns on first run and
nothing cryptographically ties a downloaded binary to this repository. That is a
stated cost of a free tool rather than a defect, and it cuts both ways: an
installer claiming to be Murmur proves nothing about where it came from. Anyone
who would rather not trust a binary can build one with `build.bat`, or skip the
installer and run from source.
