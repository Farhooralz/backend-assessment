"""Redis-backed per-account login failure counter shared by every worker."""

import redis
from django.conf import settings

# One server-side transaction: a crash after the call cannot leave a key without
# a TTL, and concurrent workers cannot interleave a read with the increment.
RECORD_FAILURE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def redis_client() -> redis.Redis:
    """Build the client from settings; all workers point at the same Redis DB."""
    return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)


def failure_key(username: str) -> str:
    return f"login_failures:{username}"


def is_limited(username: str) -> bool:
    """True once LOGIN_FAILURE_LIMIT failures are stored inside the window."""
    value = redis_client().get(failure_key(username))
    return value is not None and int(value) >= settings.LOGIN_FAILURE_LIMIT


def record_failure(username: str) -> int:
    """Atomically increment the counter, arm the window on first hit, return the count."""
    count = redis_client().eval(
        RECORD_FAILURE_SCRIPT,
        1,
        failure_key(username),
        settings.LOGIN_FAILURE_WINDOW_SECONDS,
    )
    return int(count)


def clear_failures(username: str) -> None:
    """A successful login clears the account's failure history."""
    redis_client().delete(failure_key(username))
