import logging
import os
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Body
from fastapi.responses import JSONResponse
from werkzeug.security import check_password_hash
from ably import AblyRest

from api.dependencies import AuthenticatedClient, get_base_client
import api.queries as q
from api.command_schema import validate_command_envelope

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
        token_details = await ably.auth.request_token({
            "client_id": board_id,
            "capability": capability,
        })
        return JSONResponse({"token": token_details.token})
    except Exception as e:
        logger.error(f"Board Ably token error: {e}")
        raise HTTPException(status_code=500, detail="Token generation failed")


@router.post("/boards/{board_id}/inventory", name="ably.board_inventory")
async def board_inventory(
    request: Request,
    board_id: str,
    x_board_secret: str = Header(None, alias="X-Board-Secret"),
):
    """
    Receive board inventory snapshot from the device.
    The board posts its current file inventory so the web UI can display it.

    Expected payload:
    {
        "inbox_count": 5,
        "art_count": 3,
        "inbox_ids": ["uuid1", "uuid2", ...],
        "art_ids": ["uuid3", "uuid4", ...],
        "last_eviction": "uuid-of-evicted-item" | null
    }
    """
    if not x_board_secret:
        raise HTTPException(status_code=401, detail="Missing board secret")

    base_client = request.app.state.get_base_client()

    try:
        board = await q.selectBoardBySecretKey(base_client, board_id=UUID(board_id))
    except Exception:
        board = None

    if not board or not board.secret_key_hash:
        raise HTTPException(status_code=403, detail="Invalid board")

    if not check_password_hash(board.secret_key_hash, x_board_secret):
        raise HTTPException(status_code=403, detail="Invalid secret key")

    body = await request.json()

    # Publish inventory to the board's status channel so the web UI can pick it up
    try:
        ably = _get_ably_client()
        owner_id = str(board.owner_id)
        status_channel = ably.channels.get(f"status:{owner_id}")
        await status_channel.publish("board_inventory", {
            "board_id": board_id,
            "inbox_count": body.get("inbox_count", 0),
            "art_count": body.get("art_count", 0),
            "inbox_ids": body.get("inbox_ids", []),
            "art_ids": body.get("art_ids", []),
            "last_eviction": body.get("last_eviction"),
        })
    except Exception as e:
        logger.warning(f"Failed to publish inventory to Ably: {e}")

    return JSONResponse({"status": "ok"})


@router.post("/boards/{board_id}/settings", name="ably.board_settings")
async def board_device_settings(
    request: Request,
    board_id: str,
    x_board_secret: str = Header(None, alias="X-Board-Secret"),
):
    """
    Return current board settings for the device to apply on boot/sync.
    Board authenticates via secret key header.
    """
    if not x_board_secret:
        raise HTTPException(status_code=401, detail="Missing board secret")

    base_client = request.app.state.get_base_client()

    try:
        board = await q.selectBoardBySecretKey(base_client, board_id=UUID(board_id))
    except Exception:
        board = None

    if not board or not board.secret_key_hash:
        raise HTTPException(status_code=403, detail="Invalid board")

    if not check_password_hash(board.secret_key_hash, x_board_secret):
        raise HTTPException(status_code=403, detail="Invalid secret key")

    # Fetch full board settings including WiFi profiles
    try:
        if hasattr(q, "selectBoardSettingsForDevice"):
            settings = await q.selectBoardSettingsForDevice(
                base_client, board_id=UUID(board_id)
            )
        else:
            settings = None
    except Exception as e:
        logger.error(f"Error fetching board settings: {e}")
        settings = None

    if not settings:
        return JSONResponse({
            "display_mode": "inbox",
            "auto_rotate": False,
            "brightness": 0.5,
            "wifi_profiles": [],
        })

    # Build WiFi profiles list
    wifi_list = []
    if hasattr(settings, "wifi_profiles") and settings.wifi_profiles:
        for profile in settings.wifi_profiles:
            wifi_list.append({
                "ssid": profile.ssid,
                "password": profile.password,
                "priority": profile.priority,
            })

    display_mode_str = "inbox"
    if hasattr(settings, "display_mode") and settings.display_mode:
        dm = str(settings.display_mode)
        if "art" in dm.lower():
            display_mode_str = "art"

    return JSONResponse({
        "display_mode": display_mode_str,
        "auto_rotate": getattr(settings, "auto_rotate", False) or False,
        "brightness": getattr(settings, "brightness", 0.5) or 0.5,
        "wifi_profiles": wifi_list,
    })
