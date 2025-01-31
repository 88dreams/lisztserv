"""
Integration tests for API endpoints.
"""
import pytest
from decimal import Decimal
import json
from unittest.mock import patch
from flask import url_for

@pytest.mark.integration
class TestPaymentAPI:
    def test_create_payment_intent_success(self, client, test_user, mock_stripe):
        """Test successful creation of payment intent."""
        data = {
            'package_id': 'starter',
            'currency': 'usd'
        }
        
        with patch('stripe.PaymentIntent.create') as mock_create:
            mock_create.return_value = {
                'id': 'pi_test123',
                'client_secret': 'secret_test123',
                'status': 'requires_payment_method'
            }
            
            response = client.post(
                '/api/v1/payments/create-intent',
                json=data,
                headers={'Authorization': f'Bearer {test_user.create_token()}'}
            )
            
            assert response.status_code == 200
            assert 'client_secret' in response.json
            assert 'payment_intent_id' in response.json

    def test_create_payment_intent_unauthorized(self, client):
        """Test payment intent creation without authentication."""
        data = {
            'package_id': 'starter',
            'currency': 'usd'
        }
        
        response = client.post('/api/v1/payments/create-intent', json=data)
        assert response.status_code == 401

    def test_create_payment_intent_invalid_package(self, client, test_user):
        """Test payment intent creation with invalid package."""
        data = {
            'package_id': 'nonexistent',
            'currency': 'usd'
        }
        
        response = client.post(
            '/api/v1/payments/create-intent',
            json=data,
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        
        assert response.status_code == 400
        assert 'error' in response.json

@pytest.mark.integration
class TestCreditAPI:
    def test_get_credit_balance(self, client, test_user, test_credits):
        """Test retrieving user credit balance."""
        response = client.get(
            '/api/v1/credits/balance',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        
        assert response.status_code == 200
        assert response.json['balance'] == float(test_credits.balance)

    def test_credit_history(self, client, test_user, test_payment):
        """Test retrieving credit transaction history."""
        response = client.get(
            '/api/v1/credits/history',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        
        assert response.status_code == 200
        assert 'transactions' in response.json
        assert isinstance(response.json['transactions'], list)

@pytest.mark.integration
class TestWebhookAPI:
    def test_stripe_webhook_success(self, client, webhook_handler, sample_webhook_events):
        """Test successful webhook processing."""
        event = sample_webhook_events['payment_success']
        
        with patch('stripe.Webhook.construct_event', return_value=event):
            response = client.post(
                '/api/v1/webhooks/stripe',
                json=event,
                headers={'Stripe-Signature': 'test_signature'}
            )
            
            assert response.status_code == 200

    def test_stripe_webhook_invalid_signature(self, client):
        """Test webhook with invalid signature."""
        response = client.post(
            '/api/v1/webhooks/stripe',
            json={'type': 'test'},
            headers={'Stripe-Signature': 'invalid'}
        )
        
        assert response.status_code == 400

@pytest.mark.integration
class TestErrorHandling:
    def test_rate_limit_exceeded(self, client, test_user):
        """Test rate limiting on API endpoints."""
        # Make multiple requests quickly
        responses = []
        for _ in range(10):
            response = client.get(
                '/api/v1/credits/balance',
                headers={'Authorization': f'Bearer {test_user.create_token()}'}
            )
            responses.append(response)
        
        # At least one should be rate limited
        assert any(r.status_code == 429 for r in responses)

    def test_invalid_json(self, client, test_user):
        """Test handling of invalid JSON payload."""
        response = client.post(
            '/api/v1/payments/create-intent',
            data='invalid json',
            content_type='application/json',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        
        assert response.status_code == 400
        assert 'error' in response.json 