# Traverse

A simple, fast web demo that shows how far you can get with **Python**, **FastAPI**, **HTMX**, and **DuckDB** — no complex frontend build pipeline required.

Traverse lets you explore points of interest for a given location and "traversal method". For example:

- **Transit** in Ikebukuro, Tokyo → nearby sights reachable by train and bus.
- **Cessna 172** from KBFI → airports and waypoints within ~100 nm.

## What's here

- **🔍 Autocomplete dropdown** — as you type, DuckDB queries a unified `geocodes` table (airports + cities + POIs + navaids) and shows ranked suggestions with icons.
- **🗺️ Interactive Leaflet map** — origin + markers for airports, POIs, and user waypoints auto-fitted in view.
- **📍 User waypoints** — add custom places via form; they persist in DuckDB and appear in geo-searches.
- **🔗 Remote data sources** — register live views or snapshots over remote CSV/Parquet/JSON URLs. DuckDB queries them directly via `httpfs`.
- **⚡ DuckDB `spatial`** — `ST_Distance_Sphere` when available, silent fallback to inline haversine.
- **📡 Offline geocoding** — exact code match (KSVR, KBFI, U42), name search, city search, and fuzzy fallback all against ~166k unified rows.

## Tech Stack

- **FastAPI** – API and HTML rendering
- **Jinja2** – server-side templates
- **HTMX** – dynamic partial-page updates via attributes, no JS bundler
- **DuckDB** – embedded analytics DB for fast geo queries
- **DuckDB spatial** – PostGIS-like `ST_Distance_Sphere`
- **DuckDB httpfs** – `read_csv_auto('https://...')` directly over HTTP
- **httpx** – async HTTP for geocoding (Nominatim)
- **Leaflet.js** – lightweight map via CDN

## Quick Start

Requires [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies
uv sync

# 2. Seed the local DuckDB database (downloads ~50MB of CSVs)
uv run python scripts/bootstrap.py

# 3. Run the dev server
uv run python -m traverse.main
```

Open [http://localhost:8000](http://localhost:8000) and try typing in the location field.

## How It Works

### Geocoding
As you type, the browser sends `GET /autocomplete?q=...` to the server. DuckDB queries a unified `geocodes` table built from:
- ~73k airports (each exposed under ident, gps_code, iata_code, local_code)
- ~24 supplemental cities (Nara, Kobe, Kyoto, etc.)
- Demo POIs
- ~3.8k navaids

Results are ranked: exact code match > exact name > starts-with > city > contains. Deduplication ensures the same airport doesn't appear multiple times.

### Search
When you submit, the location is geocoded (Nominatim first, then local fallback). The fallback handles:
- Exact codes: `KSVR` → South Valley Regional, `U42` → same via K-prefix alternation
- Names: `Nara, JP` → Nara city
- City prefix and fuzzy contains on the unified table

### Query
DuckDB computes distance with `ST_Distance_Sphere` if the `spatial` extension loaded, otherwise inline haversine. Searches cover:
- Airports within the method's radius
- Built-in POIs
- User waypoints you added

### Map
Leaflet renders via `htmx:afterSettle` — each search response injects a `#map` div with data attributes. The JS reads them, creates markers (red origin, blue airports, green POIs, orange waypoints), and auto-fits bounds.

### Remote Data Sources
Paste any CSV, Parquet, or JSON URL. DuckDB's `httpfs` extension fetches it directly:
- **Live View**: `CREATE VIEW name AS SELECT * FROM read_csv_auto('url')` — always current, queries remote each time
- **Snapshot**: `CREATE TABLE name AS SELECT * FROM read_csv_auto('url')` — copies into local DuckDB

This works for public datasets like OurAirports, FAA data, NOAA, etc.

## Project Structure

```
├── data/
│   ├── cities.csv             # Supplemental city locations (Nara, Kyoto, etc.)
│   ├── pois.csv               # Demo POIs (Tokyo, Seattle, etc.)
│   └── traverse.db            # DuckDB file created by bootstrap
├── scripts/
│   └── bootstrap.py           # Downloads airports/navaids CSVs, builds unified geocodes
├── src/traverse/
│   ├── main.py                # FastAPI app and lifespan
│   ├── config.py              # Settings (pydantic-settings)
│   ├── db.py                  # DuckDB + spatial + httpfs init
│   ├── api/
│   │   ├── autocomplete.py    # GET /autocomplete?q=... (ranked geocode search)
│   │   ├── pages.py           # HTML page routes
│   │   ├── search.py          # HTMX search endpoint (with map JSON)
│   │   ├── sources.py         # Remote data source CRUD + preview
│   │   └── waypoints.py       # User waypoint CRUD
│   └── services/
│       ├── geocode.py         # Nominatim + local fallback (exact code, K-prefix, fuzzy)
│       ├── search.py          # Haversine / spatial geo queries
│       └── sources.py         # DuckDB remote read helpers
├── templates/
│   ├── base.html              # Base layout + HTMX + Leaflet + autocomplete JS
│   ├── index.html             # Search form + autocomplete + waypoints + sources
│   └── partials/
│       ├── autocomplete.html  # Dropdown list items
│       ├── results.html       # Swappable results + map div
│       ├── source_preview.html # Remote data preview table
│       ├── sources.html       # Registered source list
│       └── waypoints.html     # Swappable waypoint list
├── static/
│   └── style.css              # Dark-mode CSS + autocomplete + table + map tweaks
└── DESIGN.md                  # Original design notes
```

## Bootstrap details

`scripts/bootstrap.py` downloads two public datasets:
- [OurAirports airports.csv](https://davidmegginson.github.io/ourairports-data/airports.csv) — ~73k airports, heliports, seaplane bases
- [OurAirports navaids.csv](https://davidmegginson.github.io/ourairports-data/navaids.csv) — ~3.8k VOR/VOR-DME/VORTAC/DME

It then builds a unified `geocodes` table that exposes each airport under:
- `ident` (e.g. `KU42`)
- `gps_code` (e.g. `KSVR`) — catches FAA reassignments
- `iata_code` (e.g. `SEA`)
- `local_code` (e.g. `SVR`)

This means typing `KSVR`, `U42`, `SVR`, or `KBFI` all resolve correctly.

## Future Ideas

- Geocode waypoint addresses automatically (instead of raw lat/lon)
- Support more traversal methods (hiking, e-bike, kayak)
- Import POIs from CSV / drag-and-drop
- Cache Nominatim results in DuckDB to speed up repeat queries
- Add route planning (ordered itinerary) rather than just radius search
- MotherDuck cloud persistence for shared waypoint databases
