import os
import sys
from decimal import Decimal
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.lisztserv.database import get_db
from src.lisztserv.database.models import User, Payment, UserCredits, UsageRecord
from src.lisztserv.payments.credit_service import CreditService
from src.lisztserv.payments.stripe_service import StripeService
from src.lisztserv.payments.credit_packages import CreditPackageManager

def cleanup_test_user(session, email: str):
    """Clean up test user and all related records."""
    try:
        user = session.query(User).filter_by(email=email).first()
        if user:
            print("Cleaning up existing test user...")
            # Delete related records first
            session.query(Payment).filter_by(user_id=user.id).delete()
            session.query(UserCredits).filter_by(user_id=user.id).delete()
            session.query(UsageRecord).filter_by(user_id=user.id).delete()
            # Then delete the user
            session.delete(user)
            session.commit()
            print("Cleanup completed")

    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        session.rollback()

def test_payment_system():
    """Test the complete payment system flow."""
    session = next(get_db())
    credit_service = CreditService(session)
    stripe_service = StripeService(session)  # Pass session to StripeService
    package_manager = CreditPackageManager()

    try:
        # Clean up any existing test data
        cleanup_test_user(session, "test_payment@example.com")

        # 1. Create a test user
        test_user = User(
            email="test_payment@example.com",
            password_hash="test_password_hash"  # Changed from hashed_password to match model
        )
        session.add(test_user)
        session.commit()
        print(f"✓ Created test user: {test_user.email}")

        # 2. Create Stripe customer
        customer_id = stripe_service.create_or_get_customer(test_user)
        test_user.stripe_customer_id = customer_id
        session.commit()
        print(f"✓ Created Stripe customer: {customer_id}")

        # 3. Get a credit package
        package = package_manager.get_package('starter')  # Changed to match CreditPackageManager implementation
        print(f"✓ Selected package: {package.name} ({package.credits} credits)")

        # 4. Create a payment intent
        success, message, payment_data = stripe_service.create_payment_intent(test_user, package)
        if not success:
            raise ValueError(message)
        print(f"✓ Created payment intent: {payment_data['payment_id']}")

        # 5. Simulate successful payment
        payment = session.query(Payment).filter_by(id=payment_data['payment_id']).first()
        payment.status = 'completed'
        session.commit()
        print(f"✓ Recorded payment: ${package.price_usd}")

        # 6. Add credits to user
        success, message = credit_service.add_credits(
            user_id=test_user.id,
            amount=package.credits,
            payment_id=payment.id
        )
        if not success:
            raise ValueError(message)
        print(f"✓ Added {package.credits} credits to user")

        # 7. Verify credit balance
        balance = credit_service.get_user_credits(test_user.id)
        print(f"✓ Current balance: {balance} credits")

        # 8. Test credit deduction
        deduction_amount = Decimal('1.5')
        success, message = credit_service.deduct_credits(
            user_id=test_user.id,
            amount=deduction_amount,
            usage_type="Test API usage"
        )
        if not success:
            raise ValueError(message)
        new_balance = credit_service.get_user_credits(test_user.id)
        print(f"✓ Deducted {deduction_amount} credits, new balance: {new_balance}")

        # 9. Get usage history
        history = credit_service.get_usage_history(test_user.id)
        print(f"✓ Retrieved usage history: {len(history)} records")

        # Clean up test data at the end
        cleanup_test_user(session, "test_payment@example.com")
        print("✓ Cleaned up test data")

    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    test_payment_system() 