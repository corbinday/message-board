import requests
from flask import current_app, g
from flask_login import UserMixin

import api.queries as q


class User(UserMixin):
    """
    Simple user class for `flask_login`
    """

    def __init__(self, auth_token):
        self.id = auth_token


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
