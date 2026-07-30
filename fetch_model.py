"""Fetch a Whisper model, tolerating a flaky connection.

Downloads resume, so a failed attempt is not wasted work. Parallel connections
seem to be what triggers the resets here, hence max_workers=1.
"""
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from huggingface_hub import snapshot_download

MODEL = sys.argv[1] if len(sys.argv) > 1 else "large-v3"
REPO = f"Systran/faster-whisper-{MODEL}"
ATTEMPTS = 8

for attempt in range(1, ATTEMPTS + 1):
    try:
        print(f"attempt {attempt}/{ATTEMPTS}: {REPO}", flush=True)
        path = snapshot_download(
            REPO,
            max_workers=1,          # one connection at a time
            allow_patterns=["*.bin", "*.json", "*.txt"],
        )
        print(f"OK -> {path}", flush=True)
        break
    except Exception as e:
        print(f"  failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
        if attempt == ATTEMPTS:
            print("giving up", flush=True)
            sys.exit(1)
        wait = min(5 * attempt, 30)
        print(f"  retrying in {wait}s (partial progress is kept)", flush=True)
        time.sleep(wait)
