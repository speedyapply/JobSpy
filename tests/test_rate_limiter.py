
import time
import pytest
from jobspy.util import RateLimiter

def test_rate_limiter_initialization():
    """Test that RateLimiter behaves correctly with various input parameters."""
    # Test valid initialization
    rl = RateLimiter(rate_delay_min=1, rate_delay_max=2)
    assert rl.rate_delay_min == 1
    assert rl.rate_delay_max == 2

    # Test initialization with None (disabled)
    rl_disabled = RateLimiter(rate_delay_min=None, rate_delay_max=None)
    assert rl_disabled.rate_delay_min is None
    assert rl_disabled.rate_delay_max is None

def test_rate_limiter_logic():
    """Test that enforce_delay actually sleeps for the expected duration."""
    # Functional test with a tiny delay
    rl = RateLimiter(rate_delay_min=0.1, rate_delay_max=0.2)
    # First call sets the last_request_time (no delay expected)
    rl.enforce_delay()
    
    # Second call should delay
    start_time = time.time()
    rl.enforce_delay()
    duration = time.time() - start_time
    
    # It should take at least 0.1s
    assert duration >= 0.1

def test_rate_limiter_backoff():
    """Test that backoff forces a delay regardless of min/max settings."""
    # Initialize with NO normal delay
    rl = RateLimiter(rate_delay_min=None, rate_delay_max=None)
    
    # Trigger backoff for 0.2 seconds
    rl.backoff(seconds=0.2)
    
    start_time = time.time()
    rl.enforce_delay()
    duration = time.time() - start_time
    
    assert duration >= 0.2

def test_rate_limiter_backoff_extension():
    """Test that calling backoff again extends the duration if it's further out."""
    rl = RateLimiter(rate_delay_min=None, rate_delay_max=None)
    
    rl.backoff(seconds=0.1)
    # This should override the 0.1s backoff with a 0.5s backoff (from now)
    rl.backoff(seconds=0.3)
    
    start_time = time.time()
    rl.enforce_delay()
    duration = time.time() - start_time
    
    assert duration >= 0.3

def test_rate_limiter_no_delay():
    """Test that enforce_delay does nothing when no delay is set."""
    # Explicitly pass None as required by the constructor signature
    rl = RateLimiter(rate_delay_min=None, rate_delay_max=None)
    start_time = time.time()
    rl.enforce_delay()
    duration = time.time() - start_time
    
    # Should be effectively instant
    assert duration < 0.05
