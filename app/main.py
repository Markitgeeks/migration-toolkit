import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db

# ---- app ----
_db_initialized = False


async def _ensure_db():
    global _db_initialized
    if not _db_initialized:
        await init_db()
        os.makedirs(settings.EXPORT_DIR, exist_ok=True)
        _db_initialized = True


app = FastAPI(title="Shopify Migration Toolkit", version="1.0.0")

# ---- middleware ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def lazy_init_middleware(request: Request, call_next):
    await _ensure_db()
    return await call_next(request)


# ---- routers ----
from app.routes.projects import router as projects_router  # noqa: E402
from app.routes.crawl import router as crawl_router  # noqa: E402
from app.routes.export import router as export_router  # noqa: E402

app.include_router(projects_router)
app.include_router(crawl_router)
app.include_router(export_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
