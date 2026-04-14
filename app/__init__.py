import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
socketio = SocketIO()

def create_app():
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///familyhealth.db')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'withme_secret_key_2024')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    CORS(app, origins="*")

    db.init_app(app)
    JWTManager(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='eventlet')

    from app.routes.auth import auth_bp
    from app.routes.health import health_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(health_bp, url_prefix='/api/health')

    with app.app_context():
        db.create_all()

    return app