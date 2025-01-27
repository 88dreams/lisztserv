from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, Tuple
from datetime import timedelta

from ..database.models import User, UserCredits
from .utils import verify_password, get_password_hash, create_access_token
from email_validator import validate_email, EmailNotValidError

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def validate_email_format(self, email: str) -> Tuple[bool, str]:
        """Validate email format."""
        try:
            validation = validate_email(email, check_deliverability=False)
            return True, validation.normalized
        except EmailNotValidError as e:
            return False, str(e)

    def register_user(self, email: str, password: str) -> Tuple[bool, str, Optional[User]]:
        """Register a new user."""
        # Validate email format
        is_valid, message = self.validate_email_format(email)
        if not is_valid:
            return False, f"Invalid email: {message}", None

        # Check password strength (implement your own rules)
        if len(password) < 8:
            return False, "Password must be at least 8 characters long", None

        try:
            # Create user
            user = User(
                email=email,
                password_hash=get_password_hash(password)
            )
            self.db.add(user)
            
            # Initialize user credits
            user_credits = UserCredits(user=user, balance=0.0)
            self.db.add(user_credits)
            
            self.db.commit()
            self.db.refresh(user)
            return True, "User registered successfully", user
            
        except IntegrityError:
            self.db.rollback()
            return False, "Email already registered", None
        except Exception as e:
            self.db.rollback()
            return False, f"Registration failed: {str(e)}", None

    def authenticate_user(self, email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
        """Authenticate a user and return access token."""
        try:
            user = self.db.query(User).filter(User.email == email).first()
            if not user:
                return False, "Invalid email or password", None
            
            if not verify_password(password, user.password_hash):
                return False, "Invalid email or password", None
            
            # Create access token
            access_token = create_access_token(
                data={"sub": user.id, "email": user.email},
                expires_delta=timedelta(minutes=30)
            )
            
            return True, "Login successful", {
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": user.id,
                "email": user.email
            }
            
        except Exception as e:
            return False, f"Authentication failed: {str(e)}", None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.db.query(User).filter(User.email == email).first() 