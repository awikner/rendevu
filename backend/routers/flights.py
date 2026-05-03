import asyncio
from datetime import date
from fastapi import APIRouter, HTTPException
from models import SearchRequest, DestinationResult, DestinationCity, FlightOption
from services.travelpayouts import TravelpayoutsService
from services.booking import BookingService

router = APIRouter()
_tp = TravelpayoutsService()
_booking = BookingService()


async def _fetch_fixed_flights(
    request: SearchRequest, destination: DestinationCity
) -> list[FlightOption]:
    """Specific-date search: each origin queries independently (dates are already fixed)."""
    tasks = [
        _tp.get_cheapest_on_route(
            origin=o.iata,
            origin_name=o.name,
            destination=destination.iata,
            depart_date=request.depart_date,
            return_date=request.return_date,
            travelers=o.travelers,
            nonstop_only=request.flight_constraints.nonstop_only,
            max_duration_hours=request.flight_constraints.max_duration_hours,
        )
        for o in request.origins
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    if any(isinstance(r, Exception) for r in results):
        errors = [str(r) for r in results if isinstance(r, Exception)]
        raise ValueError(f"Incomplete flights for {destination.iata}: {'; '.join(errors)}")
    return list(results)  # type: ignore[return-value]


async def _fetch_flexible_flights(
    request: SearchRequest, destination: DestinationCity
) -> list[FlightOption]:
    """Flexible-date search: find the cheapest date pair shared by ALL origins so the
    group travels on the same days."""
    map_tasks = [
        _tp.get_flexible_price_map(
            origin=o.iata,
            destination=destination.iata,
            trip_type=request.trip_type,  # type: ignore[arg-type]
            earliest_depart=request.earliest_depart,
            latest_return=request.latest_return,
            nonstop_only=request.flight_constraints.nonstop_only,
        )
        for o in request.origins
    ]
    price_maps = await asyncio.gather(*map_tasks, return_exceptions=True)
    if any(isinstance(m, Exception) for m in price_maps):
        errors = [str(m) for m in price_maps if isinstance(m, Exception)]
        raise ValueError(f"Incomplete flights for {destination.iata}: {'; '.join(errors)}")

    # Intersection: only keep date pairs available for every origin
    shared = set(price_maps[0].keys())  # type: ignore[union-attr]
    for pm in price_maps[1:]:
        shared &= pm.keys()  # type: ignore[union-attr]
    if not shared:
        raise ValueError(
            f"No shared travel dates found for all origins → {destination.iata}"
        )

    # Pick the date pair with the lowest combined cost across all travelers
    best_pair = min(
        shared,
        key=lambda p: sum(
            (pm[p][0]["price"] + pm[p][1]["price"]) * o.travelers
            for o, pm in zip(request.origins, price_maps)
        ),
    )

    return [
        _tp.flight_option_from_entries(
            origin=o.iata,
            origin_name=o.name,
            destination=destination.iata,
            out_entry=pm[best_pair][0],
            ret_entry=pm[best_pair][1],
            travelers=o.travelers,
        )
        for o, pm in zip(request.origins, price_maps)
    ]


@router.post("/search", response_model=list[DestinationResult])
async def search(request: SearchRequest) -> list[DestinationResult]:
    if not request.destinations:
        raise HTTPException(status_code=400, detail="At least one destination is required")

    tasks = [_fetch_destination(request, dest) for dest in request.destinations]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in raw if isinstance(r, DestinationResult)]
    if not results:
        raise HTTPException(
            status_code=404,
            detail="No flights found for any of the requested destinations.",
        )
    return sorted(results, key=lambda r: r.total_cost)


async def _fetch_destination(
    request: SearchRequest, destination: DestinationCity
) -> DestinationResult:
    if request.trip_type:
        flights = await _fetch_flexible_flights(request, destination)
    else:
        flights = await _fetch_fixed_flights(request, destination)
    flight_cost = sum(f.total_price for f in flights)

    nights = _nights_from_request(request)
    total_travelers = sum(o.travelers for o in request.origins)
    try:
        lodging_options = await _booking.search_lodging(
            city_iata=destination.iata,
            checkin=request.depart_date or "",
            checkout=request.return_date or "",
            preferences=request.lodging,
            total_travelers=total_travelers,
            nights=nights,
        )
    except NotImplementedError:
        lodging_options = []
    lodging_cost = lodging_options[0].total_price if lodging_options else 0.0

    return DestinationResult(
        destination_iata=destination.iata,
        destination_name=destination.name,
        total_cost=flight_cost + lodging_cost,
        flight_cost=flight_cost,
        lodging_cost=lodging_cost,
        flights=flights,
        lodging_options=lodging_options,
    )


def _nights_from_request(request: SearchRequest) -> int:
    if request.depart_date and request.return_date:
        delta = date.fromisoformat(request.return_date) - date.fromisoformat(request.depart_date)
        return max(delta.days, 1)
    if request.trip_type:
        return {"weekend": 2, "one_week": 7, "two_weeks": 14}[request.trip_type]
    return 7
