from dataclasses import dataclass
from typing import List, Dict, Optional
from decimal import Decimal

@dataclass
class CreditPackage:
    id: str
    name: str
    credits: Decimal
    price_usd: Decimal
    description: str
    tokens_per_credit: int
    is_subscription: bool = False
    subscription_interval: Optional[str] = None  # 'month' or 'year'
    
    @property
    def total_tokens(self) -> int:
        """Calculate total tokens available in this package."""
        return int(self.credits * self.tokens_per_credit)
    
    @property
    def price_per_token(self) -> Decimal:
        """Calculate price per token in USD."""
        return self.price_usd / Decimal(self.total_tokens)

class CreditPackageManager:
    # Standard conversion rate
    TOKENS_PER_CREDIT = 1000  # 1 credit = 1000 tokens
    
    # Available packages
    PACKAGES: Dict[str, CreditPackage] = {
        'starter': CreditPackage(
            id='credit_pkg_starter',
            name='Starter Package',
            credits=Decimal('10'),
            price_usd=Decimal('5.00'),
            description='Perfect for trying out the service',
            tokens_per_credit=TOKENS_PER_CREDIT
        ),
        'standard': CreditPackage(
            id='credit_pkg_standard',
            name='Standard Package',
            credits=Decimal('50'),
            price_usd=Decimal('20.00'),
            description='Most popular for regular users',
            tokens_per_credit=TOKENS_PER_CREDIT
        ),
        'professional': CreditPackage(
            id='credit_pkg_pro',
            name='Professional Package',
            credits=Decimal('150'),
            price_usd=Decimal('50.00'),
            description='Best value for power users',
            tokens_per_credit=TOKENS_PER_CREDIT
        ),
        'subscription_monthly': CreditPackage(
            id='credit_sub_monthly',
            name='Monthly Subscription',
            credits=Decimal('100'),
            price_usd=Decimal('35.00'),
            description='Monthly credits at a discounted rate',
            tokens_per_credit=TOKENS_PER_CREDIT,
            is_subscription=True,
            subscription_interval='month'
        )
    }
    
    @classmethod
    def get_package(cls, package_id: str) -> Optional[CreditPackage]:
        """Get a specific package by ID."""
        return cls.PACKAGES.get(package_id)
    
    @classmethod
    def list_packages(cls, include_subscriptions: bool = True) -> List[CreditPackage]:
        """List all available packages."""
        packages = list(cls.PACKAGES.values())
        if not include_subscriptions:
            packages = [pkg for pkg in packages if not pkg.is_subscription]
        return packages
    
    @classmethod
    def calculate_tokens(cls, credits: Decimal) -> int:
        """Calculate how many tokens a credit amount provides."""
        return int(credits * cls.TOKENS_PER_CREDIT)
    
    @classmethod
    def calculate_credits_needed(cls, tokens: int) -> Decimal:
        """Calculate how many credits are needed for a given number of tokens."""
        return Decimal(tokens) / cls.TOKENS_PER_CREDIT
    
    @classmethod
    def get_best_package_for_tokens(cls, tokens_needed: int) -> Optional[CreditPackage]:
        """Get the most cost-effective package for a given token requirement."""
        needed_credits = cls.calculate_credits_needed(tokens_needed)
        
        # Filter one-time packages that provide enough credits
        suitable_packages = [
            pkg for pkg in cls.PACKAGES.values()
            if not pkg.is_subscription and pkg.credits >= needed_credits
        ]
        
        if not suitable_packages:
            return None
            
        # Return the package with the lowest price per token
        return min(suitable_packages, key=lambda pkg: pkg.price_per_token) 