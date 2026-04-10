"""
Application factory + HTTPS hotspot hosting.
"""

from flask import Flask
from extensions import db, login_manager, bcrypt, csrf
from config import Config
from plugin_loader import load_plugins

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)

    from auth.routes import auth_bp
    from dashboard.routes import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        db.create_all()
        load_plugins(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=443, ssl_context=("cert.pem","key.pem"))