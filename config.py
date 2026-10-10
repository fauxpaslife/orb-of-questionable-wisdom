"""Defaults live here; model names never belong in application logic."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("ORB_DATA_DIR", str(ROOT / "data")))
OLLAMA_URL = "http://127.0.0.1:11434"
PORT = int(os.environ.get("ORB_PORT", "8768"))
DEFAULTS = {
    "oracle_model": os.environ.get("ORB_ORACLE_MODEL", "tev1:4b"),
    "voice_model": os.environ.get("ORB_VOICE_MODEL", "nemotron-3-nano:4b"),
    "let_think": False,
    "sound": False,
    "theatrical_delay": 1.5,
}
KEEP_ALIVE = "30m"
DISCOVERY_TIMEOUT = 90
ORACLE_TIMEOUT = 180
