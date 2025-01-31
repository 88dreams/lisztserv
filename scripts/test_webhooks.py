import os
import sys
import json
import stripe
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.lisztserv.database import get_db
from src.lisztserv.database.models import User, Payment, UserCredits, WebhookEvent
from src.lisztserv.payments.webhook_handler import WebhookHandler
from src.lisztserv.payments.credit_packages import CreditPackageManager

def create_test_event(event_type: str, data: dict) -> stripe.Event:
    """Create a test webhook event."""
    event_data = {
        'id': f'evt_test_{datetime.now().timestamp()}',
        'type': event_type,
        'data': {
            'object': data
        }
    }
    return stripe.Event.construct_from(event_data, stripe.api_key)

def test_webhook_handler():
    """Test the webhook handler with various events."""
    session = next(get_db())
    handler = WebhookHandler(session)
    package_manager = CreditPackageManager()

    try:
        # Create test user
        test_user = User(
            email="webhook_test@example.com",
            password_hash="test_password_hash"
        )
        session.add(test_user)
        session.commit()
        print(f"✓ Created test user: {test_user.email}")

        # Get a test package
        package = package_manager.get_package('starter')

        # Test payment success event
        payment = Payment(
            user_id=test_user.id,
            amount=float(package.price_usd),
            currency="usd",
            status="pending"
        )
        session.add(payment)
        session.commit()

        payment_intent_data = {
            'id': 'pi_test_123',
            'metadata': {
                'user_id': test_user.id,
                'payment_id': payment.id,
                'credits': str(package.credits)
            },
            'status': 'succeeded'
        }

        event = create_test_event('payment_intent.succeeded', payment_intent_data)
        
        # Create test payload
        payload = json.dumps(event).encode('utf-8')
        test_signature = 'test_signature'

        # Mock stripe.Webhook.construct_event to return our test event
        def mock_construct_event(*args, **kwargs):
            return event

        with patch('stripe.Webhook.construct_event', mock_construct_event):
            # Process the webhook
            success, message, status_code = handler.handle_webhook(payload, test_signature)
            print(f"\nTest payment success webhook:")
            print(f"Success: {success}")
            print(f"Message: {message}")
            print(f"Status code: {status_code}")

            # Verify the results
            payment = session.query(Payment).filter_by(id=payment.id).first()
            credits = session.query(UserCredits).filter_by(user_id=test_user.id).first()
            webhook_event = session.query(WebhookEvent).filter_by(id=event.id).first()

            print("\nVerification results:")
            print(f"Payment status: {payment.status}")
            print(f"User credits: {credits.balance if credits else 'No credits'}")
            print(f"Webhook event recorded: {webhook_event is not None}")

            # Test duplicate event handling
            print("\nTesting duplicate event handling:")
            success, message, status_code = handler.handle_webhook(payload, test_signature)
            print(f"Success: {success}")
            print(f"Message: {message}")
            print(f"Status code: {status_code}")

        # Clean up
        session.query(WebhookEvent).delete()
        session.query(UserCredits).filter_by(user_id=test_user.id).delete()
        session.query(Payment).filter_by(user_id=test_user.id).delete()
        session.delete(test_user)
        session.commit()
        print("\n✓ Test data cleaned up")

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    test_webhook_handler() 