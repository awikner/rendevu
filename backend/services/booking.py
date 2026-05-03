import os
from models import LodgingOption, LodgingPreferences


class BookingService:
    def __init__(self):
        self._affiliate_id = os.getenv("BOOKING_AFFILIATE_ID", "")
        self._api_key = os.getenv("BOOKING_API_KEY", "")

    async def search_lodging(
        self,
        city_iata: str,
        checkin: str,
        checkout: str,
        preferences: LodgingPreferences,
        total_travelers: int,
        nights: int,
    ) -> list[LodgingOption]:
        # Pending Booking.com affiliate credentials
        raise NotImplementedError(
            "Booking.com lodging search pending affiliate credentials"
        )
