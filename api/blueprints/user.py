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
)
import api.queries as q
from datetime import datetime, timedelta, timezone

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


@bp.route("/add-friend", methods=["GET", "POST"])
def add_friend():
    return render_template("user/add-friend.html")
