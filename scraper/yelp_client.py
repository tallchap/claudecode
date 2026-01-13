"""Yelp Fusion API client for restaurant search."""

import os
import time
import logging
from typing import List, Optional, Dict, Any, Iterator
from dataclasses import dataclass

import requests
import backoff

from .models import Restaurant

logger = logging.getLogger(__name__)


class YelpAPIError(Exception):
    """Raised when Yelp API returns an error."""

    pass


class YelpClient:
    """Client for Yelp Fusion API."""

    BASE_URL = "https://api.yelp.com/v3"
    SEARCH_ENDPOINT = "/businesses/search"
    BUSINESS_ENDPOINT = "/businesses/{id}"

    # Yelp API limits
    MAX_RESULTS_PER_REQUEST = 50
    MAX_OFFSET = 1000  # Yelp limits to 1000 results per search

    # Rate limiting: 5000 calls/day = ~3.5 per minute to be safe
    CALLS_PER_MINUTE = 3

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Yelp client.

        Args:
            api_key: Yelp Fusion API key. If not provided, reads from YELP_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("YELP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Yelp API key required. Set YELP_API_KEY env var or pass api_key parameter."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            }
        )
        self._last_request_time = 0
        self._min_request_interval = 60.0 / self.CALLS_PER_MINUTE  # seconds between requests

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=3)
    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a rate-limited request to the Yelp API.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            YelpAPIError: If API returns an error.
        """
        # Simple rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)

        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            self._last_request_time = time.time()
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass
            raise YelpAPIError(
                f"Yelp API error: {e}. Response: {error_data}"
            ) from e

    def search_restaurants(
        self,
        location: str = "Manhattan, NY",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius: int = 10000,
        categories: Optional[List[str]] = None,
        price: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "best_match",
    ) -> Dict[str, Any]:
        """Search for restaurants.

        Args:
            location: Location string (e.g., "Manhattan, NY").
            latitude: Latitude for center of search.
            longitude: Longitude for center of search.
            radius: Search radius in meters (max 40000).
            categories: List of category aliases to filter by.
            price: Price level filter (e.g., "4" for $$$$, "3,4" for $$$ and $$$$).
            limit: Number of results per request (max 50).
            offset: Offset for pagination (max 1000).
            sort_by: Sort order (best_match, rating, review_count, distance).

        Returns:
            API response with businesses and total count.
        """
        params = {
            "term": "restaurants",
            "limit": min(limit, self.MAX_RESULTS_PER_REQUEST),
            "offset": min(offset, self.MAX_OFFSET),
            "sort_by": sort_by,
        }

        # Use coordinates if provided, otherwise use location string
        if latitude and longitude:
            params["latitude"] = latitude
            params["longitude"] = longitude
            params["radius"] = min(radius, 40000)
        else:
            params["location"] = location

        if categories:
            params["categories"] = ",".join(categories)

        if price:
            params["price"] = price

        return self._make_request(self.SEARCH_ENDPOINT, params)

    def get_business(self, business_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific business.

        Args:
            business_id: Yelp business ID.

        Returns:
            Business details.
        """
        endpoint = self.BUSINESS_ENDPOINT.format(id=business_id)
        return self._make_request(endpoint)

    def search_all_restaurants(
        self,
        location: str = "Manhattan, NY",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius: int = 10000,
        categories: Optional[List[str]] = None,
        price: Optional[str] = None,
        max_results: int = 1000,
        sort_by: str = "best_match",
    ) -> Iterator[Dict[str, Any]]:
        """Search for all restaurants matching criteria with automatic pagination.

        Args:
            location: Location string.
            latitude: Latitude for center of search.
            longitude: Longitude for center of search.
            radius: Search radius in meters.
            categories: List of category aliases.
            price: Price level filter.
            max_results: Maximum number of results to return.
            sort_by: Sort order.

        Yields:
            Business dictionaries.
        """
        offset = 0
        total_fetched = 0

        while total_fetched < max_results:
            try:
                response = self.search_restaurants(
                    location=location,
                    latitude=latitude,
                    longitude=longitude,
                    radius=radius,
                    categories=categories,
                    price=price,
                    limit=self.MAX_RESULTS_PER_REQUEST,
                    offset=offset,
                    sort_by=sort_by,
                )
            except YelpAPIError as e:
                logger.error(f"Error searching restaurants at offset {offset}: {e}")
                break

            businesses = response.get("businesses", [])
            total = response.get("total", 0)

            if not businesses:
                break

            for business in businesses:
                if total_fetched >= max_results:
                    break
                yield business
                total_fetched += 1

            offset += len(businesses)

            # Yelp limits offset to 1000
            if offset >= min(total, self.MAX_OFFSET):
                logger.info(
                    f"Reached Yelp pagination limit. Fetched {total_fetched} of {total} total."
                )
                break

            logger.debug(f"Fetched {total_fetched} restaurants so far...")

    def search_high_end_manhattan(
        self,
        target_count: int = 1000,
        categories: Optional[List[str]] = None,
        include_three_dollar: bool = True,
    ) -> List[Restaurant]:
        """Search for high-end restaurants in Manhattan.

        First tries to get $$$$ restaurants. If not enough, also includes $$$ restaurants.

        Args:
            target_count: Target number of restaurants to find.
            categories: Categories to search. If None, searches all restaurants.
            include_three_dollar: Include $$$ if not enough $$$$ found.

        Returns:
            List of Restaurant objects.
        """
        restaurants = []
        seen_ids = set()

        # Manhattan approximate bounds for grid search
        manhattan_areas = [
            {"name": "Lower Manhattan", "lat": 40.7128, "lng": -74.0060},
            {"name": "Midtown", "lat": 40.7549, "lng": -73.9840},
            {"name": "Upper East Side", "lat": 40.7736, "lng": -73.9566},
            {"name": "Upper West Side", "lat": 40.7870, "lng": -73.9754},
            {"name": "Harlem", "lat": 40.8116, "lng": -73.9465},
            {"name": "East Village", "lat": 40.7265, "lng": -73.9815},
            {"name": "West Village", "lat": 40.7336, "lng": -74.0027},
            {"name": "Chelsea", "lat": 40.7465, "lng": -74.0014},
            {"name": "SoHo", "lat": 40.7233, "lng": -73.9961},
            {"name": "Tribeca", "lat": 40.7163, "lng": -74.0086},
        ]

        # First pass: $$$$ restaurants
        logger.info("Searching for $$$$ restaurants in Manhattan...")
        price_filter = "4"

        for area in manhattan_areas:
            if len(restaurants) >= target_count:
                break

            logger.info(f"Searching {area['name']}...")

            if categories:
                # Search each category separately to get more results
                for category in categories:
                    if len(restaurants) >= target_count:
                        break

                    for business in self.search_all_restaurants(
                        latitude=area["lat"],
                        longitude=area["lng"],
                        radius=3000,  # Smaller radius for grid search
                        categories=[category],
                        price=price_filter,
                        max_results=200,
                    ):
                        if business["id"] not in seen_ids:
                            seen_ids.add(business["id"])
                            restaurant = self._business_to_restaurant(business)
                            if restaurant.is_open:  # Only include open restaurants
                                restaurants.append(restaurant)
            else:
                # Search all restaurants
                for business in self.search_all_restaurants(
                    latitude=area["lat"],
                    longitude=area["lng"],
                    radius=3000,
                    price=price_filter,
                    max_results=200,
                ):
                    if business["id"] not in seen_ids:
                        seen_ids.add(business["id"])
                        restaurant = self._business_to_restaurant(business)
                        if restaurant.is_open:
                            restaurants.append(restaurant)

        logger.info(f"Found {len(restaurants)} $$$$ restaurants")

        # Second pass: $$$ restaurants if needed
        if include_three_dollar and len(restaurants) < target_count:
            logger.info("Adding $$$ restaurants to reach target count...")
            price_filter = "3"

            for area in manhattan_areas:
                if len(restaurants) >= target_count:
                    break

                if categories:
                    for category in categories:
                        if len(restaurants) >= target_count:
                            break

                        for business in self.search_all_restaurants(
                            latitude=area["lat"],
                            longitude=area["lng"],
                            radius=3000,
                            categories=[category],
                            price=price_filter,
                            max_results=200,
                        ):
                            if business["id"] not in seen_ids:
                                seen_ids.add(business["id"])
                                restaurant = self._business_to_restaurant(business)
                                if restaurant.is_open:
                                    restaurants.append(restaurant)
                else:
                    for business in self.search_all_restaurants(
                        latitude=area["lat"],
                        longitude=area["lng"],
                        radius=3000,
                        price=price_filter,
                        max_results=200,
                    ):
                        if business["id"] not in seen_ids:
                            seen_ids.add(business["id"])
                            restaurant = self._business_to_restaurant(business)
                            if restaurant.is_open:
                                restaurants.append(restaurant)

            logger.info(f"Total restaurants after adding $$$: {len(restaurants)}")

        return restaurants[:target_count]

    def _business_to_restaurant(self, business: Dict[str, Any]) -> Restaurant:
        """Convert Yelp business data to Restaurant object.

        Args:
            business: Yelp business dictionary.

        Returns:
            Restaurant object.
        """
        location = business.get("location", {})
        coordinates = business.get("coordinates", {})
        categories = business.get("categories", [])

        address_parts = [
            location.get("address1"),
            location.get("address2"),
            location.get("address3"),
            location.get("city"),
            location.get("state"),
            location.get("zip_code"),
        ]
        full_address = ", ".join(filter(None, address_parts))

        return Restaurant(
            name=business.get("name", ""),
            yelp_id=business.get("id"),
            yelp_url=business.get("url"),
            yelp_rating=business.get("rating"),
            yelp_review_count=business.get("review_count"),
            yelp_price=business.get("price"),
            yelp_categories=[c.get("title", "") for c in categories],
            address=full_address,
            neighborhood=location.get("city"),
            latitude=coordinates.get("latitude"),
            longitude=coordinates.get("longitude"),
            phone=business.get("display_phone"),
            is_open=not business.get("is_closed", False),
        )
