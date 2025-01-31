from decimal import Decimal
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from ..database.models import User, UserCredits, Payment, UsageRecord

class CreditService:
    def __init__(self, db: Session):
        self.db = db
    
    async def get_user_credits(self, user_id: str) -> Optional[Decimal]:
        """Get current credit balance for a user."""
        try:
            credits = self.db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
            return Decimal(str(credits.balance)) if credits else Decimal('0')
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise ValueError(f"Error getting user credits: {str(e)}")
    
    async def add_credits(self, user_id: str, amount: Decimal, payment_id: Optional[str] = None) -> Tuple[bool, str]:
        """Add credits to a user's balance."""
        try:
            credits = self.db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
            
            if not credits:
                # Initialize credits if they don't exist
                credits = UserCredits(
                    user_id=user_id,
                    balance=float(amount)  # Convert Decimal to float for storage
                )
                self.db.add(credits)
            else:
                # Convert stored float to Decimal, add the new amount, then convert back to float
                current_balance = Decimal(str(credits.balance))
                new_balance = current_balance + amount
                credits.balance = float(new_balance)
                credits.last_updated = datetime.utcnow()
            
            # Record the payment if payment_id is provided
            if payment_id:
                payment = self.db.query(Payment).filter(Payment.id == payment_id).first()
                if payment:
                    payment.status = 'completed'
            
            try:
                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                return False, f"Database error: {str(e)}"
                
            return True, f"Added {amount} credits successfully"
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            await self.db.rollback()
            return False, f"Error adding credits: {str(e)}"
    
    async def deduct_credits(self, user_id: str, amount: Decimal, usage_type: str, metadata: dict = None) -> Tuple[bool, str]:
        """Deduct credits from a user's balance and record usage."""
        try:
            # Get initial state of credits
            credits = self.db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
            
            if not credits:
                return False, "No credits found for user"
            
            # Convert stored float to Decimal for comparison
            current_balance = Decimal(str(credits.balance))
            
            if current_balance < amount:
                return False, f"Insufficient credits. Required: {amount}, Available: {current_balance}"
            
            # Perform the deduction
            new_balance = current_balance - amount
            credits.balance = float(new_balance)
            credits.last_updated = datetime.utcnow()
            
            # Record the usage
            usage_record = UsageRecord(
                user_id=user_id,
                request_type=usage_type,
                tokens_used=int(amount * 1000),
                cost=float(amount),
                usage_metadata=metadata
            )
            self.db.add(usage_record)
            
            try:
                await self.db.commit()
                return True, f"Deducted {amount} credits successfully"
            except SQLAlchemyError as e:
                await self.db.rollback()
                return False, f"Database error during commit: {str(e)}"
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            return False, f"Error deducting credits: {str(e)}"
    
    async def check_sufficient_credits(self, user_id: str, required_amount: Decimal) -> Tuple[bool, str]:
        """Check if user has sufficient credits for an operation."""
        try:
            credits = self.db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
            
            if not credits:
                return False, "No credits found for user"
            
            if credits.balance < required_amount:
                return False, f"Insufficient credits. Required: {required_amount}, Available: {credits.balance}"
            
            return True, "Sufficient credits available"
            
        except SQLAlchemyError as e:
            return False, f"Error checking credits: {str(e)}"
    
    def get_usage_history(self, user_id: str, limit: int = 10) -> list:
        """Get recent usage history for a user."""
        try:
            usage_records = (
                self.db.query(UsageRecord)
                .filter(UsageRecord.user_id == user_id)
                .order_by(UsageRecord.timestamp.desc())
                .limit(limit)
                .all()
            )
            
            return [
                {
                    'timestamp': record.timestamp,
                    'type': record.request_type,
                    'tokens': record.tokens_used,
                    'cost': record.cost,
                    'metadata': record.usage_metadata
                }
                for record in usage_records
            ]
            
        except SQLAlchemyError as e:
            raise ValueError(f"Error getting usage history: {str(e)}")
    
    def get_credit_summary(self, user_id: str) -> dict:
        """Get a summary of user's credits and usage."""
        try:
            credits = self.db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
            
            # Get total usage
            total_usage = (
                self.db.query(UsageRecord)
                .filter(UsageRecord.user_id == user_id)
                .with_entities(
                    func.sum(UsageRecord.tokens_used).label('total_tokens'),
                    func.sum(UsageRecord.cost).label('total_cost')
                )
                .first()
            )
            
            return {
                'current_balance': float(credits.balance) if credits else 0.0,
                'total_tokens_used': total_usage.total_tokens or 0,
                'total_cost': float(total_usage.total_cost) if total_usage.total_cost else 0.0,
                'last_updated': credits.last_updated if credits else None
            }
            
        except SQLAlchemyError as e:
            raise ValueError(f"Error getting credit summary: {str(e)}") 