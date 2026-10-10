"""Local fallback voice. No model calls."""
import random

QUIPS = {
    "DEFINITELY": ["Yes. I checked twice, then ignored the second check.", "Absolutely. Frame this moment.", "The spirits said yes before you finished asking. Rude, honestly.", "Yes. Do it before the universe reconsiders.", "A confident yes, powered by statistically questionable vibes."],
    "PROBABLY": ["Probably. Gas station sushi kind of probably.", "Leaning yes. Leaning, not committing.", "Yes-ish. I'd bet on it, but not my good money.", "Signs point to yes, and one sign is a napkin.", "Probably. Don't quote me, I'm a ball."],
    "ASK LATER": ["Ask later. The orb is on lunch.", "The spirits are in a meeting that could have been an email.", "Too foggy. Try again after a snack.", "Have you tried turning yourself off and on again?", "Ask again when I care more."],
    "UNLIKELY": ["Unlikely. Not impossible, just deeply unmotivated.", "The odds are low, and so is the orb's enthusiasm.", "Better odds at a rigged ring toss.", "Probably not, but hope makes a fine hobby.", "The universe winced a little."],
    "NO": ["No. And I will not be taking follow-up questions.", "No. The spirits are unanimous and slightly smug.", "Nope. Drink some water and reflect.", "A firm no, delivered with love and a tiny eye roll.", "No. Next question."],
    "CURSED": ["Cursed. Do not. A candle just died.", "The answer sounds like a dial-up modem. Run.", "Cursed. A raven just looked at me.", "Absolutely not, and also check your pockets.", "Bad omen. Specifically a 'phone at 1%' omen."],
}
SPECIAL = {
    "conflicted": "The spirits are arguing. I'm just the messenger.",
    "dizzy": "Ow. The orb is dizzy. Ask again, gently.",
    "repeat": "Asked and answered. The spirits do not do reruns.",
    "witching": "It's the witching hour. Choose your questions wisely.",
    "idle": "...are you still there? The candles are getting nervous.",
    "offline": "The spirits are unreachable.",
}


def canned(verdict):
    return SPECIAL[verdict] if verdict in SPECIAL else random.choice(QUIPS.get(verdict, QUIPS["ASK LATER"]))
