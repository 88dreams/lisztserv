"""
Integration tests for the complete payment flow.
"""
import pytest
import json
from decimal import Decimal
from unittest.mock import patch, MagicMock

from src.lisztserv.database.models import Payment, UserCredits, WebhookEvent
from src.lisztserv.payments.credit_packages import CreditPackageManager

def test_complete_payment_flow(
    db_session,
    stripe_service,
    credit_service,
    webhook_handler,
    test_user,
    mock_stripe
):
    """
    Test the complete payment flow from start to finish:
    1. Create payment intent
    2. Process successful payment webhook
    3. Verify credits added
    4. Test credit usage
    """
    # Setup
    package_manager = CreditPackageManager()
    package = package_manager.get_package('starter')
    
    # Step 1: Create a payment record
    payment = Payment(
        user_id=test_user.id,
        amount=float(package.price_usd),
        currency="USD",
        status="pending"
    )
    db_session.add(payment)
    db_session.commit()
    
    # Step 2: Create payment intent
    intent = stripe_service.create_payment_intent(
        amount=int(float(package.price_usd) * 100),  # Convert to cents
        currency="usd",
        user_id=test_user.id,
        payment_id=payment.id,
        metadata={'credits': str(package.credits)}
    )
    
    assert intent['status'] == 'requires_payment_method'
    assert payment.id is not None
    
    # Step 3: Simulate successful payment webhook
    webhook_event = {
        'id': 'evt_test_success',
        'type': 'payment_intent.succeeded',
        'data': {
            'object': {
                'id': intent['id'],
                'metadata': {
                    'user_id': test_user.id,
                    'payment_id': payment.id,
                    'credits': str(package.credits)
                },
                'status': 'succeeded'
            }
        }
    }
    
    event_json = json.dumps(webhook_event).encode('utf-8')
    
    with patch('stripe.Webhook.construct_event', return_value=webhook_event):
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert success
        assert status_code == 200
    
    # Step 4: Verify payment status
    payment = db_session.query(Payment).get(payment.id)
    assert payment.status == 'completed'
    
    # Step 5: Verify credits were added
    credits = credit_service.get_user_credits(test_user.id)
    assert credits is not None
    assert credits.balance == float(package.credits)
    
    # Step 6: Test credit usage
    success, message = credit_service.deduct_credits(test_user.id, Decimal('2.5'))
    assert success
    assert "Credits deducted successfully" in message
    
    credits = credit_service.get_user_credits(test_user.id)
    assert credits.balance == float(package.credits) - 2.5
    
    # Step 7: Verify webhook event was recorded
    webhook_record = db_session.query(WebhookEvent)\
        .filter_by(id=webhook_event['id'])\
        .first()
    
    assert webhook_record is not None
    assert webhook_record.status == 'success'

def test_failed_payment_flow(
    db_session,
    stripe_service,
    credit_service,
    webhook_handler,
    test_user,
    mock_stripe
):
    """
    Test the payment flow with a failed payment:
    1. Create payment intent
    2. Process failed payment webhook
    3. Verify no credits added
    4. Verify proper error handling
    """
    # Setup
    package_manager = CreditPackageManager()
    package = package_manager.get_package('starter')
    
    # Step 1: Create a payment record
    payment = Payment(
        user_id=test_user.id,
        amount=float(package.price_usd),
        currency="USD",
        status="pending"
    )
    db_session.add(payment)
    db_session.commit()
    
    # Step 2: Create payment intent
    intent = stripe_service.create_payment_intent(
        amount=int(float(package.price_usd) * 100),
        currency="usd",
        user_id=test_user.id,
        payment_id=payment.id,
        metadata={'credits': str(package.credits)}
    )
    
    # Step 3: Simulate failed payment webhook
    webhook_event = {
        'id': 'evt_test_failure',
        'type': 'payment_intent.payment_failed',
        'data': {
            'object': {
                'id': intent['id'],
                'metadata': {
                    'user_id': test_user.id,
                    'payment_id': payment.id
                },
                'status': 'failed',
                'last_payment_error': {
                    'message': 'Card declined'
                }
            }
        }
    }
    
    event_json = json.dumps(webhook_event).encode('utf-8')
    
    with patch('stripe.Webhook.construct_event', return_value=webhook_event):
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert not success
        assert status_code == 400
    
    # Step 4: Verify payment status
    payment = db_session.query(Payment).get(payment.id)
    assert payment.status == 'failed'
    
    # Step 5: Verify no credits were added
    credits = credit_service.get_user_credits(test_user.id)
    assert credits is None or credits.balance == 0
    
    # Step 6: Verify webhook event was recorded
    webhook_record = db_session.query(WebhookEvent)\
        .filter_by(id=webhook_event['id'])\
        .first()
    
    assert webhook_record is not None
    assert webhook_record.status == 'failed'
    assert 'Card declined' in webhook_record.error_message 