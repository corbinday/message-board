from flask import (
    g,
    Blueprint,
    Response,
    render_template,
    render_template_string,
    request,
    abort,
    make_response,
    url_for,
    current_app,
    jsonify,
)
from flask_login import login_required
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
import secrets
import api.queries as q

bp = Blueprint("app", __name__, template_folder="templates")


@bp.before_request
@login_required
def require_login():
    # This function body can be empty.
    # The @login_required decorator handles the redirect.
    pass


@bp.route("/")
def home():
    user = q.selectGlobalUser(g.client)
    boards = q.selectManyGlobalUserBoards(g.client)
    friends = q.selectFriends(g.client) if hasattr(q, "selectFriends") else []
    friend_requests = (
        q.selectFriendRequests(g.client) if hasattr(q, "selectFriendRequests") else []
    )
    drafts = q.selectUserDrafts(g.client) if hasattr(q, "selectUserDrafts") else []

    # Fetch user's graphics (StaticImages and PixelAnimations)
    graphics = []

    # Fetch user's messages (sent and received)
    messages = []
    return render_template(
        "app/index.html",
        user=user,
        boards=boards,
        friends=friends,
        friend_requests=friend_requests,
        drafts=drafts or [],
        graphics=graphics or [],
        messages=messages or [],
    )


@bp.route("/create_art")
def create_art():
    return render_template("app/create-art.html")


# =============================================================================
# Board Routes
# =============================================================================


@bp.route("/board/add", methods=["GET", "POST"])
def add_board():
    if request.method == "GET":
        return render_template("app/board/add.html")

    """ Handle POST """
    # determine the size of the board
    board_types = ["stellar", "galactic", "cosmic"]
    board_type = request.args.get("board_type").lower()
    if board_type not in board_types:
        abort(400, description=f"Invalid board type! Valid types: {board_type}")

    # save the board in the database
    board = q.insertBoard(g.client, board_type=board_type.capitalize())

    # 3. Trigger a new page load
    # We return a response with the 'HX-Location' header.
    # HTMX will see this and perform a full client-side redirect.
    response = make_response("", 204)  # 204 No Content is efficient here
    response.headers["HX-Location"] = url_for("app.board_details", board_id=board.id)
    return response


@bp.route("/board/<board_id>")
def board_details(board_id):
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    if not board:
        abort(404, description="Board does not exist!")
    return render_template("app/board/details.html", board=board)


@bp.route("/board/<board_id>/config", methods=["POST"])
def download_config(board_id):
    # 1. Collect data from the form
    # We grab the secret_key that the JS injected into the hidden field
    context = {
        "board_id": board_id,
        "secret_key": request.form.get("secret_key", ""),
        "ssid": request.form.get("wifi_ssid", ""),
        "password": request.form.get("wifi_password", ""),
        # request.host_url includes the protocol and domain (e.g., http://localhost:5000/)
        "api_url": request.host_url.rstrip("/") + "/api/log",
    }

    # 2. Render the Python config file using your .j2 template
    try:
        file_content = render_template("auth/secrets.py.j2", **context)

        # 3. Create the response object with specific headers for file download
        return Response(
            file_content,
            mimetype="text/x-python",
            headers={"Content-Disposition": "attachment; filename=secrets.py"},
        )
    except Exception as e:
        current_app.logger.error(f"Failed to generate config file: {e}")
        # If something breaks, we return a 500
        return "Internal Server Error", 500


@bp.route("/board/<board_id>/status")
def board_status(board_id):
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    if not board:
        abort(404)

    # Logic for activity state
    is_active = False
    if board.last_connected_at:
        # Check if last seen was within the last 5 minutes
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=5)
        is_active = board.last_connected_at > threshold

    return render_template(
        "app/board/status_indicator.html", board=board, is_active=is_active
    )


@bp.route("/board/<board_id>/name", methods=["GET", "PATCH"])
def update_board_name(board_id):
    if request.method == "PATCH":
        new_name = request.form.get("board_name")
        # Update DB
        board = q.updateGlobalUserBoard(g.client, board_id=board_id, name=new_name)
        # Re-render the read-only partial
        return render_template("app/board/_name_display.html", board=board)

    # GET: Show the edit form
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    return render_template("app/board/edit_name.html", board=board)


@bp.route("/board/<board_id>/name-partial")
def name_partial(board_id):
    # Helper for the 'Cancel' button to revert the UI
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    return render_template("app/board/_name_display.html", board=board)


@bp.route("/board/<board_id>", methods=["DELETE"])
def delete_board(board_id):
    # Verify board exists and belongs to user
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    if not board:
        abort(404, description="Board does not exist!")

    # Delete the board
    q.deleteGlobalUserBoard(g.client, board_id=board_id)

    # Redirect to home page
    response = make_response("", 204)
    response.headers["HX-Location"] = url_for("app.home")
    return response


@bp.route("/board/<board_id>/register", methods=["POST"])
def register_board(board_id):
    # 1. Generate the raw 256-bit key
    raw_key = secrets.token_urlsafe(32)

    # 2. Salt and Hash it
    hashed_key = generate_password_hash(raw_key, method="scrypt")

    try:
        # 3. Update the board in Gel
        # We use a 'select' inside the update to ensure the global user owns it
        updated_board = q.updateGlobalUserBoard(
            g.client, board_id=board_id, secret_key_hash=hashed_key
        )

        if not updated_board:
            abort(404, description="Board not found!")

        # 4. Return the one-time view
        return render_template(
            "app/board/key-details.html", raw_key=raw_key, board_id=board_id
        )

    except Exception as e:
        current_app.logger.error(f"Registration Error: {e}")
        # For HTMX, return a small error fragment instead of a full page
        return (
            f'<div class="text-red-500 bg-red-900/20 p-4 rounded">Failed to generate key: {str(e)}</div>',
            400,
        )


# =============================================================================
# Friend Routes
# =============================================================================


@bp.route("/friend/add", methods=["GET"])
def add_friend():
    # Get pending sent requests
    sent_requests = (
        q.selectFriendRequestsSent(g.client)
        if hasattr(q, "selectFriendRequestsSent")
        else []
    )
    return render_template("app/friend/add.html", sent_requests=sent_requests)


@bp.route("/friend/search", methods=["POST"])
def search_users():
    username = request.form.get("username", "").strip()
    if username == "":
        return render_template_string("""
        <p class="text-slate-500 text-xs text-center py-8">
        Start typing to search for users...
      </p>
        """)
    current_app.logger.info(f"Searching for users with query: {username}")

    users = q.searchUserByUsername(g.client, username=username)
    if len(users) == 0:
        return render_template_string("""
        <p class="text-slate-500 text-xs text-center py-8">
        No users found.
      </p>
        """)
    return render_template("app/friend/search-results.html", users=users)


@bp.route("/friend/request/send", methods=["POST"])
def send_friend_request():
    # 1. Get the ID from request.form (matching hx-vals)
    recipient_id = request.form.get("recipient_id")

    if not recipient_id:
        return '<span class="text-red-500">Missing ID</span>', 400

    try:
        # 2. Logic Check
        friends = q.selectFriends(g.client)
        if any(str(f.friend.id) == recipient_id for f in friends):
            # Return HTML instead of JSON
            return '<span class="text-yellow-500 text-[8px]">Already Friends</span>'

        # 3. Action
        q.insertFriendRequest(g.client, recipient_id=recipient_id)

        # 4. Success UI
        return '<span class="text-pico-green text-[8px]">Request Sent!</span>'

    except Exception as e:
        current_app.logger.error(f"Error sending friend request: {e}")
        # Return the error message as a string for HTMX to swap into the UI
        return f'<span class="text-red-500 text-[8px]">Error: {str(e)}</span>', 400


@bp.route("/friend/request/<request_id>/accept", methods=["POST"])
def accept_friend_request(request_id):
    try:
        q.acceptFriendRequest(g.client, request_id=request_id)
        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response
    except Exception as e:
        current_app.logger.error(f"Error accepting friend request: {e}")
        abort(400, description=str(e))


@bp.route("/friend/request/<request_id>/reject", methods=["POST"])
def reject_friend_request(request_id):
    try:
        q.rejectFriendRequest(g.client, request_id=request_id)
        return "", 200
    except Exception as e:
        current_app.logger.error(f"Error rejecting friend request: {e}")
        return jsonify({"error": str(e)}), 400


@bp.route("/friend/request/<request_id>", methods=["DELETE"])
def delete_friend_request(request_id):
    try:
        q.deleteFriendRequest(g.client, request_id=request_id)
        return "", 200
    except Exception as e:
        current_app.logger.error(f"Error deleting friend request: {e}")
        return jsonify({"error": str(e)}), 400


@bp.route("/friend/<friend_id>", methods=["DELETE"])
def delete_friend(friend_id):
    try:
        q.deleteFriend(g.client, friend_id=friend_id)
        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response
    except Exception as e:
        current_app.logger.error(f"Error deleting friend: {e}")
        return jsonify({"error": str(e)}), 400


# =============================================================================
# Editor Routes
# =============================================================================


@bp.route("/avatar/edit")
def avatar_edit():
    user = q.selectGlobalUser(g.client)
    return render_template("app/pixel/avatar-editor.html", user=user)


@bp.route("/message/compose")
def message_compose():
    friends = q.selectFriends(g.client)
    return render_template("app/pixel/message-composer.html", friends=friends)


@bp.route("/art/create")
def art_create():
    draft_id = request.args.get("draft_id")
    return render_template("app/pixel/art-creator.html", draft_id=draft_id)


# =============================================================================
# Draft Routes
# =============================================================================


@bp.route("/draft/save", methods=["POST"])
def save_draft():
    """Auto-save draft from pixel editor."""
    import base64
    import struct

    b64_data = request.form.get("pixel_data")
    frames = request.form.get("frames", "1")
    frame_delay_ms = request.form.get("frame_delay_ms", "100")
    size = request.form.get("size", "Galactic")
    board_id = request.form.get("board_id")  # Optional

    if not b64_data:
        return "", 204  # No content to save, just return success

    try:
        # Decode Base64 to PNG bytes
        image_data = base64.b64decode(b64_data)

        # Validate PNG format
        if not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "Invalid PNG format"}), 400

        # Parse frame count and delay
        frame_count = int(frames)
        delay_ms = int(frame_delay_ms)

        # Clamp delay to valid range (10-2000ms per schema)
        delay_ms = max(10, min(2000, delay_ms))

        # Map size string to BoardType enum
        size_map = {"Stellar": "Stellar", "Galactic": "Galactic", "Cosmic": "Cosmic"}
        board_type = size_map.get(size, "Galactic")

        # Upsert the draft
        from api.queries import BoardType

        result = q.upsertDraft(
            g.client,
            data=image_data,
            frames=frame_count,
            frame_delay_ms=delay_ms,
            size=BoardType(board_type),
            board_id=board_id if board_id else None,
        )

        return "", 204  # Success, no content needed

    except Exception as e:
        current_app.logger.error(f"Error saving draft: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/draft/reset", methods=["POST"])
def reset_draft():
    """Reset/clear draft when size changes."""
    size = request.form.get("size", "Galactic")
    board_id = request.form.get("board_id")

    try:
        # Map size string to BoardType enum
        size_map = {"Stellar": "Stellar", "Galactic": "Galactic", "Cosmic": "Cosmic"}
        board_type = size_map.get(size, "Galactic")

        from api.queries import BoardType

        # Delete existing draft if any
        existing = q.selectDraft(g.client, board_id=board_id if board_id else None)
        if existing:
            q.deleteDraft(g.client, draft_id=existing.id)

        return "", 204  # Success, no content

    except Exception as e:
        current_app.logger.error(f"Error resetting draft: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/draft/finish", methods=["POST"])
def finish_draft():
    """Convert draft to final StaticImage or PixelAnimation."""
    try:
        # Get the user's current draft
        draft = q.selectDraft(g.client, board_id=None)

        if not draft:
            return (
                '<span class="text-red-500">No draft to save</span>',
                400,
            )

        # Finish the draft (converts to StaticImage or PixelAnimation)
        q.finishDraft(g.client, draft_id=draft.id)

        if request.headers.get("HX-Request"):
            return '<span class="text-pico-green">Saved successfully!</span>'

        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response

    except Exception as e:
        current_app.logger.error(f"Error finishing draft: {e}")
        return f'<span class="text-red-500">Error: {str(e)}</span>', 500


@bp.route("/message/send", methods=["POST"])
def send_message():
    """Send a message to a friend using the current draft."""
    recipient_id = request.form.get("recipient_id")

    if not recipient_id:
        return '<span class="text-red-500">No recipient selected</span>', 400

    try:
        # Get the user's current draft
        draft = q.selectDraft(g.client, board_id=None)

        if not draft:
            return '<span class="text-red-500">No draft to send</span>', 400

        # Finish the draft and create message
        result = q.finishDraft(g.client, draft_id=draft.id)

        # Create the message linking to the new graphic
        from uuid import UUID

        q.insertMessage(
            g.client,
            data=draft.binary,
            size=draft.size,
            recipient_id=UUID(recipient_id),
        )

        if request.headers.get("HX-Request"):
            return '<span class="text-pico-green">Message sent!</span>'

        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response

    except Exception as e:
        current_app.logger.error(f"Error sending message: {e}")
        return f'<span class="text-red-500">Error: {str(e)}</span>', 500


@bp.route("/draft/<draft_id>", methods=["DELETE"])
def delete_draft_route(draft_id):
    """Delete a draft by ID."""
    try:
        q.deleteDraft(g.client, draft_id=draft_id)
        if request.headers.get("HX-Request"):
            return "", 200
        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response
    except Exception as e:
        current_app.logger.error(f"Error deleting draft: {e}")
        return f'<span class="text-red-500">Error: {str(e)}</span>', 500


@bp.route("/graphic/<graphic_id>", methods=["DELETE"])
def delete_graphic(graphic_id):
    """Delete a finished pixel graphic by ID."""
    try:
        q.deletePixelGraphic(g.client, graphic_id=graphic_id)
        if request.headers.get("HX-Request"):
            return "", 200
        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response
    except Exception as e:
        current_app.logger.error(f"Error deleting graphic: {e}")
        return f'<span class="text-red-500">Error: {str(e)}</span>', 500
