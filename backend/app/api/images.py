"""The picture files. Picture ids run in order, so each is served only through a session the asker may open."""

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import Db, Files, Me

router = APIRouter(prefix="/api")

PICTURE_NAME = re.compile(r"(\d+)\.png")


@router.get("/images/{name}")
def get_image(name: str, db: Db, files: Files, me: Me) -> FileResponse:
    match = PICTURE_NAME.fullmatch(name)
    if match is None or not db.shares.can_see_picture(me, int(match[1])):
        raise HTTPException(status_code=404, detail="picture not found")
    path = files.path(int(match[1]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="picture not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
