"""Aggregator to combine restaurant data from multiple sources."""

import os
import json
import csv
import logging
from typing import List, Optional, Callable
from datetime import datetime
from pathlib import Path

from .models import Restaurant, SearchConfig
from .yelp_client import YelpClient, YelpAPIError
from .google_client import GooglePlacesClient, GooglePlacesError
from .instagram_client import InstagramClient, InstagramError

logger = logging.getLogger(__name__)


class RestaurantAggregator:
    """Aggregates restaurant data from Yelp, Google, and Instagram."""

    def __init__(
        self,
        yelp_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        skip_instagram: bool = False,
    ):
        """Initialize the aggregator.

        Args:
            yelp_api_key: Yelp Fusion API key.
            google_api_key: Google Places API key.
            skip_instagram: If True, skip Instagram enrichment.
        """
        self.yelp_client = None
        self.google_client = None
        self.instagram_client = None

        # Initialize Yelp client (required)
        try:
            self.yelp_client = YelpClient(api_key=yelp_api_key)
            logger.info("Yelp client initialized")
        except ValueError as e:
            logger.error(f"Failed to initialize Yelp client: {e}")
            raise

        # Initialize Google client (optional but recommended)
        try:
            self.google_client = GooglePlacesClient(api_key=google_api_key)
            logger.info("Google Places client initialized")
        except ValueError as e:
            logger.warning(f"Google Places client not available: {e}")
            self.google_client = None

        # Initialize Instagram client (optional)
        if not skip_instagram:
            self.instagram_client = InstagramClient()
            logger.info("Instagram client initialized")

    def collect_restaurants(
        self,
        config: Optional[SearchConfig] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[Restaurant]:
        """Collect restaurants from all sources.

        Args:
            config: Search configuration. If None, uses defaults.
            progress_callback: Optional callback for progress updates.
                Signature: callback(stage: str, current: int, total: int)

        Returns:
            List of Restaurant objects with data from all sources.
        """
        if config is None:
            config = SearchConfig()

        restaurants = []

        # Stage 1: Search Yelp for restaurants
        logger.info("Stage 1: Searching Yelp for high-end Manhattan restaurants...")
        if progress_callback:
            progress_callback("yelp_search", 0, 1)

        try:
            restaurants = self.yelp_client.search_high_end_manhattan(
                target_count=config.target_count,
                categories=config.categories if config.categories else None,
                include_three_dollar=True,
            )
            logger.info(f"Found {len(restaurants)} restaurants from Yelp")
        except YelpAPIError as e:
            logger.error(f"Yelp search failed: {e}")
            raise

        if progress_callback:
            progress_callback("yelp_search", 1, 1)

        # Stage 2: Enrich with Google data
        if self.google_client:
            logger.info("Stage 2: Enriching with Google Places data...")
            total = len(restaurants)

            def google_progress(current, total_items):
                if progress_callback:
                    progress_callback("google_enrich", current, total_items)

            try:
                restaurants = self.google_client.enrich_restaurants(
                    restaurants,
                    progress_callback=google_progress,
                )
                logger.info("Google enrichment complete")
            except GooglePlacesError as e:
                logger.error(f"Google enrichment failed: {e}")
        else:
            logger.warning("Skipping Google enrichment (no API key)")

        # Stage 3: Enrich with Instagram data
        if self.instagram_client:
            logger.info("Stage 3: Enriching with Instagram data...")
            total = len(restaurants)

            def instagram_progress(current, total_items):
                if progress_callback:
                    progress_callback("instagram_enrich", current, total_items)

            try:
                restaurants = self.instagram_client.enrich_restaurants(
                    restaurants,
                    progress_callback=instagram_progress,
                )
                logger.info("Instagram enrichment complete")
            except InstagramError as e:
                logger.error(f"Instagram enrichment failed: {e}")
        else:
            logger.info("Skipping Instagram enrichment")

        # Filter out closed restaurants
        open_restaurants = [r for r in restaurants if r.is_open]
        logger.info(
            f"Final count: {len(open_restaurants)} open restaurants "
            f"(filtered {len(restaurants) - len(open_restaurants)} closed)"
        )

        return open_restaurants

    def save_to_csv(
        self,
        restaurants: List[Restaurant],
        output_path: str,
    ) -> str:
        """Save restaurants to CSV file.

        Args:
            restaurants: List of Restaurant objects.
            output_path: Path to output CSV file.

        Returns:
            Path to saved file.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Define CSV columns in desired order
        columns = [
            "name",
            "description",
            "website_url",
            "google_business_profile_url",
            "google_rating",
            "google_review_count",
            "yelp_url",
            "yelp_rating",
            "yelp_review_count",
            "yelp_price",
            "instagram_handle",
            "instagram_url",
            "instagram_follower_count",
            "address",
            "neighborhood",
            "phone",
            "yelp_categories",
            "latitude",
            "longitude",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()

            for restaurant in restaurants:
                row = restaurant.to_dict()
                # Convert list to comma-separated string
                if row.get("yelp_categories"):
                    row["yelp_categories"] = "; ".join(row["yelp_categories"])
                writer.writerow(row)

        logger.info(f"Saved {len(restaurants)} restaurants to {output_path}")
        return output_path

    def save_to_json(
        self,
        restaurants: List[Restaurant],
        output_path: str,
    ) -> str:
        """Save restaurants to JSON file.

        Args:
            restaurants: List of Restaurant objects.
            output_path: Path to output JSON file.

        Returns:
            Path to saved file.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_count": len(restaurants),
            },
            "restaurants": [r.to_dict() for r in restaurants],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(restaurants)} restaurants to {output_path}")
        return output_path

    def generate_summary(self, restaurants: List[Restaurant]) -> dict:
        """Generate summary statistics for the collected restaurants.

        Args:
            restaurants: List of Restaurant objects.

        Returns:
            Dictionary with summary statistics.
        """
        total = len(restaurants)

        # Price distribution
        price_counts = {}
        for r in restaurants:
            price = r.yelp_price or "Unknown"
            price_counts[price] = price_counts.get(price, 0) + 1

        # Category distribution
        category_counts = {}
        for r in restaurants:
            for cat in r.yelp_categories:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        # Top categories
        top_categories = sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # Rating stats
        yelp_ratings = [r.yelp_rating for r in restaurants if r.yelp_rating]
        google_ratings = [r.google_rating for r in restaurants if r.google_rating]

        avg_yelp = sum(yelp_ratings) / len(yelp_ratings) if yelp_ratings else 0
        avg_google = sum(google_ratings) / len(google_ratings) if google_ratings else 0

        # Data completeness
        with_google = sum(1 for r in restaurants if r.google_rating)
        with_instagram = sum(1 for r in restaurants if r.instagram_handle)
        with_website = sum(1 for r in restaurants if r.website_url)

        return {
            "total_restaurants": total,
            "price_distribution": price_counts,
            "top_categories": dict(top_categories),
            "average_yelp_rating": round(avg_yelp, 2),
            "average_google_rating": round(avg_google, 2),
            "data_completeness": {
                "with_google_data": with_google,
                "with_instagram": with_instagram,
                "with_website": with_website,
                "google_coverage_pct": round(100 * with_google / total, 1) if total else 0,
                "instagram_coverage_pct": round(100 * with_instagram / total, 1) if total else 0,
            },
        }
