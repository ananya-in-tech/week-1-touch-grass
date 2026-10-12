"""Side Quest: tiny outdoor quests from a local AI. The screen is the shortest part."""

import asyncio
import base64
import io
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from sidequest import ai, journal, quests, vision
from sidequest.config import ROOT, check_privacy, get_settings
from sidequest.db import DB, now_iso, parse_iso

log = logging.getLogger("sidequest")
_db: DB | None = None


def db() -> DB:
    global _db
    if _db is None:
        _db = DB(get_settings().db_path)
    return _db


def set_db(new: DB) -> None:
    global _db
    _db = new


async def _warm_up() -> None:
    """Load Gemma (and its vision encoder) before the first walk, not during it."""
    tiny = io.BytesIO()
    Image.new("RGB", (32, 32), (90, 140, 70)).save(tiny, "JPEG")
    try:
        await ai.chat([{"role": "user", "content": "ok", "images": [base64.b64encode(tiny.getvalue()).decode()]}], num_predict=1)
        log.info("Gemma warmed up")
    except ai.AiUnavailable as e:
        log.warning("Warm-up skipped: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    check_privacy(s)
    db()
    if s.ai_enabled and s.ai_warmup:
        asyncio.create_task(_warm_up())
    yield


app = FastAPI(title="Side Quest", version="0.1.0", lifespan=lifespan)


# --- models -----------------------------------------------------------------------------------

class BackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    screen_seconds: int = Field(ge=0, le=24 * 3600)


class FinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heard: str | None = Field(None, max_length=200)
    screen_seconds: int | None = Field(None, ge=0, le=24 * 3600)


def _public(q: dict) -> dict:
    started, returned = parse_iso(q["started_at"]), parse_iso(q["returned_at"])
    q["outside_seconds"] = int((returned - started).total_seconds()) if started and returned else None
    return q


def _get(qid: int) -> dict:
    q = db().quest(qid)
    if not q:
        raise HTTPException(404, "Quest not found")
    return q


# --- routes -----------------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"} | {"ai": await ai.health()}


@app.post("/api/quests", status_code=201)
async def new_quest(req: quests.QuestRequest):
    t = time.perf_counter()
    card, source, note = await quests.generate(req)
    db().log_ai("quest", int((time.perf_counter() - t) * 1000), source == "ai")
    qid = db().insert_quest(minutes=req.minutes, setting=req.setting, energy=req.energy, title=card.title,
                            intro=card.intro, finds=[f.model_dump() for f in card.finds], sit_spot=card.sit_spot,
                            turn_back=card.turn_back, source=source, safety_note=note)
    return _public(_get(qid))


@app.get("/api/quests")
def list_quests(status: str | None = None):
    return [_public(q) for q in db().quests(status)]


@app.get("/api/quests/{qid}")
def get_quest(qid: int):
    return _public(_get(qid))


@app.post("/api/quests/{qid}/start")
def start(qid: int):
    q = _get(qid)
    if q["status"] != "ready":
        raise HTTPException(409, "This quest has already started.")
    db().update_quest(qid, status="out", started_at=now_iso())
    return _public(_get(qid))


@app.post("/api/quests/{qid}/back")
def back(qid: int, body: BackRequest):
    q = _get(qid)
    if q["status"] != "out":
        raise HTTPException(409, "Start the quest before coming back from it.")
    db().update_quest(qid, status="back", returned_at=now_iso(), screen_seconds=body.screen_seconds)
    return _public(_get(qid))


@app.post("/api/quests/{qid}/finds/{idx}/photo")
async def add_photo(qid: int, idx: int, photo: UploadFile = File(...)):
    q = _get(qid)
    if q["status"] not in ("back", "done"):
        raise HTTPException(409, "Photos come after the walk. Tap “I'm back” first.")
    if not 0 <= idx < len(q["finds"]):
        raise HTTPException(404, "No such find")
    try:
        jpeg = vision.clean_photo(await photo.read())
    except vision.BadPhoto as e:
        raise HTTPException(422, str(e)) from e
    name = vision.save(jpeg, get_settings().photo_dir, f"q{qid}_f{idx}_{int(time.time())}.jpg")
    t = time.perf_counter()
    result = await vision.check(jpeg, q["finds"][idx]["what"])
    db().log_ai("photo", int((time.perf_counter() - t) * 1000), result is not None)
    db().upsert_photo(qid, idx, name, result.match if result else "unchecked", result.saw if result else None)
    return _public(_get(qid))


@app.post("/api/quests/{qid}/finish")
async def finish(qid: int, body: FinishRequest):
    q = _get(qid)
    if q["status"] not in ("back", "done"):
        raise HTTPException(409, "Finish the walk first.")
    fields = {"heard": body.heard.strip() if body.heard else None}
    if body.screen_seconds is not None:
        fields["screen_seconds"] = body.screen_seconds
    db().update_quest(qid, **fields)
    q = _public(_get(qid))
    facts = journal.facts_for(q, q["outside_seconds"] or 0)
    t = time.perf_counter()
    text, source, _ = await journal.write(facts)
    db().log_ai("journal", int((time.perf_counter() - t) * 1000), source == "ai")
    db().update_quest(qid, status="done", journal=text, journal_source=source)
    return _public(_get(qid))


@app.get("/api/stats")
def stats():
    return db().stats()


@app.get("/api/photos/{name}")
def photo(name: str):
    path = (get_settings().photo_dir / name).resolve()
    if path.parent != get_settings().photo_dir.resolve() or not path.is_file():
        raise HTTPException(404, "Photo not found")
    return FileResponse(path, media_type="image/jpeg")


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
