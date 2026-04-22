"""Tests for FlightAPI foundation: credit gate, concurrency gate, coalescer, cache.

These are fast unit tests against the in-process fallback paths — they don't
require Redis, a live FlightAPI key, or network access. Redis-backed paths are
exercised in integration tests once wired.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.flight_cache import flight_cache
from app.services.flight_coalescer import RequestCoalescer
from app.services.providers.flightapi.concurrency_gate import ConcurrencyGate
from app.services.providers.flightapi.credit_gate import (
    CreditBudgetExceeded,
    CreditBudgetGate,
)


# ---------------------------------------------------------------------------
# ConcurrencyGate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrency_gate_bounds_parallel_slots():
    gate = ConcurrencyGate(limit=3)
    observed_peak = 0
    current = 0
    lock = asyncio.Lock()

    async def worker():
        nonlocal current, observed_peak
        async with gate.slot():
            async with lock:
                current += 1
                observed_peak = max(observed_peak, current)
            await asyncio.sleep(0.01)
            async with lock:
                current -= 1

    await asyncio.gather(*(worker() for _ in range(10)))
    assert observed_peak <= 3
    assert observed_peak == 3  # saturates the gate


@pytest.mark.asyncio
async def test_concurrency_gate_releases_on_exception():
    gate = ConcurrencyGate(limit=1)

    async def boom():
        async with gate.slot():
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await boom()

    # Slot should be available again.
    async with gate.slot():
        pass


# ---------------------------------------------------------------------------
# CreditBudgetGate (in-memory fallback — no Redis)
# ---------------------------------------------------------------------------


def _patch_no_redis(monkeypatch):
    """Force the credit gate onto the in-memory fallback path."""
    from app.services import cache_service as cs_module

    async def no_redis():
        return None

    monkeypatch.setattr(cs_module.cache_service, "_get_redis", no_redis)


@pytest.mark.asyncio
async def test_credit_gate_reserve_and_refund(monkeypatch):
    _patch_no_redis(monkeypatch)
    gate = CreditBudgetGate()
    company_id = uuid.uuid4()

    async def fake_budget(_cid):
        return 10

    monkeypatch.setattr(gate, "_resolve_budget", fake_budget)

    assert await gate.remaining(company_id) == 10
    spent = await gate.reserve(company_id, credits=3)
    assert spent == 3
    assert await gate.remaining(company_id) == 7

    await gate.refund(company_id, credits=3)
    assert await gate.remaining(company_id) == 10


@pytest.mark.asyncio
async def test_credit_gate_raises_when_budget_exceeded(monkeypatch):
    _patch_no_redis(monkeypatch)
    gate = CreditBudgetGate()
    company_id = uuid.uuid4()

    async def fake_budget(_cid):
        return 5

    monkeypatch.setattr(gate, "_resolve_budget", fake_budget)

    await gate.reserve(company_id, credits=4)
    with pytest.raises(CreditBudgetExceeded):
        await gate.reserve(company_id, credits=2)
    # Failed reservation must not mutate the counter.
    assert await gate.remaining(company_id) == 1


@pytest.mark.asyncio
async def test_credit_gate_tenants_are_isolated(monkeypatch):
    _patch_no_redis(monkeypatch)
    gate = CreditBudgetGate()
    a = uuid.uuid4()
    b = uuid.uuid4()

    async def fake_budget(_cid):
        return 5

    monkeypatch.setattr(gate, "_resolve_budget", fake_budget)

    await gate.reserve(a, credits=5)
    # Company A is exhausted, B should still have full budget.
    assert await gate.remaining(a) == 0
    assert await gate.remaining(b) == 5
    await gate.reserve(b, credits=2)  # must not raise


# ---------------------------------------------------------------------------
# RequestCoalescer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coalescer_folds_concurrent_callers():
    coalescer = RequestCoalescer()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return "result"

    results = await asyncio.gather(
        *(coalescer.run("k1", factory) for _ in range(5))
    )
    assert results == ["result"] * 5
    assert calls == 1  # only one upstream invocation


@pytest.mark.asyncio
async def test_coalescer_runs_fresh_after_completion():
    coalescer = RequestCoalescer()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return calls

    assert await coalescer.run("k2", factory) == 1
    assert await coalescer.run("k2", factory) == 2  # prior entry cleared


@pytest.mark.asyncio
async def test_coalescer_propagates_exception_and_clears():
    coalescer = RequestCoalescer()

    async def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await coalescer.run("k3", boom)

    # Entry must be cleared so the next caller gets a fresh attempt.
    async def ok():
        return 42

    assert await coalescer.run("k3", ok) == 42


# ---------------------------------------------------------------------------
# FlightCache — tenant-prefixed v3 keys
# ---------------------------------------------------------------------------


def test_flight_cache_key_is_tenant_scoped():
    a = uuid.uuid4()
    b = uuid.uuid4()
    ka = flight_cache.flight_key(a, "JFK", "LAX", "2026-05-01", "economy")
    kb = flight_cache.flight_key(b, "JFK", "LAX", "2026-05-01", "economy")
    assert ka != kb
    assert "v3" in ka
    assert a.hex in ka
    assert b.hex in kb


def test_flight_cache_key_system_sentinel_for_none():
    k = flight_cache.flight_key(None, "JFK", "LAX", "2026-05-01", "economy")
    assert ":system:" in k


def test_flight_cache_month_calendar_key_shape():
    cid = uuid.uuid4()
    k = flight_cache.month_calendar_key(cid, "JFK", "LAX", 2026, 5, "economy")
    assert k.startswith("monthcal:v3:")
    assert cid.hex in k
    assert ":2026:05:" in k


# ---------------------------------------------------------------------------
# FlightAPIProvider pipeline — cache + coalesce + gates + client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_refunds_credits_on_upstream_failure(monkeypatch):
    """If the HTTP client raises, the credit gate must be refunded."""
    from app.services.providers.flightapi import provider as provider_module
    from datetime import date

    _patch_no_redis(monkeypatch)
    company_id = uuid.uuid4()

    # Fresh credit gate with budget=10, injected into the provider module.
    gate = CreditBudgetGate()

    async def budget(_cid):
        return 10

    monkeypatch.setattr(gate, "_resolve_budget", budget)
    monkeypatch.setattr(provider_module, "credit_budget_gate", gate)

    # Client raises on every call.
    client_mock = AsyncMock()
    client_mock.search_one_way.side_effect = RuntimeError("upstream down")
    client_mock.is_configured.return_value = True
    monkeypatch.setattr(provider_module, "flight_api_client", client_mock)

    # Bypass cache (always miss) and use a fresh coalescer to avoid state
    # leaking across tests.
    cache_mock = AsyncMock()
    cache_mock.get_flights.return_value = None
    cache_mock.flight_key.return_value = "test-key"
    monkeypatch.setattr(provider_module, "flight_cache", cache_mock)
    monkeypatch.setattr(provider_module, "flight_coalescer", RequestCoalescer())

    provider = provider_module.FlightAPIProvider()
    with pytest.raises(RuntimeError):
        await provider.search_flights(
            "JFK", "LAX", date(2026, 5, 1), company_id=company_id,
        )

    # The reservation must have been refunded.
    assert await gate.remaining(company_id) == 10
