from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
import gel
import logging
import resend
import os
import secrets

from api.routers import auth, user, message, app as app_routes
from api.dependencies import get_current_user, get_client, OptionalUser

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY")

# Global async Gel client - created at startup
base_client: gel.AsyncIOClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - create and close Gel client."""
    global base_client
    base_client = gel.create_async_client()
    yield
    await base_client.aclose()


app = FastAPI(lifespan=lifespan)

# Mount static files
static_folder = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_folder), name="static")

# Setup templates
templates_folder = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=templates_folder)


# Add custom template filters
def format_date(value):
    return value.strftime("%B %d, %Y")


def time_ago(value):
    if not value:
        return "Never"
    return value.strftime("%b %d, %I:%M %p")


templates.env.filters["format_date"] = format_date
templates.env.filters["time_ago"] = time_ago


# CSP Nonce Middleware
class CSPNonceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate nonce and store in request state
        request.state.nonce = secrets.token_urlsafe(16)

        response = await call_next(request)

        # Apply CSP header
        nonce = request.state.nonce
        csp_policy = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' ; "
            f"style-src 'self' 'nonce-{nonce}'; "
            "img-src 'self' blob: data: ;"
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp_policy
        return response


app.add_middleware(CSPNonceMiddleware)


# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(user.router, prefix="/user", tags=["user"])
app.include_router(message.router, prefix="/message", tags=["message"])
app.include_router(app_routes.router, prefix="/app", tags=["app"])


def get_base_client() -> gel.AsyncIOClient:
    """Dependency to get the base Gel client."""
    return base_client


# Helper to add common template context
def get_template_context(request: Request, **kwargs):
    """Build template context with common variables."""

    # Shim url_for to support Flask-style 'filename' param for static files
    def shimmed_url_for(name: str, **path_params):
        if name == "static" and "filename" in path_params:
            path_params["path"] = path_params.pop("filename")
        return request.url_for(name, **path_params)

    context = {
        "request": request,
        "nonce": getattr(request.state, "nonce", ""),
        "current_year": datetime.now().year,
        "url_for": shimmed_url_for,
    }
    context.update(kwargs)
    return context


# Make template context helper available to routers
app.state.get_template_context = get_template_context
app.state.templates = templates
app.state.get_base_client = get_base_client


@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(static_folder, "favicon", "favicon.ico")
    return FileResponse(favicon_path, media_type="image/vnd.microsoft.icon")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    context = get_template_context(request)
    return templates.TemplateResponse("index.html", context)


@app.get("/get-started")
async def get_started(user: OptionalUser = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/app/", status_code=302)
    return RedirectResponse(url="/auth/ui/signin", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=302)
    # Clear all cookies
    for cookie in request.cookies:
        response.delete_cookie(cookie, path="/")
    response.delete_cookie("gel-auth-challenge", path="/")
    return response


# Exception handlers
@app.exception_handler(400)
async def bad_request_handler(request: Request, exc: HTTPException):
    reason = getattr(exc, "detail", "Bad request!")
    context = get_template_context(request, error_code=400, reason=reason)
    return templates.TemplateResponse("error.html", context, status_code=400)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    context = get_template_context(request, error_code=404, reason="Page not found!")
    return templates.TemplateResponse("error.html", context, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    context = get_template_context(
        request, error_code=500, reason="Internal server error!"
    )
    return templates.TemplateResponse("error.html", context, status_code=500)
