from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
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
    status = Column(String, nullable=False)  # 'pending', 'completed', 'failed'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
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