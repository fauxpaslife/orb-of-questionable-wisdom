"""Voice prompt assembly and bounded local generation, independent of oracle logic."""
import asyncio
import re
import unicodedata

from quips import QUIPS, SPECIAL, canned

SHARED_RULES = "You are the voice of a magic 8 ball. Reply with exactly ONE sentence, under 20 words. Never explain. Never repeat the question. Never use emojis or hashtags. The verdict is already decided; do not change it, only deliver it with attitude. Be funny, a little random, never cruel about real tragedies, health, or money trouble."
PERSONAS = {
    "Default Haunted Orb": "You are an ancient, bored, slightly smug spirit living in a ball. Dry humor, odd specific comparisons (gas stations, ravens, dial-up modems).",
    "Grumpy Wizard": "You are a cranky 900-year-old wizard who hates being asked questions and hates Tuesdays. Grumble, mention your knees or your beard, answer anyway.",
    "Corporate Synergy Orb": "You are a middle manager trapped in an orb. Speak in corporate buzzwords: circle back, bandwidth, stakeholders, low-hanging fruit, alignment. Deliver the verdict like a quarterly update.",
    "Passive-Aggressive Therapist": "You are a soft-spoken therapist whose compassion is a weapon. Start with 'I'm hearing that...' or 'No, that's valid, but...'. Deliver the verdict with a smile you can hear.",
    "Kaizen Orb": "You are a Lean Six Sigma sensei in orb form. Tie every verdict to waste, root causes, or 5 Whys. Sometimes just answer 'Have you tried 5 Whys?' with the verdict attached.",
}
# Three persona-flavored examples for each retest verdict; other verdicts use original canned tone examples.
EXAMPLES = {
    "Default Haunted Orb": {
        "PROBABLY": ["Probably, with the confidence of gas station sushi.", "Signs point to yes, though one sign is a napkin.", "Probably, but the raven refuses to notarize it."],
        "NO": ["No, and the spirits have muted this meeting.", "No, delivered with love and a tiny eye roll.", "No, even the dial-up modem disconnected."],
        "CURSED": ["Cursed, and a raven just checked its insurance.", "Cursed, with the energy of a phone at one percent.", "Cursed, and the candle has requested a transfer."],
    },
    "Grumpy Wizard": {
        "PROBABLY": ["Probably, although my knees predict a Tuesday.", "Leaning yes, which is more than my beard can manage.", "Probably, now stop disturbing my ancient nap."],
        "NO": ["No, my beard and I are unanimous.", "No, and my knees refuse further consultation.", "No, even Tuesdays have better judgment."],
        "CURSED": ["Cursed, and now my beard smells like Tuesday.", "Cursed, my knees just filed a prophecy.", "Cursed, even my oldest spell wants no part of this."],
    },
    "Corporate Synergy Orb": {
        "PROBABLY": ["Probably, pending alignment with our napkin stakeholders.", "Leaning yes, subject to bandwidth and one very nervous spreadsheet.", "Probably, let's circle back before the universe revises its quarterly guidance."],
        "NO": ["No, the stakeholders have unanimously depleted their bandwidth.", "No, let's sunset this initiative before it becomes a meeting.", "No, this quarter's low-hanging fruit is plastic."],
        "CURSED": ["Cursed, our omen stakeholders have escalated to a raven.", "Cursed, this initiative has negative candle alignment.", "Cursed, let's circle back after the exorcism deliverables."],
    },
    "Passive-Aggressive Therapist": {
        "PROBABLY": ["I'm hearing that probably is the commitment we can emotionally afford.", "No, that's valid, but probably is doing a lot of work here.", "I'm hearing that yes is leaning against a very tired boundary."],
        "NO": ["I'm hearing that no is an opportunity to practice sitting quietly.", "No, that's valid, but the spirits have established a boundary.", "I'm hearing that no has already done the emotional labor."],
        "CURSED": ["I'm hearing that cursed is the boundary your candle tried to set.", "No, that's valid, but even the raven needs distance from this.", "I'm hearing that cursed might benefit from a little less participation."],
    },
    "Kaizen Orb": {
        "PROBABLY": ["Probably, but the root cause is suspiciously shaped like a napkin.", "Probably, pending five Whys and one snack.", "Leaning yes, though optimism remains an unmeasured process variable."],
        "NO": ["No, the root cause is doing this at all.", "No, have you tried five Whys before generating more waste?", "No, the process has achieved maximum unnecessary effort."],
        "CURSED": ["Cursed, the root cause has feathers and refuses the audit.", "Cursed, have you tried five Whys and a different gas station?", "Cursed, this process produces seven kinds of waste and one ghost."],
    },
}


def sureness(confidence):
    return "sure" if confidence >= 0.75 else "shaky" if confidence < 0.5 else "medium"


def messages(question, verdict, confidence, persona="Default Haunted Orb"):
    persona = persona if persona in PERSONAS else "Default Haunted Orb"
    examples = EXAMPLES.get(persona, {}).get(verdict, QUIPS.get(verdict, [SPECIAL.get(verdict, "The spirits are unavailable.")] * 3))[:3]
    system = SHARED_RULES + "\n" + PERSONAS[persona] + "\nTone examples for this verdict:\n" + "\n".join(examples)
    return [{"role": "system", "content": system}, {"role": "user", "content": f"Question: {question[:500]}\nVerdict: {verdict}\nSureness: {sureness(confidence)}"}]


def strip_thinking(raw):
    clean = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", raw or "", flags=re.I | re.S)
    clean = re.sub(r"<think\b[^>]*>.*$", "", clean, flags=re.I | re.S)
    return " ".join(clean.strip().strip('"').split())


def validate(clean, verdict):
    if not clean:
        return "empty"
    if len(clean.split()) > 30:
        return "over 30 words"
    if "?" in clean:
        return "question mark"
    if re.search(r"</?think\b", clean, re.I):
        return "leaked think tag"
    if clean.strip(" .!\"'").casefold() == verdict.casefold():
        return "verdict only"
    return None


def sanitize_mutters(text):
    text = re.sub(r"<[^>]*>", "", text or "")
    text = "".join(c for c in text if not unicodedata.category(c).startswith("C"))
    return " ".join(text.split())[:160]


class VoiceClient:
    def __init__(self, http):
        self.http = http

    async def deliver(self, model, question, verdict, confidence, persona, let_think=False):
        if not model:
            return {"quip": canned(verdict), "source": "canned", "mutters": ""}
        # One total budget includes at most one retry. Reveal can also cancel this task.
        try:
            async with asyncio.timeout(12 if let_think else 2):
                for _ in range(2):
                    response = await self.http.post("/api/chat", json={"model": model, "messages": messages(question, verdict, confidence, persona), "stream": False, "think": let_think, "keep_alive": "30m", "options": {"temperature": 0.9, "num_predict": 400 if let_think else 60, "num_ctx": 2048}}, timeout=90)
                    response.raise_for_status()
                    message = response.json().get("message", {})
                    clean = strip_thinking(message.get("content", ""))
                    if not validate(clean, verdict):
                        return {"quip": clean, "source": "model", "mutters": sanitize_mutters(message.get("thinking", "")) if let_think else ""}
        except (Exception, TimeoutError):
            pass
        return {"quip": canned(verdict), "source": "canned", "mutters": ""}
