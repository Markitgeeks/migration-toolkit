import os
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings, IS_VERCEL
from app.database import init_db

logger = logging.getLogger(__name__)

# ---- paths ----
# On Vercel the lambda runs from the project root, so try multiple strategies
_this_dir = Path(__file__).resolve().parent          # …/app/
_root_from_file = _this_dir.parent                    # …/
_root_from_cwd = Path.cwd()                           # fallback

def _find_dir(name: str) -> Path:
    """Find a project directory by name, trying several roots."""
    for root in [_root_from_file, _root_from_cwd, Path("/var/task")]:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    # ultimate fallback
    return _root_from_file / name

STATIC_DIR = _find_dir("static")
TEMPLATES_DIR = _find_dir("templates")

logger.info("STATIC_DIR=%s exists=%s", STATIC_DIR, STATIC_DIR.is_dir())
logger.info("TEMPLATES_DIR=%s exists=%s", TEMPLATES_DIR, TEMPLATES_DIR.is_dir())

# ---- app ----
_db_initialized = False

async def _ensure_db():
    global _db_initialized
    if not _db_initialized:
        await init_db()
        os.makedirs(settings.EXPORT_DIR, exist_ok=True)
        _db_initialized = True

if IS_VERCEL:
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

# ---- debug endpoint (remove later) ----
@app.get("/debug/paths")
async def debug_paths():
    return {
        "__file__": str(Path(__file__).resolve()),
        "cwd": str(Path.cwd()),
        "STATIC_DIR": str(STATIC_DIR),
        "static_exists": STATIC_DIR.is_dir(),
        "TEMPLATES_DIR": str(TEMPLATES_DIR),
        "templates_exists": TEMPLATES_DIR.is_dir(),
        "static_files": os.listdir(str(STATIC_DIR)) if STATIC_DIR.is_dir() else [],
        "IS_VERCEL": IS_VERCEL,
    }

# ---- root route ----
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
