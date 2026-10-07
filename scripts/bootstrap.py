#!/usr/bin/env python3
"""Bootstrap script: download public datasets and seed DuckDB."""

import sys
from pathlib import Path

import duckdb
import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "traverse.db"

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
NAVAIDS_URL = "https://davidmegginson.github.io/ourairports-data/navaids.csv"
CITIES_CSV = DATA_DIR / "cities.csv"
POIS_CSV = DATA_DIR / "pois.csv"

AIRPORTS_CSV = DATA_DIR / "airports.csv"
NAVAIDS_CSV = DATA_DIR / "navaids.csv"


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url} ...")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
    print(f"Saved to {dest}")


def _load_cities(conn: duckdb.DuckDBPyConnection) -> None:
    """Load supplementary city locations from CSV."""
    conn.execute("DROP TABLE IF EXISTS cities")
    if CITIES_CSV.exists():
        conn.execute(
            """
            CREATE TABLE cities AS
            SELECT name, country_code, lat, lon
            FROM read_csv(?, header=true, nullstr='')
            """,
            [str(CITIES_CSV)],
        )
        # Deduplicate by name+country_code average coordinates
        conn.execute(
            """
            CREATE TABLE cities_dedup AS
            SELECT name, country_code, avg(lat) AS lat, avg(lon) AS lon
            FROM cities GROUP BY name, country_code
            """
        )
        conn.execute("DROP TABLE cities")
        conn.execute("ALTER TABLE cities_dedup RENAME TO cities")
        conn.execute("CREATE INDEX idx_cities_name ON cities(name)")
        conn.execute("CREATE INDEX idx_cities_country ON cities(country_code)")
        count = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
        print(f"Loaded {count} supplemental cities.")
    else:
        conn.execute(
            "CREATE TABLE cities (name VARCHAR, country_code VARCHAR, lat DOUBLE, lon DOUBLE)"
        )
        print("No cities.csv found; created empty table.")


def _build_geocodes(conn: duckdb.DuckDBPyConnection) -> None:
    """Build a unified geocodes table from all sources for fast offline lookup."""
    conn.execute("DROP TABLE IF EXISTS geocodes")

    # Unified table with columns useful for quick keyword/code matching
    conn.execute(
        """
        CREATE TABLE geocodes AS

        -- Airports: ident
        SELECT
            'airport' AS source,
            ident AS lookup_code,
            name AS canonical_name,
            municipality AS city,
            iso_country AS country,
            latitude_deg AS lat,
            longitude_deg AS lon,
            type,
            CONCAT_WS(' ', ident, name, municipality) AS search_text
        FROM airports
        WHERE ident IS NOT NULL AND ident != ''

        UNION ALL

        -- Airports: gps_code ( covers KSVR-like re-codes )
        SELECT
            'airport' AS source,
            gps_code AS lookup_code,
            name AS canonical_name,
            municipality AS city,
            iso_country AS country,
            latitude_deg AS lat,
            longitude_deg AS lon,
            type,
            CONCAT_WS(' ', gps_code, name, municipality) AS search_text
        FROM airports
        WHERE gps_code IS NOT NULL AND gps_code != ''

        UNION ALL

        -- Airports: iata_code
        SELECT
            'airport' AS source,
            iata_code AS lookup_code,
            name AS canonical_name,
            municipality AS city,
            iso_country AS country,
            latitude_deg AS lat,
            longitude_deg AS lon,
            type,
            CONCAT_WS(' ', iata_code, name, municipality) AS search_text
        FROM airports
        WHERE iata_code IS NOT NULL AND iata_code != ''

        UNION ALL

        -- Airports: local_code
        SELECT
            'airport' AS source,
            local_code AS lookup_code,
            name AS canonical_name,
            municipality AS city,
            iso_country AS country,
            latitude_deg AS lat,
            longitude_deg AS lon,
            type,
            CONCAT_WS(' ', local_code, name, municipality) AS search_text
        FROM airports
        WHERE local_code IS NOT NULL AND local_code != ''

        UNION ALL

        -- Cities from supplemental CSV
        SELECT
            'city' AS source,
            name AS lookup_code,
            name AS canonical_name,
            name AS city,
            country_code AS country,
            lat,
            lon,
            'city' AS type,
            CONCAT_WS(' ', name, country_code) AS search_text
        FROM cities

        UNION ALL

        -- Demo POIs
        SELECT
            'poi' AS source,
            CAST(poi_id AS VARCHAR) AS lookup_code,
            name AS canonical_name,
            city AS city,
            country AS country,
            lat,
            lon,
            type,
            CONCAT_WS(' ', name, city, country, tags) AS search_text
        FROM pois

        UNION ALL

        -- Navaids
        SELECT
            'navaid' AS source,
            ident AS lookup_code,
            name AS canonical_name,
            NULL AS city,
            iso_country AS country,
            latitude_deg AS lat,
            longitude_deg AS lon,
            type,
            CONCAT_WS(' ', ident, name) AS search_text
        FROM navaids
        """
    )

    conn.execute("CREATE INDEX idx_geocodes_code ON geocodes(lookup_code)")
    conn.execute("CREATE INDEX idx_geocodes_name ON geocodes(canonical_name)")

    count = conn.execute("SELECT COUNT(*) FROM geocodes").fetchone()[0]
    print(f"Built unified geocodes table with {count} rows.")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))

    # --- Airports ---
    conn.execute("DROP TABLE IF EXISTS airports")
    conn.execute(
        """
        CREATE TABLE airports AS
        SELECT
            id,
            ident,
            type,
            name,
            iata_code,
            local_code,
            latitude_deg,
            longitude_deg,
            elevation_ft,
            iso_country,
            municipality,
            scheduled_service,
            gps_code,
            home_link,
            wikipedia_link,
            keywords
        FROM read_csv(?, header=true, nullstr='')
        WHERE type IN ('large_airport', 'medium_airport', 'small_airport', 'seaplane_base', 'heliport')
        """,
        [str(AIRPORTS_CSV)],
    )
    conn.execute("CREATE INDEX idx_airports_iata ON airports(iata_code)")
    conn.execute("CREATE INDEX idx_airports_ident ON airports(ident)")
    conn.execute("CREATE INDEX idx_airports_name ON airports(name)")
    count = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
    print(f"Loaded {count} airports.")

    # --- Navaids ---
    conn.execute("DROP TABLE IF EXISTS navaids")
    conn.execute(
        """
        CREATE TABLE navaids AS
        SELECT
            id,
            ident,
            name,
            type,
            frequency_khz,
            latitude_deg,
            longitude_deg,
            elevation_ft,
            iso_country,
            dme_latitude_deg,
            dme_longitude_deg,
            associated_airport
        FROM read_csv(?, header=true, nullstr='')
        WHERE type IN ('VOR', 'VOR-DME', 'VORTAC', 'DME')
        """,
        [str(NAVAIDS_CSV)],
    )
    conn.execute("CREATE INDEX idx_navaids_ident ON navaids(ident)")
    count = conn.execute("SELECT COUNT(*) FROM navaids").fetchone()[0]
    print(f"Loaded {count} navaids.")

    # --- POIs ---
    conn.execute("DROP TABLE IF EXISTS pois")
    if POIS_CSV.exists():
        conn.execute(
            """
            CREATE TABLE pois AS
            SELECT poi_id, name, type, lat, lon, city, country, tags
            FROM read_csv(?, header=true, nullstr='')
            """,
            [str(POIS_CSV)],
        )
        count = conn.execute("SELECT COUNT(*) FROM pois").fetchone()[0]
        print(f"Loaded {count} POIs.")
    else:
        conn.execute(
            "CREATE TABLE pois (poi_id INTEGER, name VARCHAR, type VARCHAR, "
            "lat DOUBLE, lon DOUBLE, city VARCHAR, country VARCHAR, tags VARCHAR)"
        )
        print("No pois.csv found; created empty table.")

    # --- Cities ---
    _load_cities(conn)

    # --- Unified geocodes ---
    _build_geocodes(conn)

    conn.close()
    print(f"Database ready at {DB_PATH}")


def main() -> int:
    download(AIRPORTS_URL, AIRPORTS_CSV)
    download(NAVAIDS_URL, NAVAIDS_CSV)
    init_db()
    return 0


if __name__ == "__main__":
    sys.exit(main())
