import base64
import struct
import secrets
import logging
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query, Header
from fastapi.responses import HTMLResponse, Response, JSONResponse
from werkzeug.security import generate_password_hash

from api.dependencies import (
    Client,
    RequiredUser,
    get_authenticated_client,
    AuthenticatedClient,
)
import api.queries as q
from api.queries import BoardType

router = APIRouter()
logger = logging.getLogger(__name__)


def get_templates(request: Request):
    return request.app.state.templates


def get_context(request: Request, **kwargs):
    return request.app.state.get_template_context(request, **kwargs)


def _get_public_api_url(request: Request) -> str:
    """Return the public-facing API base URL.

    In production on Railway, RAILWAY_PUBLIC_DOMAIN is set automatically
    (e.g. 'picomessageboard.com'). We use that with HTTPS.
    In development, fall back to request.base_url.
    """
    public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if public_domain:
        return f"https://{public_domain}"
    return str(request.base_url).rstrip("/")


# =============================================================================
# Home Routes
# =============================================================================


@router.get("/", response_class=HTMLResponse, name="app.home")
async def home(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    user = await q.selectGlobalUser(client)
    boards = await q.selectManyGlobalUserBoards(client)
    friends = await q.selectFriends(client) if hasattr(q, "selectFriends") else []
    friend_requests = (
        await q.selectFriendRequests(client)
        if hasattr(q, "selectFriendRequests")
        else []
    )
    drafts = await q.selectUserDrafts(client) if hasattr(q, "selectUserDrafts") else []

    # Fetch user's graphics (StaticImages and PixelAnimations)
    graphics = (
        await q.selectUserGraphics(client) if hasattr(q, "selectUserGraphics") else []
    )

    # Fetch user's most recent received messages
    messages = []
    try:
        if user and hasattr(q, "selectUserMessagesRecent"):
            messages = await q.selectUserMessagesRecent(client)
    except Exception as e:
        logger.error(f"Error loading messages: {e}")

    context = get_context(
        request,
        user=user,
        boards=boards,
        friends=friends,
        friend_requests=friend_requests,
        drafts=drafts or [],
        graphics=graphics or [],
        messages=messages or [],
    )
    return templates.TemplateResponse("app/index.html", context)


@router.get("/messages", response_class=HTMLResponse, name="app.messages_list")
async def messages_list(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    user = await q.selectGlobalUser(client)
    messages = []
    try:
        if user and hasattr(q, "selectUserMessages"):
            messages = await q.selectUserMessages(client)
    except Exception as e:
        logger.error(f"Error loading messages: {e}")

    context = get_context(request, messages=messages or [])
    return templates.TemplateResponse("app/messages/list.html", context)


@router.get("/create_art", response_class=HTMLResponse, name="app.create_art")
async def create_art(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    context = get_context(request)
    return templates.TemplateResponse("app/create-art.html", context)


# =============================================================================
# Board Routes
# =============================================================================


@router.get("/art", response_class=HTMLResponse, name="app.art_list")
async def art_list(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    graphics = (
        await q.selectUserGraphics(client) if hasattr(q, "selectUserGraphics") else []
    )

    context = get_context(request, graphics=graphics)
    return templates.TemplateResponse("app/art/list.html", context)


@router.get("/graphic/{graphic_id}/image", name="app.serve_graphic")
async def serve_graphic(graphic_id: str, client: AuthenticatedClient):
    """Serve the graphic image binary data."""
    try:
        # Re-using selectDraft-like query logic via a new query or just select PixelGraphic
        # Since we don't have selectPixelGraphic yet, we can't easily reuse.
        # But we can query PixelGraphic directly.
        # Actually, let's just create a quick query here using the client directly or add a new query file.
        # Adding a new query file 'selectPixelGraphic' is cleaner but for speed I'll add it to the file list later.
        # For now, let's assume we can fetch it.
        # Wait, I should add selectPixelGraphic.edgeql.

        # Let's use a raw query for this simple fetch if needed, or better, add the file.
        # I'll add selectPixelGraphic.edgeql in the next tool call.
        # For now, let's assume it exists or use inline query if possible (not with generated client easily).
        # Actually, I can use q.selectUserGraphics filtering in python but that's inefficient.

        # I will create selectPixelGraphic.edgeql
        graphic = await q.selectPixelGraphic(client, graphic_id=UUID(graphic_id))

        if not graphic:
            return Response(status_code=404)

        return Response(
            content=graphic.binary,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error(f"Error serving graphic {graphic_id}: {e}")
        return Response(status_code=500)


@router.get("/board/add", response_class=HTMLResponse, name="app.add_board")
async def add_board_get(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    context = get_context(request)
    return templates.TemplateResponse("app/board/add.html", context)


@router.post("/board/add", name="app.add_board_post")
async def add_board_post(
    request: Request,
    client: AuthenticatedClient,
    board_type: str = Query(...),
):
    """Handle POST to add a new board."""
    board_types = ["stellar", "galactic", "cosmic"]
    board_type_lower = board_type.lower()
    if board_type_lower not in board_types:
        raise HTTPException(
            status_code=400, detail=f"Invalid board type! Valid types: {board_types}"
        )

    # save the board in the database
    board = await q.insertBoard(client, board_type=board_type_lower.capitalize())

    # Trigger a new page load via HX-Location
    response = Response(content="", status_code=204)
    response.headers["HX-Location"] = f"/app/board/{board.id}"
    return response


@router.get("/board/{board_id}", response_class=HTMLResponse, name="app.board_details")
async def board_details(request: Request, board_id: str, client: AuthenticatedClient):
    templates = get_templates(request)
    board = await q.selectGlobalUserBoard(client, board_id=board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board does not exist!")
    context = get_context(request, board=board)
    return templates.TemplateResponse("app/board/details.html", context)


@router.post("/board/{board_id}/config", name="app.download_config")
async def download_config(
    request: Request,
    board_id: str,
    client: AuthenticatedClient,
    secret_key: str = Form(""),
    wifi_ssid: str = Form(""),
    wifi_password: str = Form(""),
):
    templates = get_templates(request)

    # Look up board and user info for SpaceOS config
    board = await q.selectGlobalUserBoard(client, board_id=board_id)
    user = await q.selectGlobalUser(client)

    # Determine board dimensions
    board_type_str = str(board.boardType.value) if board and hasattr(board.boardType, "value") else "Cosmic"
    size_map = {"Stellar": (16, 16), "Galactic": (53, 11), "Cosmic": (32, 32)}
    board_width, board_height = size_map.get(board_type_str, (32, 32))

    # Collect data from the form
    context = {
        "board_id": board_id,
        "secret_key": secret_key,
        "ssid": wifi_ssid,
        "password": wifi_password,
        # Use the public domain in production (Railway), fall back to request.base_url
        "api_url": _get_public_api_url(request),
        "user_id": str(user.id) if user else "",
        "board_type": board_type_str,
        "board_width": board_width,
        "board_height": board_height,
    }

    # Render the Python config file using the .j2 template
    try:
        file_content = templates.get_template("auth/secrets.py.j2").render(**context)

        return Response(
            content=file_content,
            media_type="text/x-python",
            headers={"Content-Disposition": "attachment; filename=secrets.py"},
        )
    except Exception as e:
        logger.error(f"Failed to generate config file: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get(
    "/board/{board_id}/status", response_class=HTMLResponse, name="app.board_status"
)
async def board_status(request: Request, board_id: str, client: AuthenticatedClient):
    templates = get_templates(request)
    board = await q.selectGlobalUserBoard(client, board_id=board_id)
    if not board:
        raise HTTPException(status_code=404)

    # Logic for activity state
    is_active = False
    if board.last_connected_at:
        # Check if last seen was within the last 5 minutes
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=5)
        is_active = board.last_connected_at > threshold

    context = get_context(request, board=board, is_active=is_active)
    return templates.TemplateResponse("app/board/status_indicator.html", context)


@router.get(
    "/board/{board_id}/name", response_class=HTMLResponse, name="app.get_board_name"
)
async def get_board_name(request: Request, board_id: str, client: AuthenticatedClient):
    """GET: Show the edit form."""
    templates = get_templates(request)
    board = await q.selectGlobalUserBoard(client, board_id=board_id)
    context = get_context(request, board=board)
    return templates.TemplateResponse("app/board/edit_name.html", context)


@router.patch(
    "/board/{board_id}/name", response_class=HTMLResponse, name="app.update_board_name"
)
async def update_board_name(
    request: Request,
    board_id: str,
    client: AuthenticatedClient,
    board_name: str = Form(...),
):
    """PATCH: Update the board name."""
    templates = get_templates(request)
    # Update DB
    board = await q.updateGlobalUserBoard(client, board_id=board_id, name=board_name)
    # Re-render the read-only partial
    context = get_context(request, board=board)
    return templates.TemplateResponse("app/board/_name_display.html", context)


@router.get(
    "/board/{board_id}/name-partial",
    response_class=HTMLResponse,
    name="app.name_partial",
)
async def name_partial(request: Request, board_id: str, client: AuthenticatedClient):
    """Helper for the 'Cancel' button to revert the UI."""
    templates = get_templates(request)
    board = await q.selectGlobalUserBoard(client, board_id=board_id)
    context = get_context(request, board=board)
    return templates.TemplateResponse("app/board/_name_display.html", context)


@router.delete("/board/{board_id}", name="app.delete_board")
async def delete_board(board_id: str, client: AuthenticatedClient):
    # Verify board exists and belongs to user
    board = await q.selectGlobalUserBoard(client, board_id=board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board does not exist!")

    # Delete the board
    await q.deleteGlobalUserBoard(client, board_id=board_id)

    # Redirect to home page
    response = Response(content="", status_code=204)
    response.headers["HX-Location"] = "/app/"
    return response


@router.post(
    "/board/{board_id}/register", response_class=HTMLResponse, name="app.register_board"
)
async def register_board(request: Request, board_id: str, client: AuthenticatedClient):
    templates = get_templates(request)
    # 1. Generate the raw 256-bit key
    raw_key = secrets.token_urlsafe(32)

    # 2. Salt and Hash it
    hashed_key = generate_password_hash(raw_key, method="scrypt")

    try:
        # 3. Update the board in Gel
        updated_board = await q.updateGlobalUserBoard(
            client, board_id=board_id, secret_key_hash=hashed_key
        )

        if not updated_board:
            raise HTTPException(status_code=404, detail="Board not found!")

        # 4. Return the one-time view
        context = get_context(request, raw_key=raw_key, board_id=board_id)
        return templates.TemplateResponse("app/board/key-details.html", context)

    except Exception as e:
        logger.error(f"Registration Error: {e}")
        # For HTMX, return a small error fragment instead of a full page
        return HTMLResponse(
            f'<div class="text-red-500 bg-red-900/20 p-4 rounded">Failed to generate key: {str(e)}</div>',
            status_code=400,
        )


# =============================================================================
# Friend Routes
# =============================================================================


@router.get("/friend/add", response_class=HTMLResponse, name="app.add_friend")
async def add_friend(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    # Get pending sent requests
    sent_requests = (
        await q.selectFriendRequestsSent(client)
        if hasattr(q, "selectFriendRequestsSent")
        else []
    )
    context = get_context(request, sent_requests=sent_requests)
    return templates.TemplateResponse("app/friend/add.html", context)


@router.post("/friend/search", response_class=HTMLResponse, name="app.search_users")
async def search_users(
    request: Request,
    client: AuthenticatedClient,
    username: str = Form(""),
):
    templates = get_templates(request)
    username = username.strip()
    if username == "":
        return HTMLResponse("""
        <p class="text-slate-500 text-xs text-center py-8">
        Start typing to search for users...
      </p>
        """)

    logger.info(f"Searching for users with query: {username}")

    users = await q.searchUserByUsername(client, username=username)
    if len(users) == 0:
        return HTMLResponse("""
        <p class="text-slate-500 text-xs text-center py-8">
        No users found.
      </p>
        """)

    context = get_context(request, users=users)
    return templates.TemplateResponse("app/friend/search-results.html", context)


@router.post(
    "/friend/request/send", response_class=HTMLResponse, name="app.send_friend_request"
)
async def send_friend_request(
    request: Request,
    client: AuthenticatedClient,
    recipient_id: str = Form(None),
):
    # 1. Get the ID from request.form (matching hx-vals)
    if not recipient_id:
        return HTMLResponse(
            '<span class="text-red-500">Missing ID</span>', status_code=400
        )

    try:
        # 2. Logic Check
        friends = await q.selectFriends(client)
        if any(str(f.friend.id) == recipient_id for f in friends):
            # Return HTML instead of JSON
            return HTMLResponse(
                '<span class="text-yellow-500 text-[8px]">Already Friends</span>'
            )

        # 3. Action
        await q.insertFriendRequest(client, recipient_id=recipient_id)

        # 4. Success UI
        return HTMLResponse(
            '<span class="text-pico-green text-[8px]">Request Sent!</span>'
        )

    except Exception as e:
        logger.error(f"Error sending friend request: {e}")
        # Return the error message as a string for HTMX to swap into the UI
        return HTMLResponse(
            f'<span class="text-red-500 text-[8px]">Error: {str(e)}</span>',
            status_code=400,
        )


@router.post("/friend/request/{request_id}/accept", name="app.accept_friend_request")
async def accept_friend_request(request_id: str, client: AuthenticatedClient):
    try:
        await q.acceptFriendRequest(client, request_id=request_id)
        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/app/"
        return response
    except Exception as e:
        logger.error(f"Error accepting friend request: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/friend/request/{request_id}/reject", name="app.reject_friend_request")
async def reject_friend_request(request_id: str, client: AuthenticatedClient):
    try:
        await q.rejectFriendRequest(client, request_id=request_id)
        return Response(content="", status_code=200)
    except Exception as e:
        logger.error(f"Error rejecting friend request: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.delete("/friend/request/{request_id}", name="app.delete_friend_request")
async def delete_friend_request(request_id: str, client: AuthenticatedClient):
    try:
        await q.deleteFriendRequest(client, request_id=request_id)
        return Response(content="", status_code=200)
    except Exception as e:
        logger.error(f"Error deleting friend request: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.delete("/friend/{friend_id}", name="app.delete_friend")
async def delete_friend(friend_id: str, client: AuthenticatedClient):
    try:
        await q.deleteFriend(client, friend_id=friend_id)
        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/app/"
        return response
    except Exception as e:
        logger.error(f"Error deleting friend: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


# =============================================================================
# Editor Routes
# =============================================================================


@router.get("/avatar/edit", response_class=HTMLResponse, name="app.avatar_edit")
async def avatar_edit(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    user = await q.selectGlobalUser(client)
    context = get_context(request, user=user)
    return templates.TemplateResponse("app/pixel/avatar-editor.html", context)


@router.get("/message/compose", response_class=HTMLResponse, name="app.message_compose")
async def message_compose(request: Request, client: AuthenticatedClient):
    templates = get_templates(request)
    friends = await q.selectFriends(client)
    friend_boards = {}
    for rel in friends:
        try:
            boards = await client.query(
                """
                select Board {
                  id,
                  name,
                  boardType
                }
                filter .owner.id = <uuid>$user_id
                order by .name
                """,
                user_id=rel.friend.id,
            )
            friend_boards[str(rel.friend.id)] = [
                {
                    "id": str(board.id),
                    "name": board.name,
                    "boardType": board.boardType.value
                    if hasattr(board.boardType, "value")
                    else str(board.boardType),
                }
                for board in boards
            ]
        except Exception as e:
            logger.error(f"Error loading boards for friend {rel.friend.id}: {e}")
            friend_boards[str(rel.friend.id)] = []

    context = get_context(request, friends=friends, friend_boards=friend_boards)
    return templates.TemplateResponse("app/pixel/message-composer.html", context)


@router.get("/art/create", response_class=HTMLResponse, name="app.art_create")
async def art_create(
    request: Request,
    client: AuthenticatedClient,
    draft_id: str = Query(None),
):
    templates = get_templates(request)

    initial_src = None
    editor_width = 32
    editor_height = 32

    if draft_id:
        try:
            draft = await q.selectDraft(client, draft_id=UUID(draft_id))
            if draft:
                b64 = base64.b64encode(draft.binary).decode("utf-8")
                initial_src = f"data:image/png;base64,{b64}"

                # Set dimensions based on draft size
                # Handle Enum or string representation
                size_str = str(draft.size)
                if hasattr(draft.size, "value"):
                    size_str = draft.size.value

                if size_str == "Stellar":
                    editor_width = 16
                    editor_height = 16
                elif size_str == "Galactic":
                    editor_width = 53
                    editor_height = 11
                # Cosmic is default 32x32

                frame_delay = draft.frame_delay_ms
        except Exception as e:
            logger.error(f"Error loading draft {draft_id}: {e}")
            pass

    context = get_context(
        request,
        draft_id=draft_id,
        initial_src=initial_src,
        editor_width=editor_width,
        editor_height=editor_height,
        # Pass the draft size string explicitly so the template can select the right button
        draft_size=size_str if "size_str" in locals() else "Cosmic",
        frame_delay=frame_delay if "frame_delay" in locals() else 100,
    )
    return templates.TemplateResponse("app/pixel/art-creator.html", context)


# =============================================================================
# Draft Routes
# =============================================================================


@router.get("/draft/{draft_id}/image", name="app.serve_draft")
async def serve_draft(draft_id: str, client: AuthenticatedClient):
    """Serve the draft image binary data."""
    try:
        draft = await q.selectDraft(client, draft_id=UUID(draft_id))
        if not draft:
            return Response(status_code=404)

        return Response(
            content=draft.binary,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=60"},
        )
    except Exception as e:
        logger.error(f"Error serving draft {draft_id}: {e}")
        return Response(status_code=500)


@router.post("/draft/save", name="app.save_draft")
async def save_draft(
    request: Request,
    client: AuthenticatedClient,
    pixel_data: str = Form(None),
    frames: str = Form("1"),
    frame_delay_ms: str = Form("100"),
    size: str = Form("Galactic"),
    board_id: str = Form(None),
    draft_id: str = Form(None),
):
    """Auto-save draft from pixel editor."""
    if not pixel_data:
        return Response(content="", status_code=204)  # No content to save

    try:
        # Decode Base64 to PNG bytes
        image_data = base64.b64decode(pixel_data)

        # Validate PNG format
        if not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return JSONResponse({"error": "Invalid PNG format"}, status_code=400)

        # Parse frame count and delay
        frame_count = int(frames)
        delay_ms = int(frame_delay_ms)

        # Clamp delay to valid range (10-2000ms per schema)
        delay_ms = max(10, min(2000, delay_ms))

        # Map size string to BoardType enum
        size_map = {"Stellar": "Stellar", "Galactic": "Galactic", "Cosmic": "Cosmic"}
        board_type = size_map.get(size, "Galactic")

        # Upsert the draft
        result = await q.upsertDraft(
            client,
            data=image_data,
            frames=frame_count,
            frame_delay_ms=delay_ms,
            size=BoardType(board_type),
            board_id=board_id if board_id else None,
            draft_id=UUID(draft_id) if draft_id else None,
        )

        # Return OOB swap to update draft_id input if it was new
        if result and str(result.id) != draft_id:
            response = HTMLResponse(
                f'<input type="hidden" id="draft-id" name="draft_id" value="{result.id}" hx-swap-oob="true" />',
                status_code=200,
            )
            response.headers["HX-Trigger"] = json.dumps(
                {"draft-saved": {"draftId": str(result.id)}}
            )
            current_url = request.headers.get("HX-Current-URL", "")
            if "/app/art/create" in current_url:
                # Update browser URL so refresh doesn't lose context
                response.headers["HX-Push-Url"] = f"/app/art/create?draft_id={result.id}"
            return response

        response = Response(content="", status_code=200)  # Success, no content needed
        if result and result.id:
            response.headers["HX-Trigger"] = json.dumps(
                {"draft-saved": {"draftId": str(result.id)}}
            )
        return response

    except Exception as e:
        logger.error(f"Error saving draft: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/draft/reset", name="app.reset_draft")
async def reset_draft(
    request: Request,
    client: AuthenticatedClient,
    size: str = Form("Galactic"),
    board_id: str = Form(None),
):
    """Reset/clear draft when size changes."""
    try:
        # Map size string to BoardType enum
        size_map = {"Stellar": "Stellar", "Galactic": "Galactic", "Cosmic": "Cosmic"}
        board_type = size_map.get(size, "Galactic")

        # Delete existing draft if any
        existing = await q.selectDraft(client, board_id=board_id if board_id else None)
        if existing:
            await q.deleteDraft(client, draft_id=existing.id)

        return Response(content="", status_code=204)  # Success, no content

    except Exception as e:
        logger.error(f"Error resetting draft: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/draft/finish", response_class=HTMLResponse, name="app.finish_draft")
async def finish_draft(
    request: Request, client: AuthenticatedClient, draft_id: str = Form(...)
):
    """Convert draft to final StaticImage or PixelAnimation."""
    try:
        # Finish the draft (converts to StaticImage or PixelAnimation)
        result = await q.finishDraft(client, draft_id=UUID(draft_id))

        if not result:
            return HTMLResponse(
                '<span class="text-red-500">Draft not found or already saved</span>',
                status_code=404,
            )

        if request.headers.get("HX-Request"):
            return HTMLResponse(
                '<span class="text-pico-green">Saved successfully!</span>'
            )

        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/app/"
        return response

    except Exception as e:
        logger.error(f"Error finishing draft: {e}")
        return HTMLResponse(
            f'<span class="text-red-500">Error: {str(e)}</span>', status_code=500
        )


@router.post("/message/send", response_class=HTMLResponse, name="app.send_message")
async def send_message(
    request: Request,
    client: AuthenticatedClient,
    recipient_id: str = Form(None),
    board_id: str = Form(None),
    draft_id: str = Form(None),
):
    """Send a message to a friend using the current draft."""
    if not recipient_id:
        return HTMLResponse(
            '<span class="text-red-500">No recipient selected</span>', status_code=400
        )

    try:
        # Get the user's current draft
        if draft_id:
            draft = await q.selectDraft(client, draft_id=UUID(draft_id))
        elif board_id:
            draft = await q.selectDraft(client, board_id=UUID(board_id))
        else:
            draft = await q.selectDraft(client, board_id=None)

        if not draft:
            return HTMLResponse(
                '<span class="text-red-500">No draft to send</span>', status_code=400
            )

        # Finish the draft and create message
        result = await q.finishDraft(client, draft_id=draft.id)
        graphic_id = result.graphic.id if result and result.graphic else None
        if not graphic_id:
            return HTMLResponse(
                '<span class="text-red-500">Failed to finalize draft</span>',
                status_code=500,
            )

        if hasattr(q, "insertMessageWithBoard"):
            message_result = await q.insertMessageWithBoard(
                client,
                graphic_id=graphic_id,
                recipient_id=UUID(recipient_id),
            )

            # Publish Ably command to notify recipient's boards
            try:
                ably_key = os.getenv("ABLY_API_KEY", "")
                if ably_key and message_result:
                    from ably import AblyRest

                    ably = AblyRest(ably_key)

                    # Determine dimensions from draft size
                    size_str = str(draft.size.value) if hasattr(draft.size, "value") else str(draft.size)
                    if size_str == "Stellar":
                        width, height = 16, 16
                    elif size_str == "Galactic":
                        width, height = 53, 11
                    else:
                        width, height = 32, 32

                    command_channel = ably.channels.get(f"commands:{recipient_id}")
                    await command_channel.publish("new_message", {
                        "messageId": str(message_result.id),
                        "width": width,
                        "height": height,
                        "frames": draft.frames,
                        "fps": round(1000 / draft.frame_delay_ms) if draft.frame_delay_ms > 0 else 10,
                    })
                    logger.info(f"Ably command published for message {message_result.id}")
            except Exception as ably_err:
                logger.warning(f"Ably command publish failed (non-fatal): {ably_err}")

        if request.headers.get("HX-Request"):
            response = HTMLResponse('<span class="text-pico-green">Message sent!</span>')
            response.headers["HX-Location"] = "/app/"
            return response

        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/app/"
        return response

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return HTMLResponse(
            f'<span class="text-red-500">Error: {str(e)}</span>', status_code=500
        )


@router.post(
    "/message/graphic/{graphic_id}/save",
    response_class=HTMLResponse,
    name="app.save_message_graphic",
)
async def save_message_graphic(
    request: Request, graphic_id: str, client: AuthenticatedClient
):
    """Save a received message graphic to the user's gallery."""
    try:
        if hasattr(q, "copyGraphicToGallery"):
            await q.copyGraphicToGallery(client, graphic_id=UUID(graphic_id))
        return HTMLResponse(
            '<span class="text-pico-green">Saved to gallery!</span>'
        )
    except Exception as e:
        logger.error(f"Error saving message graphic {graphic_id}: {e}")
        return HTMLResponse(
            f'<span class="text-red-500">Error: {str(e)}</span>', status_code=500
        )


@router.delete(
    "/draft/{draft_id}", response_class=HTMLResponse, name="app.delete_draft_route"
)
async def delete_draft_route(
    request: Request, draft_id: str, client: AuthenticatedClient
):
    """Delete a draft by ID."""
    try:
        await q.deleteDraft(client, draft_id=draft_id)

        # Always redirect to dashboard using HX-Location
        response = Response(content="", status_code=200)
        response.headers["HX-Location"] = "/app/"
        return response
    except Exception as e:
        logger.error(f"Error deleting draft: {e}")
        return HTMLResponse(
            f'<span class="text-red-500">Error: {str(e)}</span>', status_code=500
        )


@router.post(
    "/graphic/{graphic_id}/copy", response_class=HTMLResponse, name="app.copy_graphic"
)
async def copy_graphic(request: Request, graphic_id: str, client: AuthenticatedClient):
    """Copy a finished graphic to a new draft and open in editor."""
    try:
        # Use query from api.queries to create a draft from the graphic
        new_draft = await q.copyGraphicToDraft(client, graphic_id=UUID(graphic_id))

        # Redirect to the editor with the new draft ID
        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = f"/app/art/create?draft_id={new_draft.id}"
        return response
    except Exception as e:
        logger.error(f"Error copying graphic {graphic_id}: {e}")
        return HTMLResponse(
            f'<span class="text-red-500">Error: {str(e)}</span>', status_code=500
        )


@router.delete(
    "/graphic/{graphic_id}", response_class=HTMLResponse, name="app.delete_graphic"
)
async def delete_graphic(
    request: Request, graphic_id: str, client: AuthenticatedClient
):
    """Delete a finished pixel graphic by ID."""
    try:
        await q.deletePixelGraphic(client, graphic_id=graphic_id)
        if request.headers.get("HX-Request"):
            return Response(content="", status_code=200)
        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/app/"
        return response
    except Exception as e:
        logger.error(f"Error deleting graphic: {e}")
        return HTMLResponse(
            f'<span class="text-red-500">Error: {str(e)}</span>', status_code=500
        )


# =============================================================================
# Space Pack API (Board-facing)
# =============================================================================


@router.get("/space-pack/{message_id}", name="app.space_pack")
async def space_pack(
    request: Request,
    message_id: str,
    x_board_id: str = Header(None, alias="X-Board-Id"),
    x_board_secret: str = Header(None, alias="X-Board-Secret"),
):
    """
    Serve the Space Pack binary for a message.
    Authenticated via board secret key headers.

    SP binary format:
    | Offset | Field      | Size | Type   |
    | 0      | Magic "SP" | 2B   | Char   |
    | 2      | Message ID | 16B  | UUID   |
    | 18     | Meta Len   | 2B   | uint16 |
    | 20     | Pixel Len  | 4B   | uint32 |
    | 24     | Metadata   | Var  | JSON   |
    | End    | Pixel Data | Var  | RGB    |
    """
    # Authenticate the board
    if not x_board_id or not x_board_secret:
        raise HTTPException(status_code=401, detail="Missing board credentials")

    base_client = request.app.state.get_base_client()

    try:
        board = await q.selectBoardBySecretKey(base_client, board_id=UUID(x_board_id))
    except Exception:
        board = None

    if not board or not board.secret_key_hash:
        raise HTTPException(status_code=403, detail="Invalid board")

    from werkzeug.security import check_password_hash

    if not check_password_hash(board.secret_key_hash, x_board_secret):
        raise HTTPException(status_code=403, detail="Invalid secret key")

    # Fetch message data
    try:
        msg = await q.selectMessageForSpacePack(base_client, message_id=UUID(message_id))
    except Exception as e:
        logger.error(f"Space Pack query error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Build SP binary
    # Metadata JSON
    frames = msg.graphic_frames
    fps = round(1000 / msg.graphic_frame_delay_ms) if msg.graphic_frame_delay_ms > 0 else 10
    meta = json.dumps({
        "sender": msg.sender_username or "Unknown",
        "fps": fps,
        "is_anim": frames > 1,
    }).encode("utf-8")

    # Raw pixel data from PNG -> extract RGB888
    # The graphic binary is stored as PNG, we need to decode it to raw RGB
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(msg.graphic_binary))
    img = img.convert("RGB")

    # For animations (spritesheets), the full spritesheet is in the binary
    pixel_bytes = img.tobytes()

    # UUID as 16 raw bytes
    raw_uuid = UUID(message_id).bytes

    # Build the binary package
    meta_len = len(meta)
    pixel_len = len(pixel_bytes)

    sp_data = bytearray()
    sp_data.extend(b"SP")                              # Magic (2B)
    sp_data.extend(raw_uuid)                           # Message ID (16B)
    sp_data.extend(struct.pack(">H", meta_len))        # Meta length (2B, uint16 BE)
    sp_data.extend(struct.pack(">I", pixel_len))        # Pixel length (4B, uint32 BE)
    sp_data.extend(meta)                               # Metadata (variable)
    sp_data.extend(pixel_bytes)                        # Pixel data (variable)

    return Response(
        content=bytes(sp_data),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=sp-{message_id}.bin",
            "Cache-Control": "no-cache",
        },
    )


@router.get("/boards/{board_id}/sync", name="app.board_sync")
async def board_sync(
    request: Request,
    board_id: str,
    x_board_secret: str = Header(None, alias="X-Board-Secret"),
):
    """
    Return recent messages for a board's owner, filtered to the board's size.
    Used by SpaceOS at boot to sync missed messages.
    Authenticated via board secret key header.
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

    from werkzeug.security import check_password_hash

    if not check_password_hash(board.secret_key_hash, x_board_secret):
        raise HTTPException(status_code=403, detail="Invalid secret key")

    owner_id = board.owner_id
    board_size = str(board.boardType.value) if hasattr(board.boardType, "value") else str(board.boardType)

    # Determine board dimensions
    size_map = {"Stellar": (16, 16), "Galactic": (53, 11), "Cosmic": (32, 32)}
    board_width, board_height = size_map.get(board_size, (32, 32))

    # Query recent messages for this owner with matching graphic size
    try:
        messages = await base_client.query(
            """\
            select Message {
              id,
              graphic: {
                size,
                frames := [is PixelAnimation].frames ?? <int16>1,
                frame_delay_ms := [is PixelAnimation].frame_delay_ms ?? <int16>100
              }
            }
            filter .recipient.id = <uuid>$owner_id
               and .graphic.size = <BoardType>$board_size
            order by .sent_at desc
            limit 5\
            """,
            owner_id=owner_id,
            board_size=board_size,
        )
    except Exception as e:
        logger.error(f"Board sync query error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

    result = []
    for msg in messages:
        fps = round(1000 / msg.graphic.frame_delay_ms) if msg.graphic.frame_delay_ms > 0 else 10
        result.append({
            "messageId": str(msg.id),
            "width": board_width,
            "height": board_height,
            "frames": msg.graphic.frames,
            "fps": fps,
        })

    return JSONResponse({"messages": result})
