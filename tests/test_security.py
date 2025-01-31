"""
Security tests for authentication, authorization, and rate limiting.
"""
import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import patch
import time

@pytest.mark.security
class TestAuthentication:
    def test_valid_token_auth(self, client, test_user):
        """Test authentication with valid token."""
        token = test_user.create_token()
        response = client.get(
            '/api/v1/credits/balance',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 200

    def test_expired_token(self, client, test_user):
        """Test authentication with expired token."""
        # Create token that's already expired
        expired_token = jwt.encode(
            {
                'user_id': str(test_user.id),
                'exp': datetime.utcnow() - timedelta(hours=1)
            },
            'test_secret',
            algorithm='HS256'
        )
        
        response = client.get(
            '/api/v1/credits/balance',
            headers={'Authorization': f'Bearer {expired_token}'}
        )
        assert response.status_code == 401
        assert 'token expired' in response.json['error'].lower()

    def test_invalid_token_format(self, client):
        """Test authentication with malformed token."""
        response = client.get(
            '/api/v1/credits/balance',
            headers={'Authorization': 'Bearer invalid_token_format'}
        )
        assert response.status_code == 401
        assert 'invalid token' in response.json['error'].lower()

    def test_missing_token(self, client):
        """Test request without authentication token."""
        response = client.get('/api/v1/credits/balance')
        assert response.status_code == 401
        assert 'missing token' in response.json['error'].lower()

@pytest.mark.security
class TestAuthorization:
    def test_resource_access_control(self, client, test_user, test_payment):
        """Test access control for user-specific resources."""
        # Try to access another user's payment
        other_payment_id = 'different_payment_id'
        response = client.get(
            f'/api/v1/payments/{other_payment_id}',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 403

    def test_admin_only_endpoint(self, client, test_user):
        """Test endpoints restricted to admin users."""
        response = client.get(
            '/api/v1/admin/users',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 403

    def test_role_based_access(self, client, test_user):
        """Test role-based access control."""
        # Regular user attempting admin action
        response = client.post(
            '/api/v1/admin/credits/adjust',
            json={'user_id': str(test_user.id), 'amount': 100},
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 403

@pytest.mark.security
class TestRateLimiting:
    def test_api_rate_limiting(self, client, test_user):
        """Test rate limiting on API endpoints."""
        # Make requests at maximum allowed rate
        for _ in range(5):
            response = client.get(
                '/api/v1/credits/balance',
                headers={'Authorization': f'Bearer {test_user.create_token()}'}
            )
            assert response.status_code == 200

        # Additional request should be rate limited
        response = client.get(
            '/api/v1/credits/balance',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 429
        assert 'rate limit exceeded' in response.json['error'].lower()

    def test_rate_limit_reset(self, client, test_user):
        """Test rate limit reset after window expiration."""
        # Hit rate limit
        for _ in range(6):
            client.get(
                '/api/v1/credits/balance',
                headers={'Authorization': f'Bearer {test_user.create_token()}'}
            )

        # Wait for rate limit window to reset
        time.sleep(1)  # Assuming 1 second window for tests

        # Should be able to make request again
        response = client.get(
            '/api/v1/credits/balance',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 200

    def test_different_endpoint_limits(self, client, test_user):
        """Test different rate limits for different endpoints."""
        # Test regular API endpoint
        for _ in range(5):
            client.get(
                '/api/v1/credits/balance',
                headers={'Authorization': f'Bearer {test_user.create_token()}'}
            )

        # Test webhook endpoint (should have different limit)
        response = client.post(
            '/api/v1/webhooks/stripe',
            json={'type': 'test'},
            headers={'Stripe-Signature': 'test_signature'}
        )
        assert response.status_code != 429  # Webhook should have separate limit

@pytest.mark.security
class TestInputValidation:
    def test_sql_injection_prevention(self, client, test_user):
        """Test prevention of SQL injection attempts."""
        malicious_input = "'; DROP TABLE users; --"
        response = client.get(
            f'/api/v1/users/search?query={malicious_input}',
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 400
        assert 'invalid input' in response.json['error'].lower()

    def test_xss_prevention(self, client, test_user):
        """Test prevention of XSS attempts."""
        xss_payload = "<script>alert('xss')</script>"
        response = client.post(
            '/api/v1/users/profile',
            json={'name': xss_payload},
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 400
        assert 'invalid input' in response.json['error'].lower()

    def test_request_size_limit(self, client, test_user):
        """Test request size limitations."""
        large_payload = 'x' * (1024 * 1024 * 10)  # 10MB
        response = client.post(
            '/api/v1/payments/create-intent',
            json={'data': large_payload},
            headers={'Authorization': f'Bearer {test_user.create_token()}'}
        )
        assert response.status_code == 413  # Payload Too Large 