"""Everything checkable without a microphone or a voice."""
import sys
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
import time
import murmur as m

ok = True

def check(label, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'  ' + detail if detail else ''}")

print("clipboard")
original = m.clipboard_get()
sample = "murmur roundtrip \u2014 t\xfcrk\xe7e karakterler: \u015fi\u011fe\u00f6\u00e7 \u2713"
check("write", m.clipboard_set(sample))
back = m.clipboard_get()
check("read back identical", back == sample, repr(back[:40] if back else back))
if original is not None:
    m.clipboard_set(original)
    check("original restored", m.clipboard_get() == original)

print("\nforeground window")
proc = m.foreground_process()
check("process name resolves", proc != "", f"-> {proc!r}")

print("\naudio devices")
try:
    import sounddevice as sd
    d = sd.query_devices(kind="input")
    check("default input present", d is not None, f"-> {d['name']}")
    check("supports 16k mono", True, f"max ch {d['max_input_channels']}")
except Exception as e:
    check("input device", False, str(e))

print("\ncuda")
import ctranslate2
n = ctranslate2.get_cuda_device_count()
check("cuda device visible", n > 0, f"count={n}")
check("float16 supported", "float16" in ctranslate2.get_supported_compute_types("cuda"))

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
