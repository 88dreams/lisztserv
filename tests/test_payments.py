"""
Tests for the payment system components.
"""
import pytest
import json
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import stripe

from lisztserv.database.models import Payment, UserCredits, WebhookEvent, FailedWebhookEvent
from lisztserv.utils.retry import RetryableError, MaxRetriesExceeded

# Stripe Service Tests
class TestStripeService:
    def test_create_customer(self, stripe_service, test_user):
        """Test creating a Stripe customer."""
        customer = stripe_service.create_customer(test_user)
        assert customer['id'] == 'cus_test123'
        assert customer['email'] == test_user.email

    def test_create_payment_intent(self, stripe_service, test_user, test_payment):
        """Test creating a payment intent."""
        success, intent = stripe_service.create_payment_intent(
            amount=500,  # $5.00
            currency="usd",
            user_id=test_user.id,
            payment_id=test_payment.id,
            metadata={'credits': '10'}
        )
        assert success
        assert intent['id'] == 'pi_test123'

# Credit Service Tests
class TestCreditService:
    def test_add_initial_credits(self, credit_service, test_user):
        """Test adding initial credits to a user."""
        success, message = credit_service.add_credits(test_user.id, Decimal('10.0'))
        assert success
        assert "Added 10.0 credits successfully" in message
        
        credits = credit_service.get_user_credits(test_user.id)
        assert credits == Decimal('10.0')
    
    def test_add_additional_credits(self, credit_service, test_user):
        """Test adding more credits to a user with existing balance."""
        # Setup initial credits
        credit_service.add_credits(test_user.id, Decimal('10.0'))
        
        # Add more credits
        success, message = credit_service.add_credits(test_user.id, Decimal('5.0'))
        assert success
        credits = credit_service.get_user_credits(test_user.id)
        assert credits == Decimal('15.0')

    def test_deduct_credits_success(self, credit_service, test_user, test_credits):
        """Test successfully deducting credits."""
        success, message = credit_service.deduct_credits(
            user_id=test_user.id,
            amount=Decimal('3.0'),
            usage_type='test_usage'
        )
        assert success
        assert "Deducted 3.0 credits successfully" in message
        
        credits = credit_service.get_user_credits(test_user.id)
        assert credits == Decimal('7.0')
    
    def test_deduct_credits_insufficient(self, credit_service, test_user, test_credits):
        """Test deducting more credits than available."""
        success, message = credit_service.deduct_credits(
            user_id=test_user.id,
            amount=Decimal('20.0'),
            usage_type='test_usage'
        )
        assert not success
        assert "Insufficient credits" in message

    def test_concurrent_credit_update(self, credit_service, test_user, test_credits):
        """Test handling of concurrent credit updates."""
        update_count = 0
        def simulate_concurrent_update(*args):
            nonlocal update_count
            if update_count == 0:
                update_count += 1
                # Simulate another process updating credits by directly modifying the database
                credits = credit_service.db.query(UserCredits).filter_by(user_id=test_user.id).first()
                credits.balance = float(Decimal(str(credits.balance)) + Decimal('5.0'))
                return True
            return True

        with patch('sqlalchemy.orm.Session.commit', side_effect=simulate_concurrent_update):
            success, message = credit_service.deduct_credits(
                user_id=test_user.id,
                amount=Decimal('3.0'),
                usage_type='test_usage'
            )
            assert not success
            assert "Concurrent update detected" in message

# Webhook Handler Tests
class TestWebhookHandler:
    @pytest.mark.parametrize("event_type,expected_status", [
        ('payment_success', 'completed'),
        ('payment_failure', 'failed')
    ])
    def test_payment_events(
        self,
        webhook_handler, 
        sample_webhook_events, 
        test_payment,
        event_type,
        expected_status
    ):
        """Test webhook handler processing different payment events."""
        event = sample_webhook_events[event_type]
        event_json = json.dumps(event).encode('utf-8')
        
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert success == (expected_status == 'completed')
        assert status_code in (200, 400)
        
        payment = webhook_handler.db.query(Payment).get(test_payment.id)
        assert payment.status == expected_status

    def test_duplicate_event(self, webhook_handler, sample_webhook_events):
        """Test handling of duplicate webhook events."""
        event = sample_webhook_events['payment_success']
        event_json = json.dumps(event).encode('utf-8')
        
        # First attempt
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        assert success
        
        # Second attempt (duplicate)
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        assert success
        assert "Duplicate event ignored" in message
        assert status_code == 200

    def test_retry_mechanism(self, webhook_handler, sample_webhook_events):
        """Test webhook handler retry mechanism for temporary failures."""
        event = sample_webhook_events['payment_success']
        event_json = json.dumps(event).encode('utf-8')

        failure_count = 0
        def mock_process_with_failure(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            if failure_count < 2:
                raise RetryableError("Temporary failure")
            return True, "Success after retry"

        with patch.object(webhook_handler, '_process_event', side_effect=mock_process_with_failure):
            success, message, status_code = webhook_handler.handle_webhook(
                event_json,
                'test_signature'
            )

            assert success
            assert failure_count == 2  # One failure, one success
            assert "Success after retry" in message

    def test_dead_letter_queue(self, webhook_handler, sample_webhook_events):
        """Test moving failed events to dead letter queue."""
        event = sample_webhook_events['payment_success']
        event_json = json.dumps(event).encode('utf-8')

        def mock_process_with_permanent_failure(*args, **kwargs):
            raise Exception("Permanent failure")

        with patch.object(webhook_handler, '_process_event', side_effect=mock_process_with_permanent_failure):
            success, message, status_code = webhook_handler.handle_webhook(
                event_json,
                'test_signature'
            )

            assert not success
            assert status_code == 500
            assert "dead letter queue" in message.lower()

            failed_event = webhook_handler.db.query(FailedWebhookEvent).filter(
                FailedWebhookEvent.webhook_id == event['id']
            ).first()
            assert failed_event is not None
            assert "Permanent failure" in failed_event.error_message

    def test_retry_failed_event(self, webhook_handler, sample_webhook_events):
        """Test retrying a failed webhook event."""
        event = sample_webhook_events['payment_success']

        # Create a failed event record
        failed_event = FailedWebhookEvent(
            webhook_id=event['id'],
            type=event['type'],
            status='pending',
            error_message="Initial failure",
            raw_data=json.dumps(event['data']['object']),
            retry_count=0
        )
        webhook_handler.db.add(failed_event)
        webhook_handler.db.commit()

        with patch.object(webhook_handler, '_process_event', return_value=(True, "Success")):
            success, message = webhook_handler.retry_failed_event(failed_event.id)

            assert success
            assert "Success" in message

            failed_event = webhook_handler.db.query(FailedWebhookEvent).get(failed_event.id)
            assert failed_event.status == 'resolved'
            assert failed_event.retry_count == 1
            assert failed_event.resolved_at is not None

# Error Handling Tests
class TestPaymentErrorHandling:
    def test_invalid_payment_data(self, stripe_service, test_user):
        """Test handling of invalid payment data."""
        with pytest.raises(ValueError) as exc_info:
            stripe_service.create_payment_intent(
                amount=-500,  # Invalid negative amount
                currency="usd",
                user_id=test_user.id,
                payment_id=999,  # Invalid payment ID
                metadata={}
            )
        assert "Amount must be positive" in str(exc_info.value)

    def test_stripe_api_error(self, stripe_service, test_user, test_payment):
        """Test handling of Stripe API errors."""
        with patch('stripe.PaymentIntent.create', side_effect=stripe.error.StripeError("API Error")):
            success, error = stripe_service.create_payment_intent(
                amount=500,
                currency="usd",
                user_id=test_user.id,
                payment_id=test_payment.id,
                metadata={'credits': '10'}
            )
            assert not success
            assert "Stripe API error: API Error" == error['error']

    def test_database_error_handling(self, credit_service, test_user):
        """Test handling of database errors during credit operations."""
        with patch('sqlalchemy.orm.Session.commit', side_effect=Exception("DB Error")):
            success, message = credit_service.add_credits(test_user.id, Decimal('10.0'))
            assert not success
            assert "Database error" in message
            
            # Verify no credits were added
            credits = credit_service.get_user_credits(test_user.id)
            assert credits == Decimal('0.0')

    def test_malformed_webhook_payload(self, webhook_handler):
        """Test handling of malformed webhook payloads."""
        malformed_json = b'{"invalid": json data'
        
        success, message, status_code = webhook_handler.handle_webhook(
            malformed_json,
            'test_signature'
        )
        
        assert not success
        assert status_code == 400
        assert "Invalid JSON payload" in message

# Refund Tests
class TestPaymentRefunds:
    def test_create_refund(self, stripe_service, test_payment):
        """Test creating a refund for a payment."""
        # Set the original payment amount
        test_payment.amount = 500
        stripe_service.db.commit()

        mock_refund = {
            'id': 're_test123',
            'payment_intent': test_payment.stripe_payment_id,
            'amount': 500,
            'status': 'succeeded'
        }
        
        with patch('stripe.Refund.create', return_value=mock_refund):
            success, refund = stripe_service.create_refund(
                payment_id=test_payment.id,
                amount=500,
                reason='requested_by_customer'
            )
            
            assert success
            assert refund['id'] == 're_test123'
            assert refund['status'] == 'succeeded'
            
            # Verify payment status is updated
            payment = stripe_service.db.query(Payment).get(test_payment.id)
            assert payment.status == 'refunded'
            assert payment.refund_id == 're_test123'

    def test_partial_refund(self, stripe_service, test_payment):
        """Test creating a partial refund."""
        mock_refund = {
            'id': 're_partial123',
            'payment_intent': test_payment.stripe_payment_id,
            'amount': 250,  # Half of original amount
            'status': 'succeeded'
        }
        
        with patch('stripe.Refund.create', return_value=mock_refund):
            success, refund = stripe_service.create_refund(
                payment_id=test_payment.id,
                amount=250,
                reason='partial_refund'
            )
            
            assert success
            assert refund['amount'] == 250
            
            # Verify payment status
            payment = stripe_service.db.query(Payment).get(test_payment.id)
            assert payment.status == 'partially_refunded'
            assert payment.refunded_amount == 250

    def test_refund_webhook_handling(self, webhook_handler):
        """Test handling of refund webhook events."""
        refund_event = {
            'id': 'evt_refund_test',
            'type': 'charge.refunded',
            'data': {
                'object': {
                    'payment_intent': 'pi_test123',
                    'refund': {
                        'id': 're_test123',
                        'amount': 500,
                        'status': 'succeeded'
                    }
                }
            }
        }
        
        event_json = json.dumps(refund_event).encode('utf-8')
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert success
        assert status_code == 200
        assert "Refund processed" in message

    def test_failed_refund(self, stripe_service, test_payment):
        """Test handling of failed refund attempts."""
        # Set initial payment status to completed
        test_payment.status = 'completed'
        stripe_service.db.commit()

        with patch('stripe.Refund.create', side_effect=stripe.error.StripeError("Refund failed")):
            success, error = stripe_service.create_refund(
                payment_id=test_payment.id,
                amount=500,
                reason='requested_by_customer'
            )
            
            assert not success
            assert "Refund failed" in str(error.get('error', ''))
            
            # Verify payment status remains unchanged
            payment = stripe_service.db.query(Payment).get(test_payment.id)
            assert payment.status == 'completed'
            assert payment.refund_id is None

# Dispute Handling Tests
class TestPaymentDisputes:
    def test_dispute_created(self, webhook_handler):
        """Test handling of new dispute creation."""
        dispute_event = {
            'id': 'evt_dispute_test',
            'type': 'charge.dispute.created',
            'data': {
                'object': {
                    'id': 'dp_test123',
                    'payment_intent': 'pi_test123',
                    'amount': 500,
                    'status': 'needs_response',
                    'reason': 'fraudulent'
                }
            }
        }
        
        event_json = json.dumps(dispute_event).encode('utf-8')
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert success
        assert status_code == 200
        
        # Verify payment status is updated
        payment = webhook_handler.db.query(Payment).filter_by(
            stripe_payment_id='pi_test123'
        ).first()
        assert payment.status == 'disputed'
        assert payment.dispute_id == 'dp_test123'

    def test_dispute_won(self, webhook_handler, test_payment):
        """Test handling of won dispute."""
        test_payment.status = 'disputed'  # Set initial status
        webhook_handler.db.commit()

        dispute_event = {
            'id': 'evt_dispute_won',
            'type': 'charge.dispute.closed',
            'data': {
                'object': {
                    'id': 'dp_test123',
                    'payment_intent': test_payment.stripe_payment_id,
                    'status': 'won',
                    'amount': 500
                }
            }
        }
        
        event_json = json.dumps(dispute_event).encode('utf-8')
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert success
        assert status_code == 200
        
        # Verify payment status is updated
        payment = webhook_handler.db.query(Payment).get(test_payment.id)
        assert payment.status == 'completed'
        assert payment.dispute_status == 'won'

    def test_dispute_lost(self, webhook_handler, test_payment):
        """Test handling of lost dispute."""
        test_payment.status = 'disputed'  # Set initial status
        webhook_handler.db.commit()

        dispute_event = {
            'id': 'evt_dispute_lost',
            'type': 'charge.dispute.closed',
            'data': {
                'object': {
                    'id': 'dp_test123',
                    'payment_intent': test_payment.stripe_payment_id,
                    'status': 'lost',
                    'amount': 500
                }
            }
        }
        
        event_json = json.dumps(dispute_event).encode('utf-8')
        success, message, status_code = webhook_handler.handle_webhook(
            event_json,
            'test_signature'
        )
        
        assert success
        assert status_code == 200
        
        # Verify payment status and credits are updated
        payment = webhook_handler.db.query(Payment).get(test_payment.id)
        assert payment.status == 'charged_back'
        assert payment.dispute_status == 'lost'
        
        # Verify credits were deducted
        user_credits = webhook_handler.db.query(UserCredits).filter_by(
            user_id=payment.user_id
        ).first()
        assert user_credits.balance == Decimal('0.0')

    def test_dispute_evidence_submission(self, stripe_service, test_payment):
        """Test submitting evidence for a dispute."""
        mock_dispute = {
            'id': 'dp_test123',
            'payment_intent': test_payment.stripe_payment_id,
            'status': 'needs_response'
        }
        
        evidence = {
            'customer_email_address': 'customer@example.com',
            'service_date': datetime.now().isoformat(),
            'product_description': 'API Credits Purchase',
            'customer_purchase_ip': '192.168.1.1'
        }
        
        with patch('stripe.Dispute.modify', return_value=mock_dispute):
            success, dispute = stripe_service.submit_dispute_evidence(
                dispute_id='dp_test123',
                evidence=evidence
            )
            
            assert success
            assert dispute['status'] == 'needs_response' 