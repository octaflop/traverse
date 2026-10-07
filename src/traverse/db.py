import duckdb

_connection: duckdb.DuckDBPyConnection | None = None
_spatial_available: bool = False


def connect_db() -> duckdb.DuckDBPyConnection:
    global _connection, _spatial_available
    from traverse.config import settings

    _connection = duckdb.connect(settings.db_path)
    _spatial_available = _init_spatial()
    _init_httpfs()
    return _connection


def _init_httpfs() -> None:
    try:
        conn = get_connection()
        conn.install_extension("httpfs")
        conn.load_extension("httpfs")
    except Exception:
        pass


def _init_spatial() -> bool:
    try:
        conn = get_connection()
        conn.install_extension("spatial")
        conn.load_extension("spatial")
        return True
    except Exception:
        return False


def is_spatial_available() -> bool:
    return _spatial_available


def get_connection() -> duckdb.DuckDBPyConnection:
    if _connection is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _connection


def disconnect_db() -> None:
    global _connection, _spatial_available
    if _connection:
        _connection.close()
        _connection = None
        _spatial_available = False


def init_schema() -> None:
    """Ensure expected tables exist (bootstrap may already have created them)."""
    conn = get_connection()
    required = {"airports", "navaids", "pois"}
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    if not required.issubset(existing):
        raise RuntimeError(
            f"Missing tables: {required - existing}. Run: python scripts/bootstrap.py"
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_waypoints (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            type TEXT,
            lat DOUBLE,
            lon DOUBLE,
            city TEXT,
            country TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )


def list_user_waypoints() -> list[dict]:
    conn = get_connection()
    res = conn.execute(
        "SELECT id, name, type, lat, lon, city, country, tags, created_at "
        "FROM user_waypoints ORDER BY created_at DESC"
    )
    cols = [desc[0] for desc in res.description]
    return [dict(zip(cols, row)) for row in res.fetchall()]


def add_user_waypoint(
    name: str,
    type: str,
    lat: float,
    lon: float,
    city: str,
    country: str,
    tags: str,
) -> str:
    conn = get_connection()
    inserted = conn.execute(
        "INSERT INTO user_waypoints (name, type, lat, lon, city, country, tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [name, type, lat, lon, city, country, tags],
    ).fetchone()
    return str(inserted[0])


def delete_user_waypoint(waypoint_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM user_waypoints WHERE id = ?", [waypoint_id])
