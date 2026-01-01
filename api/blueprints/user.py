from flask import g, Blueprint, render_template, request
import api.queries as q

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
    else:
        pass


@bp.route("/add-friend", methods=["GET", "POST"])
def add_friend():
    return render_template("user/add-friend.html")
