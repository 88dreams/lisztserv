import stripe
import json
import logging
from typing import Tuple, Dict, Any, Optional, Union
from datetime import datetime
from sqlalchemy.orm import Session
from .stripe_service import StripeService
from .credit_service import CreditService
from ..database.models import Payment, User, UserCredits, WebhookEvent, FailedWebhookEvent, Subscription
from decimal import Decimal
from ..utils.retry import with_retry, retry_with_transaction, RetryConfig, RetryableError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger('payment-webhooks')

class WebhookProcessingError(RetryableError):
    """Raised when webhook processing fails in a way that should be retried."""
    pass

class WebhookHandler:
    def __init__(self, db: Session):
        self.db = db
        self.stripe_service = StripeService(db)
        self.credit_service = CreditService(db)
        self.retry_config = RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            retryable_exceptions=(
                WebhookProcessingError,
                stripe.error.StripeError,
                Exception
            )
        )

    def handle_webhook(self, payload: bytes, signature: str) -> Tuple[bool, str, int]:
        """
        Handle incoming webhook events from Stripe with retry logic and dead letter queue.
        Returns: (success, message, status_code)
        """
        event = None
        try:
            # First try to decode and parse the JSON payload
            try:
                event_data = json.loads(payload.decode('utf-8'))
                if not isinstance(event_data, dict):
                    return False, "Invalid JSON format", 400
            except json.JSONDecodeError:
                return False, "Invalid JSON payload", 400

            # Parse event data for test environment
            if not self.stripe_service.webhook_secret or self.stripe_service.webhook_secret == 'test_secret':
                event = event_data
            else:
                # Verify webhook signature for production
                try:
                    event = stripe.Webhook.construct_event(
                        payload,
                        signature,
                        self.stripe_service.webhook_secret
                    )
                except stripe.error.SignatureVerificationError:
                    return False, "Invalid webhook signature", 401
                except Exception as e:
                    return False, f"Error verifying webhook: {str(e)}", 400

            if not event:
                return False, "Invalid event data", 400

            # Check for duplicate events
            if self._is_duplicate_event(event['id']):
                return True, "Duplicate event ignored", 200

            try:
                # Process the event with retry logic
                success, message = self._process_event_with_retry(event)
                
                # Record the event processing
                self._record_processed_event(event, None if success else message)
                
                if success:
                    return True, message, 200
                
                # For payment failures, we still return 200 as it's an expected failure
                if event['type'] == 'payment_intent.payment_failed':
                    return False, message, 200
                
                # For other failures, move to dead letter queue
                error_msg = f"Failed to process event: {message}"
                self._move_to_dead_letter_queue(event, error_msg)
                return False, f"Event moved to dead letter queue: {error_msg}", 500

            except Exception as e:
                # Handle any non-retryable errors
                error_msg = str(e)
                self._move_to_dead_letter_queue(event, error_msg)
                return False, f"Event moved to dead letter queue: {error_msg}", 500

        except Exception as e:
            logger.error(f"Webhook error: {str(e)}", exc_info=True)
            error_msg = str(e)
            if event:
                try:
                    self._move_to_dead_letter_queue(event, error_msg)
                except Exception:
                    pass
            return False, f"Webhook processing error: {error_msg}", 500

    def _process_event(self, event: Dict[str, Any]) -> Tuple[bool, str]:
        """Process different types of Stripe events."""
        try:
            event_object = event.get('data', {}).get('object', {})
            event_type = event.get('type', '')
            
            if not event_object:
                return False, "Invalid event data: missing object"
            
            if event_type == 'payment_intent.succeeded':
                return self._handle_payment_success(event_object)
            elif event_type == 'payment_intent.payment_failed':
                return self._handle_payment_failure(event_object)
            elif event_type == 'customer.subscription.created':
                return self._handle_subscription_created(event_object)
            elif event_type == 'customer.subscription.updated':
                return self._handle_subscription_updated(event_object)
            elif event_type == 'customer.subscription.deleted':
                return self._handle_subscription_deleted(event_object)
            elif event_type == 'invoice.paid':
                return self._handle_subscription_payment(event_object)
            elif event_type == 'invoice.payment_failed':
                return self._handle_invoice_payment_failed(event_object)
            elif event_type == 'charge.refunded':
                return self._handle_refund(event_object)
            elif event_type == 'charge.dispute.created':
                return self._handle_dispute_created(event_object)
            elif event_type == 'charge.dispute.closed':
                success, message = self._handle_dispute_closed(event_object)
                if not success:
                    logger.error(f"Failed to handle dispute closed: {message}")
                    raise WebhookProcessingError(message)
                return True, message
            else:
                logger.info(f"Unhandled event type: {event_type}")
                return True, f"Unhandled event type: {event_type}"
                
        except Exception as e:
            logger.error(f"Error processing event: {str(e)}", exc_info=True)
            raise RetryableError(str(e))

    def _handle_payment_success(self, payment_intent: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle successful payment intent."""
        try:
            payment_id = payment_intent.get('metadata', {}).get('payment_id')
            if not payment_id:
                return False, "No payment_id in metadata"

            payment = self.db.query(Payment).filter(Payment.id == payment_id).first()
            if not payment:
                return False, f"Payment not found: {payment_id}"

            # Add credits if specified in metadata
            credits = payment_intent.get('metadata', {}).get('credits')
            if credits:
                success, message = self.credit_service.add_credits(
                    user_id=payment.user_id,
                    amount=Decimal(credits),
                    payment_id=payment_id
                )
                if not success:
                    return False, f"Failed to add credits: {message}"

            payment.status = 'completed'
            payment.stripe_payment_id = payment_intent['id']
            self.db.commit()

            return True, f"Payment {payment_id} marked as completed"
        except Exception as e:
            raise WebhookProcessingError(f"Error handling payment success: {str(e)}")

    def _handle_payment_failure(self, payment_intent: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle failed payment intent."""
        try:
            payment_id = payment_intent.get('metadata', {}).get('payment_id')
            if not payment_id:
                return False, "No payment_id in metadata"

            payment = self.db.query(Payment).filter(Payment.id == payment_id).first()
            if not payment:
                return False, f"Payment not found: {payment_id}"

            payment.status = 'failed'
            self.db.commit()

            return False, f"Payment {payment_id} marked as failed"
        except Exception as e:
            raise WebhookProcessingError(f"Error handling payment failure: {str(e)}")

    def _handle_subscription_created(self, subscription: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle new subscription creation."""
        try:
            metadata = subscription.get('metadata', {})
            user_id = metadata.get('user_id')
            credits_per_interval = metadata.get('credits_per_interval')

            if not user_id or not credits_per_interval:
                return False, "Missing required metadata"

            # Add initial credits for the subscription
            success, message = self.credit_service.add_credits(
                user_id=user_id,
                amount=Decimal(credits_per_interval)
            )
            if not success:
                return False, f"Failed to add initial subscription credits: {message}"

            return True, "Subscription created and initial credits added"
        except Exception as e:
            raise WebhookProcessingError(f"Error handling subscription creation: {str(e)}")

    async def _handle_subscription_updated(self, subscription_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle subscription update events."""
        try:
            subscription_id = subscription_data.get('id')
            if not subscription_id:
                return False, "No subscription ID in event"

            subscription = self.db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if not subscription:
                return False, f"Subscription not found: {subscription_id}"

            # Update subscription details
            subscription.status = subscription_data.get('status', subscription.status)
            subscription.current_period_start = datetime.fromtimestamp(subscription_data.get('current_period_start', 0))
            subscription.current_period_end = datetime.fromtimestamp(subscription_data.get('current_period_end', 0))
            
            # Update price if available
            if 'items' in subscription_data and subscription_data['items'].get('data'):
                price_data = subscription_data['items']['data'][0].get('price', {})
                if 'unit_amount' in price_data:
                    subscription.price_usd = Decimal(price_data['unit_amount']) / 100

            # Update credits if available in metadata
            if 'metadata' in subscription_data:
                credits = subscription_data['metadata'].get('credits_per_interval')
                if credits:
                    subscription.credits_per_interval = float(credits)

            # Handle cancel_at_period_end
            if subscription_data.get('cancel_at_period_end'):
                subscription.status = 'canceling'

            try:
                await self.db.commit()
                return True, f"Subscription updated successfully"
            except SQLAlchemyError as e:
                await self.db.rollback()
                raise WebhookProcessingError(f"Database error: {str(e)}")

        except Exception as e:
            await self.db.rollback()
            raise WebhookProcessingError(f"Error updating subscription: {str(e)}")

    async def _handle_subscription_deleted(self, subscription_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle subscription deletion events."""
        try:
            subscription_id = subscription_data.get('id')
            if not subscription_id:
                return False, "No subscription ID in event"

            subscription = self.db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if not subscription:
                return False, f"Subscription not found: {subscription_id}"

            subscription.status = 'canceled'
            subscription.canceled_at = datetime.now()

            try:
                await self.db.commit()
                return True, f"Subscription canceled successfully"
            except SQLAlchemyError as e:
                await self.db.rollback()
                raise WebhookProcessingError(f"Database error: {str(e)}")

        except Exception as e:
            await self.db.rollback()
            raise WebhookProcessingError(f"Error canceling subscription: {str(e)}")

    async def _handle_subscription_payment(self, invoice: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle subscription payment success."""
        try:
            subscription_id = invoice.get('subscription')
            if not subscription_id:
                return False, "No subscription ID in invoice"

            # Get the subscription from database
            subscription = self.db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if not subscription:
                return False, f"Subscription not found: {subscription_id}"

            # Update subscription status to active
            subscription.status = 'active'

            # Add the subscription credits
            success, message = await self.credit_service.add_credits(
                user_id=subscription.user_id,
                amount=Decimal(str(subscription.credits_per_interval))
            )
            
            if not success:
                raise WebhookProcessingError(f"Failed to add subscription credits: {message}")

            try:
                await self.db.commit()
                return True, f"Subscription payment processed successfully"
            except SQLAlchemyError as e:
                await self.db.rollback()
                raise WebhookProcessingError(f"Database error: {str(e)}")

        except Exception as e:
            await self.db.rollback()
            raise WebhookProcessingError(f"Error handling subscription payment: {str(e)}")

    async def _handle_invoice_payment_failed(self, invoice: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle failed subscription payments."""
        try:
            subscription_id = invoice.get('subscription')
            if not subscription_id:
                return False, "No subscription ID in invoice"

            subscription = self.db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if not subscription:
                return False, f"Subscription not found: {subscription_id}"

            # Update status based on payment attempt
            attempt_count = invoice.get('attempt_count', 0)
            next_attempt = invoice.get('next_payment_attempt')
            
            if next_attempt:
                subscription.status = 'past_due'
            else:
                subscription.status = 'failed'

            try:
                await self.db.commit()
                return True, f"Payment failure handled successfully"
            except SQLAlchemyError as e:
                await self.db.rollback()
                raise WebhookProcessingError(f"Database error: {str(e)}")

        except Exception as e:
            await self.db.rollback()
            raise WebhookProcessingError(f"Error handling payment failure: {str(e)}")

    def _handle_refund(self, charge: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle refund webhook events."""
        try:
            payment_intent_id = charge.get('payment_intent')
            if not payment_intent_id:
                return False, "No payment intent ID in charge"

            payment = self.db.query(Payment).filter(
                Payment.stripe_payment_id == payment_intent_id
            ).first()
            if not payment:
                return False, f"Payment not found for intent: {payment_intent_id}"

            refund = charge.get('refund', {})
            payment.refund_id = refund.get('id')
            payment.refunded_amount = refund.get('amount', 0)
            payment.refunded_at = datetime.utcnow()

            # Update payment status based on refund amount
            if payment.refunded_amount == payment.amount:
                payment.status = 'refunded'
            else:
                payment.status = 'partially_refunded'

            self.db.commit()
            return True, "Refund processed successfully"
        except Exception as e:
            raise WebhookProcessingError(f"Error handling refund: {str(e)}")

    def _handle_dispute_created(self, dispute: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle new dispute creation."""
        try:
            payment_intent_id = dispute.get('payment_intent')
            if not payment_intent_id:
                return False, "No payment intent ID in dispute"

            payment = self.db.query(Payment).filter(
                Payment.stripe_payment_id == payment_intent_id
            ).first()
            if not payment:
                return False, f"Payment not found for intent: {payment_intent_id}"

            payment.dispute_id = dispute.get('id')
            payment.dispute_reason = dispute.get('reason')
            payment.disputed_at = datetime.utcnow()
            payment.dispute_status = dispute.get('status')
            payment.status = 'disputed'

            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                raise WebhookProcessingError(f"Database error: {str(e)}")

            return True, "Dispute created and recorded"
        except Exception as e:
            self.db.rollback()
            raise WebhookProcessingError(f"Error handling dispute creation: {str(e)}")

    def _handle_dispute_closed(self, dispute: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle dispute resolution."""
        try:
            payment_intent_id = dispute.get('payment_intent')
            if not payment_intent_id:
                return False, "No payment intent ID in dispute"

            payment = self.db.query(Payment).filter(
                Payment.stripe_payment_id == payment_intent_id
            ).first()
            if not payment:
                return False, f"Payment not found for intent: {payment_intent_id}"

            # Get the dispute status and amount
            dispute_status = dispute.get('status')
            dispute_amount = Decimal(str(dispute.get('amount', 0))) / 100  # Convert cents to dollars

            # Update dispute status
            payment.dispute_status = dispute_status
            payment.dispute_resolved_at = datetime.utcnow()
            
            try:
                if dispute_status == 'won':
                    # If dispute is won, restore the payment status
                    payment.status = 'completed'
                    
                    # If credits were deducted during dispute, restore them
                    if hasattr(payment, 'credits_deducted_for_dispute') and payment.credits_deducted_for_dispute:
                        success, message = self.credit_service.add_credits(
                            user_id=payment.user_id,
                            amount=payment.credits_deducted_for_dispute,
                            payment_id=payment.id
                        )
                        if not success:
                            raise WebhookProcessingError(f"Failed to restore credits: {message}")
                        payment.credits_deducted_for_dispute = None
                
                elif dispute_status == 'lost':
                    # If dispute is lost, mark payment as charged back
                    payment.status = 'charged_back'
                    
                    # Calculate credits to deduct based on dispute amount
                    credits_to_deduct = min(
                        dispute_amount,
                        payment.credits_added if hasattr(payment, 'credits_added') else Decimal('0')
                    )
                    
                    if credits_to_deduct > 0:
                        success, message = self.credit_service.deduct_credits(
                            user_id=payment.user_id,
                            amount=credits_to_deduct,
                            usage_type='chargeback',
                            metadata={'dispute_id': dispute.get('id')}
                        )
                        if not success:
                            raise WebhookProcessingError(f"Failed to deduct credits: {message}")
                        payment.credits_deducted_for_dispute = credits_to_deduct
                else:
                    return False, f"Unexpected dispute status: {dispute_status}"
                
                self.db.commit()
                return True, f"Dispute {dispute_status} processed successfully"
                
            except Exception as e:
                self.db.rollback()
                raise WebhookProcessingError(f"Error processing dispute outcome: {str(e)}")
                
        except Exception as e:
            self.db.rollback()
            raise WebhookProcessingError(f"Error handling dispute resolution: {str(e)}")

    def _move_to_dead_letter_queue(self, event: Dict[str, Any], error_message: str):
        """Move failed event to dead letter queue for manual review."""
        try:
            failed_event = FailedWebhookEvent(
                webhook_id=event['id'],
                type=event['type'],
                status='pending',
                error_message=error_message,
                raw_data=json.dumps(event['data']['object']),
            )
            self.db.add(failed_event)
            self.db.commit()
            logger.info(f"Event {event['id']} moved to dead letter queue: {error_message}")
        except Exception as e:
            logger.error(f"Error moving event to dead letter queue: {str(e)}", exc_info=True)
            raise WebhookProcessingError(f"Error moving event to dead letter queue: {str(e)}")

    def _is_duplicate_event(self, event_id: str) -> bool:
        """Check if event has already been processed."""
        return bool(
            self.db.query(WebhookEvent)
            .filter(WebhookEvent.id == event_id)
            .first()
        )

    def _record_processed_event(self, event: Dict[str, Any], error: str = None):
        """Record successful event processing."""
        webhook_event = WebhookEvent(
            id=event['id'],
            type=event['type'],
            status='success' if not error else 'failed',
            error_message=error,
            raw_data=json.dumps(event['data']['object']),
        )
        self.db.add(webhook_event)
        self.db.commit()

    def _process_event_with_retry(self, event: Dict[str, Any]) -> Tuple[bool, str]:
        """Process event with retry logic."""
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                success, message = self._process_event(event)
                if success:
                    return True, message
                # If _process_event returns False, treat it as a retryable error
                raise RetryableError(message)
            except RetryableError as e:
                retry_count += 1
                last_error = e
                if retry_count >= max_retries:
                    logger.error(f"Failed to process event after {max_retries} retries: {str(e)}")
                    return False, str(e)
                logger.warning(f"Retry {retry_count} of {max_retries} after error: {str(e)}")
                continue
            except Exception as e:
                # Non-retryable errors should fail immediately
                logger.error(f"Non-retryable error processing event: {str(e)}")
                raise e
        
        return False, str(last_error) if last_error else "Max retries exceeded"

    def retry_failed_event(self, failed_event_id: str) -> Tuple[bool, str]:
        """Retry processing a failed webhook event."""
        failed_event = self.db.query(FailedWebhookEvent).get(failed_event_id)
        if not failed_event:
            return False, "Failed event not found"

        if failed_event.retry_count >= failed_event.max_retries:
            return False, "Max retries exceeded"

        try:
            # Reconstruct the original event
            raw_data = json.loads(failed_event.raw_data) if isinstance(failed_event.raw_data, str) else failed_event.raw_data
            event_data = {
                'id': failed_event.webhook_id,
                'type': failed_event.type,
                'data': {
                    'object': raw_data
                }
            }

            # Attempt to process the event
            success, message = self._process_event(event_data)  # Don't use retry here
            
            # Update the failed event record
            failed_event.retry_count += 1
            failed_event.last_retry = datetime.utcnow()
            
            if success:
                failed_event.status = 'resolved'
                failed_event.resolved_at = datetime.utcnow()
                failed_event.resolution_notes = f"Successfully processed on retry {failed_event.retry_count}"
            else:
                failed_event.status = 'failed' if failed_event.retry_count >= failed_event.max_retries else 'pending'
                failed_event.error_message = message

            self.db.commit()
            return success, message

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error retrying failed event: {str(e)}", exc_info=True)
            return False, str(e) 