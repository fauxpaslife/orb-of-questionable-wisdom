"""Typed System One calls; decision models are never sent chat prompts."""
import math

import httpx

from config import KEEP_ALIVE, ORACLE_TIMEOUT

VERDICTS = ("DEFINITELY", "PROBABLY", "ASK LATER", "UNLIKELY", "NO", "CURSED")
QUESTIONS = {
    "verdict": {"type": "choice", "instructions": "Judge the question using the available facts. Use ASK LATER when no verdict fits or evidence is insufficient.", "criteria": {
        "DEFINITELY": "A clear yes supported by the facts.", "PROBABLY": "A likely yes with some uncertainty.", "ASK LATER": "No matching answer or insufficient information.", "UNLIKELY": "A likely no with some uncertainty.", "NO": "A clear no supported by the facts.", "CURSED": "An ominous or disastrous prospect.",
    }},
    "answerable": {"type": "noul", "instructions": "Is this a real question with a knowable outcome?", "criteria": {"true": "A real question with a knowable outcome.", "false": "Not a real question or no knowable outcome."}},
    "vibe": {"type": "score", "instructions": "Rate the emotional outlook of this question.", "criteria": ["doom: ominous or disastrous", "meh: neutral or uncertain", "hopeful: positive or promising"]},
}
PROBE = {"probe": {"type": "noul", "instructions": "Is the statement true?"}}


class OracleError(Exception):
    def __init__(self, kind, message, hint=""):
        self.kind, self.hint = kind, hint
        super().__init__(message)


def bounded(value, low, high):
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError("Out-of-range oracle value")
    return result


def parse_answers(raw):
    try:
        answers = raw["answers"]
        verdict = answers["verdict"]["choice"]
        probabilities = {key: bounded(value, 0, 1) for key, value in answers["verdict"]["probabilities"].items()}
        if verdict not in VERDICTS or set(probabilities) != set(VERDICTS) or not 0.99 <= sum(probabilities.values()) <= 1.01:
            raise ValueError("Invalid verdict distribution")
        answerable = bounded(answers["answerable"]["noul"], 0, 1)
        vibe = bounded(answers["vibe"]["score"], 0, 2)
        return {"verdict": verdict, "confidence": probabilities[verdict], "probabilities": probabilities, "answerable": answerable, "vibe": vibe, "conflicted": answerable < 0.35 and verdict in ("DEFINITELY", "PROBABLY", "NO"), "split": 1 - max(probabilities.values())}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise OracleError("malformed", "The spirits sent a scrambled omen.", "Using dice only for this shake; rescan or choose another decision model.") from exc


class OracleClient:
    def __init__(self, http):
        self.http = http

    async def predict(self, model, question):
        try:
            response = await self.http.post("/v1/systemone", json={"model": model, "state": "Question: " + question[:500], "questions": QUESTIONS, "keep_alive": KEEP_ALIVE}, timeout=ORACLE_TIMEOUT)
            if response.status_code == 404:
                error = response.text.lower()
                if "model" in error and ("not found" in error or "missing" in error):
                    raise OracleError("missing", "A spirit is missing from the room.", f"ollama pull {model}")
                raise OracleError("unsupported", "This doorway to the spirits is sealed.", "System One is unavailable; using dice only. Update Ollama to 0.35 or later.")
            if response.status_code >= 400:
                raise OracleError("unsupported", "This spirit cannot read omens.", "Using dice only; choose another decision model or rescan.")
            return parse_answers(response.json())
        except OracleError:
            raise
        except httpx.ConnectError as exc:
            raise OracleError("offline", "The spirits are unreachable.", "Start Ollama, then shake again (ollama serve).") from exc
        except httpx.TimeoutException as exc:
            raise OracleError("timeout", "The spirits are taking an extended lunch.", "Using dice only for this shake; the model may still be loading.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OracleError("malformed", "The spirits sent a scrambled omen.", "Using dice only; rescan or choose another decision model.") from exc

    async def prewarm(self, model):
        response = await self.http.post("/v1/systemone", json={"model": model, "state": "The sky is blue.", "questions": PROBE, "keep_alive": KEEP_ALIVE}, timeout=ORACLE_TIMEOUT)
        response.raise_for_status()
