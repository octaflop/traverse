"""Search logic for POIs, airports, and user waypoints."""

from traverse.db import get_connection, is_spatial_available

# radius definitions in km
_RADII = {
    "cessna 172": 185,  # ~100 nm
    "transit": 20,
    "walk": 5,
    "bike": 20,
    "default": 50,
}


def _method_radius(method: str) -> float:
    m = method.lower().strip()
    for key, radius in _RADII.items():
        if key in m:
            return radius
    return _RADII["default"]


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
    conn = get_connection()
    dist_expr = _distance_km_sql(lat, lon, "airports", "latitude_deg", "longitude_deg")
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
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, limit])
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
            {dist_expr} AS distance_km
        FROM pois
        WHERE {dist_expr} < ?
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, limit])
    cols = [desc[0] for desc in res.description]
    return _rows_to_dicts(res.fetchall(), cols)


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
            {dist_expr} AS distance_km
        FROM user_waypoints
        WHERE {dist_expr} < ?
        ORDER BY distance_km
        LIMIT ?
    """
    res = conn.execute(sql, [radius, limit])
    cols = [desc[0] for desc in res.description]
    return _rows_to_dicts(res.fetchall(), cols)
