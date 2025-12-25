import requests
from flask import current_app, g, Blueprint, render_template, request

import api.queries as q

bp = Blueprint("user", __name__, template_folder="templates")


def create_new_user(data):
    # Determine the Auth Provider
    provider = q.selectGlobalIdentity(g.client).issuer
    if "github" in provider:
        # Get GitHub Emails
        provider_token = data.get("provider_token")
        emails = get_github_emails(provider_token)
        primary_email = next((e["email"] for e in emails if e.get("primary")), None)
        current_app.logger.info(primary_email)
        q.insertUserFromGitHubProvider(g.client, email=primary_email)
    elif provider == "local":
        # flushed-artists.5w@icloud.com
        current_app.logger.debug(f"provider: {provider}")
        q.inserUserFromLocalProvider(g.client)
    else:
        raise Exception("Unsupported Auth Provider!")


def get_github_emails(access_token: str):
    url = "https://api.github.com/user/emails"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # raise if bad token or missing scope
    return response.json()


@bp.route("/username/new", methods=["GET", "POST"])
def check_username():
    username = request.args.get("username").strip()
    if len(username) < 4:
        return render_template(
            "user/username-availability.html",
            message="Username must be longer than 3 characters",
            status="error",
        )
    elif q.usernameExists(g.client, username=username):
        return render_template(
            "user/username-availability.html",
            message=f"{username} is not available",
            status="error",
        )
    else:
        return render_template(
            "user/username-availability.html",
            message=f"{username} is available!",
            status="available",
        )
