from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class TripType(str, Enum):
    weekend = "weekend"
    one_week = "one_week"
    two_weeks = "two_weeks"


class LodgingType(str, Enum):
    hotel = "hotel"
    vacation_rental = "vacation_rental"
    any = "any"


class OriginCity(BaseModel):
    name: str
    iata: str = Field(..., description="IATA airport code, e.g. JFK")
    travelers: int = Field(..., ge=1)


class FlightConstraints(BaseModel):
    nonstop_only: bool = False
    max_duration_hours: Optional[float] = None


class LodgingPreferences(BaseModel):
    rooms: int = Field(1, ge=1)
    type: LodgingType = LodgingType.any
    min_rating: Optional[float] = Field(None, ge=1.0, le=5.0)


class DestinationCity(BaseModel):
    name: str
    iata: str = Field(..., description="IATA airport code, e.g. CDG")


class SearchRequest(BaseModel):
    origins: list[OriginCity]
    destinations: list[DestinationCity]
    depart_date: Optional[str] = Field(None, description="YYYY-MM-DD, used with specific dates")
    return_date: Optional[str] = Field(None, description="YYYY-MM-DD, used with specific dates")
    trip_type: Optional[TripType] = Field(None, description="Used when no specific dates given")
    earliest_depart: Optional[str] = Field(None, description="YYYY-MM-DD, start of acceptable travel window")
    latest_return: Optional[str] = Field(None, description="YYYY-MM-DD, end of acceptable travel window")
    flight_constraints: FlightConstraints = Field(default_factory=FlightConstraints)
    lodging: LodgingPreferences = Field(default_factory=LodgingPreferences)


class FlightOption(BaseModel):
    origin_iata: str
    origin_name: str
    destination_iata: str
    price_per_person: float
    total_price: float
    depart_date: str
    return_date: str
    airline: Optional[str] = None
    outbound_url: Optional[str] = None   # link to book the outbound leg
    return_url: Optional[str] = None     # link to book the return leg


class LodgingOption(BaseModel):
    name: str
    type: str
    price_per_night: float
    total_price: float
    nights: int
    rating: Optional[float] = None
    booking_url: Optional[str] = None


class DestinationResult(BaseModel):
    destination_iata: str
    destination_name: str
    total_cost: float
    flight_cost: float
    lodging_cost: float
    flights: list[FlightOption]
    lodging_options: list[LodgingOption]
