"""Google Places API client for restaurant data enrichment."""

import os
import time
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus

import requests
import backoff

from .models import Restaurant

logger = logging.getLogger(__name__)


class GooglePlacesError(Exception):
    """Raised when Google Places API returns an error."""

    pass


class GooglePlacesClient:
    """Client for Google Places API."""

    BASE_URL = "https://maps.googleapis.com/maps/api/place"
    FIND_PLACE_ENDPOINT = "/findplacefromtext/json"
    DETAILS_ENDPOINT = "/details/json"
    TEXT_SEARCH_ENDPOINT = "/textsearch/json"

    # Rate limiting: Stay well under quota
    CALLS_PER_MINUTE = 10

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Google Places client.

        Args:
            api_key: Google Places API key. If not provided, reads from env var.
        """
        self.api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Google Places API key required. Set GOOGLE_PLACES_API_KEY env var."
            )

        self.session = requests.Session()
        self._last_request_time = 0
        self._min_request_interval = 60.0 / self.CALLS_PER_MINUTE

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=3)
    def _make_request(
        self, endpoint: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make a rate-limited request to the Google Places API.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            GooglePlacesError: If API returns an error.
        """
        # Simple rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)

        url = f"{self.BASE_URL}{endpoint}"
        params["key"] = self.api_key

        try:
            response = self.session.get(url, params=params, timeout=30)
            self._last_request_time = time.time()
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status not in ("OK", "ZERO_RESULTS"):
                error_msg = data.get("error_message", "Unknown error")
                raise GooglePlacesError(
                    f"Google Places API error: {status} - {error_msg}"
                )

            return data

        except requests.HTTPError as e:
            raise GooglePlacesError(f"Google Places API HTTP error: {e}") from e

    def find_place(
        self,
        query: str,
        location_bias: Optional[tuple] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find a place by text query.

        Args:
            query: Search query (e.g., restaurant name + address).
            location_bias: Optional (lat, lng) tuple to bias results.

        Returns:
            Place candidate or None if not found.
        """
        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "place_id,name,formatted_address,geometry",
        }

        if location_bias:
            lat, lng = location_bias
            params["locationbias"] = f"point:{lat},{lng}"

        data = self._make_request(self.FIND_PLACE_ENDPOINT, params)

        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0]
        return None

    def get_place_details(
        self,
        place_id: str,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get detailed information about a place.

        Args:
            place_id: Google Place ID.
            fields: List of fields to return. If None, returns common fields.

        Returns:
            Place details dictionary.
        """
        if fields is None:
            fields = [
                "place_id",
                "name",
                "formatted_address",
                "formatted_phone_number",
                "website",
                "url",  # Google Maps URL
                "rating",
                "user_ratings_total",
                "price_level",
                "opening_hours",
                "business_status",
                "geometry",
            ]

        params = {
            "place_id": place_id,
            "fields": ",".join(fields),
        }

        data = self._make_request(self.DETAILS_ENDPOINT, params)
        return data.get("result", {})

    def search_restaurant(
        self,
        name: str,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Search for a specific restaurant and get its details.

        Args:
            name: Restaurant name.
            address: Restaurant address.
            latitude: Restaurant latitude (for location bias).
            longitude: Restaurant longitude (for location bias).

        Returns:
            Restaurant details or None if not found.
        """
        # Build search query
        query_parts = [name]
        if address:
            query_parts.append(address)
        else:
            query_parts.append("Manhattan, NY")

        query = " ".join(query_parts)

        # Set location bias if coordinates provided
        location_bias = None
        if latitude and longitude:
            location_bias = (latitude, longitude)

        # Find the place
        place = self.find_place(query, location_bias)

        if not place:
            logger.debug(f"Could not find place for: {query}")
            return None

        # Get detailed information
        place_id = place.get("place_id")
        if not place_id:
            return None

        try:
            details = self.get_place_details(place_id)
            return details
        except GooglePlacesError as e:
            logger.error(f"Error getting details for {name}: {e}")
            return None

    def enrich_restaurant(self, restaurant: Restaurant) -> Restaurant:
        """Enrich a Restaurant object with Google Places data.

        Args:
            restaurant: Restaurant object with at least name and location.

        Returns:
            Restaurant object with Google data added.
        """
        details = self.search_restaurant(
            name=restaurant.name,
            address=restaurant.address,
            latitude=restaurant.latitude,
            longitude=restaurant.longitude,
        )

        if not details:
            logger.debug(f"No Google data found for: {restaurant.name}")
            return restaurant

        # Update restaurant with Google data
        restaurant.google_place_id = details.get("place_id")
        restaurant.google_rating = details.get("rating")
        restaurant.google_review_count = details.get("user_ratings_total")

        # Google Maps URL
        google_url = details.get("url")
        if google_url:
            restaurant.google_maps_url = google_url
            # The Google Business Profile URL is the Maps URL
            restaurant.google_business_profile_url = google_url

        # Website
        website = details.get("website")
        if website and not restaurant.website_url:
            restaurant.website_url = website

        # Check if business is operational
        business_status = details.get("business_status")
        if business_status and business_status != "OPERATIONAL":
            restaurant.is_open = False

        # Update phone if not already set
        phone = details.get("formatted_phone_number")
        if phone and not restaurant.phone:
            restaurant.phone = phone

        return restaurant

    def enrich_restaurants(
        self,
        restaurants: List[Restaurant],
        progress_callback=None,
    ) -> List[Restaurant]:
        """Enrich multiple restaurants with Google Places data.

        Args:
            restaurants: List of Restaurant objects.
            progress_callback: Optional callback function for progress updates.

        Returns:
            List of enriched Restaurant objects.
        """
        enriched = []
        total = len(restaurants)

        for i, restaurant in enumerate(restaurants):
            try:
                enriched_restaurant = self.enrich_restaurant(restaurant)
                enriched.append(enriched_restaurant)
            except Exception as e:
                logger.error(f"Error enriching {restaurant.name}: {e}")
                enriched.append(restaurant)

            if progress_callback:
                progress_callback(i + 1, total)

            if (i + 1) % 50 == 0:
                logger.info(f"Enriched {i + 1}/{total} restaurants with Google data")

        return enriched
