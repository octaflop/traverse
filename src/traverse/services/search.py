"""Search logic for POIs, airports, and user waypoints."""

from datetime import datetime

from traverse.db import get_connection, is_spatial_available

# radius definitions in km
_RADII = {
    "cessna 172": 185,  # ~100 nm
    "transit": 20,
    "walk": 5,
    "bike": 20,
    "default": 50,
}

_METHOD_IS_FLYING = {"cessna 172", "fly", "pilot", "glider", "heli"}


def _method_radius(method: str) -> float:
    m = method.lower().strip()
    for key, radius in _RADII.items():
        if key in m:
            return radius
    return _RADII["default"]


def _is_flying(method: str) -> bool:
    m = method.lower().strip()
    return any(f in m for f in _METHOD_IS_FLYING)


def _airport_types_for_method(method: str) -> tuple[str, ...]:
    """Return airport types relevant for this traversal method."""
    if _is_flying(method):
        return ("large_airport", "medium_airport", "small_airport", "seaplane_base", "heliport")
    # For ground transit, heliports are irrelevant
    return ("large_airport", "medium_airport", "small_airport", "seaplane_base")


def _current_month_name() -> str:
    return datetime.utcnow().strftime("%b").lower()  # "jan", "feb", etc.


def _current_month_num() -> int:
    return datetime.utcnow().month  # 1-12


def _season_matches(seasons_str: str | None) -> bool:
    """Check if a seasons string (e.g. 'mar-apr', 'may-sep', 'all') matches current month."""
    if not seasons_str or seasons_str.lower() == "all":
        return True

    current = _current_month_num()
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    for part in seasons_str.lower().split(";"):
        part = part.strip()
        if "-" in part:
            # Range like "mar-apr" or "may-sep"
            start_str, end_str = part.split("-", 1)
            start_mo = month_map.get(start_str.strip()[:3], 0)
            end_mo = month_map.get(end_str.strip()[:3], 0)
            if start_mo and end_mo:
                if start_mo <= end_mo:
                    if start_mo <= current <= end_mo:
                        return True
                else:
                    # Wrap around (e.g. nov-mar)
                    if current >= start_mo or current <= end_mo:
                        return True
        else:
            # Single month
            if month_map.get(part[:3], 0) == current:
                return True
    return False


def _method_matches(methods_str: str | None, requested_method: str) -> bool:
    """Check if a methods string (e.g. 'walk;bike;transit' or 'all') includes the requested method."""
    if not methods_str or methods_str.lower() == "all":
        return True
    m = requested_method.lower().strip()
    allowed = {p.strip().lower() for p in methods_str.split(";")}
    return m in allowed or "all" in allowed


def _distance_km_sql(lat: float, lon: float, table: str, lat_col: str, lon_col: str) -> str:
    """Return a SQL expression for distance in km from (lat, lon)."""
    if is_spatial_available():
        return (
            f"ST_Distance_Sphere(ST_Point({table}.{lon_col}, {table}.{lat_col}), "
            f"ST_Point({lon}, {lat})) / 1000.0"
        )
    # Fallback haversine
    return f"""
        6371.0 * acos(
            cos(radians({lat})) * cos(radians({table}.{lat_col})) *
            cos(radians({table}.{lon_col}) - radians({lon})) +
            sin(radians({lat})) * sin(radians({table}.{lat_col}))
        )
    """.strip()


import uuid


def _clean_value(val):
    if isinstance(val, uuid.UUID):
        return str(val)
    return val


def _rows_to_dicts(rows, columns):
    return [{k: _clean_value(v) for k, v in zip(columns, row)} for row in rows]


def search_airports(lat: float, lon: float, method: str, limit: int = 20):
    radius = _method_radius(method)
    types = _airport_types_for_method(method)
    conn = get_connection()
    dist_expr = _distance_km_sql(lat, lon, "airports", "latitude_deg", "longitude_deg")

    # Build IN clause for types
    placeholders = ", ".join("?" for _ in types)
    sql = f"""
        SELECT
            ident,
            name,
            iata_code,
            municipality,
            iso_country,
            latitude_deg,
            longitude_deg,
            {dist_expr} AS distance_km
        FROM airports
        WHERE {dist_expr} < ?
          AND type IN ({placeholders})
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, *types, limit])
    cols = [desc[0] for desc in res.description]
    return _rows_to_dicts(res.fetchall(), cols)


def search_pois(lat: float, lon: float, method: str, limit: int = 20):
    radius = _method_radius(method)
    conn = get_connection()
    dist_expr = _distance_km_sql(lat, lon, "pois", "lat", "lon")
    sql = f"""
        SELECT
            poi_id,
            name,
            type,
            city,
            country,
            tags,
            lat,
            lon,
            methods,
            seasons,
            {dist_expr} AS distance_km
        FROM pois
        WHERE {dist_expr} < ?
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, limit])
    cols = [desc[0] for desc in res.description]
    rows = _rows_to_dicts(res.fetchall(), cols)

    # Post-filter by method and season
    filtered = []
    for row in rows:
        if not _method_matches(row.get("methods"), method):
            continue
        if not _season_matches(row.get("seasons")):
            continue
        row["in_season"] = _season_matches(row.get("seasons"))
        filtered.append(row)
    return filtered


def search_user_waypoints(lat: float, lon: float, method: str, limit: int = 20):
    radius = _method_radius(method)
    conn = get_connection()
    dist_expr = _distance_km_sql(lat, lon, "user_waypoints", "lat", "lon")
    sql = f"""
        SELECT
            id,
            name,
            type,
            city,
            country,
            tags,
            lat,
            lon,
            methods,
            seasons,
            {dist_expr} AS distance_km
        FROM user_waypoints
        WHERE {dist_expr} < ?
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, limit])
    cols = [desc[0] for desc in res.description]
    rows = _rows_to_dicts(res.fetchall(), cols)

    filtered = []
    for row in rows:
        if not _method_matches(row.get("methods"), method):
            continue
        if not _season_matches(row.get("seasons")):
            continue
        row["in_season"] = _season_matches(row.get("seasons"))
        filtered.append(row)
    return filtered


def current_season_context() -> dict:
    """Return a dict with current month/season for UI context."""
    now = datetime.utcnow()
    month = now.month
    month_name = now.strftime("%B")
    seasons = {
        12: "Winter", 1: "Winter", 2: "Winter",
        3: "Spring", 4: "Spring", 5: "Spring",
        6: "Summer", 7: "Summer", 8: "Summer",
        9: "Autumn", 10: "Autumn", 11: "Autumn",
    }
    return {
        "month_num": month,
        "month_name": month_name,
        "season": seasons.get(month, ""),
    }
