from flask import Blueprint, request, jsonify
from ..database import SessionLocal
from .service import AuthService
from functools import wraps
from .utils import verify_token

auth_bp = Blueprint('auth', __name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"error": "Invalid token format"}), 401
        
        if not token:
            return jsonify({"error": "Token is missing"}), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({"error": "Invalid token"}), 401
        
        # Add user info to request
        request.user = payload
        return f(*args, **kwargs)
    
    return decorated

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({"error": "Email and password are required"}), 400
    
    db = next(get_db())
    auth_service = AuthService(db)
    
    success, message, user = auth_service.register_user(
        email=data['email'],
        password=data['password']
    )
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({
        "message": message,
        "user": {
            "id": user.id,
            "email": user.email
        }
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({"error": "Email and password are required"}), 400
    
    db = next(get_db())
    auth_service = AuthService(db)
    
    success, message, auth_data = auth_service.authenticate_user(
        email=data['email'],
        password=data['password']
    )
    
    if not success:
        return jsonify({"error": message}), 401
    
    return jsonify(auth_data), 200

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user():
    db = next(get_db())
    auth_service = AuthService(db)
    
    user = auth_service.get_user_by_id(request.user['sub'])
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat()
    }), 200 