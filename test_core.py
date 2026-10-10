"""Behavior checks use temporary SQLite and synthetic local HTTP responses."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from config import DEFAULTS
from db import Database
from discovery import Discovery, is_remote
from oracle_client import OracleClient, OracleError, VERDICTS, parse_answers
from server import Room, app
from voice_client import messages, strip_thinking, sureness, validate


def answer(verdict="PROBABLY", answerable=.8):
    probs = {v: .04 for v in VERDICTS}
    probs[verdict] = .8
    return {"answers": {"verdict": {"choice": verdict, "probabilities": probs, "confidence": .13}, "answerable": {"noul": answerable}, "vibe": {"score": 1.5}}}


def tag(name, capabilities=None, **kwargs):
    return {"name": name, "digest": "test-digest", "capabilities": capabilities or ["completion"], **kwargs}


class PureTests(unittest.TestCase):
    def test_launcher_waits_for_server_and_opens_page(self):
        import launch
        process = unittest.mock.Mock()
        process.poll.side_effect = [None, None, 0]
        with patch('launch.ready', side_effect=[False, False, True]), patch('launch.subprocess.Popen', return_value=process) as spawn, patch('launch.webbrowser.open') as open_page, patch('launch.time.sleep'):
            launch.main()
        self.assertEqual(Path(spawn.call_args.args[0][1]).name, 'server.py')
        open_page.assert_called_once_with(launch.URL)
        process.wait.assert_any_call()
        process.terminate.assert_not_called()

    def test_launcher_reuses_existing_orb(self):
        import launch
        with patch('launch.ready', return_value=True), patch('launch.subprocess.Popen') as spawn, patch('launch.webbrowser.open') as open_page:
            launch.main()
        spawn.assert_not_called()
        open_page.assert_called_once_with(launch.URL)

    def test_launcher_does_not_open_after_server_failure(self):
        import launch
        process = unittest.mock.Mock()
        process.poll.return_value = 1
        with patch('launch.ready', return_value=False), patch('launch.subprocess.Popen', return_value=process), patch('launch.webbrowser.open') as open_page:
            with self.assertRaises(SystemExit):
                launch.main()
        open_page.assert_not_called()

    def test_confidence_and_conflicted(self):
        result = parse_answers(answer(answerable=.2))
        self.assertEqual(result["confidence"], .8)
        self.assertTrue(result["conflicted"])
        self.assertEqual(set(result["probabilities"]), set(VERDICTS))
        self.assertFalse(parse_answers(answer("ASK LATER", .2))["conflicted"])

    def test_bad_distribution_is_rejected(self):
        raw = answer()
        raw["answers"]["verdict"]["probabilities"]["NO"] = float("nan")
        with self.assertRaises(OracleError):
            parse_answers(raw)

    def test_prompt_has_words_not_probabilities(self):
        for confidence, word in ((.9, "sure"), (.3, "shaky"), (.6, "medium")):
            prompt = messages("Should I text them back?", "PROBABLY", confidence)
            self.assertEqual(prompt[1]["content"], f"Question: Should I text them back?\nVerdict: PROBABLY\nSureness: {word}")
            self.assertNotIn(str(confidence), json.dumps(prompt))
        self.assertEqual(sureness(.75), "sure")
        self.assertEqual(sureness(.5), "medium")

    def test_thinking_and_rejection(self):
        self.assertEqual(strip_thinking("<think>private</think> Probably, a raven approves."), "Probably, a raven approves.")
        self.assertEqual(strip_thinking("<think>unfinished private reasoning"), "")
        for text in ("", "NO.", "Have you tried 5 Whys?", "word " * 31, "No </think>"):
            self.assertIsNotNone(validate(text, "NO"))

    def test_settings_and_cache_survive_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orb.db"
            db = Database(path)
            self.assertEqual(db.settings()["voice_model"], DEFAULTS["voice_model"])
            db.save_settings({"voice_model": "local:small"})
            db.cache_model("local:small", "sha", "voice", "failed")
            reopened = Database(path)
            self.assertEqual(reopened.settings()["voice_model"], "local:small")
            self.assertEqual(reopened.cache()["local:small"]["digest"], "sha")

    def test_remote_detection(self):
        for model in (tag("secret:cloud"), tag("local-looking", remote_host="https://example.com"), tag("name-cloud")):
            self.assertTrue(is_remote(model))


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.directory.name) / "orb.db")

    async def asyncTearDown(self):
        self.directory.cleanup()

    async def test_oracle_request_shape_and_truncation(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=answer())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434") as http:
            result = await OracleClient(http).predict("decision:test", "x" * 700)
        payload = json.loads(requests[0].content)
        self.assertEqual(requests[0].url.path, "/v1/systemone")
        self.assertEqual(payload["state"], "Question: " + "x" * 500)
        self.assertEqual(set(payload["questions"]), {"verdict", "answerable", "vibe"})
        self.assertNotIn("intensity", payload)
        self.assertEqual(result["confidence"], .8)

    async def test_discovery_publishes_before_slow_probe_and_caches(self):
        gate = asyncio.Event()
        probed = []
        async def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [tag("tev1:test", ["decision"]), tag("voice:test"), tag("cloud:test", remote_host="https://example.com"), tag("embed:test", ["embedding"])]})
            if request.url.path == "/api/version":
                return httpx.Response(200, json={"version": "0.40.2"})
            model = json.loads(request.content)["model"]
            probed.append(model)
            await gate.wait()
            return httpx.Response(200, json={"answers": {"probe": {"noul": .9}}}) if model.startswith("tev1") else httpx.Response(400, json={"error": "unsupported"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434") as http:
            discovery = Discovery(http, self.db)
            discovery.start()
            try:
                async with asyncio.timeout(3):
                    while not probed:
                        await asyncio.sleep(.01)
                self.assertTrue(discovery.scanning)
                self.assertEqual({m["name"] for m in discovery.models}, {"tev1:test", "voice:test"})
                self.assertEqual(discovery.model("tev1:test")["role"], "decision")
            finally:
                gate.set()
                await discovery.task
            count = len(probed)
            await discovery.scan()
            self.assertEqual(len(probed), count)
            self.assertNotIn("cloud:test", probed)

    async def test_discovery_does_not_deadlock_prediction_lock(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), base_url="http://127.0.0.1:11434") as http:
            lock = asyncio.Lock()
            discovery = Discovery(http, self.db, lock)
            discovery.activity.set()
            task = asyncio.create_task(discovery.probe({"name": "tev1:test"}))
            async with asyncio.timeout(.5):
                async with lock:
                    discovery.activity.clear()
                await task

    async def test_voice_cannot_hold_reveal(self):
        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434") as http:
            room = Room(self.db, http)
            room.local_model = AsyncMock(return_value=tag("test"))
            room.loaded = AsyncMock(return_value=True)
            room.oracle.predict = AsyncMock(return_value=parse_answers(answer()))
            async def slow(*args):
                await asyncio.sleep(10)
            room.voice.deliver = slow
            room.jobs["id"] = {"state": "listening"}
            settings = {**DEFAULTS, "voice_model": "voice:test", "theatrical_delay": .05}
            start = time.monotonic()
            with patch('server.VOICE_TIMEOUT', .1):
                await room.predict("id", "Question?", settings)
            self.assertLess(time.monotonic() - start, .5)
            self.assertGreaterEqual(time.monotonic() - start, .095)
            self.assertEqual(room.jobs["id"]["result"]["source"], "canned")

    async def test_unsupported_oracle_is_explicit_dice_only(self):
        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434") as http:
            room = Room(self.db, http)
            room.local_model = AsyncMock(return_value=tag("test"))
            room.loaded = AsyncMock(return_value=False)
            room.oracle.predict = AsyncMock(side_effect=OracleError("unsupported", "Unavailable", "Use dice only"))
            room.jobs["id"] = {"state": "stirring"}
            await room.predict("id", "Question?", {**DEFAULTS, "theatrical_delay": 0})
            result = room.jobs["id"]["result"]
            self.assertEqual(result["mode"], "dice-only")
            self.assertIsNone(result["confidence"])
            self.assertEqual(result["probabilities"], {})

    async def test_offline_and_missing_model_hints(self):
        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434") as http:
            room = Room(self.db, http)
            for kind, hint in (("offline", "ollama serve"), ("missing", "ollama pull test:model")):
                room.local_model = AsyncMock(side_effect=OracleError(kind, "Unreachable", hint))
                room.jobs[kind] = {"state": "stirring"}
                await room.predict(kind, "Question?", {**DEFAULTS, "theatrical_delay": 0})
                self.assertEqual(room.jobs[kind]["state"], "error")
                self.assertEqual(room.jobs[kind]["hint"], hint)

    async def test_voice_retry_is_bounded(self):
        from voice_client import VoiceClient
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"message": {"content": "<think>unfinished"}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434") as http:
            result = await VoiceClient(http).deliver("voice:test", "Question?", "NO", .8, "Default Haunted Orb")
        self.assertEqual(len(requests), 2)
        self.assertEqual(result["source"], "canned")

    async def test_remote_voice_never_receives_generation_call(self):
        requests = []
        def handler(request):
            requests.append(request.url.path)
            return httpx.Response(200, json={"models": [tag("decision:test", ["decision"]), tag("remote-looking-local", remote_host="https://example.com")]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434") as http:
            room = Room(self.db, http)
            room.loaded = AsyncMock(return_value=True)
            room.oracle.predict = AsyncMock(return_value=parse_answers(answer()))
            room.jobs["id"] = {"state": "stirring"}
            await room.predict("id", "Question?", {**DEFAULTS, "oracle_model": "decision:test", "voice_model": "remote-looking-local", "theatrical_delay": .05})
            self.assertEqual(room.jobs["id"]["result"]["source"], "canned")
            self.assertIn("remote models are disabled", room.jobs["id"]["result"]["hint"])
            self.assertEqual(requests, ["/api/tags"])

    async def test_missing_voice_shows_exact_pull_command(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"models": [tag("decision:test", ["decision"])]})), base_url="http://127.0.0.1:11434") as http:
            room = Room(self.db, http)
            room.loaded = AsyncMock(return_value=True)
            room.oracle.predict = AsyncMock(return_value=parse_answers(answer()))
            room.jobs["id"] = {"state": "stirring"}
            await room.predict("id", "Question?", {**DEFAULTS, "oracle_model": "decision:test", "voice_model": "missing:voice", "theatrical_delay": .05})
            self.assertEqual(room.jobs["id"]["result"]["hint"], "ollama pull missing:voice")


class APITests(unittest.TestCase):
    def test_local_api_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "orb.db")
            with patch("server.Database", return_value=db), patch.object(Room, "startup", new=AsyncMock()):
                with TestClient(app, base_url="http://127.0.0.1") as client:
                    room = app.state.room
                    room.discovery.models = [{"name": "test:oracle", "role": "decision"}, {"name": "test:voice", "role": "voice"}]
                    room.local_model = AsyncMock(return_value=tag("test"))
                    room.prewarm = AsyncMock()
                    room.prewarm_voice = AsyncMock()
                    self.assertEqual(client.get("/").status_code, 200)
                    self.assertEqual(client.get("/api/state").json()["settings"]["voice_model"], DEFAULTS["voice_model"])
                    saved = client.patch("/api/settings", json={"oracle_model": "test:oracle", "voice_model": "test:voice"})
                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(db.settings()["voice_model"], "test:voice")
                    self.assertFalse(db.settings()["sound"])
                    self.assertEqual(client.patch('/api/settings', json={'sound': True}).status_code, 200)
                    self.assertTrue(db.settings()['sound'])
                    self.assertEqual(client.patch("/api/settings", json={"oracle_model": "test:voice"}).status_code, 422)
                    self.assertEqual(client.post("/api/predictions", json={"question": " "}).status_code, 422)
                    self.assertEqual(client.post("/api/predictions", json={"question": "x" * 501}).status_code, 422)
                    self.assertEqual(client.get("/", headers={"host": "evil.example"}).status_code, 403)
                    self.assertEqual(client.post("/api/rescan", headers={"origin": "https://evil.example"}).status_code, 403)
                    self.assertIn("default-src 'self'", client.get("/").headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
