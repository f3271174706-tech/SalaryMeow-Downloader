from __future__ import annotations

import pytest

from app.infrastructure.rate_limit import AsyncConcurrencyLimit, ConcurrencyLimitExceeded


@pytest.mark.asyncio
async def test_async_limit_stays_acquired_until_explicit_release() -> None:
    limit = AsyncConcurrencyLimit(1)
    await limit.acquire()

    with pytest.raises(ConcurrencyLimitExceeded):
        await limit.acquire()

    limit.release()
    await limit.acquire()
    limit.release()
