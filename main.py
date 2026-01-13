#!/usr/bin/env python3
"""
Manhattan High-End Restaurant Scraper

Collects data on high-end restaurants in Manhattan from Yelp, Google Places,
and Instagram.

Usage:
    python main.py [options]

Examples:
    # Basic run with default settings
    python main.py

    # Specify target count and output format
    python main.py --count 500 --output json

    # Skip Instagram (faster but less complete data)
    python main.py --skip-instagram

    # Use specific categories only
    python main.py --categories italian,japanese,french
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from scraper import RestaurantAggregator
from scraper.models import SearchConfig

# Load environment variables
load_dotenv()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging.

    Args:
        verbose: If True, set DEBUG level. Otherwise, INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Collect high-end Manhattan restaurant data from multiple sources.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
    YELP_API_KEY            Yelp Fusion API key (required)
    GOOGLE_PLACES_API_KEY   Google Places API key (optional, for Google data)

Examples:
    %(prog)s --count 500 --output csv
    %(prog)s --categories italian,japanese --skip-instagram
    %(prog)s --verbose --output both
        """,
    )

    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Target number of restaurants to collect (default: 1000)",
    )

    parser.add_argument(
        "--output",
        choices=["csv", "json", "both"],
        default="both",
        help="Output format (default: both)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Output directory (default: output)",
    )

    parser.add_argument(
        "--categories",
        type=str,
        help="Comma-separated list of restaurant categories to search",
    )

    parser.add_argument(
        "--skip-instagram",
        action="store_true",
        help="Skip Instagram data enrichment (faster)",
    )

    parser.add_argument(
        "--skip-google",
        action="store_true",
        help="Skip Google Places data enrichment",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def create_progress_callback():
    """Create a progress callback using tqdm.

    Returns:
        Tuple of (callback function, dict of progress bars).
    """
    bars = {}

    def callback(stage: str, current: int, total: int):
        if stage not in bars:
            stage_names = {
                "yelp_search": "Searching Yelp",
                "google_enrich": "Enriching with Google",
                "instagram_enrich": "Enriching with Instagram",
            }
            bars[stage] = tqdm(
                total=total,
                desc=stage_names.get(stage, stage),
                unit="restaurants",
            )
        bars[stage].n = current
        bars[stage].refresh()

        if current >= total:
            bars[stage].close()

    return callback, bars


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger(__name__)

    # Check for required API key
    if not os.getenv("YELP_API_KEY"):
        logger.error(
            "YELP_API_KEY environment variable is required. "
            "Get your key at: https://www.yelp.com/developers/v3/manage_app"
        )
        return 1

    # Warn about optional keys
    if not os.getenv("GOOGLE_PLACES_API_KEY") and not args.skip_google:
        logger.warning(
            "GOOGLE_PLACES_API_KEY not set. Google data will not be available. "
            "Use --skip-google to suppress this warning."
        )

    # Parse categories
    categories = None
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]

    # Create search config
    config = SearchConfig(
        target_count=args.count,
        categories=categories if categories else SearchConfig().categories,
    )

    logger.info("=" * 60)
    logger.info("Manhattan High-End Restaurant Scraper")
    logger.info("=" * 60)
    logger.info(f"Target count: {config.target_count}")
    logger.info(f"Categories: {len(config.categories)} types")
    logger.info(f"Skip Google: {args.skip_google}")
    logger.info(f"Skip Instagram: {args.skip_instagram}")
    logger.info("=" * 60)

    try:
        # Initialize aggregator
        google_key = None if args.skip_google else os.getenv("GOOGLE_PLACES_API_KEY")
        aggregator = RestaurantAggregator(
            google_api_key=google_key,
            skip_instagram=args.skip_instagram,
        )

        # Create progress callback
        progress_callback, _ = create_progress_callback()

        # Collect restaurants
        logger.info("\nStarting data collection...")
        restaurants = aggregator.collect_restaurants(
            config=config,
            progress_callback=progress_callback,
        )

        if not restaurants:
            logger.error("No restaurants found!")
            return 1

        # Generate summary
        logger.info("\n" + "=" * 60)
        logger.info("Collection Summary")
        logger.info("=" * 60)

        summary = aggregator.generate_summary(restaurants)
        logger.info(f"Total restaurants: {summary['total_restaurants']}")
        logger.info(f"Price distribution: {summary['price_distribution']}")
        logger.info(f"Average Yelp rating: {summary['average_yelp_rating']}")
        logger.info(f"Average Google rating: {summary['average_google_rating']}")
        logger.info(f"Data completeness:")
        for key, value in summary["data_completeness"].items():
            logger.info(f"  - {key}: {value}")

        # Save output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.output in ("csv", "both"):
            csv_path = output_dir / f"manhattan_restaurants_{timestamp}.csv"
            aggregator.save_to_csv(restaurants, str(csv_path))
            logger.info(f"\nCSV saved: {csv_path}")

        if args.output in ("json", "both"):
            json_path = output_dir / f"manhattan_restaurants_{timestamp}.json"
            aggregator.save_to_json(restaurants, str(json_path))
            logger.info(f"JSON saved: {json_path}")

        logger.info("\nDone!")
        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        return 1
    except Exception as e:
        logger.exception(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
