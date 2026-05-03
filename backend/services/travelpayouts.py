import asyncio
import os
from datetime import date, timedelta
from typing import Optional
import httpx
from models import FlightOption, TripType

_AVIASALES_BASE = "https://www.aviasales.com"
_V3_BASE = "https://api.travelpayouts.com/aviasales/v3"

# Acceptable night-count range per trip type for flexible searches
_TRIP_DURATION_RANGE: dict[TripType, tuple[int, int]] = {
    TripType.weekend:   (2,  3),
    TripType.one_week:  (5,  9),
    TripType.two_weeks: (11, 18),
}


class TravelpayoutsService:
    def __init__(self):
        self._token = os.getenv("TRAVELPAYOUTS_TOKEN", "")

    async def get_cheapest_on_route(
        self,
        origin: str,
        origin_name: str,
        destination: str,
        depart_date: Optional[str],
        return_date: Optional[str],
        trip_type: Optional[TripType] = None,
        earliest_depart: Optional[str] = None,
        latest_return: Optional[str] = None,
        travelers: int = 1,
        nonstop_only: bool = False,
        max_duration_hours: Optional[float] = None,
    ) -> FlightOption:
        if depart_date and return_date:
            return await self._by_dates(
                origin, origin_name, destination,
                depart_date, return_date, travelers, nonstop_only,
            )
        if trip_type:
            return await self._by_flexible(
                origin, origin_name, destination,
                trip_type, earliest_depart, latest_return, travelers, nonstop_only,
            )
        raise ValueError("Provide either depart/return dates or a trip_type")

    # ── Specific-date search ────────────────────────────────────────────────
    # Round trip = cheapest outbound leg + cheapest return leg (two one-way queries).
    # Travelpayouts caches one-way prices; exact dates often have no data so we
    # fall back to a month-level query automatically.

    async def _by_dates(
        self,
        origin: str,
        origin_name: str,
        destination: str,
        depart_date: str,
        return_date: str,
        travelers: int,
        nonstop_only: bool,
    ) -> FlightOption:
        async with httpx.AsyncClient(timeout=10.0) as client:
            out_ticket, ret_ticket = await asyncio.gather(
                self._cheapest_one_way(client, origin, destination, depart_date, nonstop_only),
                self._cheapest_one_way(client, destination, origin, return_date, nonstop_only),
            )

        price_pp = out_ticket["price"] + ret_ticket["price"]
        return FlightOption(
            origin_iata=origin,
            origin_name=origin_name,
            destination_iata=destination,
            price_per_person=price_pp,
            total_price=price_pp * travelers,
            depart_date=_parse_date(out_ticket.get("departure_at", "")),
            return_date=_parse_date(ret_ticket.get("departure_at", "")),
            airline=out_ticket.get("airline"),
            outbound_url=_build_url(out_ticket.get("link")),
            return_url=_build_url(ret_ticket.get("link")),
        )

    async def _cheapest_one_way(
        self,
        client: httpx.AsyncClient,
        origin: str,
        destination: str,
        around_date: str,
        nonstop_only: bool,
    ) -> dict:
        """Try the exact date first; fall back to the full month if no cached data."""
        for date_param in [around_date, around_date[:7]]:
            resp = await client.get(
                f"{_V3_BASE}/prices_for_dates",
                params={
                    "origin": origin,
                    "destination": destination,
                    "departure_at": date_param,
                    "currency": "usd",
                    "sorting": "price",
                    "direct": str(nonstop_only).lower(),
                    "limit": 1,
                    "token": self._token,
                },
            )
            if resp.status_code == 200:
                data = resp.json().get("data") or []
                if data:
                    return data[0]

        raise ValueError(f"No flights found: {origin} → {destination} around {around_date}")

    # ── Flexible-date search ────────────────────────────────────────────────
    # Use prices_for_dates with month-level departure_at queries for both legs,
    # then find the cheapest valid day-pair matching the trip-type duration.
    # (v2/prices/month-matrix is not used here because it ignores the month
    # parameter and always returns the current cache window.)

    async def _by_flexible(
        self,
        origin: str,
        origin_name: str,
        destination: str,
        trip_type: TripType,
        earliest_depart: Optional[str],
        latest_return: Optional[str],
        travelers: int,
        nonstop_only: bool,
    ) -> FlightOption:
        window_start = date.fromisoformat(earliest_depart) if earliest_depart else date.today()
        window_end = (
            date.fromisoformat(latest_return)
            if latest_return
            else window_start + timedelta(days=90)
        )
        min_nights, max_nights = _TRIP_DURATION_RANGE[trip_type]

        out_months = _months_in_range(window_start, window_end)
        ret_months = _months_in_range(
            window_start + timedelta(days=min_nights),
            window_end,
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            out_tasks = [
                self._prices_for_month(client, origin, destination, m, nonstop_only)
                for m in out_months
            ]
            ret_tasks = [
                self._prices_for_month(client, destination, origin, m, nonstop_only)
                for m in ret_months
            ]
            all_results = await asyncio.gather(*out_tasks, *ret_tasks)

        n_out = len(out_months)
        out_entries = [e for batch in all_results[:n_out] for e in batch]
        ret_entries = [e for batch in all_results[n_out:] for e in batch]

        if not out_entries or not ret_entries:
            raise ValueError(
                f"No flexible flights found: {origin} → {destination} "
                f"between {window_start} and {window_end}"
            )

        best_total: Optional[float] = None
        best_out = best_ret = None

        for out_e in out_entries:
            out_d = date.fromisoformat(_parse_date(out_e.get("departure_at", "")))
            if out_d < window_start:
                continue
            for ret_e in ret_entries:
                ret_d = date.fromisoformat(_parse_date(ret_e.get("departure_at", "")))
                nights = (ret_d - out_d).days
                if not (min_nights <= nights <= max_nights):
                    continue
                if ret_d > window_end:
                    continue
                total = out_e["price"] + ret_e["price"]
                if best_total is None or total < best_total:
                    best_total = total
                    best_out = out_e
                    best_ret = ret_e

        if best_out is None:
            raise ValueError(
                f"No {trip_type} trip found: {origin} → {destination} "
                f"between {window_start} and {window_end}"
            )

        price_pp = best_out["price"] + best_ret["price"]
        return FlightOption(
            origin_iata=origin,
            origin_name=origin_name,
            destination_iata=destination,
            price_per_person=price_pp,
            total_price=price_pp * travelers,
            depart_date=_parse_date(best_out.get("departure_at", "")),
            return_date=_parse_date(best_ret.get("departure_at", "")),
            airline=best_out.get("airline"),
            outbound_url=_build_url(best_out.get("link")),
            return_url=_build_url(best_ret.get("link")),
        )

    async def _prices_for_month(
        self,
        client: httpx.AsyncClient,
        origin: str,
        destination: str,
        month: date,
        nonstop_only: bool,
    ) -> list[dict]:
        resp = await client.get(
            f"{_V3_BASE}/prices_for_dates",
            params={
                "origin": origin,
                "destination": destination,
                "departure_at": month.strftime("%Y-%m"),
                "currency": "usd",
                "sorting": "price",
                "direct": str(nonstop_only).lower(),
                "limit": 30,
                "token": self._token,
            },
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("data") or []


# ── Helpers ─────────────────────────────────────────────────────────────────

def _parse_date(iso_str: str) -> str:
    """Extract YYYY-MM-DD from a full ISO datetime string or return as-is."""
    return iso_str[:10] if iso_str else ""


def _build_url(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    return f"{_AVIASALES_BASE}{link}"


def _months_in_range(start: date, end: date) -> list[date]:
    months: list[date] = []
    current = start.replace(day=1)
    while current <= end.replace(day=1):
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months
