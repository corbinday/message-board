from datetime import datetime
from flask import Flask, g, redirect, render_template, url_for, make_response, request
from flask_login import LoginManager, current_user, logout_user
from dotenv import load_dotenv
import gel
import logging
import resend
import os
import secrets
import api.blueprints.auth as auth
import api.blueprints.user as user
import api.blueprints.message as message
import api.blueprints.app as app_routes
from api.user import User

load_dotenv()
app = Flask(__name__, static_folder="../static", template_folder="../templates")
app.debug = True
app.logger.setLevel(logging.DEBUG)
resend.api_key = os.getenv("RESEND_API_KEY")
base_client = gel.create_client()

login_manager = LoginManager(app)


@login_manager.request_loader
def load_user_from_request(req):
    token = req.cookies.get("gel-auth-token")

    if token:
        # perform login
        return User(token)

    # unauthenticated user case
    return None


app.register_blueprint(auth.bp, url_prefix="/auth")
app.register_blueprint(user.bp, url_prefix="/user")
app.register_blueprint(message.bp, url_prefix="/message")
app.register_blueprint(app_routes.bp, url_prefix="/app")


@app.before_request
def generate_nonce():
    g.nonce = secrets.token_urlsafe(16)


@app.before_request
def initialize_gel_client():
    """
    Attaches a scoped Gel client to g.client.
    The request_loader has already validated the cookie by this point.
    """
    if current_user.is_authenticated:
        # current_user.id contains the token (see User class)
        g.client = base_client.with_globals(
            {"ext::auth::client_token": current_user.id}
        )
    else:
        # No token? Use the base client.
        # Ensure your Gel Access Policies handle NULL globals safely!
        g.client = base_client


@app.after_request
def close_gel_client(response):
    g.client.close()
    return response


@app.context_processor
def inject_nonce():
    if "nonce" not in g:
        g.nonce = generate_nonce()
    return {"nonce": g.nonce}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/get-started")
def get_started():
    if current_user.is_authenticated:
        return redirect(url_for("app.home"))

    # User is anonymous, send them to the sign-in/sign-up choice
    # You could also redirect straight to /ui/signin if you want to skip a step
    return redirect(url_for("auth.signin"))


@app.route("/logout")
def logout():
    # 1. Clear the Flask-Login session context
    logout_user()

    # 2. Prepare the redirect
    response = make_response(redirect(url_for("index")))

    # 3. Explicitly clear all auth-related cookies
    # We set expires to 0 to tell the browser to delete them immediately
    for cookie in request.cookies:
        response.set_cookie(cookie, "", expires=0, path="/")
    response.set_cookie("gel-auth-challenge", "", expires=0, path="/")

    return response


@app.route("/welcome")
def welcome():
    return render_template("user/welcome.html")


@app.after_request
def apply_csp(response):
    csp_policy = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{g.nonce}' ; "
        f"style-src 'self' 'nonce-{g.nonce}'; "
        "img-src 'self' https://gj6vlq8nqjtpg33c.public.blob.vercel-storage.com/; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers["Content-Security-Policy"] = csp_policy
    return response


@app.context_processor
def current_year():
    return {"current_year": datetime.now().year}


@app.template_filter("format_date")
def format_date(value):
    return value.strftime("%B %d, %Y")
