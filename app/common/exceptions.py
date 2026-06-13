
class ConcurrentUpdateError(Exception):
    """Raised when an optimistic lock check fails (mirrors Spring OptimisticLockingFailureException)."""


class BusinessRuleError(Exception):
    """Raised when a business invariant is violated (mirrors Spring IllegalStateException)."""
