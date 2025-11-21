import requests
from flask import current_app


def create_new_user(data):
    # Determin the Auth Provider

    # Get GitHub Emails
    provider_token = data.get("provider_token")
    emails = get_github_emails(provider_token)
    primary_email = next((e["email"] for e in emails if e.get("primary")), None)
    current_app.logger.info(primary_email)


def get_github_emails(access_token: str):
    url = "https://api.github.com/user/emails"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # raise if bad token or missing scope
    return response.json()
