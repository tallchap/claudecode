# Manhattan High-End Restaurant Scraper

A Python tool to collect comprehensive data on high-end restaurants in Manhattan from multiple sources: Yelp, Google Places, and Instagram.

## Features

- **Yelp Data**: Restaurant names, ratings, reviews, price levels, categories
- **Google Places Data**: Google ratings, review counts, business profile URLs
- **Instagram Data**: Instagram handles and follower counts (where available)
- **Filtering**: Targets $$$$ and $$$ restaurants (high-end dining)
- **Output**: CSV and JSON export formats

## Data Collected

For each restaurant, the scraper collects:

| Field | Source | Description |
|-------|--------|-------------|
| `name` | Yelp | Restaurant name |
| `description` | Generated | Short description |
| `website_url` | Google | Restaurant website |
| `google_business_profile_url` | Google | Google Maps/Business URL |
| `google_rating` | Google | Rating (1-5) |
| `google_review_count` | Google | Number of reviews |
| `yelp_url` | Yelp | Yelp page URL |
| `yelp_rating` | Yelp | Rating (1-5) |
| `yelp_review_count` | Yelp | Number of reviews |
| `yelp_price` | Yelp | Price level ($-$$$$) |
| `instagram_handle` | Instagram | Instagram username |
| `instagram_url` | Instagram | Profile URL |
| `instagram_follower_count` | Instagram | Follower count |
| `address` | Yelp/Google | Full address |
| `phone` | Yelp/Google | Phone number |
| `yelp_categories` | Yelp | Restaurant categories |

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd manhattan-restaurant-scraper
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up API keys:
```bash
cp .env.example .env
# Edit .env with your API keys
```

## API Keys Required

### Yelp Fusion API (Required)

1. Go to [Yelp Developers](https://www.yelp.com/developers/v3/manage_app)
2. Create a new app
3. Copy the API Key

### Google Places API (Recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the "Places API"
4. Create credentials (API Key)
5. Copy the API Key

**Note**: Google Places API has usage costs. See [pricing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing).

### Instagram (No API key needed)

Instagram data is fetched via web scraping. Note that:
- Rate limiting is aggressive to avoid blocks
- Success rate varies based on restaurant Instagram presence
- Some profiles may not be found

## Usage

### Basic Usage

```bash
# Run with defaults (1000 restaurants, all categories)
python main.py
```

### Options

```bash
# Specify target count
python main.py --count 500

# Output format (csv, json, or both)
python main.py --output csv

# Skip Instagram (faster)
python main.py --skip-instagram

# Skip Google (if no API key)
python main.py --skip-google

# Specific categories only
python main.py --categories italian,japanese,french

# Verbose logging
python main.py --verbose

# Custom output directory
python main.py --output-dir ./data
```

### Example Commands

```bash
# Quick run: 200 Italian restaurants, no Instagram
python main.py --count 200 --categories italian --skip-instagram

# Full run: 1000 restaurants with all data sources
python main.py --count 1000 --verbose

# JSON only output
python main.py --output json --output-dir ./exports
```

## Output Files

Output files are saved to the `output/` directory (configurable):

- `manhattan_restaurants_YYYYMMDD_HHMMSS.csv` - Spreadsheet format
- `manhattan_restaurants_YYYYMMDD_HHMMSS.json` - JSON format with metadata

### CSV Example

```csv
name,description,website_url,google_business_profile_url,google_rating,yelp_rating,instagram_handle,instagram_follower_count,...
Le Bernardin,,https://le-bernardin.com,https://maps.google.com/...,4.8,4.5,lebernardinny,85000,...
```

### JSON Example

```json
{
  "metadata": {
    "generated_at": "2024-01-15T10:30:00",
    "total_count": 1000
  },
  "restaurants": [
    {
      "name": "Le Bernardin",
      "yelp_rating": 4.5,
      "google_rating": 4.8,
      "instagram_handle": "lebernardinny",
      "instagram_follower_count": 85000,
      ...
    }
  ]
}
```

## Rate Limiting & Costs

### Yelp API
- Free tier: 5,000 calls/day
- The scraper uses ~3-4 calls per minute to stay well under limits

### Google Places API
- Find Place: $17 per 1,000 calls
- Place Details: $17 per 1,000 calls
- Estimated cost for 1000 restaurants: ~$34

### Instagram
- No API costs (web scraping)
- Very conservative rate limiting (5 requests/minute)
- May be blocked if used too aggressively

## Project Structure

```
.
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore rules
├── README.md               # This file
├── scraper/
│   ├── __init__.py
│   ├── models.py           # Data models (Restaurant, SearchConfig)
│   ├── yelp_client.py      # Yelp Fusion API client
│   ├── google_client.py    # Google Places API client
│   ├── instagram_client.py # Instagram scraper
│   └── aggregator.py       # Data aggregation and export
└── output/                 # Generated output files
```

## Limitations

1. **Yelp API Pagination**: Yelp limits to 1000 results per search query. The scraper works around this by searching multiple Manhattan neighborhoods.

2. **Instagram Discovery**: Finding Instagram handles is heuristic-based. Not all restaurants will have Instagram data.

3. **Real-time Accuracy**: Restaurant data changes. The scraper captures a point-in-time snapshot.

4. **Rate Limits**: To respect API limits and avoid blocks, the scraper runs at a controlled pace. A full run (1000 restaurants with all sources) may take 2-4 hours.

## Troubleshooting

### "YELP_API_KEY environment variable is required"
Make sure you've created a `.env` file with your Yelp API key.

### Google data missing
Ensure you've set `GOOGLE_PLACES_API_KEY` and that the Places API is enabled in your Google Cloud project.

### Instagram data missing
Instagram scraping is best-effort. Many restaurants don't have detectable Instagram handles, or the profiles may be private.

### Rate limit errors
The scraper includes rate limiting, but if you hit errors, try running with `--skip-instagram` first, then enriching Instagram data separately.

## License

MIT License
