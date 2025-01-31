import os
import sys
import time
from unittest.mock import Mock

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lisztserv.utils.retry import RetryConfig, with_retry, RetryableError

def test_retry_mechanism():
    """Test the retry mechanism with various scenarios."""
    
    # Test 1: Retry with eventual success
    print("\n1. Testing retry with eventual success:")
    attempt_count = 0
    
    @with_retry(RetryConfig(max_attempts=3, base_delay=0.1))
    def function_with_temporary_failure():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise RetryableError("Temporary failure")
        return "Success"
    
    try:
        result = function_with_temporary_failure()
        print(f"✓ Function succeeded after {attempt_count} attempts")
        print(f"Result: {result}")
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
    
    # Test 2: Retry with max attempts exceeded
    print("\n2. Testing retry with max attempts exceeded:")
    
    @with_retry(RetryConfig(max_attempts=2, base_delay=0.1))
    def function_always_fails():
        raise RetryableError("Persistent failure")
    
    try:
        function_always_fails()
        print("✗ Function should have failed")
    except Exception as e:
        print(f"✓ Expected failure: {str(e)}")
    
    # Test 3: Test exponential backoff
    print("\n3. Testing exponential backoff:")
    attempt_times = []
    
    @with_retry(RetryConfig(max_attempts=3, base_delay=0.1, jitter=False))
    def function_with_timing():
        attempt_times.append(time.time())
        raise RetryableError("Failure for timing test")
    
    try:
        function_with_timing()
    except Exception:
        delays = [attempt_times[i] - attempt_times[i-1] for i in range(1, len(attempt_times))]
        print(f"Delays between attempts: {[f'{delay:.3f}s' for delay in delays]}")
        if delays[1] > delays[0]:
            print("✓ Delay increased exponentially")
        else:
            print("✗ Delay did not increase exponentially")

if __name__ == "__main__":
    test_retry_mechanism() 