# Traverse

A simple, fast web demo that shows how far you can get with **Python**, **FastAPI**, **HTMX**, and **DuckDB** — no complex frontend build pipeline required.

Traverse lets you explore points of interest for a given location and "traversal method". For example:

- **Transit** in Ikebukuro, Tokyo → nearby sights reachable by train and bus.
- **Cessna 172** from KBFI → airports and waypoints within ~100 nm.

## Tech Stack

- **FastAPI** – API and HTML rendering
- **Jinja2** – server-side templates
- **HTMX** – dynamic partial-page updates via attributes, no JS bundler
- **DuckDB** – embedded analytics DB for fast geo queries on CSVs
- **httpx** – async HTTP for geocoding (Nominatim)

## Quick Start

Requires [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies
uv sync

# 2. Seed the local DuckDB database
uv run python scripts/bootstrap.py

# 3. Run the dev server
uv run python -m traverse.main
```

Open [http://localhost:8000](http://localhost:8000) and try a search.

## How It Works

1. **Geocode** – the user submits a location and traversal method. We try Nominatim (OpenStreetMap) first, then fall back to our local DuckDB tables (airports by ident/name, or POIs by city).
2. **Query** – using a haversine distance formula directly in DuckDB SQL, we find airports and points of interest inside the method's default radius.
3. **Render** – HTMX swaps in a partial HTML template with results. No page reload, no React.

## Project Structure

```
├── data/
│   ├── pois.csv                 # Demo points of interest (Tokyo, Seattle, etc.)
│   └── traverse.db              # DuckDB file created by bootstrap
├── scripts/
│   └── bootstrap.py            # Downloads airports/navaids CSVs, loads DuckDB
├── src/traverse/
│   ├── main.py                 # FastAPI app and lifespan
│   ├── config.py               # Settings (pydantic-settings)
│   ├── db.py                   # DuckDB connection helpers
│   ├── api/
│   │   ├── pages.py            # HTML page routes
│   │   └── search.py           # HTMX search endpoint
│   └── services/
│       ├── geocode.py          # Nominatim + local fallback
│       └── search.py           # Haversine geo queries in DuckDB
├── templates/
│   ├── base.html               # Base layout with HTMX CDN
│   ├── index.html              # Search form
│   └── partials/
│       └── results.html        # Swappable results fragment
├── static/
│   └── style.css               # Simple dark-mode CSS
└── DESIGN.md                   # Original design notes
```

## Design Notes

See [DESIGN.md](DESIGN.md) for goals and reference architecture.

## Future Ideas

- Support more traversal methods (hiking, e-bike, kayak)
- Add a map visualization (Leaflet or MapLibre)
- Plug in real GTFS transit data for route-aware searches
- Cache Nominatim results in DuckDB to speed up repeat queries
