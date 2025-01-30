from flask import Blueprint, request, jsonify
from ..database import SessionLocal
from ..auth.routes import token_required
from .credit_packages import CreditPackageManager
from .credit_service import CreditService
from .stripe_service import StripeService
from ..database.models import User

payments_bp = Blueprint('payments', __name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@payments_bp.route('/api/credits/packages', methods=['GET'])
def list_packages():
    """List available credit packages."""
    include_subscriptions = request.args.get('include_subscriptions', 'true').lower() == 'true'
    packages = CreditPackageManager.list_packages(include_subscriptions=include_subscriptions)
    
    return jsonify([{
        'id': pkg.id,
        'name': pkg.name,
        'credits': float(pkg.credits),
        'price_usd': float(pkg.price_usd),
        'description': pkg.description,
        'tokens': pkg.total_tokens,
        'is_subscription': pkg.is_subscription,
        'subscription_interval': pkg.subscription_interval
    } for pkg in packages])

@payments_bp.route('/api/credits/purchase', methods=['POST'])
@token_required
def purchase_credits():
    """Initiate a credit package purchase."""
    data = request.json
    package_id = data.get('package_id')
    
    if not package_id:
        return jsonify({'error': 'Package ID is required'}), 400
    
    package = CreditPackageManager.get_package(package_id)
    if not package:
        return jsonify({'error': 'Invalid package ID'}), 400
    
    db = next(get_db())
    stripe_service = StripeService(db)
    
    # Get user from database
    user = db.query(User).filter(User.id == request.user['sub']).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        if package.is_subscription:
            success, message, data = stripe_service.create_subscription(user, package)
        else:
            success, message, data = stripe_service.create_payment_intent(user, package)
        
        if not success:
            return jsonify({'error': message}), 400
            
        return jsonify({
            'success': True,
            'message': message,
            'data': data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payments_bp.route('/api/credits/balance', methods=['GET'])
@token_required
def get_balance():
    """Get user's current credit balance."""
    db = next(get_db())
    credit_service = CreditService(db)
    
    try:
        balance = credit_service.get_user_credits(request.user['sub'])
        return jsonify({
            'balance': float(balance)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payments_bp.route('/api/credits/history', methods=['GET'])
@token_required
def get_history():
    """Get user's credit usage history."""
    db = next(get_db())
    credit_service = CreditService(db)
    
    try:
        limit = int(request.args.get('limit', 10))
        history = credit_service.get_usage_history(request.user['sub'], limit=limit)
        return jsonify(history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payments_bp.route('/api/credits/summary', methods=['GET'])
@token_required
def get_summary():
    """Get user's credit usage summary."""
    db = next(get_db())
    credit_service = CreditService(db)
    
    try:
        summary = credit_service.get_credit_summary(request.user['sub'])
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payments_bp.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events."""
    if 'stripe-signature' not in request.headers:
        return jsonify({'error': 'No signature header'}), 400
        
    payload = request.get_data()
    sig_header = request.headers['stripe-signature']
    
    db = next(get_db())
    stripe_service = StripeService(db)
    
    success, message = stripe_service.handle_webhook(payload, sig_header)
    
    if not success:
        return jsonify({'error': message}), 400
        
    return jsonify({'message': message}) 