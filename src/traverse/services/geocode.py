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

    # Fallback: unified offline lookup across airports, cities, pois, navaids
    return _local_geocode(q)


def _local_geocode(q: str) -> tuple[float, float] | None:
    conn = get_connection()
    q_clean = q.strip()

    # Exact code match (ident, iata, local_code, gps_code, poi_id)
    row = conn.execute(
        "SELECT lat, lon FROM geocodes WHERE UPPER(lookup_code) = UPPER(?) LIMIT 1",
        [q_clean],
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    # For US airport codes: try adding/removing K prefix (SVR -> KSVR, U42 -> U42/KU42)
    if len(q_clean) <= 5:
        if q_clean.upper().startswith('K'):
            alt = q_clean[1:]
        else:
            alt = 'K' + q_clean
        row = conn.execute(
            "SELECT lat, lon FROM geocodes WHERE UPPER(lookup_code) = UPPER(?) LIMIT 1",
            [alt],
        ).fetchone()
        if row:
            return float(row[0]), float(row[1])

    # Exact name match
    row = conn.execute(
        "SELECT lat, lon FROM geocodes WHERE UPPER(canonical_name) = UPPER(?) LIMIT 1",
        [q_clean],
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    # Starts-with name (e.g. "Nara" matches "Nara, JP")
    row = conn.execute(
        "SELECT lat, lon FROM geocodes WHERE canonical_name ILIKE ? || '%' ORDER BY source='city' DESC LIMIT 1",
        [q_clean],
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    # City prefix
    row = conn.execute(
        "SELECT lat, lon FROM geocodes WHERE city ILIKE ? || '%' ORDER BY source='city' DESC LIMIT 1",
        [q_clean],
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    # Contains in search_text (last resort)
    row = conn.execute(
        """
        SELECT lat, lon FROM geocodes
        WHERE search_text ILIKE '%' || ? || '%'
        ORDER BY
            CASE source
                WHEN 'city' THEN 1
                WHEN 'poi' THEN 2
                WHEN 'airport' THEN 3
                WHEN 'navaid' THEN 4
            END
        LIMIT 1
        """,
        [q_clean],
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    # Very fuzzy fallback: partial code match
    # This catches things like "U42" matching "MU42", "KU42", etc.
    row = conn.execute(
        "SELECT lat, lon FROM geocodes WHERE lookup_code ILIKE '%' || ? || '%' ORDER BY source='airport' DESC LIMIT 1",
        [q_clean],
    ).fetchone()
    if row:
        return float(row[0]), float(row[1])

    return None
