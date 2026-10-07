import duckdb

_connection: duckdb.DuckDBPyConnection | None = None


def connect_db() -> duckdb.DuckDBPyConnection:
    global _connection
    from traverse.config import settings

    _connection = duckdb.connect(settings.db_path)
    return _connection


def get_connection() -> duckdb.DuckDBPyConnection:
    if _connection is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _connection


def disconnect_db() -> None:
    global _connection
    if _connection:
        _connection.close()
        _connection = None


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
