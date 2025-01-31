from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import jwt
from . import Base
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    openai_key = Column(String, nullable=True)  # User's own OpenAI key if provided
    stripe_customer_id = Column(String, nullable=True)
    
    # Relationships
    usage_records = relationship("UsageRecord", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    credits = relationship("UserCredits", back_populates="user", uselist=False)
    subscriptions = relationship("Subscription", back_populates="user")
    package_purchases = relationship("PackagePurchase", back_populates="user")

    def create_token(self, expiration_hours=24):
        """Create a JWT token for the user.
        
        Args:
            expiration_hours (int): Number of hours until token expires
            
        Returns:
            str: JWT token
        """
        payload = {
            'user_id': self.id,
            'exp': datetime.utcnow() + timedelta(hours=expiration_hours)
        }
        return jwt.encode(payload, 'test_secret', algorithm='HS256')

class UsageRecord(Base):
    __tablename__ = "usage_records"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    request_type = Column(String, nullable=False)  # 'gpt', 'url', etc.
    tokens_used = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    usage_metadata = Column(JSON, nullable=True)  # Additional usage data
    
    # Relationships
    user = relationship("User", back_populates="usage_records")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    stripe_payment_id = Column(String, nullable=True)
    status = Column(String, nullable=False)  # 'pending', 'completed', 'failed', 'refunded', 'partially_refunded', 'disputed', 'charged_back'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Refund fields
    refund_id = Column(String, nullable=True)
    refunded_amount = Column(Float, nullable=True)
    refund_reason = Column(String, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    
    # Dispute fields
    dispute_id = Column(String, nullable=True)
    dispute_status = Column(String, nullable=True)  # 'needs_response', 'under_review', 'won', 'lost'
    dispute_reason = Column(String, nullable=True)
    disputed_at = Column(DateTime, nullable=True)
    dispute_evidence_submitted_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="payments")

class UserCredits(Base):
    __tablename__ = "user_credits"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="credits")

class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    
    id = Column(String, primary_key=True)  # Stripe event ID
    type = Column(String, nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False)  # 'success' or 'failed'
    error_message = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)  # Store full event data for debugging

    __table_args__ = (
        Index('ix_webhook_events_type', 'type'),
        Index('ix_webhook_events_processed_at', 'processed_at'),
    )

class FailedWebhookEvent(Base):
    """Dead Letter Queue for failed webhook events that need manual intervention."""
    __tablename__ = "failed_webhook_events"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    webhook_id = Column(String, nullable=False)  # Original Stripe event ID
    type = Column(String, nullable=False)
    failed_at = Column(DateTime, default=datetime.utcnow)
    last_retry = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    status = Column(String, nullable=False)  # 'pending', 'retrying', 'failed', 'resolved'
    error_message = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)
    resolution_notes = Column(String, nullable=True)  # Notes on how the issue was resolved
    resolved_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('ix_failed_webhook_events_status', 'status'),
        Index('ix_failed_webhook_events_webhook_id', 'webhook_id'),
    )

class Subscription(Base):
    """Subscription model for recurring credit packages."""
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, nullable=False)
    plan_id = Column(String, nullable=False)  # Reference to credit package
    status = Column(String, nullable=False)  # 'active', 'past_due', 'canceled'
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    credits_per_interval = Column(Float, nullable=False)
    interval = Column(String, nullable=False)  # 'month' or 'year'
    price_usd = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    canceled_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")
    
    __table_args__ = (
        Index('ix_subscriptions_user_id', 'user_id'),
        Index('ix_subscriptions_status', 'status'),
    )

class PackagePurchase(Base):
    """One-time credit package purchase records."""
    __tablename__ = "package_purchases"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    package_id = Column(String, nullable=False)  # Reference to credit package
    amount_paid = Column(Float, nullable=False)
    credits_granted = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # 'completed', 'refunded'
    purchase_date = Column(DateTime, default=datetime.utcnow)
    stripe_payment_id = Column(String, nullable=True)
    refund_date = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="package_purchases")
    
    __table_args__ = (
        Index('ix_package_purchases_user_id', 'user_id'),
        Index('ix_package_purchases_status', 'status'),
    ) 