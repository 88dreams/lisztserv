import os
import stripe
from typing import Optional, Dict, Any, Tuple
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
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    def create_or_get_customer(self, user: User) -> str:
        """Create or get a Stripe customer for the user."""
        if user.stripe_customer_id:
            return user.stripe_customer_id
            
        # Create new customer
        customer = stripe.Customer.create(
            email=user.email,
            metadata={
                'user_id': user.id
            }
        )
        
        # Update user with Stripe customer ID
        user.stripe_customer_id = customer.id
        self.db.commit()
        
        return customer.id
    
    def create_payment_intent(self, user: User, package: CreditPackage) -> Tuple[bool, str, Optional[Dict]]:
        """Create a Stripe PaymentIntent for a credit package purchase."""
        try:
            customer_id = self.create_or_get_customer(user)
            
            # Create payment record
            payment = Payment(
                user_id=user.id,
                amount=float(package.price_usd),
                currency='USD',
                status='pending'
            )
            self.db.add(payment)
            self.db.commit()
            
            # Create payment intent
            intent = stripe.PaymentIntent.create(
                amount=int(package.price_usd * 100),  # Convert to cents
                currency='usd',
                customer=customer_id,
                metadata={
                    'user_id': user.id,
                    'payment_id': payment.id,
                    'package_id': package.id,
                    'credits': str(package.credits),
                    'is_subscription': str(package.is_subscription)
                }
            )
            
            # Update payment with Stripe ID
            payment.stripe_payment_id = intent.id
            self.db.commit()
            
            return True, "Payment intent created", {
                'client_secret': intent.client_secret,
                'payment_id': payment.id
            }
            
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}", None
        except Exception as e:
            return False, f"Error creating payment: {str(e)}", None
    
    def create_subscription(self, user: User, package: CreditPackage) -> Tuple[bool, str, Optional[Dict]]:
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
    
    def _handle_subscription_payment(self, invoice: stripe.Invoice) -> Tuple[bool, str]:
        """Handle subscription payments."""
        try:
            subscription = stripe.Subscription.retrieve(invoice.subscription)
            metadata = subscription.metadata
            user_id = metadata.get('user_id')
            credits = Decimal(metadata.get('credits_per_interval', '0'))
            
            # Add credits to user's balance
            success, message = self.credit_service.add_credits(
                user_id=user_id,
                amount=credits
            )
            
            if not success:
                raise ValueError(f"Failed to add subscription credits: {message}")
            
            return True, "Subscription payment processed successfully"
            
        except Exception as e:
            return False, f"Error processing subscription payment: {str(e)}" 