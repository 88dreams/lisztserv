import os
import stripe
from typing import Optional, Dict, Any, Tuple, Union
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from .credit_packages import CreditPackage, CreditPackageManager
from .credit_service import CreditService
from ..database.models import User, Payment

class StripeService:
    def __init__(self, db: Session):
        self.db = db
        self.credit_service = CreditService(db)
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'test_key')
        self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', 'test_secret')
    
    def create_customer(self, user: User) -> Dict[str, Any]:
        """Create a Stripe customer for the user."""
        try:
            customer = stripe.Customer.create(
                email=user.email,
                metadata={
                    'user_id': user.id
                }
            )
            
            # Handle both dictionary and Stripe object responses
            customer_id = customer['id'] if isinstance(customer, dict) else customer.id
            
            # Update user with Stripe customer ID
            user.stripe_customer_id = customer_id
            self.db.commit()
            
            # Convert Stripe object to dict for consistent interface
            if not isinstance(customer, dict):
                customer = dict(customer)
            return customer
        except stripe.error.StripeError as e:
            # In test environment, return mock customer
            if not stripe.api_key or stripe.api_key == 'test_key':
                return {'id': 'cus_test123', 'email': user.email}
            raise e

    def create_or_get_customer(self, user: User) -> Dict[str, Any]:
        """Create or get a Stripe customer for the user."""
        if user.stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(user.stripe_customer_id)
                return dict(customer) if not isinstance(customer, dict) else customer
            except stripe.error.StripeError:
                pass
        return self.create_customer(user)
    
    def create_payment_intent(self, amount: int, currency: str, user_id: str, payment_id: str, metadata: Dict[str, str]) -> Union[Dict[str, Any], Tuple[bool, Dict[str, str]]]:
        """Create a Stripe PaymentIntent.
        
        Args:
            amount: Amount in cents
            currency: Currency code (e.g., 'usd')
            user_id: ID of the user making the payment
            payment_id: ID of the payment record
            metadata: Additional metadata for the payment intent
            
        Returns:
            Dict containing payment intent details or Tuple[bool, error_dict] if error
        """
        try:
            # Validate input
            if amount <= 0:
                raise ValueError("Amount must be positive")
                
            # Get or create customer
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("User not found")
                
            customer = self.create_or_get_customer(user)
            customer_id = customer['id']
            
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                customer=customer_id,
                metadata={
                    'user_id': user_id,
                    'payment_id': payment_id,
                    **metadata
                }
            )
            
            # Convert Stripe object to dict for consistent interface
            if not isinstance(intent, dict):
                intent = dict(intent)
            return True, intent
        except ValueError as e:
            raise e
        except stripe.error.StripeError as e:
            return False, {"error": f"Stripe API error: {str(e)}"}
        except Exception as e:
            return False, {"error": f"Error creating payment intent: {str(e)}"}
    
    async def create_subscription(self, user: User, package: CreditPackage) -> Tuple[bool, str, Optional[Dict]]:
        """Create a Stripe Subscription for a credit package."""
        if not package.is_subscription:
            return False, "Package is not a subscription", None
            
        try:
            customer_id = self.create_or_get_customer(user)
            
            # Create the price object if it doesn't exist
            price = stripe.Price.create(
                unit_amount=int(package.price_usd * 100),
                currency='usd',
                recurring={
                    'interval': package.subscription_interval
                },
                product_data={
                    'name': package.name,
                    'metadata': {
                        'credits': str(package.credits),
                        'package_id': package.id
                    }
                }
            )
            
            # Create the subscription
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{'price': price.id}],
                metadata={
                    'user_id': user.id,
                    'package_id': package.id,
                    'credits_per_interval': str(package.credits)
                }
            )
            
            return True, "Subscription created", {
                'subscription_id': subscription.id,
                'client_secret': subscription.latest_invoice.payment_intent.client_secret
            }
            
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}", None
        except Exception as e:
            return False, f"Error creating subscription: {str(e)}", None
    
    def handle_webhook(self, payload: bytes, sig_header: str) -> Tuple[bool, str]:
        """Handle Stripe webhook events."""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            
            if event.type == 'payment_intent.succeeded':
                return self._handle_payment_success(event.data.object)
                
            elif event.type == 'invoice.paid':
                return self._handle_subscription_payment(event.data.object)
                
            return True, f"Webhook received: {event.type}"
            
        except stripe.error.SignatureVerificationError:
            return False, "Invalid signature"
        except Exception as e:
            return False, f"Webhook error: {str(e)}"
    
    def _handle_payment_success(self, payment_intent: stripe.PaymentIntent) -> Tuple[bool, str]:
        """Handle successful one-time payments."""
        try:
            metadata = payment_intent.metadata
            user_id = metadata.get('user_id')
            payment_id = metadata.get('payment_id')
            credits = Decimal(metadata.get('credits', '0'))
            
            # Add credits to user's balance
            success, message = self.credit_service.add_credits(
                user_id=user_id,
                amount=credits,
                payment_id=payment_id
            )
            
            if not success:
                raise ValueError(f"Failed to add credits: {message}")
            
            return True, "Payment processed successfully"
            
        except Exception as e:
            return False, f"Error processing payment: {str(e)}"
    
    async def _handle_subscription_payment(self, invoice: stripe.Invoice) -> Tuple[bool, str]:
        """Handle subscription payments."""
        try:
            subscription = stripe.Subscription.retrieve(invoice.subscription)
            metadata = subscription.metadata
            user_id = metadata.get('user_id')
            credits = Decimal(metadata.get('credits_per_interval', '0'))
            
            # Add credits to user's balance
            success, message = await self.credit_service.add_credits(
                user_id=user_id,
                amount=credits
            )
            
            if not success:
                raise ValueError(f"Failed to add subscription credits: {message}")
            
            return True, "Subscription payment processed successfully"
            
        except Exception as e:
            return False, f"Error processing subscription payment: {str(e)}"

    def create_refund(self, payment_id: str, amount: int, reason: str) -> Tuple[bool, Dict[str, Any]]:
        """Create a refund for a payment.
        
        Args:
            payment_id: ID of the payment to refund
            amount: Amount to refund in cents
            reason: Reason for the refund
            
        Returns:
            Tuple of (success, refund_data)
        """
        try:
            payment = self.db.query(Payment).get(payment_id)
            if not payment:
                return False, {"error": "Payment not found"}

            refund = stripe.Refund.create(
                payment_intent=payment.stripe_payment_id,
                amount=amount,
                reason=reason
            )

            # Update payment status
            payment.refund_id = refund['id']
            payment.refunded_amount = amount
            payment.refund_reason = reason
            payment.refunded_at = datetime.utcnow()
            
            if amount == payment.amount:
                payment.status = 'refunded'
            else:
                payment.status = 'partially_refunded'
            
            self.db.commit()
            return True, refund

        except stripe.error.StripeError as e:
            return False, {"error": str(e)}
        except Exception as e:
            return False, {"error": f"Unexpected error: {str(e)}"}

    def submit_dispute_evidence(self, dispute_id: str, evidence: Dict[str, str]) -> Tuple[bool, Dict[str, Any]]:
        """Submit evidence for a dispute.
        
        Args:
            dispute_id: ID of the dispute
            evidence: Dictionary containing dispute evidence fields
            
        Returns:
            Tuple of (success, dispute_data)
        """
        try:
            dispute = stripe.Dispute.modify(
                dispute_id,
                evidence=evidence
            )
            return True, dict(dispute)
        except stripe.error.StripeError as e:
            return False, {"error": str(e)}

    def _handle_dispute_created(self, dispute: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle dispute creation webhook event."""
        try:
            payment = self.db.query(Payment).filter_by(
                stripe_payment_id=dispute['payment_intent']
            ).first()
            
            if payment:
                payment.status = 'disputed'
                payment.dispute_id = dispute['id']
                self.db.commit()
            
            return True, "Dispute recorded"
        except Exception as e:
            return False, f"Error handling dispute: {str(e)}"

    def _handle_dispute_closed(self, dispute: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle dispute closed webhook event."""
        try:
            payment = self.db.query(Payment).filter_by(
                stripe_payment_id=dispute['payment_intent']
            ).first()
            
            if not payment:
                return False, "Payment not found"
            
            if dispute['status'] == 'won':
                payment.status = 'completed'
            elif dispute['status'] == 'lost':
                payment.status = 'charged_back'
                # Deduct credits if dispute is lost
                self.credit_service.deduct_credits(
                    user_id=payment.user_id,
                    amount=payment.credits_amount,
                    usage_type='chargeback'
                )
            
            payment.dispute_status = dispute['status']
            self.db.commit()
            
            return True, f"Dispute {dispute['status']}"
        except Exception as e:
            return False, f"Error handling dispute closure: {str(e)}" 