import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter(prefix="/api", tags=["images"])


@router.get("/image/{image_path:path}")
async def get_image(image_path: str):
    base = os.path.normpath(settings.google_keep_path)
    full_path = os.path.normpath(os.path.join(base, image_path))
    if not full_path.startswith(base):
        raise HTTPException(status_code=400, detail="Invalid image path")
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(full_path)
