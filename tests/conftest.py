"""
Test configuration and fixtures for pytest.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
import stripe
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timedelta
from flask import Flask
from flask.testing import FlaskClient
import json
import uuid

from lisztserv.database import Base
from lisztserv.database.models import User, Payment, UserCredits, WebhookEvent, FailedWebhookEvent, Subscription, PackagePurchase
from lisztserv.payments.stripe_service import StripeService
from lisztserv.payments.credit_service import CreditService
from lisztserv.payments.webhook_handler import WebhookHandler
from lisztserv.app import create_app
from lisztserv.core import user_message

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///test.db"

@pytest.fixture(scope="session")
def app():
    """Create a Flask application for testing."""
    app = create_app({
        'TESTING': True,
        'DATABASE_URL': TEST_DATABASE_URL,
        'SECRET_KEY': 'test_secret_key',
        'STRIPE_SECRET_KEY': 'test_stripe_key',
        'STRIPE_WEBHOOK_SECRET': 'test_webhook_secret'
    })
    return app

@pytest.fixture
def client(app) -> FlaskClient:
    """Create a test client for the Flask application."""
    return app.test_client()

@pytest.fixture(scope="session")
async def engine():
    """Create a test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def db_session(engine):
    """Create a new database session for a test."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
def mock_stripe(monkeypatch):
    """Mock Stripe API responses."""
    def mock_customer_create(*args, **kwargs):
        return {
            'id': 'cus_test123',
            'email': kwargs.get('email', 'test@example.com'),
            'metadata': kwargs.get('metadata', {})
        }
    
    def mock_payment_intent_create(*args, **kwargs):
        return {
            'id': 'pi_test123',
            'status': 'requires_payment_method',
            'client_secret': 'secret_test123',
            'customer': kwargs.get('customer', 'cus_test123'),
            'metadata': kwargs.get('metadata', {})
        }
    
    def mock_webhook_construct_event(*args, **kwargs):
        payload = args[0]
        if isinstance(payload, bytes):
            event_data = json.loads(payload.decode('utf-8'))
        else:
            event_data = payload
            
        return {
            'id': event_data.get('id', 'evt_test123'),
            'type': event_data.get('type', 'payment_intent.succeeded'),
            'data': {
                'object': event_data.get('data', {}).get('object', {})
            }
        }
    
    # Mock Stripe classes
    monkeypatch.setattr('stripe.Customer.create', mock_customer_create)
    monkeypatch.setattr('stripe.PaymentIntent.create', mock_payment_intent_create)
    monkeypatch.setattr('stripe.Webhook.construct_event', mock_webhook_construct_event)
    
    # Mock Stripe API key
    monkeypatch.setattr('stripe.api_key', 'test_key')
    
    return {
        'customer_create': mock_customer_create,
        'payment_intent_create': mock_payment_intent_create,
        'webhook_construct_event': mock_webhook_construct_event
    }

@pytest.fixture
async def test_user(db_session):
    """Create a test user with a unique email."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    user = User(
        email=f"test_{timestamp}@example.com",
        password_hash="test_hash"
    )
    db_session.add(user)
    await db_session.commit()
    return user

@pytest.fixture
async def test_payment(db_session, test_user):
    """Create a test payment."""
    payment = Payment(
        user_id=test_user.id,
        amount=5.00,
        currency="USD",
        status="pending"
    )
    db_session.add(payment)
    await db_session.commit()
    return payment

@pytest.fixture
async def test_credits(db_session, test_user):
    """Create test user credits."""
    credits = UserCredits(
        user_id=test_user.id,
        balance=10.0
    )
    db_session.add(credits)
    await db_session.commit()
    return credits

@pytest.fixture
def stripe_service(db_session, mock_stripe):
    """Create a Stripe service with mocked Stripe API."""
    service = StripeService(db_session)
    service._stripe = mock_stripe
    return service

@pytest.fixture
def credit_service(db_session):
    """Create a credit service."""
    return CreditService(db_session)

@pytest.fixture
def webhook_handler(db_session, mock_stripe):
    """Create a webhook handler."""
    handler = WebhookHandler(db_session)
    handler.stripe_service._stripe = mock_stripe
    handler.stripe_service.webhook_secret = 'test_webhook_secret'
    return handler

@pytest.fixture
def create_webhook_event():
    """Factory fixture to create webhook events."""
    def _create_event(event_type: str, data: dict):
        return {
            'id': f'evt_test_{datetime.now().timestamp()}',
            'type': event_type,
            'data': {
                'object': data
            }
        }
    return _create_event

@pytest.fixture
def sample_webhook_events(test_payment):
    """Create sample webhook events for testing."""
    timestamp = datetime.now().timestamp()
    return {
        'payment_success': {
            'id': f'evt_test_success_{timestamp}',
            'type': 'payment_intent.succeeded',
            'data': {
                'object': {
                    'id': 'pi_test123',
                    'status': 'succeeded',
                    'metadata': {
                        'payment_id': test_payment.id,
                        'credits': '10'
                    }
                }
            }
        },
        'payment_failure': {
            'id': f'evt_test_failure_{timestamp}',
            'type': 'payment_intent.payment_failed',
            'data': {
                'object': {
                    'id': 'pi_test456',
                    'status': 'failed',
                    'metadata': {
                        'payment_id': test_payment.id
                    }
                }
            }
        },
        'subscription_created': {
            'id': f'evt_test_sub_{timestamp}',
            'type': 'customer.subscription.created',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'status': 'active',
                    'metadata': {
                        'user_id': test_payment.user_id,
                        'credits_per_interval': '100'
                    }
                }
            }
        },
        'invoice_paid': {
            'id': f'evt_test_invoice_{timestamp}',
            'type': 'invoice.paid',
            'data': {
                'object': {
                    'id': 'in_test123',
                    'subscription': 'sub_test123',
                    'status': 'paid',
                    'metadata': {
                        'user_id': test_payment.user_id,
                        'credits_per_interval': '100'
                    }
                }
            }
        }
    }

@pytest.fixture
async def test_subscription(db_session, test_user):
    """Create a test subscription."""
    subscription = Subscription(
        user_id=test_user.id,
        stripe_subscription_id=f'sub_test_{uuid.uuid4().hex[:8]}',
        plan_id='credit_sub_monthly',
        status='active',
        current_period_start=datetime.now(),
        current_period_end=datetime.now() + timedelta(days=30),
        credits_per_interval=100,
        interval='month',
        price_usd=35.00
    )
    db_session.add(subscription)
    await db_session.commit()
    return subscription

@pytest.fixture
def test_subscription_plan():
    """Create a test subscription plan configuration."""
    return {
        'id': 'credit_sub_monthly',
        'name': 'Monthly Credits Plan',
        'credits_per_interval': 100,
        'price_usd': 35.00,
        'interval': 'month',
        'description': 'Monthly subscription with 100 credits',
        'stripe_price_id': 'price_test123'
    }

@pytest.fixture
def test_credit_package():
    """Create a test credit package configuration."""
    from lisztserv.payments.credit_packages import CreditPackage
    from decimal import Decimal
    
    return CreditPackage(
        id='test_package',
        name='Test Package',
        credits=Decimal('50'),
        price_usd=Decimal('25.00'),
        description='Test credit package',
        tokens_per_credit=1000,
        is_subscription=False
    )

@pytest.fixture
def test_subscription_package():
    """Create a test subscription package configuration."""
    from lisztserv.payments.credit_packages import CreditPackage
    from decimal import Decimal
    
    return CreditPackage(
        id='test_sub_package',
        name='Test Subscription',
        credits=Decimal('100'),
        price_usd=Decimal('35.00'),
        description='Test subscription package',
        tokens_per_credit=1000,
        is_subscription=True,
        subscription_interval='month'
    )

@pytest.fixture
async def test_package_purchase(db_session, test_user, test_credit_package):
    """Create a test package purchase record."""
    purchase = PackagePurchase(
        user_id=test_user.id,
        package_id=test_credit_package.id,
        amount_paid=float(test_credit_package.price_usd),
        credits_granted=float(test_credit_package.credits),
        status='completed',
        purchase_date=datetime.now()
    )
    db_session.add(purchase)
    await db_session.commit()
    return purchase

@pytest.fixture
def mock_stripe_subscription():
    """Mock Stripe subscription responses."""
    return {
        'id': 'sub_test123',
        'customer': 'cus_test123',
        'status': 'active',
        'current_period_start': int(datetime.now().timestamp()),
        'current_period_end': int((datetime.now() + timedelta(days=30)).timestamp()),
        'items': {
            'data': [{
                'price': {
                    'id': 'price_test123',
                    'unit_amount': 3500,
                    'currency': 'usd',
                    'recurring': {
                        'interval': 'month'
                    }
                }
            }]
        },
        'metadata': {
            'user_id': 'test_user_id',
            'credits_per_interval': '100'
        }
    } 