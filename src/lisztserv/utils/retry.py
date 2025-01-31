import time
import logging
import functools
from typing import TypeVar, Callable, Optional, Type, Union, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

T = TypeVar('T')

class RetryableError(Exception):
    """Base class for errors that should trigger a retry."""
    pass

class MaxRetriesExceeded(Exception):
    """Raised when max retries are exceeded."""
    pass

class RetryConfig:
    """Configuration for retry behavior."""
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or (RetryableError,)

def with_retry(
    retry_config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
) -> Callable:
    """
    Decorator that implements retry logic with exponential backoff.
    
    Args:
        retry_config: Configuration for retry behavior
        on_retry: Callback function called when a retry occurs
        
    Example:
        @with_retry(RetryConfig(max_attempts=3))
        def process_payment(payment_id: str) -> bool:
            # Process payment logic here
            pass
    """
    if retry_config is None:
        retry_config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 1
            last_exception = None

            while attempt <= retry_config.max_attempts:
                try:
                    return func(*args, **kwargs)
                except retry_config.retryable_exceptions as e:
                    last_exception = e
                    if attempt == retry_config.max_attempts:
                        break

                    delay = min(
                        retry_config.base_delay * (retry_config.exponential_base ** (attempt - 1)),
                        retry_config.max_delay
                    )

                    if retry_config.jitter:
                        import random
                        delay *= (0.5 + random.random())

                    if on_retry:
                        on_retry(e, attempt)

                    logger.warning(
                        f"Attempt {attempt}/{retry_config.max_attempts} failed for {func.__name__}. "
                        f"Retrying in {delay:.2f}s. Error: {str(e)}"
                    )

                    time.sleep(delay)
                    attempt += 1

            raise MaxRetriesExceeded(
                f"Max retries ({retry_config.max_attempts}) exceeded for {func.__name__}. "
                f"Last error: {str(last_exception)}"
            ) from last_exception

        return wrapper
    return decorator

def retry_with_transaction(session, retry_config: Optional[RetryConfig] = None):
    """
    Decorator that combines retry logic with database transaction management.
    
    Example:
        @retry_with_transaction(session)
        def process_payment_with_credits(payment_id: str, user_id: str):
            # Update payment and add credits in a single transaction
            pass
    """
    if retry_config is None:
        retry_config = RetryConfig(
            retryable_exceptions=(RetryableError, Exception)
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        @with_retry(retry_config)
        def wrapper(*args, **kwargs) -> T:
            try:
                result = func(*args, **kwargs)
                session.commit()
                return result
            except Exception as e:
                session.rollback()
                raise RetryableError(f"Transaction failed: {str(e)}") from e

        return wrapper
    return decorator 