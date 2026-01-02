from flask import g, Blueprint, render_template, current_app
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
    friends = list()
    return render_template("app/index.html", user=user, boards=boards, friends=friends)
