"""Shared ingress token bucket; Redis is never the accepted-work store."""

import math
import uuid
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

TOKENS_PER_SECOND = 10
BURST_TOKENS = 20

# Redis TIME makes every API instance use one clock. EVAL makes refill and debit atomic.
TOKEN_BUCKET_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) + tonumber(now_parts[2]) / 1000000
local state = redis.call('HMGET', KEYS[1], 'tokens', 'at')
local tokens = tonumber(state[1]) or tonumber(ARGV[1])
local previous = tonumber(state[2]) or now
tokens = math.min(tonumber(ARGV[1]), tokens + math.max(0, now - previous) * tonumber(ARGV[2]))
local allowed = 0
local retry_after = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    retry_after = math.ceil((1 - tokens) / tonumber(ARGV[2]))
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'at', now)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return {allowed, retry_after}
"""


async def admit_ingest(redis: Redis, organization_id: uuid.UUID) -> int | None:
    """Return retry seconds when denied, or None when one token was consumed."""
    allowed, retry_after = await cast(
        Awaitable[list[int]],
        redis.eval(
            TOKEN_BUCKET_SCRIPT,
            1,
            f"eventflow:ingest:{organization_id}",
            str(BURST_TOKENS),
            str(TOKENS_PER_SECOND),
            "4",
        ),
    )
    return None if int(allowed) == 1 else max(1, math.ceil(float(retry_after)))


async def admit_login(redis: Redis, username_hash: str) -> int | None:
    """Allow five login attempts in a burst, replenishing one every 12 seconds."""
    allowed, retry_after = await cast(
        Awaitable[list[int]],
        redis.eval(
            TOKEN_BUCKET_SCRIPT,
            1,
            f"eventflow:login:{username_hash}",
            "5",
            str(1 / 12),
            "120",
        ),
    )
    return None if int(allowed) == 1 else max(1, math.ceil(float(retry_after)))
