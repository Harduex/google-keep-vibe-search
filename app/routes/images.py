from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter(prefix="/api", tags=["images"])


@router.get("/image/{image_path:path}")
async def get_image(image_path: str):
    # Resolve both sides (this also follows symlinks) and require true
    # containment via Path.is_relative_to rather than a string prefix check,
    # which a sibling directory like "Keep_other" could satisfy while
    # escaping "Keep". Never echo the attempted path back in the response.
    base = Path(settings.google_keep_path).resolve()
    full_path = (base / image_path).resolve()
    if not full_path.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Invalid image path")
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(full_path)
