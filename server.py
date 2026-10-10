"""Local FastAPI server and two-stage orchestration; no animation logic."""
import asyncio
import os
import logging
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import OLLAMA_URL, ROOT, PORT
from db import Database
from discovery import Discovery, is_remote, memory_warning
from oracle_client import OracleClient, OracleError, VERDICTS
from quips import canned
from voice_client import VoiceClient

os.environ["OTEL_SDK_DISABLED"] = "true"


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class SettingsChange(BaseModel):
    oracle_model: str | None = Field(default=None, max_length=200)
    voice_model: str | None = Field(default=None, max_length=200)
    let_think: bool | None = None
    sound: bool | None = None


class Room:
    def __init__(self, db, http):
        self.db, self.http = db, http
        self.lock = asyncio.Lock()
        self.discovery = Discovery(http, db, self.lock)
        self.oracle = OracleClient(http)
        self.voice = VoiceClient(http)
        self.jobs = {}
        self.tasks = set()
        self.warming = ""
        self.warm_error = ""
        self.voice_warm_task = None
        self.local_catalog = []

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def local_model(self, name, catalog=None):
        try:
            if catalog is None:
                response = await self.http.get("/api/tags", timeout=5)
                response.raise_for_status()
                catalog = response.json()["models"]
                self.local_catalog = catalog
            tag = next((m for m in catalog if m["name"] == name), None)
            if not tag:
                raise OracleError("missing", "A spirit is missing from the room.", f"ollama pull {name}")
            if is_remote(tag):
                raise OracleError("remote", "That spirit lives beyond this room.", "Choose an installed local model; remote models are disabled.")
            return tag
        except OracleError:
            raise
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise OracleError("offline", "The spirits are unreachable.", "Start Ollama (ollama serve), then shake again.") from exc

    async def loaded(self, model):
        try:
            response = await self.http.get("/api/ps", timeout=3)
            return any(m.get("name", m.get("model")) == model for m in response.json().get("models", []))
        except (httpx.HTTPError, ValueError):
            return False

    async def prewarm(self):
        model = (await asyncio.to_thread(self.db.settings))["oracle_model"]
        self.warming, self.warm_error = model, ""
        try:
            async with self.lock:
                await self.local_model(model)
                if not await self.loaded(model):
                    await self.oracle.prewarm(model)
        except (OracleError, httpx.HTTPError) as exc:
            self.warm_error = str(exc)
        finally:
            if self.warming == model:
                self.warming = ""

    async def startup(self):
        # Prewarm first, then probe other catalog entries; neither blocks HTTP startup.
        self.discovery.start()
        await self.prewarm()
        if self.discovery.task:
            await self.discovery.task
        await self.prewarm()
        self.voice_warm_task = self.spawn(self.prewarm_voice())

    async def prewarm_voice(self):
        model = (await asyncio.to_thread(self.db.settings))["voice_model"]
        if not model:
            return
        try:
            await self.local_model(model)
            response = await self.http.post("/api/generate", json={"model": model, "keep_alive": "30m", "options": {"num_ctx": 2048}}, timeout=90)
            response.raise_for_status()
        except (OracleError, httpx.HTTPError):
            # A voice that cannot load still has a complete canned fallback.
            pass

    async def deliver_voice(self, settings, question, verdict, confidence, catalog):
        model = settings["voice_model"]
        if model:
            try:
                # Both roles use the fresh catalog fetched at the start of this prediction.
                await self.local_model(model, catalog=catalog)
            except OracleError as exc:
                return {"quip": canned(verdict), "source": "canned", "mutters": "", "hint": exc.hint}
        return {**await self.voice.deliver(model, question, verdict, confidence, "Default Haunted Orb", settings["let_think"]), "hint": ""}

    async def predict(self, job_id, question, settings):
        job = self.jobs[job_id]
        model = settings["oracle_model"]
        started = time.monotonic()
        self.discovery.activity.set()
        voice_task = None
        try:
            async with self.lock:
                await self.local_model(model)
                catalog = list(self.local_catalog)
                job["state"] = "listening" if await self.loaded(model) else "stirring"
                prediction = await self.oracle.predict(model, question)
            self.discovery.online = True
            self.discovery.error = ""
            job["state"] = "murmuring"
            verdict = "conflicted" if prediction["conflicted"] else prediction["verdict"]
            voice_model = settings["voice_model"]
            voice_task = asyncio.create_task(self.deliver_voice(settings, question, verdict, prediction["confidence"], catalog))
            # Ordinary voice may use only the remaining theatrical window.
            remaining = max(0, settings["theatrical_delay"] - (time.monotonic() - started))
            if settings["let_think"] and voice_model:
                remaining = 12
            voice = {"quip": canned(verdict), "source": "canned", "mutters": "", "hint": ""}
            if remaining > 0:
                try:
                    voice = await asyncio.wait_for(voice_task, timeout=remaining)
                except TimeoutError:
                    pass
            else:
                voice_task.cancel()
            if not settings["let_think"] or not voice_model:
                await asyncio.sleep(max(0, settings["theatrical_delay"] - (time.monotonic() - started)))
            job.update(state="revealed", result={**prediction, **voice, "question": question, "model": model, "mode": "single", "notice": "The spirits are conflicted." if prediction["conflicted"] else ""})
        except OracleError as exc:
            await asyncio.sleep(max(0, settings["theatrical_delay"] - (time.monotonic() - started)))
            if exc.kind in ("offline", "missing", "remote"):
                job.update(state="error", error=str(exc), hint=exc.hint)
                if exc.kind == "offline":
                    self.discovery.online = False
                    self.discovery.error = str(exc)
            else:
                verdict = secrets.choice(VERDICTS)
                job.update(state="revealed", result={"verdict": verdict, "confidence": None, "probabilities": {}, "answerable": None, "vibe": 1, "conflicted": False, "split": 0, "quip": canned(verdict), "source": "canned", "mutters": "", "question": question, "model": None, "mode": "dice-only", "notice": str(exc), "hint": exc.hint})
        except Exception:
            logging.getLogger("orb").exception("Prediction failed")
            job.update(state="error", error="The spirits tripped over a candle.", hint="Try another shake; check the local server terminal if it keeps happening.")
        finally:
            if voice_task:
                if not voice_task.done():
                    voice_task.cancel()
                await asyncio.gather(voice_task, return_exceptions=True)
            job["finished"] = time.monotonic()
            self.discovery.activity.clear()

    async def close(self):
        await self.discovery.close()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


@asynccontextmanager
async def lifespan(app):
    db = Database()
    async with httpx.AsyncClient(base_url=OLLAMA_URL, trust_env=False, timeout=90) as http:
        room = Room(db, http)
        app.state.room = room
        room.spawn(room.startup())
        yield
        await room.close()


app = FastAPI(title="Orb of Questionable Wisdom", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    if host not in ("localhost", "127.0.0.1"):
        return JSONResponse({"detail": "This orb stays on localhost."}, status_code=403)
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.hostname != host or parsed.netloc != request.headers.get("host") or parsed.scheme != request.url.scheme:
            return JSONResponse({"detail": "Only the local orb page may make this request."}, status_code=403)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/state")
async def state(request: Request):
    room = request.app.state.room
    return {"app": "orb-of-questionable-wisdom", "settings": await asyncio.to_thread(room.db.settings), "models": room.discovery.models, "scanning": room.discovery.scanning, "online": room.discovery.online, "discovery_error": room.discovery.error, "version": room.discovery.version, "warming": room.warming, "warm_error": room.warm_error, "memory_warning": memory_warning()}


@app.post("/api/rescan", status_code=202)
async def rescan(request: Request):
    room = request.app.state.room
    room.discovery.start(force=True)
    async def restore_warmth():
        await room.discovery.task
        await room.prewarm()
    room.spawn(restore_warmth())
    return {"status": "scanning"}


@app.patch("/api/settings")
async def save_settings(changes: SettingsChange, request: Request):
    room = request.app.state.room
    update = changes.model_dump(exclude_none=True)
    for key, role in (("oracle_model", "decision"), ("voice_model", "voice")):
        if key in update and update[key]:
            await room.local_model(update[key])
            candidate = room.discovery.model(update[key])
            if not candidate or candidate["role"] != role:
                raise HTTPException(422, f"Choose a discovered {role} model.")
    if "oracle_model" in update and not update["oracle_model"]:
        raise HTTPException(422, "Choose a decision model.")
    old = await asyncio.to_thread(room.db.settings)
    result = await asyncio.to_thread(room.db.save_settings, update)
    if old["oracle_model"] != result["oracle_model"]:
        room.spawn(room.prewarm())
    if old["voice_model"] != result["voice_model"]:
        if room.voice_warm_task and not room.voice_warm_task.done():
            room.voice_warm_task.cancel()
        room.voice_warm_task = room.spawn(room.prewarm_voice())
    return result


@app.exception_handler(OracleError)
async def oracle_exception(request, exc):
    return JSONResponse({"detail": str(exc), "hint": exc.hint}, status_code=422)


@app.post("/api/predictions", status_code=202)
async def ask(body: Ask, request: Request):
    room = request.app.state.room
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Whisper a question first.")
    if any(job["state"] not in ("revealed", "error") for job in room.jobs.values()):
        raise HTTPException(409, "The spirits are already considering a question.")
    for key in list(room.jobs)[:-24]:
        del room.jobs[key]
    job_id = secrets.token_urlsafe(16)
    room.jobs[job_id] = {"id": job_id, "state": "stirring", "result": None}
    settings = await asyncio.to_thread(room.db.settings)
    room.spawn(room.predict(job_id, question, settings))
    return {"id": job_id, "state": room.jobs[job_id]["state"]}


@app.get("/api/predictions/{job_id}")
async def prediction(job_id: str, request: Request):
    job = request.app.state.room.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "This omen has drifted away.")
    return job


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, access_log=False)
