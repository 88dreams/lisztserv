from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from lisztserv.database import SessionLocal
from lisztserv.database.models import User, UserCredits

def test_database_operations():
    """Test basic database operations with a test user."""
    db = SessionLocal()
    try:
        # Create a test user
        test_user = User(
            email="test@example.com",
            password_hash="test_hash_not_for_production",
            is_active=True
        )
        
        # Add user to database
        print("Creating test user...")
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        print(f"Created user with ID: {test_user.id}")
        
        # Initialize user credits
        user_credits = UserCredits(
            user_id=test_user.id,
            balance=10.0  # Starting balance
        )
        db.add(user_credits)
        db.commit()
        print(f"Added initial credits: {user_credits.balance}")
        
        # Verify we can retrieve the user
        retrieved_user = db.query(User).filter(User.email == "test@example.com").first()
        print("\nRetrieved user details:")
        print(f"Email: {retrieved_user.email}")
        print(f"Active: {retrieved_user.is_active}")
        print(f"Credit Balance: {retrieved_user.credits.balance}")
        
        # Clean up test data
        print("\nCleaning up test data...")
        db.delete(user_credits)
        db.delete(test_user)
        db.commit()
        print("Test data cleaned up successfully!")
        
    except Exception as e:
        print(f"Error during database test: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_database_operations() 