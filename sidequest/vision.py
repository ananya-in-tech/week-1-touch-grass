"""Photo checks with Gemma's vision, entirely on this computer.

Photos are re-encoded before anything else happens: EXIF (including GPS location) is dropped,
and they're shrunk to 768px so CPU inference stays fast.
"""

import base64
import io
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sidequest import ai

MAX_SIDE = 768
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class PhotoCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: Literal["yes", "maybe", "no"]
    saw: str = Field(min_length=2, max_length=140)


class BadPhoto(Exception):
    pass


def clean_photo(raw: bytes) -> bytes:
    """Decode, fix rotation, strip all metadata, resize, re-encode as JPEG."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise BadPhoto("That photo is too large (max 15 MB).")
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise BadPhoto("That file isn't a photo Side Quest can read.") from e
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    clean = Image.new("RGB", img.size)
    clean.paste(img)  # fresh image: no EXIF, no GPS, no camera serials
    clean.save(out, "JPEG", quality=85)
    return out.getvalue()


PROMPT = """Someone is on an outdoor quest. They were asked to find: "{what}".
Look at the photo and answer as JSON.
- match: "yes" if the photo clearly shows it, "maybe" if it partly or possibly does, "no" if it doesn't.
- saw: what is actually visible, in under 15 words. Describe, don't guess species or facts you can't see.
Be generous with "maybe": the point is that they went outside and looked."""


async def check(jpeg: bytes, what: str) -> PhotoCheck | None:
    """None when the model is unavailable or answers badly; the photo is still saved."""
    try:
        reply = await ai.chat(
            [{"role": "user", "content": PROMPT.format(what=what), "images": [base64.b64encode(jpeg).decode()]}],
            schema=PhotoCheck.model_json_schema(), num_predict=80,
        )
        return PhotoCheck.model_validate_json(reply.content)
    except (ai.AiUnavailable, ValidationError):
        return None


def save(jpeg: bytes, folder: Path, name: str) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(jpeg)
    return name
