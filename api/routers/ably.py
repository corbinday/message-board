import logging
import os
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from werkzeug.security import check_password_hash
from ably import AblyRest

from api.dependencies import AuthenticatedClient, get_base_client
import api.queries as q

router = APIRouter()
logger = logging.getLogger(__name__)

ABLY_API_KEY = os.getenv("ABLY_API_KEY", "")


def _get_ably_client():
    """Get an Ably REST client instance."""
    if not ABLY_API_KEY:
        raise HTTPException(status_code=503, detail="Ably not configured")
    return AblyRest(ABLY_API_KEY)


@router.get("/token", name="ably.web_token")
async def web_token(request: Request, client: AuthenticatedClient):
    """
    Issue an Ably token for the authenticated web user.
    The token grants access to:
      - status:{userId} (presence + subscribe)
      - commands:{userId} (subscribe)
      - status:{friendUserId} channels (subscribe only, for friend presence)
    """
    ably = _get_ably_client()

    user = await q.selectGlobalUser(client)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    user_id = str(user.id)

    # Build capabilities: user can enter presence on their own status channel,
    # subscribe to their command channel, and subscribe to any status channel
    capability = {
        f"status:{user_id}": ["presence", "subscribe", "publish"],
        f"commands:{user_id}": ["subscribe"],
        "status:*": ["subscribe", "presence"],
    }

    try:
        token_request = await ably.auth.create_token_request({
            "client_id": user_id,
            "capability": capability,
        })
        return JSONResponse(token_request.to_dict())
    except Exception as e:
        logger.error(f"Ably token error: {e}")
        raise HTTPException(status_code=500, detail="Token generation failed")


@router.post("/boards/{board_id}/token", name="ably.board_token")
async def board_token(
    request: Request,
    board_id: str,
    x_board_secret: str = Header(None, alias="X-Board-Secret"),
):
    """
    Issue an Ably token for a board device.
    Authenticates via board secret key header.
    """
    if not x_board_secret:
        raise HTTPException(status_code=401, detail="Missing board secret")

    ably = _get_ably_client()

    # Get the base client (no user auth needed, we verify via secret key)
    base_client = request.app.state.get_base_client()

    # Look up the board and verify secret
    try:
        board = await q.selectBoardBySecretKey(base_client, board_id=UUID(board_id))
    except Exception:
        board = None

    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    if not board.secret_key_hash:
        raise HTTPException(status_code=403, detail="Board not registered")

    if not check_password_hash(board.secret_key_hash, x_board_secret):
        raise HTTPException(status_code=403, detail="Invalid secret key")

    owner_id = str(board.owner_id)

    # Board capabilities: publish/subscribe to its status channel,
    # subscribe to command channel
    capability = {
        f"status/{owner_id}/{board_id}": ["publish", "subscribe"],
        f"commands:{owner_id}": ["subscribe"],
    }

    try:
        token_request = await ably.auth.create_token_request({
            "client_id": board_id,
            "capability": capability,
        })
        return JSONResponse({"token": token_request.to_dict()})
    except Exception as e:
        logger.error(f"Board Ably token error: {e}")
        raise HTTPException(status_code=500, detail="Token generation failed")
