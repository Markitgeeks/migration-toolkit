import asyncio
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
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
from app.connectors import get_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crawl", tags=["crawl"])


# ── Background crawl task ──
async def _run_crawl(project_id: int):
    """Execute the crawl in the background and persist results to the DB."""
    async with async_session() as db:
        try:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                return

            # Mark as crawling
            project.status = "crawling"
            await db.commit()

            # Log start
            db.add(CrawlLog(
                project_id=project_id, url=project.source_url,
                status="ok", message="Crawl started",
            ))
            await db.commit()

            # Pick the right connector
            connector = get_connector(
                project.platform,
                store_url=project.source_url,
                api_key=project.api_key or "",
                api_secret=project.api_secret or "",
                access_token=project.access_token or "",
            )

            # Test connection first
            ok = await connector.test_connection()
            if not ok:
                project.status = "failed"
                db.add(CrawlLog(
                    project_id=project_id, url=project.source_url,
                    status="error", message="Connection test failed — site may be unreachable",
                ))
                await db.commit()
                return

            db.add(CrawlLog(
                project_id=project_id, url=project.source_url,
                status="ok", message="Connection test passed",
            ))
            await db.commit()

            # Fetch all data
            data = await connector.fetch_all()

            # ── Persist products + variants ──
            for p in data.get("products", []):
                product = Product(
                    project_id=project_id,
                    title=p.get("title", "Untitled"),
                    handle=p.get("handle"),
                    description_html=p.get("description_html"),
                    vendor=p.get("vendor"),
                    product_type=p.get("product_type"),
                    tags=p.get("tags"),
                    status=p.get("status"),
                    sku=p.get("sku"),
                    barcode=p.get("barcode"),
                    price=p.get("price"),
                    compare_at_price=p.get("compare_at_price"),
                    cost_per_item=p.get("cost_per_item"),
                    source_url=p.get("source_url"),
                    image_urls=p.get("image_urls"),
                    seo_title=p.get("seo_title"),
                    seo_description=p.get("seo_description"),
                )
                db.add(product)
                await db.flush()

                for v in p.get("variants", []):
                    db.add(Variant(
                        product_id=product.id,
                        project_id=project_id,
                        title=v.get("title"),
                        sku=v.get("sku"),
                        barcode=v.get("barcode"),
                        price=v.get("price"),
                        compare_at_price=v.get("compare_at_price"),
                        inventory_qty=v.get("inventory_qty"),
                        weight=v.get("weight"),
                        weight_unit=v.get("weight_unit"),
                        option1_name=v.get("option1_name"),
                        option1_value=v.get("option1_value"),
                        option2_name=v.get("option2_name"),
                        option2_value=v.get("option2_value"),
                        option3_name=v.get("option3_name"),
                        option3_value=v.get("option3_value"),
                        image_url=v.get("image_url"),
                        position=v.get("position"),
                    ))

            # ── Persist collections ──
            for c in data.get("collections", []):
                db.add(Collection(
                    project_id=project_id,
                    title=c.get("title", "Untitled"),
                    handle=c.get("handle"),
                    description_html=c.get("description_html"),
                    image_url=c.get("image_url"),
                    seo_title=c.get("seo_title"),
                    seo_description=c.get("seo_description"),
                    sort_order=c.get("sort_order"),
                    product_handles=c.get("product_handles"),
                ))

            # ── Persist pages ──
            for pg in data.get("pages", []):
                db.add(Page(
                    project_id=project_id,
                    title=pg.get("title", "Untitled"),
                    handle=pg.get("handle"),
                    body_html=pg.get("body_html"),
                    seo_title=pg.get("seo_title"),
                    seo_description=pg.get("seo_description"),
                    published=pg.get("published", True),
                    source_url=pg.get("source_url"),
                ))

            # ── Persist blog posts ──
            for b in data.get("blogs", []):
                db.add(BlogPost(
                    project_id=project_id,
                    blog_title=b.get("blog_title"),
                    title=b.get("title", "Untitled"),
                    handle=b.get("handle"),
                    author=b.get("author"),
                    body_html=b.get("body_html"),
                    tags=b.get("tags"),
                    featured_image=b.get("featured_image"),
                    seo_title=b.get("seo_title"),
                    seo_description=b.get("seo_description"),
                    published_at=None,
                    source_url=b.get("source_url"),
                ))

            await db.commit()

            # Count what we got
            counts = {
                "products": len(data.get("products", [])),
                "collections": len(data.get("collections", [])),
                "pages": len(data.get("pages", [])),
                "blogs": len(data.get("blogs", [])),
            }
            total = sum(counts.values())

            project.status = "completed"
            db.add(CrawlLog(
                project_id=project_id, url=project.source_url,
                status="ok",
                message=f"Crawl complete — {total} items extracted ({counts})",
            ))
            await db.commit()
            logger.info("Crawl %d complete: %s", project_id, counts)

        except Exception as exc:
            logger.error("Crawl %d failed: %s", project_id, exc)
            logger.error(traceback.format_exc())
            try:
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                if project:
                    project.status = "failed"
                db.add(CrawlLog(
                    project_id=project_id, url="",
                    status="error", message=str(exc)[:500],
                ))
                await db.commit()
            except Exception:
                pass


# ── Endpoints ──

@router.post("/{project_id}/start")
async def start_crawl(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Kick off a crawl for the given project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == "crawling":
        raise HTTPException(status_code=409, detail="Crawl already in progress")

    project.status = "crawling"
    await db.commit()

    background_tasks.add_task(_run_crawl, project_id)
    return {"status": "started", "project_id": project_id}


@router.get("/{project_id}/stats")
async def crawl_stats(project_id: int, db: AsyncSession = Depends(get_db)):
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
