import base64
import hashlib
import os
import httpx
import secrets
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from api.dependencies import Client
from api.user import create_new_user

router = APIRouter()
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
GEL_AUTH_BASE_URL = os.getenv("GEL_AUTH_BASE_URL", "").rstrip("/")
GEL_AUTH_INTERNAL_URL = os.getenv("GEL_AUTH_INTERNAL_URL", "").rstrip("/") or None
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_use_cloudflare_rewrite() -> bool:
    """Decide whether auth URLs should use Cloudflare rewrite paths.

    - production/staging default to rewrite enabled.
    - USE_CLOUDFLARE_REWRITE can explicitly override in any environment.
    """
    explicit = os.getenv("USE_CLOUDFLARE_REWRITE")
    if explicit is not None:
        return _parse_bool(explicit)
    return ENVIRONMENT in {"production", "staging"}

COOKIE_OPTS = {
    "httponly": True,
    "secure": ENVIRONMENT in {"production", "staging"},
    "samesite": "lax",
    "path": "/",
}


def build_auth_url(path: str) -> str:
    """Build a browser-facing auth URL.

    In production/staging we rely on Cloudflare path rewrite, so
    the target path is simply /signin, /signup, etc.
    In local development, we use the full Gel extension path.
    """
    if should_use_cloudflare_rewrite():
        return f"{GEL_AUTH_BASE_URL}{path}"

    # Local Gel auth UI routes include the /ui/ segment.
    if path in {"/signin", "/signup"}:
        return f"{GEL_AUTH_BASE_URL}/db/main/ext/auth/ui{path}"

    return f"{GEL_AUTH_BASE_URL}/db/main/ext/auth{path}"


def build_internal_auth_url(path: str) -> str:
    """Build a server-to-server auth URL that bypasses Cloudflare.

    Uses the internal Railway network URL when available (production/staging),
    falling back to the same logic as build_auth_url for local development.
    """
    if GEL_AUTH_INTERNAL_URL:
        return f"{GEL_AUTH_INTERNAL_URL}/db/main/ext/auth{path}"

    return build_auth_url(path)


def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    challenge = hashlib.sha256(verifier.encode()).digest()
    challenge_base64 = base64.urlsafe_b64encode(challenge).decode("utf-8").rstrip("=")
    return verifier, challenge_base64


async def retrieve_auth_token(request: Request):
    """Exchange OAuth code for auth token."""
    # 1. Extract ?code
    code = request.query_params.get("code")
    if not code:
        error = request.query_params.get("error", "Unknown error")
        raise HTTPException(
            status_code=400,
            detail=f"OAuth callback is missing 'code'. OAuth provider responded with error: {error}",
        )

    # 2. Read PKCE verifier from cookie
    verifier = request.cookies.get("gel-pkce-verifier")
    if not verifier:
        raise HTTPException(
            status_code=400,
            detail="Could not find 'verifier' in the cookie store. "
            "Is this the same user agent/browser that started the authorization flow?",
        )

    # 3. Build the code exchange URL (server-to-server, bypass Cloudflare)
    code_exchange_url = build_internal_auth_url("/token")
    params = {"code": code, "verifier": verifier}

    # 4. Exchange code + verifier for auth_token (async HTTP)
    async with httpx.AsyncClient() as http_client:
        exchange_resp = await http_client.get(code_exchange_url, params=params)

    if not exchange_resp.is_success:
        raise HTTPException(
            status_code=400,
            detail=f"Error from the auth server: {exchange_resp.text}",
        )

    return exchange_resp.json()


def create_login_response(auth_token: str, redirect_url: str) -> RedirectResponse:
    """Create a redirect response with auth cookies set."""
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie("gel-auth-token", auth_token, **COOKIE_OPTS)
    response.delete_cookie("gel-pkce-verifier", path="/")
    response.delete_cookie("gel-auth-challenge", path="/")
    return response


@router.get("/ui/signup", name="auth.signup")
async def signup():
    verifier, challenge = generate_pkce()
    # Construct redirect URL for Gel auth UI signup
    redirect_url = f"{build_auth_url('/signup')}?challenge={challenge}"

    response = RedirectResponse(url=redirect_url, status_code=302)

    # Set HttpOnly cookie
    response.set_cookie("gel-pkce-verifier", verifier, **COOKIE_OPTS)

    # Set the challenge as a cookie for the gel auth ui on local email flows
    response.set_cookie("gel-auth-challenge", challenge, **COOKIE_OPTS)

    return response


@router.get("/callback/signup", name="auth.callback_signup")
async def callback_signup(request: Request, client: Client):
    logger.info("Handling SIGN-UP")
    data = await retrieve_auth_token(request)
    logger.info(data)
    auth_token = data.get("auth_token")

    # Update client with auth token for user creation
    if auth_token:
        client = client.with_globals({"ext::auth::client_token": auth_token})

    # Create new User
    try:
        await create_new_user(client, data)
    except Exception as e:
        error_message = str(e)
        templates = request.app.state.templates
        get_context = request.app.state.get_template_context
        context = get_context(request, message=error_message)
        return templates.TemplateResponse("error.html", context, status_code=401)

    # Redirect to welcome page
    return create_login_response(auth_token, "/app/")


@router.get("/ui/signin", name="auth.signin")
async def signin():
    verifier, challenge = generate_pkce()

    # Build redirect URL for Gel auth UI signin
    redirect_url = f"{build_auth_url('/signin')}?challenge={challenge}"

    response = RedirectResponse(url=redirect_url, status_code=302)

    # Set the PKCE verifier cookie
    response.set_cookie("gel-pkce-verifier", verifier, **COOKIE_OPTS)

    # Set the challenge as a cookie for the gel auth ui on local email flows
    response.set_cookie("gel-auth-challenge", challenge, **COOKIE_OPTS)

    return response


@router.get("/callback/signin", name="auth.callback_signin")
async def callback_signin(request: Request, client: Client):
    logger.info("Handling SIGN-IN")
    data = await retrieve_auth_token(request)
    logger.info(data)
    auth_token = data.get("auth_token")

    return create_login_response(auth_token, "/app/")
