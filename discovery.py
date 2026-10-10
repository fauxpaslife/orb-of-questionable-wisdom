"""Name-first discovery; probes run in a background task and are cached in SQLite."""
import asyncio
import ctypes
import re

import httpx

from config import DISCOVERY_TIMEOUT, KEEP_ALIVE
from oracle_client import PROBE


def memory_warning():
    if not hasattr(ctypes, "windll"):
        return ""
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(key, ctypes.c_ulonglong) for key in ("total", "available", "page", "available_page", "virtual", "available_virtual", "extended")]
    status = Memory()
    status.length = ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) and (status.load >= 85 or status.available < 2 * 1024 ** 3):
        return "Memory is tight; use a smaller model or canned voice. Court seats will be optional when Court arrives."
    return ""


def is_remote(model):
    name = model.get("name", "").lower()
    return bool(model.get("remote_host") or model.get("remote_model") or name.endswith(":cloud") or name.endswith("-cloud"))


class Discovery:
    def __init__(self, http, db, inference_lock=None):
        self.http, self.db = http, db
        self.models = []
        self.scanning = False
        self.online = False
        self.error = ""
        self.version = ""
        self.task = None
        self.activity = asyncio.Event()
        self.inference_lock = inference_lock or asyncio.Lock()

    def start(self, force=False):
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self.scan(force))

    def model(self, name):
        return next((m for m in self.models if m["name"] == name), None)

    async def probe(self, entry):
        # Never wait on prediction activity while holding the inference lock.
        # Predictions set activity before acquiring that same lock.
        while True:
            while self.activity.is_set():
                await asyncio.sleep(0.25)
            async with self.inference_lock:
                if not self.activity.is_set():
                    settings = await asyncio.to_thread(self.db.settings)
                    keep_alive = KEEP_ALIVE if entry["name"] == settings["oracle_model"] else 0
                    return await self.http.post("/v1/systemone", json={"model": entry["name"], "state": "The sky is blue.", "questions": PROBE, "keep_alive": keep_alive}, timeout=DISCOVERY_TIMEOUT)
            await asyncio.sleep(0.25)

    async def scan(self, force=False):
        self.scanning = True
        try:
            response = await self.http.get("/api/tags", timeout=5)
            response.raise_for_status()
            tags = response.json()["models"]
            self.online, self.error = True, ""
            try:
                self.version = (await self.http.get("/api/version", timeout=5)).json().get("version", "")
            except (httpx.HTTPError, ValueError):
                pass
            cache = await asyncio.to_thread(self.db.cache)
            selected = (await asyncio.to_thread(self.db.settings))["oracle_model"]
            candidates = []
            models = []
            for tag in tags:
                if is_remote(tag):
                    continue
                name = tag["name"]
                capabilities = tag.get("capabilities", [])
                if "completion" not in capabilities and "decision" not in capabilities and capabilities:
                    continue
                named = bool(re.match(r"^(?:.*/)?(?:tev1|nimble)(?::|$)", name, re.I))
                role = "decision" if named or "decision" in capabilities else "voice"
                entry = {"name": name, "digest": tag.get("digest", ""), "role": role, "probe": "name match" if named else "catalog hint", "size": tag.get("size", 0)}
                old = cache.get(name)
                if old and old["digest"] == entry["digest"] and old["probe"] not in ("name match", "catalog hint") and not force:
                    entry.update(old)
                else:
                    candidates.append(entry)
                models.append(entry)
            # Publish the full name-first catalog before any cache write or model probe.
            self.models = models
            candidates.sort(key=lambda m: m["name"] != selected)
            await asyncio.to_thread(self.db.cache_models, models)
            for entry in candidates:
                while self.activity.is_set():
                    await asyncio.sleep(0.25)
                try:
                    response = await self.probe(entry)
                    if response.status_code == 200 and "probe" in response.json().get("answers", {}):
                        entry.update(role="decision", probe="passed")
                    elif response.status_code >= 500:
                        entry["probe"] = "inconclusive: server error"
                    else:
                        entry["probe"] = "failed; name fallback" if re.match(r"^(?:.*/)?(?:tev1|nimble)(?::|$)", entry["name"], re.I) else "failed"
                        if entry["probe"] == "failed":
                            entry["role"] = "voice"
                except (httpx.HTTPError, ValueError):
                    entry["probe"] = "inconclusive: timeout or connection"
                await asyncio.to_thread(self.db.cache_model, entry["name"], entry["digest"], entry["role"], entry["probe"])
        except (httpx.HTTPError, ValueError, KeyError):
            self.online = False
            self.error = "The spirits are unreachable. Start Ollama (ollama serve), then Rescan."
        finally:
            self.scanning = False

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
