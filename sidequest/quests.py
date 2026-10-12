"""Quest generation: Gemma writes the quest, code keeps it short, safe and valid."""

import random
import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sidequest import ai
from sidequest.config import get_settings

Setting = Literal["park", "street", "garden", "water", "woods", "campus"]
Energy = Literal["calm", "curious", "active"]


class QuestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minutes: Literal[15, 30, 45, 60] = 30
    setting: Setting = "park"
    energy: Energy = "curious"


class Find(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what: str = Field(min_length=3, max_length=80)
    hint: str = Field(min_length=3, max_length=140)


class QuestCard(BaseModel):
    """Exactly what the model may return."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=60)
    intro: str = Field(min_length=10, max_length=220)
    finds: list[Find] = Field(min_length=3, max_length=3)
    sit_spot: str = Field(min_length=10, max_length=220)
    turn_back: str = Field(min_length=10, max_length=180)


# --- context ----------------------------------------------------------------------------------

TROPICAL_SOUTH_ASIA = {"Asia/Kolkata", "Asia/Calcutta", "Asia/Colombo", "Asia/Dhaka", "Asia/Kathmandu"}


def season_for(month: int, hemisphere: str = "north", timezone: str = "") -> str:
    """A season that matches what's actually outside. A 'temperate autumn' in Bengaluru would send
    people looking for red maple leaves that aren't there."""
    if timezone in TROPICAL_SOUTH_ASIA:
        if month in (6, 7, 8, 9):
            return "monsoon (wet, green, puddles, frogs and snails after rain)"
        if month in (10, 11):
            return "post-monsoon (clear skies, lush green, flowers, migrating birds arriving)"
        if month in (12, 1, 2):
            return "winter (cool mornings, mist, dry leaves, winter birds)"
        return "summer (hot, bright, flowering trees like gulmohar, seek shade)"
    north = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
             6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
    season = north[month]
    if hemisphere == "south":
        season = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}[season]
    return season


def part_of_day(hour: int) -> str:
    if hour < 5 or hour >= 19:
        return "night"
    if hour < 11:
        return "morning"
    if hour < 16:
        return "afternoon"
    return "evening"


# --- safety -----------------------------------------------------------------------------------

UNSAFE = re.compile(
    r"\b(eat|eating|taste|tasting|lick|swallow|chew|forage|mushroom|berr(y|ies)|feed|touch (a|the|any)? ?(animal|bird|snake|dog|cat|insect|spider|bee)"
    r"|pick up (a|the)? ?(animal|bird|snake|insect)|climb|trespass|private property|fence|cross (the|a) (road|street)|swim|wade|deep water"
    r"|cliff|ledge|edge of|rooftop|railway|train track|stranger|follow (a|the) (person|stranger))\b",
    re.IGNORECASE,
)


def is_unsafe(text: str) -> bool:
    return bool(UNSAFE.search(text))


# --- built-in deck (used offline and to replace anything unsafe) ------------------------------

DECK: dict[str, list[tuple[str, str]]] = {
    "park": [("A leaf bigger than your hand", "Look under the biggest tree first."),
             ("Something red that isn't a flower", "Benches, berries on bushes, signs, a lost glove."),
             ("A bird you can hear but not see", "Stand still for 30 seconds and listen up."),
             ("Bark with a pattern you like", "Compare two different trees."),
             ("A shadow shaped like an animal", "Low sun makes the best shadows."),
             ("Three different shades of green", "Grass, moss, a leaf in the light.")],
    "street": [("A plant growing where it shouldn't", "Cracks in walls and pavements."),
               ("The oldest-looking door on the block", "Paint layers and worn handles."),
               ("Something reflecting the sky", "Windows, puddles, car mirrors."),
               ("A tree with roots breaking the pavement", "Follow the bumpy footpath."),
               ("A hand-painted sign", "Small shops and chai stalls."),
               ("A bird on a wire", "Look up at the cables.")],
    "garden": [("A flower with five petals", "Count slowly, then count again."),
               ("Something a bee would visit", "Bright, open flowers in the sun."),
               ("A leaf with a bite taken out of it", "Turn leaves over gently."),
               ("The tallest plant in the garden", "Stand back to compare."),
               ("A seed or seed pod", "Dry, brown tips of stems."),
               ("Dew or water caught on a leaf", "Shady corners hold it longest.")],
    "water": [("Ripples that aren't from the wind", "Watch the surface for a full minute."),
              ("A smooth, round stone on the path", "Look along the edge of the path, not in the water."),
              ("A bird near the water", "Herons and egrets stand very still."),
              ("A reflection of a tree", "Find a calm stretch of water."),
              ("Something carried by the current", "Leaves, twigs, petals."),
              ("A plant that only grows near water", "Reeds and tall grasses.")],
    "woods": [("Moss on the shady side of something", "Logs, rocks, the base of trees."),
              ("A fallen branch shaped like a letter", "Y, V and T are the easiest."),
              ("A hole in a tree", "Look at eye level and higher."),
              ("A feather on the ground", "Look, don't touch. A photo is enough."),
              ("Light coming through the canopy", "Look straight up in a clearing."),
              ("A fungus on a log (look, don't touch)", "Damp, rotting wood.")],
    "campus": [("The quietest bench on campus", "Away from the main paths."),
               ("A tree older than the buildings", "Thick trunk, wide canopy."),
               ("A bird building or using a nest", "Ledges, tall trees, lamp posts."),
               ("Something growing on a wall", "Old brick and stone walls."),
               ("A spot with a long view", "Stairs, a field, the end of a path."),
               ("Five different kinds of leaves", "Walk the hedge line.")],
}

SIT_SPOTS = [
    "Sit or stand still for two minutes. Count how many different sounds you can hear, near and far.",
    "Find a spot to sit for two minutes. Close your eyes and notice what you can smell.",
    "Stop for two minutes and watch one small patch of ground. What moves?",
]


def fallback_card(req: QuestRequest, seed: int) -> QuestCard:
    rng = random.Random(f"{req.setting}-{req.minutes}-{seed}")
    items = rng.sample(DECK[req.setting], 3)
    return QuestCard(
        title=f"A {req.minutes}-minute {req.setting} quest",
        intro="Three things to find, one minute of stillness, and then home. Your phone stays in your pocket.",
        finds=[Find(what=w, hint=h) for w, h in items],
        sit_spot=rng.choice(SIT_SPOTS),
        turn_back=f"Head back after about {req.minutes} minutes, or once you've found all three. Whichever comes first.",
    )


def make_safe(card: QuestCard, req: QuestRequest, seed: int) -> tuple[QuestCard, str | None]:
    """Replace any unsafe part with a deck item. The model writes, the rules decide."""
    deck = [Find(what=w, hint=h) for w, h in DECK[req.setting]]
    swapped: list[str] = []
    finds: list[Find] = []
    for f in card.finds:
        if is_unsafe(f.what) or is_unsafe(f.hint):
            pool = [d for d in deck if d.what not in {x.what for x in finds + card.finds}]
            finds.append(random.Random(seed + len(swapped)).choice(pool))
            swapped.append(f.what)
        else:
            finds.append(f)
    sit = card.sit_spot
    if is_unsafe(sit):
        sit = SIT_SPOTS[seed % len(SIT_SPOTS)]
        swapped.append("the sit-spot activity")
    note = ("Side Quest swapped " + ", ".join(f'"{w}"' if w != "the sit-spot activity" else w for w in swapped)
            + " for something you only need to look at.") if swapped else None
    return card.model_copy(update={"finds": finds, "sit_spot": sit}), note


# --- generation -------------------------------------------------------------------------------

PROMPT = """You design tiny outdoor quests that get someone off their screen and outside.

Context:
- Where: {setting}
- Time available: {minutes} minutes (including walking back)
- Mood: {energy}
- Season: {season}
- Time of day: {part_of_day}
- Region: {region}

Write ONE quest as JSON matching the schema:
- title: playful, under 6 words.
- intro: one sentence that makes them want to step outside now.
- finds: exactly 3 things they can SEE and photograph in a {setting} in {season}. Each is concrete and findable in {minutes} minutes. Each hint is one short sentence about where to look.
- sit_spot: one 1-2 minute stillness activity (listening, watching, noticing).
- turn_back: when to head home. It MUST say "{minutes} minutes".

Rules:
- Look, listen and photograph only. Never ask them to eat, taste, pick, touch or feed anything alive, climb, enter water, cross roads, or go anywhere private.
- If it is night, keep everything to well-lit, familiar paths.
- No emojis. Plain, warm language.
"""


async def generate(req: QuestRequest, seed: int | None = None, now: datetime | None = None) -> tuple[QuestCard, str, str | None]:
    """Returns (card, source, safety_note). source is 'ai' or 'fallback'."""
    s = get_settings()
    seed = seed if seed is not None else random.randrange(10**6)
    now = now or datetime.now(ZoneInfo(s.timezone))
    prompt = PROMPT.format(
        setting=req.setting, minutes=req.minutes, energy=req.energy,
        season=season_for(now.month, s.hemisphere, s.timezone), part_of_day=part_of_day(now.hour), region=s.timezone,
    )
    try:
        reply = await ai.chat([{"role": "user", "content": prompt}], schema=QuestCard.model_json_schema(),
                              temperature=0.8, num_predict=450)
        card = QuestCard.model_validate_json(reply.content)
    except (ai.AiUnavailable, ValidationError):
        return fallback_card(req, seed), "fallback", None
    card, note = make_safe(tidy(card, req), req, seed)
    return card, "ai", note


def tidy(card: QuestCard, req: QuestRequest) -> QuestCard:
    """Trim stray whitespace, and make sure the turn-back cue is an actual time limit."""
    def t(x: str) -> str:
        return " ".join(x.split())

    turn_back = t(card.turn_back)
    if str(req.minutes) not in turn_back:
        turn_back = f"Head back after about {req.minutes} minutes, or once you've found all three. Whichever comes first."
    return card.model_copy(update={
        "title": t(card.title), "intro": t(card.intro), "sit_spot": t(card.sit_spot), "turn_back": turn_back,
        "finds": [Find(what=t(f.what), hint=t(f.hint)) for f in card.finds],
    })
