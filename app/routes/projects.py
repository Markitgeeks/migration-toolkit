from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "source_url": p.source_url,
            "platform": p.platform,
            "auth_type": p.auth_type,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in projects
    ]


@router.post("/", status_code=201)
async def create_project(data: dict, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=data["name"],
        source_url=data["source_url"],
        platform=data.get("platform", "custom"),
        auth_type=data.get("auth_type", "crawl"),
        api_key=data.get("api_key"),
        api_secret=data.get("api_secret"),
        access_token=data.get("access_token"),
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return {
        "id": project.id,
        "name": project.name,
        "source_url": project.source_url,
        "platform": project.platform,
        "status": project.status,
    }


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": project.id,
        "name": project.name,
        "source_url": project.source_url,
        "platform": project.platform,
        "auth_type": project.auth_type,
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
