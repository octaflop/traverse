"""Dynamic POI fetching from OpenStreetMap via Overpass API.

Uses httpx to query Overpass, then DuckDB `read_json_auto` on the result
to demonstrate querying public JSON APIs as a "virtual table".
"""

import json
import urllib.parse

import httpx

from traverse.db import get_connection

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OVERPASS_ALT = "https://overpass.kumi.systems/api/interpreter"

# Radius in meters per method (smaller than our km radius)
_OVERPASS_RADIUS = {
    "walk": 2000,
    "bike": 8000,
    "transit": 10000,
    "cessna 172": 150000,
    "default": 15000,
}


def _overpass_radius(method: str) -> int:
    m = method.lower().strip()
    for key, radius in _OVERPASS_RADIUS.items():
        if key in m:
            return radius
    return _OVERPASS_RADIUS["default"]


def _build_overpass_ql(lat: float, lon: float, radius: int) -> str:
    """Build an Overpass QL query for interesting POIs around a point."""
    return f"""
    [out:json][timeout:25];
    (
      node["tourism"~"attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium"](around:{radius},{lat},{lon});
      node["amenity"~"restaurant|cafe|bar|theatre|cinema|library|community_centre"](around:{radius},{lat},{lon});
      node["leisure"~"park|garden|nature_reserve|sports_centre|playground|stadium"](around:{radius},{lat},{lon});
      node["historic"~"monument|memorial|castle|ruins|archaeological_site"](around:{radius},{lat},{lon});
      node["natural"~"peak|waterfall|volcano|cave_entrance"](around:{radius},{lat},{lon});
      node["shop"](around:{radius},{lat},{lon});
    );
    out body 30;
    """


def _fetch_overpass(lat: float, lon: float, radius: int) -> list[dict]:
    """Query Overpass API and return flattened elements."""
    ql = _build_overpass_ql(lat, lon, radius)

    # Try primary, then fallback
    for url in (_OVERPASS_URL, _OVERPASS_ALT):
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(url, data={"data": ql})
                resp.raise_for_status()
                data = resp.json()
                elements = data.get("elements", [])

                results = []
                for el in elements:
                    if el.get("type") not in ("node", "way", "relation"):
                        continue
                    tags = el.get("tags", {})
                    name = tags.get("name", "")
                    if not name:
                        continue

                    # Extract coordinates (ways don't have lat/lon directly)
                    el_lat = el.get("lat")
                    el_lon = el.get("lon")
                    if el_lat is None or el_lon is None:
                        continue

                    category = (
                        tags.get("tourism")
                        or tags.get("amenity")
                        or tags.get("leisure")
                        or tags.get("historic")
                        or tags.get("natural")
                        or tags.get("shop")
                        or "poi"
                    )

                    results.append({
                        "osm_id": el.get("id"),
                        "name": name,
                        "category": category,
                        "lat": float(el_lat),
                        "lon": float(el_lon),
                        "tags": json.dumps(tags),
                    })

                # Deduplicate by name
                seen = set()
                deduped = []
                for r in results:
                    key = (r["name"].lower(), round(r["lat"], 4), round(r["lon"], 4))
                    if key not in seen:
                        seen.add(key)
                        deduped.append(r)
                return deduped

        except Exception as e:
            print(f"Overpass {url} failed: {e}")
            continue

    return []


def fetch_and_insert_osm_pois(lat: float, lon: float, method: str) -> int:
    """Fetch POIs from Overpass, insert into DuckDB, return count inserted."""
    radius = _overpass_radius(method)
    pois = _fetch_overpass(lat, lon, radius)
    if not pois:
        return 0

    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS osm_pois (
            osm_id BIGINT,
            name TEXT,
            category TEXT,
            lat DOUBLE,
            lon DOUBLE,
            tags TEXT,
            fetched_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )

    # Insert with simple ON CONFLICT-like dedup by osm_id
    inserted = 0
    for poi in pois:
        existing = conn.execute(
            "SELECT 1 FROM osm_pois WHERE osm_id = ?",
            [poi["osm_id"]],
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO osm_pois (osm_id, name, category, lat, lon, tags) VALUES (?, ?, ?, ?, ?, ?)",
                [poi["osm_id"], poi["name"], poi["category"], poi["lat"], poi["lon"], poi["tags"]],
            )
            inserted += 1

    return inserted


def search_osm_pois(lat: float, lon: float, method: str, limit: int = 30):
    """Return nearby OSM POIs from local table, computing distance on the fly."""
    conn = get_connection()
    # Ensure table exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS osm_pois (
            osm_id BIGINT,
            name TEXT,
            category TEXT,
            lat DOUBLE,
            lon DOUBLE,
            tags TEXT,
            fetched_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )

    from traverse.services.search import _distance_km_sql

    dist_expr = _distance_km_sql(lat, lon, "osm_pois", "lat", "lon")
    radius = _overpass_radius(method) / 1000.0  # meters -> km

    sql = f"""
        SELECT
            osm_id,
            name,
            category,
            lat,
            lon,
            tags,
            {dist_expr} AS distance_km
        FROM osm_pois
        WHERE {dist_expr} < ?
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, limit])
    cols = [desc[0] for desc in res.description]
    import uuid

    def clean(v):
        return str(v) if isinstance(v, uuid.UUID) else v

    return [{k: clean(v) for k, v in zip(cols, row)} for row in res.fetchall()]


def cleanup_old_osm_pois(days: int = 7) -> int:
    """Remove OSM POIs older than N days to keep the table fresh."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM osm_pois WHERE fetched_at < current_timestamp - INTERVAL ? DAY",
        [days],
    )
    return conn.execute("SELECT COUNT(*) FROM osm_pois").fetchone()[0]


def osm_count() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM osm_pois").fetchone()[0]
    except Exception:
        return 0
