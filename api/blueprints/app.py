from flask import g, Blueprint, render_template, current_app, abort, make_response
from flask_login import login_required
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
        graphics=graphics or [],
        messages=messages or [],
    )

@bp.route("/create_art")
def create_art():
    return render_template("app/create-art.html")