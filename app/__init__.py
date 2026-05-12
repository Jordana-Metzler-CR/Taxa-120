from flask import Flask
from app.extensions import db
from app.config import Config
from app.routes.ping_routes import ping_bp
from app.routes.taxa_120_routes import taxa120_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(ping_bp)
    app.register_blueprint(taxa120_bp)
    db.init_app(app)
    return app
