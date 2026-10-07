"""Geocode locations via Nominatim (OpenStreetMap) with local fallback."""

import httpx

from traverse.db import get_connection

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


async def geocode_location(q: str) -> tuple[float, float] | None:
    """Return (lat, lon) or None if not found."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                _NOMINATIM_URL,
                params={"q": q, "format": "json", "limit": 1},
                headers={"User-Agent": "Traverse/0.1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass

    # Fallback: local lookup against airports/pois
    return _local_geocode(q)


def _local_geocode(q: str) -> tuple[float, float] | None:
    conn = get_connection()
    # Try airports by ident / iata / name
    rows = conn.execute(
        """
        SELECT latitude_deg, longitude_deg FROM airports
        WHERE ident ILIKE ? OR iata_code ILIKE ? OR name ILIKE ?
        LIMIT 1
        """,
        [f"%{q}%", f"%{q}%", f"%{q}%"],
    ).fetchall()
    if rows:
        return float(rows[0][0]), float(rows[0][1])

    # Try POIs by city or name
    rows = conn.execute(
        """
        SELECT lat, lon FROM pois
        WHERE city ILIKE ? OR name ILIKE ?
        LIMIT 1
        """,
        [f"%{q}%", f"%{q}%"],
    ).fetchall()
    if rows:
        return float(rows[0][0]), float(rows[0][1])

    return None
