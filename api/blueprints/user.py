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
import api.queries as q
from datetime import datetime, timedelta, timezone
import base64
import struct
from api.utils.avatar import generate_default_avatar

bp = Blueprint("user", __name__, template_folder="templates")


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


@bp.route("/add-board", methods=["GET", "POST"])
def add_board():
    if request.method == "GET":
        return render_template("user/add-board.html")

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
    response.headers["HX-Location"] = url_for("user.board_details", board_id=board.id)
    return response


@bp.route("/board/<board_id>")
def board_details(board_id):
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    if not board:
        abort(404, description="Board does not exist!")
    return render_template("user/board/details.html", board=board)


@bp.route("/board/<board_id>/download_config", methods=["POST"])
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
        "user/board/status_indicator.html", board=board, is_active=is_active
    )


@bp.route("/board/<board_id>/update-name", methods=["GET", "PATCH"])
def update_board_name(board_id):
    if request.method == "PATCH":
        new_name = request.form.get("board_name")
        # Update DB
        board = q.updateGlobalUserBoard(g.client, board_id=board_id, name=new_name)
        # Re-render the read-only partial
        return render_template("user/board/_name_display.html", board=board)

    # GET: Show the edit form
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    return render_template("user/board/edit_name.html", board=board)


@bp.route("/board/<board_id>/name-partial")
def name_partial(board_id):
    # Helper for the 'Cancel' button to revert the UI
    board = q.selectGlobalUserBoard(g.client, board_id=board_id)
    return render_template("user/board/_name_display.html", board=board)


@bp.route("/add-friend", methods=["GET"])
def add_friend():
    # Get pending sent requests
    sent_requests = (
        q.selectFriendRequestsSent(g.client)
        if hasattr(q, "selectFriendRequestsSent")
        else []
    )
    return render_template("user/friend/add.html", sent_requests=sent_requests)


@bp.route("/search", methods=["POST"])
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
    return render_template("user/friend/search-results.html", users=users)


@bp.route("/friend-request/send", methods=["POST"])
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


@bp.route("/friend-request/<request_id>/accept", methods=["POST"])
def accept_friend_request(request_id):
    try:
        q.acceptFriendRequest(g.client, request_id=request_id)
        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("app.home")
        return response
    except Exception as e:
        current_app.logger.error(f"Error accepting friend request: {e}")
        abort(400, description=str(e))


@bp.route("/friend-request/<request_id>/reject", methods=["POST"])
def reject_friend_request(request_id):
    try:
        q.rejectFriendRequest(g.client, request_id=request_id)
        return "", 200
    except Exception as e:
        current_app.logger.error(f"Error rejecting friend request: {e}")
        return jsonify({"error": str(e)}), 400


@bp.route("/friend-request/<request_id>", methods=["DELETE"])
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


@bp.route("/avatar", methods=["GET", "POST"])
def avatar():
    if request.method == "GET":
        # Get current user's avatar if exists
        current_user = q.selectGlobalUser(g.client)
        has_avatar = current_user.avatar is not None if current_user else False
        return render_template(
            "user/avatar.html", has_avatar=has_avatar, user=current_user
        )

    # POST: Save avatar
    mode = request.form.get("mode")  # "paint" or "upload"

    try:
        if mode == "paint":
            # Paint mode: receive base64 PNG data (from canvas.toDataURL)
            base64_string = request.form.get("pixel_data")
            if not base64_string:
                return jsonify({"error": "No pixel data received"}), 400

            # Remove data URL prefix if present (data:image/png;base64,...)
            if base64_string.startswith("data:image"):
                base64_string = base64_string.split(",", 1)[1]

            # Decode base64 to PNG bytes
            png_data = base64.b64decode(base64_string)

            # Validate PNG dimensions by reading IHDR chunk
            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                return jsonify({"error": "Invalid PNG format"}), 400

            # Read width and height from IHDR (bytes 16-23)
            width, height = struct.unpack(">II", png_data[16:24])
            if width != 32 or height != 32:
                return jsonify({"error": "Image must be exactly 32x32 pixels"}), 400

        elif mode == "upload":
            # Upload mode: receive PNG file
            if "avatar_file" not in request.files:
                return jsonify({"error": "No file uploaded"}), 400

            file = request.files["avatar_file"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            # Read PNG data
            png_data = file.read()

            # Validate PNG format
            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                return jsonify({"error": "Invalid PNG format"}), 400

            # Read width and height from IHDR (bytes 16-23)
            width, height = struct.unpack(">II", png_data[16:24])
            if width != 32 or height != 32:
                return jsonify({"error": "Image must be exactly 32x32 pixels"}), 400
        else:
            return jsonify({"error": "Invalid mode"}), 400

        # Save to database
        q.updateGlobalUser(g.client, avatar=png_data)

        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("user.avatar")
        return response

    except Exception as e:
        current_app.logger.error(f"Error saving avatar: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/avatar/paint", methods=["GET"])
def avatar_paint():
    return render_template(
        "paint/canvas.html", BOARD_WIDTH=32, BOARD_HEIGHT=32, avatar_mode=True
    )


@bp.route("/avatar/<user_id>")
def serve_avatar(user_id):
    avatar_data = q.selectUserAvatar(g.client, user_id=user_id)

    if avatar_data is None:
        # Return default avatar
        avatar_data = generate_default_avatar()

    return Response(
        avatar_data,
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
