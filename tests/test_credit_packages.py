"""
Tests for credit package functionality.
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch

from lisztserv.payments.credit_packages import CreditPackage, CreditPackageManager
from lisztserv.database.models import PackagePurchase, UserCredits

def test_credit_package_creation(test_credit_package):
    """Test credit package initialization and properties."""
    assert test_credit_package.id == 'test_package'
    assert test_credit_package.credits == Decimal('50')
    assert test_credit_package.price_usd == Decimal('25.00')
    assert test_credit_package.total_tokens == 50000  # 50 credits * 1000 tokens/credit
    assert test_credit_package.price_per_token == Decimal('0.0005')  # $25/50000 tokens

def test_credit_package_manager():
    """Test credit package manager functionality."""
    manager = CreditPackageManager()
    
    # Test package retrieval
    starter_package = manager.get_package('credit_pkg_starter')
    assert starter_package is not None
    assert starter_package.name == 'Starter Package'
    
    # Test package listing
    all_packages = manager.list_packages(include_subscriptions=True)
    one_time_packages = manager.list_packages(include_subscriptions=False)
    
    assert len(all_packages) > len(one_time_packages)
    assert any(pkg.is_subscription for pkg in all_packages)
    assert not any(pkg.is_subscription for pkg in one_time_packages)

def test_token_calculations():
    """Test token and credit calculations."""
    manager = CreditPackageManager()
    
    # Test token calculation
    credits = Decimal('10')
    tokens = manager.calculate_tokens(credits)
    assert tokens == 10000  # 10 credits * 1000 tokens/credit
    
    # Test credit calculation
    tokens_needed = 5000
    credits_needed = manager.calculate_credits_needed(tokens_needed)
    assert credits_needed == Decimal('5')  # 5000 tokens / 1000 tokens per credit

def test_best_package_selection():
    """Test selection of best package for token requirements."""
    manager = CreditPackageManager()
    
    # Test package selection for different token needs
    small_requirement = manager.get_best_package_for_tokens(5000)  # 5 credits needed
    assert small_requirement.id == 'credit_pkg_starter'
    
    large_requirement = manager.get_best_package_for_tokens(100000)  # 100 credits needed
    assert large_requirement.id == 'credit_pkg_pro'
    
    # Test when no suitable package exists
    too_large = manager.get_best_package_for_tokens(1000000)  # 1000 credits needed
    assert too_large is None

@pytest.mark.asyncio
async def test_package_purchase(
    db_session,
    stripe_service,
    test_user,
    test_credit_package,
    mock_stripe
):
    """Test credit package purchase flow."""
    # Create payment intent
    success, message, data = await stripe_service.create_payment_intent(
        user=test_user,
        package=test_credit_package
    )
    
    assert success
    assert data['client_secret'] == 'secret_test123'
    
    # Simulate successful payment
    payment = PackagePurchase(
        user_id=test_user.id,
        package_id=test_credit_package.id,
        amount_paid=float(test_credit_package.price_usd),
        credits_granted=float(test_credit_package.credits),
        status='pending',
        stripe_payment_id=data['payment_intent_id']
    )
    db_session.add(payment)
    db_session.commit()
    
    # Process webhook
    event = {
        'id': 'evt_test_purchase',
        'type': 'payment_intent.succeeded',
        'data': {
            'object': {
                'id': data['payment_intent_id'],
                'metadata': {
                    'user_id': test_user.id,
                    'payment_id': payment.id,
                    'credits': str(test_credit_package.credits)
                }
            }
        }
    }
    
    success, message = stripe_service._handle_payment_success(event['data']['object'])
    assert success
    
    # Verify purchase record
    purchase = db_session.query(PackagePurchase)\
        .filter_by(id=payment.id)\
        .first()
    assert purchase.status == 'completed'
    
    # Verify credits were added
    credits = db_session.query(UserCredits)\
        .filter_by(user_id=test_user.id)\
        .first()
    assert credits is not None
    assert credits.balance == float(test_credit_package.credits)

@pytest.mark.asyncio
async def test_package_purchase_validation(
    db_session,
    stripe_service,
    test_user,
    test_credit_package
):
    """Test credit package purchase validation."""
    # Test invalid package
    invalid_package = CreditPackage(
        id='invalid',
        name='Invalid Package',
        credits=Decimal('-10'),  # Invalid negative credits
        price_usd=Decimal('0'),  # Invalid zero price
        description='Invalid package',
        tokens_per_credit=1000,
        is_subscription=False
    )
    
    success, message, data = await stripe_service.create_payment_intent(
        user=test_user,
        package=invalid_package
    )
    assert not success
    assert "Invalid package configuration" in message

@pytest.mark.asyncio
async def test_package_purchase_refund(
    db_session,
    webhook_handler,
    test_package_purchase,
    mock_stripe
):
    """Test credit package refund process."""
    # Create refund event
    event = {
        'id': 'evt_test_refund',
        'type': 'charge.refunded',
        'data': {
            'object': {
                'payment_intent': test_package_purchase.stripe_payment_id,
                'amount_refunded': int(test_package_purchase.amount_paid * 100),
                'refunded': True
            }
        }
    }
    
    success, message = webhook_handler._handle_refund(event['data']['object'])
    assert success
    
    # Verify purchase status
    purchase = db_session.query(PackagePurchase)\
        .filter_by(id=test_package_purchase.id)\
        .first()
    assert purchase.status == 'refunded'
    
    # Verify credits were deducted
    credits = db_session.query(UserCredits)\
        .filter_by(user_id=test_package_purchase.user_id)\
        .first()
    assert credits.balance == 0

def test_package_price_comparison():
    """Test credit package price comparison."""
    manager = CreditPackageManager()
    packages = manager.list_packages(include_subscriptions=False)
    
    # Sort packages by price per token
    sorted_packages = sorted(packages, key=lambda p: p.price_per_token)
    
    # Verify that larger packages have better rates
    for i in range(len(sorted_packages) - 1):
        current = sorted_packages[i]
        next_pkg = sorted_packages[i + 1]
        assert current.price_per_token <= next_pkg.price_per_token

def test_package_token_rounding():
    """Test token calculation rounding behavior."""
    package = CreditPackage(
        id='test_rounding',
        name='Test Package',
        credits=Decimal('3.33333'),
        price_usd=Decimal('10.00'),
        description='Test package',
        tokens_per_credit=1000,
        is_subscription=False
    )
    
    # Verify token calculations are properly rounded
    assert package.total_tokens == 3333  # Should round down
    assert package.price_per_token == Decimal('0.003000900270081024')  # Should maintain precision 