"""Stand a stub in for PyAV, which this build does not ship.

The module being stubbed is PyAV (https://pyav.org), the Python bindings to
FFmpeg's libav* libraries, which imports under the name "av". That "av" is
audio/video, and this file has nothing whatever to do with antivirus - Murmur
disables no scanner and asks for no exclusion.

faster-whisper imports PyAV at the top of its audio module to decode audio
*files*. Murmur never gives it one: the microphone produces a numpy array and
the --file path is read with the standard library's wave module, so transcribe()
is only ever handed an array and decode_audio is never reached. PyAV's only
contribution to the build was sixty megabytes of bundled FFmpeg.

The import still has to succeed, hence this. Every attribute access raises with
a message naming this file, so if a future faster-whisper does reach for PyAV
the failure explains itself instead of arriving as a bare AttributeError.
"""
import sys
import types

if "av" not in sys.modules:
    _stub = types.ModuleType("av")

    def _unavailable(name):
        # Introspection - functools.wraps, inspect.unwrap, the import system -
        # probes modules for dunders it expects to be missing, and the contract
        # for a name that is not there is AttributeError. Raising anything else
        # turns a routine lookup into a crash, which is how av.__wrapped__ took
        # down the first build of this.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise RuntimeError(
            f"PyAV was excluded from this build, so av.{name} does not exist "
            f"(see rthook_no_pyav.py). Audio has to be passed to transcribe() "
            f"as a numpy array rather than as a file."
        )

    _stub.__getattr__ = _unavailable
    sys.modules["av"] = _stub
