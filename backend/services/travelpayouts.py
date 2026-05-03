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

    async def get_flexible_price_map(
        self,
        origin: str,
        destination: str,
        trip_type: TripType,
        earliest_depart: Optional[str],
        latest_return: Optional[str],
        nonstop_only: bool = False,
    ) -> dict[tuple[str, str], tuple[dict, dict]]:
        """Return all valid {(depart_date, return_date): (out_entry, ret_entry)} pairs.

        Callers that need to coordinate travel dates across multiple origins
        (so everyone flies on the same days) should use this directly instead
        of get_cheapest_on_route.
        """
        window_start = date.fromisoformat(earliest_depart) if earliest_depart else date.today()
        window_end = (
            date.fromisoformat(latest_return)
            if latest_return
            else window_start + timedelta(days=90)
        )
        min_nights, max_nights = _TRIP_DURATION_RANGE[trip_type]

        async with httpx.AsyncClient(timeout=30.0) as client:
            if trip_type == TripType.weekend:
                # Month-level queries only return the cheapest N flights, which tend
                # to be mid-week. For weekends, query each Fri/Sat and Sun/Mon date
                # directly so we only get data for the days we actually want.
                # weekday() → 0=Mon … 4=Fri, 5=Sat, 6=Sun
                out_dates = _dates_with_weekdays(window_start, window_end, {4, 5})
                ret_dates = _dates_with_weekdays(
                    window_start + timedelta(days=min_nights), window_end, {6, 0}
                )
                out_raw, ret_raw = await asyncio.gather(
                    asyncio.gather(*[
                        self._price_on_date(client, origin, destination, d, nonstop_only)
                        for d in out_dates
                    ]),
                    asyncio.gather(*[
                        self._price_on_date(client, destination, origin, d, nonstop_only)
                        for d in ret_dates
                    ]),
                )
                out_entries = [e for e in out_raw if e is not None]
                ret_entries = [e for e in ret_raw if e is not None]
            else:
                out_months = _months_in_range(window_start, window_end)
                ret_months = _months_in_range(
                    window_start + timedelta(days=min_nights), window_end,
                )
                all_results = await asyncio.gather(
                    *[self._prices_for_month(client, origin, destination, m, nonstop_only)
                      for m in out_months],
                    *[self._prices_for_month(client, destination, origin, m, nonstop_only)
                      for m in ret_months],
                )
                n_out = len(out_months)
                out_entries = [e for batch in all_results[:n_out] for e in batch]
                ret_entries = [e for batch in all_results[n_out:] for e in batch]

        price_map = self._build_price_map(out_entries, ret_entries, window_start, window_end, min_nights, max_nights)

        # Fallback for weekends: if no cached pairs land on Fri/Sat→Sun/Mon (common
        # when the price cache is sparse), retry with month-level queries and accept
        # any 2-3 night combination so the search still returns a result.
        if not price_map and trip_type == TripType.weekend:
            out_months = _months_in_range(window_start, window_end)
            ret_months = _months_in_range(window_start + timedelta(days=min_nights), window_end)
            async with httpx.AsyncClient(timeout=30.0) as client:
                all_results = await asyncio.gather(
                    *[self._prices_for_month(client, origin, destination, m, nonstop_only)
                      for m in out_months],
                    *[self._prices_for_month(client, destination, origin, m, nonstop_only)
                      for m in ret_months],
                )
            n_out = len(out_months)
            out_entries = [e for batch in all_results[:n_out] for e in batch]
            ret_entries = [e for batch in all_results[n_out:] for e in batch]
            price_map = self._build_price_map(out_entries, ret_entries, window_start, window_end, min_nights, max_nights)

        return price_map

    @staticmethod
    def _build_price_map(
        out_entries: list[dict],
        ret_entries: list[dict],
        window_start: date,
        window_end: date,
        min_nights: int,
        max_nights: int,
    ) -> dict[tuple[str, str], tuple[dict, dict]]:
        price_map: dict[tuple[str, str], tuple[dict, dict]] = {}
        for out_e in out_entries:
            out_d = date.fromisoformat(_parse_date(out_e.get("departure_at", "")))
            if out_d < window_start or out_d > window_end:
                continue
            for ret_e in ret_entries:
                ret_d = date.fromisoformat(_parse_date(ret_e.get("departure_at", "")))
                nights = (ret_d - out_d).days
                if not (min_nights <= nights <= max_nights):
                    continue
                if ret_d > window_end:
                    continue
                key = (_parse_date(out_e["departure_at"]), _parse_date(ret_e["departure_at"]))
                total = out_e["price"] + ret_e["price"]
                if key not in price_map or total < price_map[key][0]["price"] + price_map[key][1]["price"]:
                    price_map[key] = (out_e, ret_e)
        return price_map

    async def _price_on_date(
        self,
        client: httpx.AsyncClient,
        origin: str,
        destination: str,
        departure_date: date,
        nonstop_only: bool,
    ) -> Optional[dict]:
        """Return the cheapest cached price for an exact departure date, or None."""
        date_str = departure_date.strftime("%Y-%m-%d")
        resp = await client.get(
            f"{_V3_BASE}/prices_for_dates",
            params={
                "origin": origin,
                "destination": destination,
                "departure_at": date_str,
                "currency": "usd",
                "sorting": "price",
                "direct": str(nonstop_only).lower(),
                "limit": 1,
                "token": self._token,
            },
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or []
        if not data:
            return None
        entry = data[0]
        # Reject if the API returned a flight on a different date
        if _parse_date(entry.get("departure_at", "")) != date_str:
            return None
        return entry

    def flight_option_from_entries(
        self,
        origin: str,
        origin_name: str,
        destination: str,
        out_entry: dict,
        ret_entry: dict,
        travelers: int,
    ) -> FlightOption:
        price_pp = out_entry["price"] + ret_entry["price"]
        return FlightOption(
            origin_iata=origin,
            origin_name=origin_name,
            destination_iata=destination,
            price_per_person=price_pp,
            total_price=price_pp * travelers,
            depart_date=_parse_date(out_entry.get("departure_at", "")),
            return_date=_parse_date(ret_entry.get("departure_at", "")),
            airline=out_entry.get("airline"),
            outbound_url=_build_url(out_entry.get("link")),
            return_url=_build_url(ret_entry.get("link")),
        )

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
        price_map = await self.get_flexible_price_map(
            origin, destination, trip_type, earliest_depart, latest_return, nonstop_only,
        )
        if not price_map:
            window_start = date.fromisoformat(earliest_depart) if earliest_depart else date.today()
            window_end = (
                date.fromisoformat(latest_return)
                if latest_return
                else window_start + timedelta(days=90)
            )
            raise ValueError(
                f"No {trip_type} trip found: {origin} → {destination} "
                f"between {window_start} and {window_end}"
            )
        best_key = min(price_map, key=lambda k: price_map[k][0]["price"] + price_map[k][1]["price"])
        out_e, ret_e = price_map[best_key]
        return self.flight_option_from_entries(origin, origin_name, destination, out_e, ret_e, travelers)

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


def _dates_with_weekdays(start: date, end: date, weekdays: set[int]) -> list[date]:
    return [
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() in weekdays
    ]


def _months_in_range(start: date, end: date) -> list[date]:
    months: list[date] = []
    current = start.replace(day=1)
    while current <= end.replace(day=1):
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months
