import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    # --- startup ---
    await init_db()
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    yield
    # --- shutdown (nothing needed for now) ---


app = FastAPI(
    title="Shopify Migration Toolkit",
    version="1.0.0",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- static files & templates ---
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# --- routers ---
from app.routes.projects import router as projects_router  # noqa: E402
from app.routes.crawl import router as crawl_router  # noqa: E402
from app.routes.export import router as export_router  # noqa: E402

app.include_router(projects_router)
app.include_router(crawl_router)
app.include_router(export_router)


# --- root route ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
