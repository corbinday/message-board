from datetime import datetime
from flask import Flask, g, make_response, render_template, request
from dotenv import load_dotenv
import gel
import json
import logging
import resend
import os
import secrets
import api.auth as auth
import api.user as user
import api.message as message

load_dotenv()
app = Flask(__name__, static_folder="../static", template_folder="../templates")
app.debug = True
app.logger.setLevel(logging.DEBUG)
resend.api_key = os.getenv("RESEND_API_KEY")
base_client = gel.create_client()

app.register_blueprint(auth.bp, url_prefix="/auth")
app.register_blueprint(user.bp, url_prefix="/user")
app.register_blueprint(message.bp, url_prefix="/message")


@app.before_request
def generate_nonce():
    g.nonce = secrets.token_urlsafe(16)


@app.before_request
def initialize_gel_client():
    """
    Attaches a client to g.client for the duration of the request.
    If an auth token is present, it configures the client to use it.
    """
    # 2. Retrieve the token from the cookie
    # Make sure this matches the key you used in response.set_cookie()
    auth_token = request.cookies.get("gel-auth-token")

    if auth_token:
        # 3. Create a lightweight "view" of the client with the auth global set.
        # This borrows a connection from base_client and applies the token.
        g.client = base_client.with_globals({"ext::auth::client_token": auth_token})
    else:
        # 4. Fallback: No auth token found.
        # This client acts with the default permissions (usually Admin/Superuser).
        # BE CAREFUL: Queries here might return data you expect to be hidden by Access Policies.
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
    pass


@app.route("/home")
def home():
    return render_template("home.html")


@app.route("/welcome")
def welcome():
    return render_template("user/welcome.html")


@app.route("/email-test")
def email_test():
    resend.Emails.send(
        {
            "from": "corbin@corbinday.com",
            "to": "flushed-artists.5w@icloud.com",
            "subject": "Pico Message Board",
            "html": "<p>Email sent from Pico Message Board!</p>",
        }
    )
    return render_template("email-sent.html")


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
