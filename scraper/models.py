"""Data models for restaurant information."""

from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json


@dataclass
class Restaurant:
    """Represents a restaurant with data from multiple sources."""

    # Basic info
    name: str
    description: Optional[str] = None

    # Location
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # URLs
    website_url: Optional[str] = None
    yelp_url: Optional[str] = None
    google_maps_url: Optional[str] = None

    # Yelp data
    yelp_id: Optional[str] = None
    yelp_rating: Optional[float] = None
    yelp_review_count: Optional[int] = None
    yelp_price: Optional[str] = None  # $, $$, $$$, $$$$
    yelp_categories: List[str] = field(default_factory=list)

    # Google data
    google_place_id: Optional[str] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    google_business_profile_url: Optional[str] = None

    # Instagram data
    instagram_handle: Optional[str] = None
    instagram_url: Optional[str] = None
    instagram_follower_count: Optional[int] = None

    # Phone
    phone: Optional[str] = None

    # Status
    is_open: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Restaurant":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SearchConfig:
    """Configuration for restaurant search."""

    # Location bounds for Manhattan
    location: str = "Manhattan, NY"
    latitude: float = 40.7831
    longitude: float = -73.9712
    radius_meters: int = 10000  # ~6.2 miles covers Manhattan

    # Price filter (Yelp uses 1-4, Google uses 0-4)
    min_price_level: int = 4  # $$$$ on Yelp

    # Categories to search (if not getting enough $$$$)
    categories: List[str] = field(default_factory=lambda: [
        "italian",
        "japanese",
        "french",
        "mexican",
        "steakhouses",
        "seafood",
        "newamerican",
        "mediterranean",
        "chinese",
        "korean",
        "thai",
        "indian",
        "spanish",
        "greek",
        "vietnamese",
        "sushi",
        "tapas",
        "brazilian",
        "peruvian",
        "middleeastern",
    ])

    # Target number of restaurants
    target_count: int = 1000

    # Only include currently open businesses
    open_only: bool = True
