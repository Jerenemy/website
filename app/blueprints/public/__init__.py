from flask import Blueprint
bp = Blueprint("public", __name__, template_folder="../../templates", static_folder="../../static")

from . import routes  # noqa
