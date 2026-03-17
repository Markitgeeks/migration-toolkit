import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings, IS_VERCEL
from app.database import init_db

# ---- paths (absolute, works in both local & Vercel) ----
ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"

# ---- app factory ----
_db_initialized = False


async def _ensure_db():
    """Lazy DB init — called on first request (works on Vercel where lifespan is skipped)."""
    global _db_initialized
    if not _db_initialized:
        await init_db()
        os.makedirs(settings.EXPORT_DIR, exist_ok=True)
        _db_initialized = True


if IS_VERCEL:
    # Vercel doesn't fire ASGI lifespan events — skip it entirely
    app = FastAPI(title="Shopify Migration Toolkit", version="1.0.0")
else:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await _ensure_db()
        yield

    app = FastAPI(title="Shopify Migration Toolkit", version="1.0.0", lifespan=lifespan)

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
    """Ensure the database is initialized before handling any request."""
    await _ensure_db()
    return await call_next(request)


# ---- static files & templates ----
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---- routers ----
from app.routes.projects import router as projects_router  # noqa: E402
from app.routes.crawl import router as crawl_router  # noqa: E402
from app.routes.export import router as export_router  # noqa: E402

app.include_router(projects_router)
app.include_router(crawl_router)
app.include_router(export_router)


# ---- root route ----
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
