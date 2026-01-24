from flask import (
    g,
    Blueprint,
    Response,
    render_template,
    request,
    abort,
    make_response,
    url_for,
    current_app,
    jsonify,
)
import api.queries as q
import base64
import struct
from api.utils.avatar import generate_default_avatar

bp = Blueprint("user", __name__, template_folder="templates")


@bp.route("/username/new", methods=["GET", "POST"])
def check_username():
    username = request.args.get("username").strip()
    if len(username) < 4:
        return render_template(
            "app/user/username-availability.html",
            message="Username must be longer than 3 characters",
            status="error",
        )
    elif q.usernameExists(g.client, username=username):
        return render_template(
            "app/user/username-availability.html",
            message=f"{username} is not available",
            status="error",
        )
    else:
        return render_template(
            "app/user/username-availability.html",
            message=f"{username} is available!",
            status="available",
        )


@bp.route("/avatar", methods=["GET", "POST"])
def avatar():
    if request.method == "GET":
        # Get current user's avatar if exists
        current_user = q.selectGlobalUser(g.client)
        has_avatar = current_user.avatar is not None if current_user else False
        return render_template(
            "app/user/avatar.html", has_avatar=has_avatar, user=current_user
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
            if width != 16 or height != 16:
                return jsonify({"error": "Avatar must be exactly 16x16 pixels"}), 400

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
            if width != 16 or height != 16:
                return jsonify({"error": "Avatar must be exactly 16x16 pixels"}), 400
        else:
            return jsonify({"error": "Invalid mode"}), 400

        # Create Avatar object
        try:
            user = q.selectGlobalUser(g.client)
            if not user:
                return jsonify({"error": "User not found"}), 401

            # Insert new Avatar
            avatar_result = q.insertAvatar(g.client, data=png_data)

            # Set as active avatar
            q.updateGlobalUser(g.client, avatar_id=avatar_result.id)

            response = make_response("", 204)
            response.headers["HX-Location"] = url_for("user.avatar")
            return response

        except Exception as e:
            current_app.logger.error(f"Error creating avatar: {e}")
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        current_app.logger.error(f"Error saving avatar: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/avatar/paint", methods=["GET"])
def avatar_paint():
    return render_template(
        "paint/canvas.html", BOARD_WIDTH=16, BOARD_HEIGHT=16, avatar_mode=True
    )


@bp.route("/avatar/editor", methods=["GET"])
def avatar_editor():
    """HTMX endpoint to get avatar editor (16x16 only)."""
    user = q.selectGlobalUser(g.client)
    has_avatar = user.avatar is not None if user else False
    return render_template(
        "app/user/avatar_editor.html", user=user, initial_avatar=has_avatar
    )


@bp.route("/avatar/save", methods=["POST"])
def save_avatar():
    """Save avatar from pixel editor."""
    b64_data = request.form.get("pixel_data")

    if not b64_data:
        return jsonify({"error": "No pixel data received"}), 400

    try:
        # Decode Base64 to PNG bytes
        image_data = base64.b64decode(b64_data)

        # Validate PNG format
        if not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "Invalid PNG format"}), 400

        # Read width and height from IHDR (bytes 16-23)
        width, height = struct.unpack(">II", image_data[16:24])
        if width != 16 or height != 16:
            return jsonify({"error": "Avatar must be exactly 16x16 pixels"}), 400

        # Create Avatar object
        user = q.selectGlobalUser(g.client)
        if not user:
            return jsonify({"error": "User not found"}), 401

        # Insert new Avatar
        avatar_result = q.insertAvatar(g.client, data=image_data)

        # Set as active avatar
        q.updateGlobalUser(g.client, avatar_id=avatar_result.id)

        if request.headers.get("HX-Request"):
            return make_response(
                "<div class=\"font-['Press_Start_2P'] text-xs text-pico-green\">Avatar saved successfully!</div>",
                200,
            )

        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("user.account_settings")
        return response

    except Exception as e:
        current_app.logger.error(f"Error saving avatar: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/account/settings", methods=["GET"])
def account_settings():
    """Account settings page for updating avatar and username."""
    user = q.selectGlobalUser(g.client)
    if not user:
        abort(401)

    has_avatar = user.avatar is not None
    return render_template(
        "app/user/account-settings.html", user=user, has_avatar=has_avatar
    )


@bp.route("/account/username", methods=["POST"])
def update_username():
    """Update user's username."""
    new_username = request.form.get("username", "").strip()

    if not new_username or len(new_username) < 4:
        return jsonify({"error": "Username must be at least 4 characters"}), 400

    # Check if username is taken
    if q.usernameExists(g.client, username=new_username):
        return jsonify({"error": "Username already taken"}), 400

    try:
        user = q.selectGlobalUser(g.client)
        if not user:
            return jsonify({"error": "User not found"}), 401

        # Update username
        q.updateGlobalUser(g.client, username=new_username)

        if request.headers.get("HX-Request"):
            return make_response(
                f"<div class=\"font-['Press_Start_2P'] text-xs text-pico-green\">Username updated to {new_username}!</div>",
                200,
            )

        response = make_response("", 204)
        response.headers["HX-Location"] = url_for("user.account_settings")
        return response

    except Exception as e:
        current_app.logger.error(f"Error updating username: {e}")
        return jsonify({"error": str(e)}), 500


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
