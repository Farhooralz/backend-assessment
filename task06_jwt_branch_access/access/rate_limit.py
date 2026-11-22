"""Redis-backed per-account login failure counter shared by every worker."""

import redis
from django.conf import settings


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
    """Atomically increment the counter and start the 60 s window on first use."""
    client = redis_client()
    key = failure_key(username)
    count = client.incr(key)
    if count == 1:
        client.expire(key, settings.LOGIN_FAILURE_WINDOW_SECONDS)
    return count


def clear_failures(username: str) -> None:
    """A successful login clears the account's failure history."""
    redis_client().delete(failure_key(username))
