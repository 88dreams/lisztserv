"""
Tests for subscription management functionality.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
import stripe

from lisztserv.database.models import Subscription, UserCredits
from lisztserv.payments.stripe_service import StripeService

@pytest.mark.asyncio
async def test_create_subscription(
    db_session,
    stripe_service,
    test_user,
    test_subscription_package,
    mock_stripe_subscription
):
    """Test subscription creation."""
    user = await test_user
    with patch('stripe.Subscription.create', return_value=mock_stripe_subscription), \
         patch('stripe.Price.create', return_value={'id': 'price_test123'}):
        success, message, data = await stripe_service.create_subscription(
            user=user,
            package=test_subscription_package
        )
        
        assert success
        assert "Subscription created" in message
        assert data['subscription_id'] == mock_stripe_subscription['id']
        
        # Verify subscription record
        subscription = await db_session.execute(
            db_session.query(Subscription).filter_by(user_id=user.id)
        )
        subscription = subscription.scalar_one_or_none()
        assert subscription is not None
        assert subscription.status == 'active'
        assert subscription.credits_per_interval == float(test_subscription_package.credits)

@pytest.mark.asyncio
async def test_subscription_renewal(
    db_session,
    webhook_handler,
    test_user,
    test_subscription,
    mock_stripe_subscription
):
    """Test subscription renewal and credit grant."""
    user = await test_user
    subscription = await test_subscription
    
    # Create webhook event for invoice payment
    event = {
        'id': 'evt_test_renewal',
        'type': 'invoice.paid',
        'data': {
            'object': {
                'subscription': mock_stripe_subscription['id'],
                'customer': mock_stripe_subscription['customer']
            }
        }
    }
    
    with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription):
        success, message = await webhook_handler._handle_subscription_payment(event['data']['object'])
        assert success
        
        # Verify credits were added
        credits = await db_session.execute(
            db_session.query(UserCredits).filter_by(user_id=user.id)
        )
        credits = credits.scalar_one_or_none()
        assert credits is not None
        assert credits.balance == subscription.credits_per_interval

@pytest.mark.asyncio
async def test_subscription_cancellation(
    db_session,
    webhook_handler,
    test_subscription,
    mock_stripe_subscription
):
    """Test subscription cancellation."""
    subscription = await test_subscription
    mock_stripe_subscription['status'] = 'canceled'
    event = {
        'id': 'evt_test_cancel',
        'type': 'customer.subscription.deleted',
        'data': {
            'object': mock_stripe_subscription
        }
    }
    
    success, message = await webhook_handler._handle_subscription_deleted(event['data']['object'])
    assert success
    
    # Verify subscription status
    subscription = await db_session.execute(
        db_session.query(Subscription).filter_by(stripe_subscription_id=mock_stripe_subscription['id'])
    )
    subscription = subscription.scalar_one_or_none()
    assert subscription.status == 'canceled'

@pytest.mark.asyncio
async def test_subscription_update(
    db_session,
    webhook_handler,
    test_subscription,
    mock_stripe_subscription
):
    """Test subscription update."""
    subscription = await test_subscription
    
    # Modify subscription data
    mock_stripe_subscription['items']['data'][0]['price']['unit_amount'] = 4500
    mock_stripe_subscription['metadata']['credits_per_interval'] = '150'
    
    event = {
        'id': 'evt_test_update',
        'type': 'customer.subscription.updated',
        'data': {
            'object': mock_stripe_subscription
        }
    }
    
    success, message = await webhook_handler._handle_subscription_updated(event['data']['object'])
    assert success
    
    # Verify subscription updates
    subscription = await db_session.execute(
        db_session.query(Subscription).filter_by(stripe_subscription_id=mock_stripe_subscription['id'])
    )
    subscription = subscription.scalar_one_or_none()
    assert subscription.credits_per_interval == 150
    assert subscription.price_usd == 45.00

@pytest.mark.asyncio
async def test_subscription_payment_failure(
    db_session,
    webhook_handler,
    test_subscription,
    mock_stripe_subscription
):
    """Test handling of failed subscription payments."""
    subscription = await test_subscription
    event = {
        'id': 'evt_test_payment_failure',
        'type': 'invoice.payment_failed',
        'data': {
            'object': {
                'subscription': mock_stripe_subscription['id'],
                'customer': mock_stripe_subscription['customer'],
                'attempt_count': 1,
                'next_payment_attempt': int((datetime.now() + timedelta(days=1)).timestamp())
            }
        }
    }
    
    success, message = await webhook_handler._handle_invoice_payment_failed(event['data']['object'])
    assert success
    
    # Verify subscription status
    subscription = await db_session.execute(
        db_session.query(Subscription).filter_by(stripe_subscription_id=mock_stripe_subscription['id'])
    )
    subscription = subscription.scalar_one_or_none()
    assert subscription.status == 'past_due'

@pytest.mark.asyncio
async def test_subscription_reactivation(
    db_session,
    webhook_handler,
    test_subscription,
    mock_stripe_subscription
):
    """Test subscription reactivation after payment failure."""
    subscription = await test_subscription
    
    # Set initial status to past_due
    subscription.status = 'past_due'
    await db_session.commit()
    
    event = {
        'id': 'evt_test_reactivation',
        'type': 'invoice.paid',
        'data': {
            'object': {
                'subscription': mock_stripe_subscription['id'],
                'customer': mock_stripe_subscription['customer']
            }
        }
    }
    
    with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription):
        success, message = await webhook_handler._handle_subscription_payment(event['data']['object'])
        assert success
        
        # Verify subscription status
        subscription = await db_session.execute(
            db_session.query(Subscription).filter_by(stripe_subscription_id=mock_stripe_subscription['id'])
        )
        subscription = subscription.scalar_one_or_none()
        assert subscription.status == 'active'

@pytest.mark.asyncio
async def test_subscription_credit_calculation(test_subscription_package):
    """Test credit calculations for subscriptions."""
    # Monthly cost per credit
    cost_per_credit = test_subscription_package.price_usd / test_subscription_package.credits
    assert cost_per_credit == Decimal('0.35')  # $35/100 credits
    
    # Token calculations
    total_tokens = test_subscription_package.total_tokens
    assert total_tokens == 100000  # 100 credits * 1000 tokens/credit
    
    # Cost per token
    cost_per_token = test_subscription_package.price_per_token
    assert cost_per_token == Decimal('0.00035')  # $35/100000 tokens 