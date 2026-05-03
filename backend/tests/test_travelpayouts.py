"""
Integration tests for TravelpayoutsService.

These tests make real HTTP calls to the Travelpayouts API and require
TRAVELPAYOUTS_TOKEN to be set in backend/.env.
"""
import os
import pytest
from datetime import date, timedelta
from services.travelpayouts import TravelpayoutsService
from models import TripType

pytestmark = pytest.mark.skipif(
    not os.getenv("TRAVELPAYOUTS_TOKEN"),
    reason="TRAVELPAYOUTS_TOKEN not set in .env",
)

# ── Test dates ───────────────────────────────────────────────────────────────
# Use dates ~2 months out to maximize chance of cached API data
_today = date.today()
DEPART = (_today + timedelta(days=60)).strftime("%Y-%m-%d")
RETURN = (_today + timedelta(days=67)).strftime("%Y-%m-%d")   # 7-night trip
WINDOW_START = (_today + timedelta(days=50)).strftime("%Y-%m-%d")
WINDOW_END = (_today + timedelta(days=110)).strftime("%Y-%m-%d")  # wide enough for 2-week trips


@pytest.fixture
def tp():
    return TravelpayoutsService()


# ── Specific-date tests ──────────────────────────────────────────────────────

async def test_specific_dates_returns_valid_flight(tp):
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="LAX",
        depart_date=DEPART, return_date=RETURN, travelers=1,
    )
    assert result.origin_iata == "JFK"
    assert result.destination_iata == "LAX"
    assert result.origin_name == "New York"
    assert result.price_per_person > 0
    assert result.total_price == pytest.approx(result.price_per_person)
    assert result.depart_date != ""
    assert result.return_date != ""
    assert result.outbound_url is not None
    assert result.outbound_url.startswith("https://")


async def test_specific_dates_total_scales_with_travelers(tp):
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="LAX",
        depart_date=DEPART, return_date=RETURN, travelers=3,
    )
    assert result.total_price == pytest.approx(result.price_per_person * 3)


async def test_specific_dates_second_route(tp):
    """BOS → MIA should also have data on a popular domestic route."""
    result = await tp.get_cheapest_on_route(
        origin="BOS", origin_name="Boston", destination="MIA",
        depart_date=DEPART, return_date=RETURN, travelers=1,
    )
    assert result.price_per_person > 0
    assert result.outbound_url is not None


async def test_nonstop_only_returns_result(tp):
    """Nonstop filter should still return a valid result on a major route."""
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="LAX",
        depart_date=DEPART, return_date=RETURN,
        travelers=1, nonstop_only=True,
    )
    assert result.price_per_person > 0


async def test_invalid_iata_raises(tp):
    """A nonsense route should raise ValueError (API returns empty data)."""
    with pytest.raises((ValueError, Exception)):
        await tp.get_cheapest_on_route(
            origin="ZZZ", origin_name="Nowhere", destination="QQQ",
            depart_date=DEPART, return_date=RETURN, travelers=1,
        )


# ── Flexible-date tests ──────────────────────────────────────────────────────

async def test_flexible_weekend_duration(tp):
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="MIA",
        depart_date=None, return_date=None,
        trip_type=TripType.weekend,
        earliest_depart=WINDOW_START, latest_return=WINDOW_END,
        travelers=1,
    )
    assert result.price_per_person > 0
    nights = (
        date.fromisoformat(result.return_date) - date.fromisoformat(result.depart_date)
    ).days
    assert 2 <= nights <= 3, f"Expected weekend (2-3 nights), got {nights}"


async def test_flexible_one_week_duration(tp):
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="MIA",
        depart_date=None, return_date=None,
        trip_type=TripType.one_week,
        earliest_depart=WINDOW_START, latest_return=WINDOW_END,
        travelers=1,
    )
    assert result.price_per_person > 0
    nights = (
        date.fromisoformat(result.return_date) - date.fromisoformat(result.depart_date)
    ).days
    assert 6 <= nights <= 8, f"Expected one week (6-8 nights), got {nights}"


async def test_flexible_two_weeks_duration(tp):
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="MIA",
        depart_date=None, return_date=None,
        trip_type=TripType.two_weeks,
        earliest_depart=WINDOW_START, latest_return=WINDOW_END,
        travelers=1,
    )
    assert result.price_per_person > 0
    nights = (
        date.fromisoformat(result.return_date) - date.fromisoformat(result.depart_date)
    ).days
    assert 11 <= nights <= 18, f"Expected ~two weeks (11-18 nights), got {nights}"


async def test_flexible_respects_window_bounds(tp):
    """Returned dates must fall within the requested travel window."""
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="MIA",
        depart_date=None, return_date=None,
        trip_type=TripType.one_week,
        earliest_depart=WINDOW_START, latest_return=WINDOW_END,
        travelers=1,
    )
    assert result.depart_date >= WINDOW_START
    assert result.return_date <= WINDOW_END


async def test_flexible_no_date_window_defaults_to_90_days(tp):
    """When no date window is given, should still return a result."""
    result = await tp.get_cheapest_on_route(
        origin="JFK", origin_name="New York", destination="LAX",
        depart_date=None, return_date=None,
        trip_type=TripType.weekend,
        earliest_depart=None, latest_return=None,
        travelers=1,
    )
    assert result.price_per_person > 0
