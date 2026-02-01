import httpx
import logging
import gel

import api.queries as q

logger = logging.getLogger(__name__)


class User:
    """
    Simple user class for authentication.
    Replaces Flask-Login's UserMixin.
    """

    def __init__(self, auth_token: str):
        self.id = auth_token
        self.is_authenticated = True


async def create_new_user(client: gel.AsyncIOClient, data: dict):
    """Create a new user based on the auth provider."""
    # Determine the Auth Provider
    identity = await q.selectGlobalIdentity(client)
    provider = identity.issuer

    if "github" in provider:
        # Get GitHub Emails
        provider_token = data.get("provider_token")
        emails = await get_github_emails(provider_token)
        primary_email = next((e["email"] for e in emails if e.get("primary")), None)
        logger.info(primary_email)
        await q.insertUserFromGitHubProvider(client, email=primary_email)
    elif provider == "local":
        logger.debug(f"provider: {provider}")
        await q.inserUserFromLocalProvider(client)
    else:
        raise Exception("Unsupported Auth Provider!")


async def get_github_emails(access_token: str):
    """Fetch user emails from GitHub API."""
    url = "https://api.github.com/user/emails"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient() as http_client:
        response = await http_client.get(url, headers=headers)
        response.raise_for_status()  # raise if bad token or missing scope
        return response.json()
