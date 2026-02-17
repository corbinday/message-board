import base64
import struct
import logging
from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, Response, JSONResponse

from api.dependencies import Client, get_client
from api.utils.avatar import generate_default_avatar
import api.queries as q

router = APIRouter()
logger = logging.getLogger(__name__)


def get_templates(request: Request):
    return request.app.state.templates


def get_context(request: Request, **kwargs):
    return request.app.state.get_template_context(request, **kwargs)


@router.get("/username/new", response_class=HTMLResponse, name="user.check_username")
async def check_username(request: Request, username: str, client: Client):
    username = username.strip()
    templates = get_templates(request)

    if len(username) < 4:
        context = get_context(
            request,
            message="Username must be longer than 3 characters",
            status="error",
        )
        return templates.TemplateResponse("app/user/username-availability.html", context)
    elif await q.usernameExists(client, username=username):
        context = get_context(
            request,
            message=f"{username} is not available",
            status="error",
        )
        return templates.TemplateResponse("app/user/username-availability.html", context)
    else:
        context = get_context(
            request,
            message=f"{username} is available!",
            status="available",
        )
        return templates.TemplateResponse("app/user/username-availability.html", context)


@router.get("/avatar", response_class=HTMLResponse, name="user.avatar_get")
async def avatar_get(request: Request, client: Client):
    templates = get_templates(request)
    current_user = await q.selectGlobalUser(client)
    has_avatar = current_user.avatar is not None if current_user else False
    context = get_context(request, has_avatar=has_avatar, user=current_user)
    return templates.TemplateResponse("app/user/avatar.html", context)


@router.post("/avatar", name="user.avatar_post")
async def avatar_post(
    request: Request,
    client: Client,
    mode: str = Form(...),
    pixel_data: str = Form(None),
    avatar_file: UploadFile = File(None),
):
    templates = get_templates(request)

    try:
        if mode == "paint":
            # Paint mode: receive base64 PNG data (from canvas.toDataURL)
            base64_string = pixel_data
            if not base64_string:
                return JSONResponse({"error": "No pixel data received"}, status_code=400)

            # Remove data URL prefix if present (data:image/png;base64,...)
            if base64_string.startswith("data:image"):
                base64_string = base64_string.split(",", 1)[1]

            # Decode base64 to PNG bytes
            png_data = base64.b64decode(base64_string)

            # Validate PNG dimensions by reading IHDR chunk
            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                return JSONResponse({"error": "Invalid PNG format"}, status_code=400)

            # Read width and height from IHDR (bytes 16-23)
            width, height = struct.unpack(">II", png_data[16:24])
            if width != 16 or height != 16:
                return JSONResponse({"error": "Avatar must be exactly 16x16 pixels"}, status_code=400)

        elif mode == "upload":
            is_htmx = request.headers.get("HX-Request")

            # Upload mode: receive PNG file
            if not avatar_file:
                error_msg = "No file uploaded"
                if is_htmx:
                    return HTMLResponse(
                        f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-red\">{error_msg}</div>",
                    )
                return JSONResponse({"error": error_msg}, status_code=400)

            if avatar_file.filename == "":
                error_msg = "No file selected"
                if is_htmx:
                    return HTMLResponse(
                        f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-red\">{error_msg}</div>",
                    )
                return JSONResponse({"error": error_msg}, status_code=400)

            # Read PNG data
            png_data = await avatar_file.read()

            # Validate PNG format
            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                error_msg = "Invalid PNG format. Please upload a valid PNG file."
                if is_htmx:
                    return HTMLResponse(
                        f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-red\">{error_msg}</div>",
                    )
                return JSONResponse({"error": error_msg}, status_code=400)

            # Read width and height from IHDR (bytes 16-23)
            width, height = struct.unpack(">II", png_data[16:24])
            if width != 16 or height != 16:
                error_msg = f"Avatar must be exactly 16x16 pixels (uploaded image is {width}x{height})"
                if is_htmx:
                    return HTMLResponse(
                        f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-red\">{error_msg}</div>",
                    )
                return JSONResponse({"error": error_msg}, status_code=400)
        else:
            return JSONResponse({"error": "Invalid mode"}, status_code=400)

        # Create Avatar object
        try:
            user = await q.selectGlobalUser(client)
            if not user:
                return JSONResponse({"error": "User not found"}, status_code=401)

            # Insert new Avatar
            avatar_result = await q.insertAvatar(client, data=png_data)

            # Set as active avatar
            await q.updateGlobalUser(client, avatar_id=avatar_result.id)

            if request.headers.get("HX-Request"):
                response = HTMLResponse(
                    "<div class=\"font-['Press_Start_2P'] text-xs text-pico-green\">Avatar saved! Reloading...</div>",
                )
                response.headers["HX-Location"] = "/user/account/settings"
                return response

            response = Response(content="", status_code=204)
            response.headers["HX-Location"] = "/user/account/settings"
            return response

        except Exception as e:
            logger.error(f"Error creating avatar: {e}")
            if request.headers.get("HX-Request"):
                return HTMLResponse(
                    f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-red\">Error: {str(e)}</div>",
                )
            return JSONResponse({"error": str(e)}, status_code=500)

    except Exception as e:
        logger.error(f"Error saving avatar: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/avatar/paint", response_class=HTMLResponse, name="user.avatar_paint")
async def avatar_paint(request: Request):
    templates = get_templates(request)
    context = get_context(request, BOARD_WIDTH=16, BOARD_HEIGHT=16, avatar_mode=True)
    return templates.TemplateResponse("paint/canvas.html", context)


@router.get("/avatar/editor", response_class=HTMLResponse, name="user.avatar_editor")
async def avatar_editor(request: Request, client: Client):
    """HTMX endpoint to get avatar editor (16x16 only)."""
    templates = get_templates(request)
    user = await q.selectGlobalUser(client)
    has_avatar = user.avatar is not None if user else False
    context = get_context(request, user=user, initial_avatar=has_avatar)
    return templates.TemplateResponse("app/user/avatar_editor.html", context)


@router.post("/avatar/save", name="user.save_avatar")
async def save_avatar(
    request: Request,
    client: Client,
    pixel_data: str = Form(...),
):
    """Save avatar from pixel editor."""
    if not pixel_data:
        return JSONResponse({"error": "No pixel data received"}, status_code=400)

    try:
        # Decode Base64 to PNG bytes
        image_data = base64.b64decode(pixel_data)

        # Validate PNG format
        if not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return JSONResponse({"error": "Invalid PNG format"}, status_code=400)

        # Read width and height from IHDR (bytes 16-23)
        width, height = struct.unpack(">II", image_data[16:24])
        if width != 16 or height != 16:
            return JSONResponse({"error": "Avatar must be exactly 16x16 pixels"}, status_code=400)

        # Create Avatar object
        user = await q.selectGlobalUser(client)
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=401)

        # Insert new Avatar
        avatar_result = await q.insertAvatar(client, data=image_data)

        # Set as active avatar
        await q.updateGlobalUser(client, avatar_id=avatar_result.id)

        if request.headers.get("HX-Request"):
            return HTMLResponse(
                "<div class=\"font-['Press_Start_2P'] text-xs text-pico-green\">Avatar saved successfully!</div>",
                status_code=200,
            )

        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/user/account/settings"
        return response

    except Exception as e:
        logger.error(f"Error saving avatar: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/account/settings", response_class=HTMLResponse, name="user.account_settings")
async def account_settings(request: Request, client: Client):
    """Account settings page for updating avatar and username."""
    templates = get_templates(request)
    user = await q.selectGlobalUser(client)
    if not user:
        raise HTTPException(status_code=401)

    has_avatar = user.avatar is not None
    context = get_context(request, user=user, has_avatar=has_avatar)
    return templates.TemplateResponse("app/user/account-settings.html", context)


@router.post("/account/username", name="user.update_username")
async def update_username(
    request: Request,
    client: Client,
    username: str = Form(...),
):
    """Update user's username."""
    new_username = username.strip()

    if not new_username or len(new_username) < 4:
        return JSONResponse({"error": "Username must be at least 4 characters"}, status_code=400)

    # Check if username is taken
    if await q.usernameExists(client, username=new_username):
        return JSONResponse({"error": "Username already taken"}, status_code=400)

    try:
        user = await q.selectGlobalUser(client)
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=401)

        # Update username
        await q.updateGlobalUser(client, username=new_username)

        if request.headers.get("HX-Request"):
            return HTMLResponse(
                f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-green\">Username updated to {new_username}!</div>",
                status_code=200,
            )

        response = Response(content="", status_code=204)
        response.headers["HX-Location"] = "/user/account/settings"
        return response

    except Exception as e:
        logger.error(f"Error updating username: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/avatar/{user_id}", name="user.serve_avatar")
async def serve_avatar(user_id: str, client: Client):
    avatar_data = await q.selectUserAvatar(client, user_id=user_id)

    if avatar_data is None:
        # Return default avatar
        avatar_data = generate_default_avatar()

    return Response(
        content=avatar_data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
