import base64
import hashlib
import os
import requests
import secrets
from dotenv import load_dotenv
from flask import (
    Blueprint,
    redirect,
    request,
    make_response,
    current_app,
    url_for,
    g,
    render_template,
)
from flask_login import login_user
from urllib.parse import urljoin
from api.user import create_new_user

bp = Blueprint("auth", __name__, template_folder="templates")

# Load environment variables
load_dotenv()
GEL_AUTH_BASE_URL = os.getenv("GEL_AUTH_BASE_URL").rstrip("/") + "/"
COOKIE_OPTS = {
    "httponly": True,
    "secure": False,
    "samesite": "Lax",
    "path": "/",
}


def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    challenge = hashlib.sha256(verifier.encode()).digest()
    challenge_base64 = base64.urlsafe_b64encode(challenge).decode("utf-8").rstrip("=")
    return verifier, challenge_base64


def retrieve_auth_token():
    # 1. Extract ?code
    code = request.args.get("code")
    if not code:
        error = request.args.get("error", "Unknown error")
        return (
            f"OAuth callback is missing 'code'. OAuth provider responded with error: {error}",
            400,
        )

    # 2. Read PKCE verifier from cookie
    verifier = request.cookies.get("gel-pkce-verifier")
    if not verifier:
        return (
            "Could not find 'verifier' in the cookie store. "
            "Is this the same user agent/browser that started the authorization flow?",
            400,
        )

    # 3. Build the code exchange URL
    code_exchange_url = urljoin(GEL_AUTH_BASE_URL, "token")
    params = {"code": code, "verifier": verifier}

    # 4. Exchange code + verifier for auth_token
    exchange_resp = requests.get(code_exchange_url, params=params)

    if not exchange_resp.ok:
        return (
            f"Error from the auth server: {exchange_resp.text}",
            400,
        )

    return exchange_resp.json()


def authenticate_gel_client(data):
    auth_token = data.get("auth_token")
    if auth_token:
        g.client = g.client.with_globals({"ext::auth::client_token": auth_token})


def login(auth_token, redirect_endpoint="home"):
    redirect_url = url_for(redirect_endpoint)
    response = make_response(redirect(redirect_url))
    response.set_cookie("gel-auth-token", auth_token, **COOKIE_OPTS)
    return response


@bp.route("/ui/signup")
def signup():
    verifier, challenge = generate_pkce()
    # Construct redirect URL: GEL_AUTH_BASE_URL + "ui/signup?challenge=..."
    redirect_url = urljoin(GEL_AUTH_BASE_URL, "ui/signup")
    redirect_url = f"{redirect_url}?challenge={challenge}"

    # Create response with redirect (301)
    response = make_response(redirect(redirect_url, code=301))

    # Set HttpOnly cookie
    response.set_cookie("gel-pkce-verifier", verifier, **COOKIE_OPTS)

    return response


@bp.route("/callback/signup")
def callback_signup():
    current_app.logger.info("Handling SIGN-UP")
    data = retrieve_auth_token()
    authenticate_gel_client(data)
    current_app.logger.info(data)
    auth_token = data.get("auth_token")

    # Create new User
    try:
        create_new_user(data)
    except Exception as e:
        error_message = str(e)
        return make_response(render_template("error.html", message=error_message), 401)

    # Set the auth token cookie
    return login(auth_token, redirect_endpoint="welcome")


@bp.route("/ui/signin")
def signin():
    verifier, challenge = generate_pkce()

    # Build redirect URL
    redirect_url = urljoin(GEL_AUTH_BASE_URL, "ui/signin")
    redirect_url = f"{redirect_url}?challenge={challenge}"

    # Create a 301 redirect response
    response = make_response(redirect(redirect_url, code=301))

    # Set the PKCE verifier cookie
    response.set_cookie("gel-pkce-verifier", verifier, **COOKIE_OPTS)

    return response


@bp.route("/callback/signin")
def callback_signin():
    current_app.logger.info("Handling SIGN-IN")
    data = retrieve_auth_token()
    authenticate_gel_client(data)
    current_app.logger.info(data)
    auth_token = data.get("auth_token")

    return login(auth_token, redirect_endpoint="home")
