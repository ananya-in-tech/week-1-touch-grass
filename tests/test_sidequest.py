import io
import json
import os
from datetime import datetime, timedelta

os.environ["AI_WARMUP"] = "false"

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sidequest import ai, main, quests, vision
from sidequest.db import DB


@pytest.fixture
def client(tmp_path, monkeypatch):
    from sidequest.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    main.set_db(DB(tmp_path / "test.db"))
    with TestClient(main.app) as c:
        yield c


def fake_ai(monkeypatch, *replies):
    it = iter(replies)

    async def chat(messages, **kw):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return ai.Reply(r if isinstance(r, str) else json.dumps(r), 5)

    monkeypatch.setattr(ai, "chat", chat)


CARD = {
    "title": "Autumn Colour Hunt",
    "intro": "The park is turning gold. Go see it before dinner.",
    "finds": [
        {"what": "A yellow leaf", "hint": "Under the biggest tree."},
        {"what": "A bird you can hear", "hint": "Stand still and listen."},
        {"what": "Bark with deep grooves", "hint": "Compare two trees."},
    ],
    "sit_spot": "Sit for two minutes and count the sounds you hear.",
    "turn_back": "Head home after 30 minutes or when you've found all three.",
}


def jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (1600, 1200), (80, 140, 60))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (12.0, 58.0, 0.0)  # latitude ref + value
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


# --- quest rules ------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["Taste a wild berry", "Pick up a snake", "climb the old oak", "Feed the ducks",
                                  "Wade into the stream", "Cross the road to the field"])
def test_unsafe_suggestions_detected(text):
    assert quests.is_unsafe(text)


@pytest.mark.parametrize("text", ["A leaf bigger than your hand", "A bird you can hear", "A fungus on a log (look, don't touch)"])
def test_safe_suggestions_pass(text):
    assert not quests.is_unsafe(text)


def test_unsafe_find_is_replaced_from_deck():
    card = quests.QuestCard.model_validate({**CARD, "finds": [*CARD["finds"][:2], {"what": "Taste a wild berry", "hint": "By the hedge."}]})
    safe, note = quests.make_safe(card, quests.QuestRequest(setting="park"), seed=1)
    assert not any(quests.is_unsafe(f.what) for f in safe.finds)
    assert len({f.what for f in safe.finds}) == 3 and note


def test_fallback_card_is_valid_and_deterministic():
    req = quests.QuestRequest(minutes=15, setting="woods")
    a, b = quests.fallback_card(req, 7), quests.fallback_card(req, 7)
    assert a == b and len(a.finds) == 3


def test_season_and_daypart():
    assert quests.season_for(10) == "autumn" and quests.season_for(10, "south") == "spring"
    assert quests.season_for(10, timezone="Asia/Kolkata").startswith("post-monsoon")
    assert quests.season_for(7, timezone="Asia/Kolkata").startswith("monsoon")
    assert quests.part_of_day(21) == "night" and quests.part_of_day(8) == "morning"


# --- photos -----------------------------------------------------------------------------------

def test_clean_photo_strips_location_and_resizes():
    raw = jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif()  # has EXIF going in
    clean = vision.clean_photo(raw)
    out = Image.open(io.BytesIO(clean))
    assert max(out.size) == 768
    assert not out.getexif() and "exif" not in out.info


def test_bad_upload_rejected():
    with pytest.raises(vision.BadPhoto):
        vision.clean_photo(b"not an image")


# --- full walk --------------------------------------------------------------------------------

def test_quest_flow_with_gemma(client, monkeypatch):
    fake_ai(monkeypatch, CARD, {"match": "yes", "saw": "A bright yellow leaf on grass"},
            "You spent 25 minutes outside and found a yellow leaf glowing on the grass.")
    q = client.post("/api/quests", json={"minutes": 30, "setting": "park", "energy": "calm"}).json()
    assert q["source"] == "ai" and q["status"] == "ready" and q["title"] == "Autumn Colour Hunt"

    assert client.post(f"/api/quests/{q['id']}/finds/0/photo", files={"photo": ("a.jpg", jpeg_with_gps())}).status_code == 409
    assert client.post(f"/api/quests/{q['id']}/start").json()["status"] == "out"
    assert client.post(f"/api/quests/{q['id']}/start").status_code == 409

    # pretend the walk took 25 minutes
    main.db().update_quest(q["id"], started_at=(datetime.fromisoformat(client.get(f"/api/quests/{q['id']}").json()["started_at"])
                                                - timedelta(minutes=25)).isoformat())
    back = client.post(f"/api/quests/{q['id']}/back", json={"screen_seconds": 70}).json()
    assert back["status"] == "back" and 1490 <= back["outside_seconds"] <= 1510

    after = client.post(f"/api/quests/{q['id']}/finds/0/photo", files={"photo": ("a.jpg", jpeg_with_gps())}).json()
    assert after["photos"][0]["match"] == "yes"
    saved = Image.open(main.get_settings().photo_dir / after["photos"][0]["file"])
    assert not saved.getexif()  # no GPS on disk either

    done = client.post(f"/api/quests/{q['id']}/finish", json={"heard": "a koel and traffic", "screen_seconds": 95}).json()
    assert done["status"] == "done" and done["journal_source"] == "ai" and done["screen_seconds"] == 95

    s = client.get("/api/stats").json()
    assert s["quests_done"] == 1 and s["finds_confirmed"] == 1 and s["screen_seconds"] == 95


def test_works_without_ai(client, monkeypatch):
    down = ai.AiUnavailable("ollama off")
    fake_ai(monkeypatch, down, down, down)
    q = client.post("/api/quests", json={"setting": "street"}).json()
    assert q["source"] == "fallback" and len(q["finds"]) == 3
    client.post(f"/api/quests/{q['id']}/start")
    client.post(f"/api/quests/{q['id']}/back", json={"screen_seconds": 10})
    p = client.post(f"/api/quests/{q['id']}/finds/1/photo", files={"photo": ("a.jpg", jpeg_with_gps())}).json()
    assert p["photos"][0]["match"] == "unchecked"  # photo still saved
    done = client.post(f"/api/quests/{q['id']}/finish", json={}).json()
    assert done["journal_source"] == "template" and done["journal"]


def test_invalid_model_output_falls_back(client, monkeypatch):
    fake_ai(monkeypatch, {"title": "x", "command": "rm -rf"})
    q = client.post("/api/quests", json={"setting": "garden"}).json()
    assert q["source"] == "fallback"


def test_photo_path_traversal_blocked(client):
    assert client.get("/api/photos/..%2F..%2Fsidequest.db").status_code == 404


def test_static_app_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Side Quest" in r.text


def test_tidy_enforces_time_limit_and_trims():
    card = quests.QuestCard.model_validate({**CARD, "turn_back": "When the shadows lengthen, head home.",
                                            "finds": [{"what": " Ripples ", "hint": "Watch  the water."}, *CARD["finds"][1:]]})
    out = quests.tidy(card, quests.QuestRequest(minutes=45))
    assert "45 minutes" in out.turn_back and out.finds[0].what == "Ripples" and out.finds[0].hint == "Watch the water."
