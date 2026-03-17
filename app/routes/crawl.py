from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    CrawlLog,
    Product,
    Variant,
    Collection,
    Page,
    BlogPost,
    URLRecord,
    Project,
)

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


@router.get("/{project_id}/stats")
async def crawl_stats(project_id: int, db: AsyncSession = Depends(get_db)):
    """Return counts for every entity type belonging to the project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    counts = {}
    for label, model in [
        ("products", Product),
        ("variants", Variant),
        ("collections", Collection),
        ("pages", Page),
        ("blog_posts", BlogPost),
        ("urls", URLRecord),
    ]:
        row = await db.execute(
            select(func.count()).where(model.project_id == project_id)
        )
        counts[label] = row.scalar() or 0

    return {"project_id": project_id, "status": project.status, "counts": counts}


@router.get("/{project_id}/logs")
async def crawl_logs(
    project_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CrawlLog)
        .where(CrawlLog.project_id == project_id)
        .order_by(CrawlLog.timestamp.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "url": log.url,
            "status": log.status,
            "message": log.message,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        }
        for log in logs
    ]
