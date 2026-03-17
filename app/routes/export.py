import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Project

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{project_id}/files")
async def list_exports(project_id: int, db: AsyncSession = Depends(get_db)):
    """List available export files for a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    export_dir = os.path.join(settings.EXPORT_DIR, str(project_id))
    if not os.path.isdir(export_dir):
        return {"project_id": project_id, "files": []}

    files = []
    for name in sorted(os.listdir(export_dir)):
        path = os.path.join(export_dir, name)
        if os.path.isfile(path):
            files.append({"name": name, "size": os.path.getsize(path)})

    return {"project_id": project_id, "files": files}


@router.get("/{project_id}/files/{filename}")
async def download_export(
    project_id: int, filename: str, db: AsyncSession = Depends(get_db)
):
    """Download a specific export file."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    filepath = os.path.join(settings.EXPORT_DIR, str(project_id), filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath, filename=filename)
