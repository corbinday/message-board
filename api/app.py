from datetime import datetime
from flask import Flask, g, make_response, render_template, request
import gel
import json
import logging
import os
import secrets
import api.auth as auth


app = Flask(__name__, static_folder="../static", template_folder="../templates")
app.register_blueprint(auth.bp, url_prefix="/auth")
app.debug = True
app.logger.setLevel(logging.DEBUG)


@app.before_request
def generate_nonce():
    g.nonce = secrets.token_urlsafe(16)


@app.before_request
def initialize_gel_client():
    g.client = gel.create_client()


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

@app.route("/home")
def home():
    return render_template("home.html")

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")


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
