"""
Manhattan Restaurant Scraper

A tool to collect high-end restaurant data from Manhattan using
Yelp, Google Places, and Instagram.
"""

from .models import Restaurant
from .yelp_client import YelpClient
from .google_client import GooglePlacesClient
from .instagram_client import InstagramClient
from .aggregator import RestaurantAggregator

__all__ = [
    "Restaurant",
    "YelpClient",
    "GooglePlacesClient",
    "InstagramClient",
    "RestaurantAggregator",
]
