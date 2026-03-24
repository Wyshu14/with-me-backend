from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from app.models.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    # Validate input
    if not data.get('name') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'All fields are required'}), 400

    # Check existing user
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 409

    # Create user
    user = User(
        name=data['name'],
        email=data['email'],
        password_hash=generate_password_hash(data['password']),
        role=data.get('role', 'guardian')
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({
        'message': 'Registered successfully',
        'user': user.to_dict()
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    user = User.query.filter_by(email=data.get('email')).first()

    if not user or not check_password_hash(user.password_hash, data.get('password')):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = create_access_token(identity=str(user.id))

    return jsonify({
        'token': token,
        'user': user.to_dict()
    }), 200


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    user = User.query.get(user_id)

    if not user:
        return jsonify({'error': 'User not found'}), 404

    if not check_password_hash(user.password_hash, data.get('current_password')):
        return jsonify({'error': 'Current password is incorrect'}), 401

    user.password_hash = generate_password_hash(data.get('new_password'))

    db.session.commit()

    return jsonify({'message': 'Password changed successfully'}), 200