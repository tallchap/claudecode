"""Instagram data fetcher for restaurant profiles.

Note: Instagram does not provide a public API for fetching profile data.
This module uses web scraping techniques which may be subject to rate
limiting and terms of service restrictions. Use responsibly.
"""

import os
import re
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse

import requests
from ratelimit import limits, sleep_and_retry
import backoff

from .models import Restaurant

logger = logging.getLogger(__name__)


class InstagramError(Exception):
    """Raised when Instagram data fetch fails."""

    pass


class InstagramClient:
    """Client for fetching Instagram profile data."""

    # Very conservative rate limiting to avoid blocks
    CALLS_PER_MINUTE = 5

    # User agent to use for requests
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        """Initialize Instagram client."""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })

    @staticmethod
    def extract_instagram_handle(url: str) -> Optional[str]:
        """Extract Instagram handle from a URL.

        Args:
            url: URL that might contain an Instagram link.

        Returns:
            Instagram handle without @ symbol, or None if not found.
        """
        if not url:
            return None

        # Handle various Instagram URL formats
        instagram_patterns = [
            r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?",
            r"(?:https?://)?(?:www\.)?instagr\.am/([a-zA-Z0-9_.]+)/?",
        ]

        for pattern in instagram_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                handle = match.group(1)
                # Filter out non-profile pages
                if handle.lower() not in ("p", "reel", "reels", "explore", "stories", "tv"):
                    return handle

        return None

    @staticmethod
    def find_instagram_in_website(html: str) -> Optional[str]:
        """Find Instagram handle from website HTML.

        Args:
            html: Website HTML content.

        Returns:
            Instagram handle if found, None otherwise.
        """
        # Look for Instagram links in the HTML
        patterns = [
            r'href=["\'](?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?["\']',
            r'instagram\.com/([a-zA-Z0-9_.]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if match.lower() not in ("p", "reel", "reels", "explore", "stories", "tv"):
                    return match

        return None

    @sleep_and_retry
    @limits(calls=CALLS_PER_MINUTE, period=60)
    def _fetch_url(self, url: str, timeout: int = 15) -> Optional[str]:
        """Fetch URL content with rate limiting.

        Args:
            url: URL to fetch.
            timeout: Request timeout in seconds.

        Returns:
            Response text or None if failed.
        """
        try:
            response = self.session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None

    def get_profile_data(self, handle: str) -> Optional[Dict[str, Any]]:
        """Get Instagram profile data for a handle.

        Note: This uses web scraping and may be unreliable or blocked.

        Args:
            handle: Instagram handle (without @).

        Returns:
            Profile data dictionary or None if not found.
        """
        # Clean the handle
        handle = handle.strip().lstrip("@")

        if not handle:
            return None

        url = f"https://www.instagram.com/{handle}/"

        try:
            html = self._fetch_url(url)
            if not html:
                return None

            # Try to find profile data in the page
            # Instagram embeds some data in script tags

            # Look for follower count patterns
            follower_patterns = [
                r'"edge_followed_by":\s*\{\s*"count":\s*(\d+)',
                r'"follower_count":\s*(\d+)',
                r'(\d+(?:,\d+)*(?:\.\d+)?[KkMm]?)\s*(?:Followers|followers)',
            ]

            follower_count = None
            for pattern in follower_patterns:
                match = re.search(pattern, html)
                if match:
                    count_str = match.group(1)
                    follower_count = self._parse_follower_count(count_str)
                    if follower_count:
                        break

            return {
                "handle": handle,
                "url": url,
                "follower_count": follower_count,
            }

        except Exception as e:
            logger.debug(f"Error getting Instagram profile for {handle}: {e}")
            return None

    @staticmethod
    def _parse_follower_count(count_str: str) -> Optional[int]:
        """Parse follower count from various formats.

        Args:
            count_str: String like "1234", "1,234", "1.2K", "1.2M".

        Returns:
            Integer count or None if parsing fails.
        """
        if not count_str:
            return None

        try:
            # Remove commas
            count_str = count_str.replace(",", "")

            # Handle K/M suffixes
            multiplier = 1
            if count_str.upper().endswith("K"):
                multiplier = 1000
                count_str = count_str[:-1]
            elif count_str.upper().endswith("M"):
                multiplier = 1000000
                count_str = count_str[:-1]

            return int(float(count_str) * multiplier)

        except (ValueError, TypeError):
            return None

    def find_instagram_from_website(self, website_url: str) -> Optional[str]:
        """Try to find Instagram handle from a website.

        Args:
            website_url: Restaurant website URL.

        Returns:
            Instagram handle if found, None otherwise.
        """
        if not website_url:
            return None

        html = self._fetch_url(website_url)
        if not html:
            return None

        return self.find_instagram_in_website(html)

    def enrich_restaurant(self, restaurant: Restaurant) -> Restaurant:
        """Enrich a Restaurant object with Instagram data.

        Args:
            restaurant: Restaurant object.

        Returns:
            Restaurant object with Instagram data added.
        """
        handle = None

        # Try to find Instagram handle from website
        if restaurant.website_url:
            handle = self.find_instagram_from_website(restaurant.website_url)

        # Try to search for Instagram handle based on restaurant name
        # This is less reliable but worth trying
        if not handle:
            # Generate potential Instagram handles from restaurant name
            potential_handles = self._generate_potential_handles(restaurant.name)
            for potential_handle in potential_handles[:2]:  # Limit attempts
                profile = self.get_profile_data(potential_handle)
                if profile and profile.get("follower_count"):
                    handle = potential_handle
                    break
                time.sleep(1)  # Extra delay between attempts

        if handle:
            restaurant.instagram_handle = handle
            restaurant.instagram_url = f"https://www.instagram.com/{handle}/"

            # Get follower count
            profile = self.get_profile_data(handle)
            if profile:
                restaurant.instagram_follower_count = profile.get("follower_count")

        return restaurant

    @staticmethod
    def _generate_potential_handles(name: str) -> List[str]:
        """Generate potential Instagram handles from a restaurant name.

        Args:
            name: Restaurant name.

        Returns:
            List of potential handles to try.
        """
        if not name:
            return []

        # Clean the name
        clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", name).strip()
        words = clean_name.split()

        if not words:
            return []

        handles = []

        # Try various common patterns
        # 1. All words joined with no spaces
        handles.append("".join(words).lower())

        # 2. All words joined with underscores
        handles.append("_".join(words).lower())

        # 3. First word only
        if words:
            handles.append(words[0].lower())

        # 4. With "nyc" suffix
        handles.append("".join(words).lower() + "nyc")
        handles.append("".join(words).lower() + "_nyc")

        return handles[:5]  # Limit to 5 attempts

    def enrich_restaurants(
        self,
        restaurants: List[Restaurant],
        progress_callback=None,
    ) -> List[Restaurant]:
        """Enrich multiple restaurants with Instagram data.

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
                logger.error(f"Error enriching {restaurant.name} with Instagram: {e}")
                enriched.append(restaurant)

            if progress_callback:
                progress_callback(i + 1, total)

            if (i + 1) % 50 == 0:
                logger.info(f"Processed {i + 1}/{total} restaurants for Instagram data")

        return enriched
