"""Standard-library Windows installer; model downloads always require a choice."""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import venv
from pathlib import Path

from config import DEFAULTS, OLLAMA_URL, ROOT, DATA

START_BAT = '''@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\\Scripts\\python.exe" (
    echo Run install.bat first to create the project environment.
    pause
    exit /b 1
)
".venv\\Scripts\\python.exe" launch.py
if errorlevel 1 pause
'''


def version_tuple(value):
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        raise ValueError("Ollama returned an unreadable version; update Ollama and try again.")
    return tuple(int(part or 0) for part in match.groups())


def get_json(endpoint):
    # Ignore proxies: setup checks always stay on localhost.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(OLLAMA_URL + endpoint, timeout=10) as response:
        return json.load(response)


def configured_models():
    settings = dict(DEFAULTS)
    path = DATA / "orb.db"
    if path.exists():
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for key, value in conn.execute("SELECT key,value_json FROM settings WHERE key IN ('oracle_model','voice_model')"):
                settings[key] = json.loads(value)
        finally:
            conn.close()
    return list(dict.fromkeys(settings[key] for key in ("oracle_model", "voice_model") if settings[key]))


def remote_model(model):
    return bool(model.get("remote_host") or model.get("remote_model") or model["name"].lower().endswith((":cloud", "-cloud")))


def check_ollama(non_interactive=False):
    try:
        version = get_json("/api/version")["version"]
        if version_tuple(version) < (0, 35, 0):
            raise RuntimeError(f"Ollama {version} is too old; version 0.35 or later is required.")
        tags = get_json("/api/tags")["models"]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("The spirits are unreachable. Install/start Ollama, then rerun install.bat. If needed: ollama serve") from exc
    print(f"Ollama {version}: ready on localhost.")
    local = {model["name"] for model in tags if not remote_model(model)}
    remote = {model["name"] for model in tags if remote_model(model)}
    missing = []
    for name in configured_models():
        if name in remote or name.lower().endswith((":cloud", "-cloud")):
            raise RuntimeError("A configured model is remote; choose a local model in config.py or the orb's settings.")
        if name in local:
            print(f"Local model ready: {name}")
            continue
        missing.append(name)
        print(f"Missing local model. Run: ollama pull {name}")
        if not non_interactive and input(f"Download {name} with Ollama now? [y/N] ").strip().lower() in ("y", "yes"):
            # Argument list, never shell interpolation; arbitrary model names cannot run commands.
            try:
                subprocess.run(["ollama", "pull", name], check=True)
            except FileNotFoundError as exc:
                raise RuntimeError("Ollama's CLI is not on PATH. Reopen the terminal after installing Ollama.") from exc
            missing.remove(name)
    if missing:
        print("Setup is ready; pull the missing model before asking the oracle, or choose another installed decision model.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install Orb of Questionable Wisdom locally.")
    parser.add_argument("--non-interactive", action="store_true", help="Print missing-model commands without offering downloads.")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or later is required.")
    environment = ROOT / ".venv"
    python = environment / "Scripts" / "python.exe"
    if not environment.exists():
        print("Creating the local Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    elif not python.is_file():
        raise RuntimeError(".venv exists but its Python executable is missing. Rename that folder, then rerun install.bat.")
    print("Installing dependencies into .venv...", flush=True)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")], cwd=ROOT, check=True)
    check_ollama(args.non_interactive)
    # Generated from the same source used by the shipped launcher.
    (ROOT / "start.bat").write_text(START_BAT, encoding="ascii", newline="\r\n")
    print("Installed. Double-click start.bat to open the orb. Keep its terminal open while using it.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, sqlite3.Error, subprocess.CalledProcessError, OSError) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nSetup paused. Run install.bat again when ready.", file=sys.stderr)
        sys.exit(1)
