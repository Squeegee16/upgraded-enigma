from flask import Blueprint, render_template
from plugins.base_plugin import BasePlugin

bp = Blueprint("example", __name__, url_prefix="/example")

@bp.route("/")
def index():
    return "Example Plugin Active"

class Plugin(BasePlugin):
    name = "Example Radio Plugin"

    def get_blueprint(self):
        return bp

    def get_device(self):
        return "MockDevice"