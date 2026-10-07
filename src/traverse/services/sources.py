"""Dynamic data source management powered by DuckDB remote reads.

Showcases DuckDB's ability to query HTTP/S3/remote sources directly:
- read_csv_auto('https://...')
- read_parquet('https://...')
- read_json_auto('https://...')
- ATTACH 'md:...'  (MotherDuck, optional)
"""

import urllib.parse

from traverse.db import get_connection


def infer_read_function(url: str) -> str:
    """Pick the right DuckDB read function based on URL extension."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    if ".parquet" in path:
        return "read_parquet"
    if ".json" in path:
        return "read_json_auto"
    return "read_csv_auto"


def install_httpfs() -> bool:
    """Ensure the httpfs extension is loaded for remote reads."""
    conn = get_connection()
    try:
        conn.install_extension("httpfs")
        conn.load_extension("httpfs")
        return True
    except Exception:
        return False


def list_sources() -> list[dict]:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_sources (
            source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            read_func TEXT,
            materialized BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    res = conn.execute(
        "SELECT source_id, name, url, read_func, materialized, created_at "
        "FROM data_sources ORDER BY created_at DESC"
    )
    cols = [desc[0] for desc in res.description]
    import uuid

    def clean(v):
        return str(v) if isinstance(v, uuid.UUID) else v

    return [{k: clean(v) for k, v in zip(cols, row)} for row in res.fetchall()]


def preview_source(url: str) -> tuple[str, list[dict]]:
    """Return (read_func, sample_rows) for a remote URL."""
    install_httpfs()
    func = infer_read_function(url)
    conn = get_connection()
    # Quick peek: LIMIT 5
    res = conn.execute(
        f"SELECT * FROM {func}(?) LIMIT 5",
        [url],
    )
    cols = [desc[0] for desc in res.description]
    rows = [dict(zip(cols, row)) for row in res.fetchall()]
    return func, rows


def register_source(
    name: str, url: str, materialize: bool = False
) -> str:
    """Register a remote data source.

    If materialize=True, copies remote data into a local table.
    Otherwise creates a VIEW that queries the remote source live.
    """
    install_httpfs()
    func = infer_read_function(url)
    conn = get_connection()

    # Ensure metadata table exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_sources (
            source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            read_func TEXT,
            materialized BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )

    safe_name = name.replace(" ", "_").replace("-", "").lower()
    # Quote the URL as a SQL string literal for embedding in DDL
    # Using repr-like single-quote escaping; simpler: just replace inner quotes
    url_sql = url.replace("'", "''")

    if materialize:
        conn.execute(
            f"CREATE OR REPLACE TABLE {safe_name} AS SELECT * FROM {func}('{url_sql}')"
        )
    else:
        conn.execute(
            f"CREATE OR REPLACE VIEW {safe_name} AS SELECT * FROM {func}('{url_sql}')"
        )

    inserted = conn.execute(
        "INSERT INTO data_sources (name, url, read_func, materialized) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET url=excluded.url, "
        "read_func=excluded.read_func, materialized=excluded.materialized "
        "RETURNING source_id",
        [name, url, func, materialize],
    ).fetchone()
    return str(inserted[0])


def remove_source(source_id: str) -> None:
    conn = get_connection()
    row = conn.execute(
        "SELECT name, materialized FROM data_sources WHERE source_id = ?",
        [source_id],
    ).fetchone()
    if row:
        safe_name = row[0].replace(" ", "_").replace("-", "_").lower()
        if row[1]:
            conn.execute(f"DROP TABLE IF EXISTS {safe_name}")
        else:
            conn.execute(f"DROP VIEW IF EXISTS {safe_name}")
    conn.execute("DELETE FROM data_sources WHERE source_id = ?", [source_id])


def query_source(name: str, limit: int = 100) -> list[dict]:
    """Run a SELECT * on a registered source."""
    conn = get_connection()
    safe_name = name.replace(" ", "_").replace("-", "_").lower()
    res = conn.execute(f"SELECT * FROM {safe_name} LIMIT ?", [limit])
    cols = [desc[0] for desc in res.description]
    return [dict(zip(cols, row)) for row in res.fetchall()]
