#!/usr/bin/env python3
"""
Run the AutoSRE backend (uvicorn, port 8000) and dashboard (vite, port 5173) together.
Ctrl+C stops both.   python scripts/dev.py
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> None:
    if not PY.exists():
        sys.exit("No .venv found. Run: python scripts/setup.py")
    procs = [
        subprocess.Popen([str(PY), "-m", "uvicorn", "autosre_api.asgi:application", "--app-dir", "backend",
                          "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT),
        subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
                         cwd=ROOT / "frontend", shell=os.name == "nt"),
    ]
    print("\nAutoSRE backend  -> http://127.0.0.1:8000/api/v1/health")
    print("AutoSRE dashboard -> http://127.0.0.1:5173   (Ctrl+C to stop)\n")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is not None:
                continue
            if os.name == "nt":  # npm runs under a shell: end the whole process tree
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
