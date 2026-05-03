"""
Integration tests for POST /api/search.

Auth and validation tests run without a real API key.
Tests marked with the tp_required marker make live Travelpayouts calls
and are skipped when TRAVELPAYOUTS_TOKEN is not set.
"""
import os
import pytest
from datetime import date, timedelta

_today = date.today()
DEPART = (_today + timedelta(days=60)).strftime("%Y-%m-%d")
RETURN = (_today + timedelta(days=67)).strftime("%Y-%m-%d")
WINDOW_START = (_today + timedelta(days=50)).strftime("%Y-%m-%d")
WINDOW_END = (_today + timedelta(days=110)).strftime("%Y-%m-%d")

_tp_required = pytest.mark.skipif(
    not os.getenv("TRAVELPAYOUTS_TOKEN"),
    reason="TRAVELPAYOUTS_TOKEN not set in .env",
)

# ── Auth & validation (no API key needed) ────────────────────────────────────

async def test_missing_token_returns_401(client_no_token):
    resp = await client_no_token.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [{"name": "Los Angeles", "iata": "LAX"}],
        "depart_date": DEPART, "return_date": RETURN,
    })
    assert resp.status_code == 401


async def test_empty_destinations_returns_400(client):
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [],
        "depart_date": DEPART, "return_date": RETURN,
    })
    assert resp.status_code == 400


async def test_missing_required_fields_returns_422(client):
    """Sending a body missing origins should return a validation error."""
    resp = await client.post("/api/search", json={
        "destinations": [{"name": "Los Angeles", "iata": "LAX"}],
        "depart_date": DEPART, "return_date": RETURN,
    })
    assert resp.status_code == 422


async def test_health_endpoint_is_public():
    """The /health endpoint must not require a token."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── Live API tests ────────────────────────────────────────────────────────────

@_tp_required
async def test_end_to_end_two_origins_two_destinations(client):
    """Core use-case: 2 origins, 2 destinations, results sorted by cost."""
    resp = await client.post("/api/search", json={
        "origins": [
            {"name": "New York", "iata": "JFK", "travelers": 2},
            {"name": "Boston", "iata": "BOS", "travelers": 1},
        ],
        "destinations": [
            {"name": "Los Angeles", "iata": "LAX"},
            {"name": "Miami", "iata": "MIA"},
        ],
        "depart_date": DEPART,
        "return_date": RETURN,
    })
    assert resp.status_code == 200
    results = resp.json()
    assert isinstance(results, list)
    assert len(results) >= 1

    for r in results:
        assert r["destination_iata"] in ("LAX", "MIA")
        assert r["flight_cost"] > 0
        assert r["total_cost"] >= r["flight_cost"]  # lodging is 0 until Phase 3
        assert len(r["flights"]) == 2              # one leg per origin
        for f in r["flights"]:
            assert f["price_per_person"] > 0
            assert f["total_price"] > 0
            assert f["outbound_url"] is not None
            assert f["outbound_url"].startswith("https://")


@_tp_required
async def test_results_sorted_by_total_cost(client):
    resp = await client.post("/api/search", json={
        "origins": [{"name": "Chicago", "iata": "ORD", "travelers": 1}],
        "destinations": [
            {"name": "Los Angeles", "iata": "LAX"},
            {"name": "Miami", "iata": "MIA"},
        ],
        "depart_date": DEPART,
        "return_date": RETURN,
    })
    assert resp.status_code == 200
    results = resp.json()
    costs = [r["total_cost"] for r in results]
    assert costs == sorted(costs), "Results must be sorted ascending by total_cost"


@_tp_required
async def test_single_traveler_total_equals_per_person(client):
    """With 1 traveler, total_price must equal price_per_person."""
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [{"name": "Los Angeles", "iata": "LAX"}],
        "depart_date": DEPART,
        "return_date": RETURN,
    })
    assert resp.status_code == 200
    results = resp.json()
    for r in results:
        for f in r["flights"]:
            assert f["total_price"] == pytest.approx(f["price_per_person"])


@_tp_required
async def test_destination_name_propagated(client):
    """destination_name should be the human name, not just the IATA code."""
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [{"name": "Los Angeles", "iata": "LAX"}],
        "depart_date": DEPART,
        "return_date": RETURN,
    })
    assert resp.status_code == 200
    results = resp.json()
    if results:
        assert results[0]["destination_name"] == "Los Angeles"
        assert results[0]["flights"][0]["origin_name"] == "New York"


@_tp_required
async def test_failed_destination_skipped_not_fatal(client):
    """One bad destination should be silently dropped; valid ones still return."""
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [
            {"name": "Los Angeles", "iata": "LAX"},  # valid
            {"name": "Nowhere", "iata": "ZZZ"},       # invalid — no flights
        ],
        "depart_date": DEPART,
        "return_date": RETURN,
    })
    assert resp.status_code == 200
    results = resp.json()
    # ZZZ should have been dropped; LAX should still appear
    iatas = [r["destination_iata"] for r in results]
    assert "LAX" in iatas
    assert "ZZZ" not in iatas


@_tp_required
async def test_nonstop_only_flag_accepted(client):
    """nonstop_only=True should complete without error on a major route."""
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [{"name": "Los Angeles", "iata": "LAX"}],
        "depart_date": DEPART,
        "return_date": RETURN,
        "flight_constraints": {"nonstop_only": True},
    })
    assert resp.status_code == 200


@_tp_required
async def test_flexible_weekend_search(client):
    """Flexible weekend search should return flights with 2-3 night duration."""
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [{"name": "Miami", "iata": "MIA"}],
        "trip_type": "weekend",
        "earliest_depart": WINDOW_START,
        "latest_return": WINDOW_END,
    })
    assert resp.status_code == 200
    results = resp.json()
    if results:
        f = results[0]["flights"][0]
        nights = (
            date.fromisoformat(f["return_date"]) - date.fromisoformat(f["depart_date"])
        ).days
        assert 2 <= nights <= 3


@_tp_required
async def test_flexible_one_week_search(client):
    resp = await client.post("/api/search", json={
        "origins": [{"name": "New York", "iata": "JFK", "travelers": 1}],
        "destinations": [{"name": "Miami", "iata": "MIA"}],
        "trip_type": "one_week",
        "earliest_depart": WINDOW_START,
        "latest_return": WINDOW_END,
    })
    assert resp.status_code == 200
    results = resp.json()
    if results:
        f = results[0]["flights"][0]
        nights = (
            date.fromisoformat(f["return_date"]) - date.fromisoformat(f["depart_date"])
        ).days
        assert 6 <= nights <= 8
