#!/usr/bin/env python3
"""Bootstrap script: download public datasets and seed DuckDB."""

import sys
import zipfile
from io import BytesIO
from pathlib import Path

import duckdb
import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "traverse.db"

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
NAVAIDS_URL = "https://davidmegginson.github.io/ourairports-data/navaids.csv"
CITIES500_URL = "http://download.geonames.org/export/dump/cities500.zip"

POIS_CSV = DATA_DIR / "pois.csv"
CITIES_CSV = DATA_DIR / "cities.csv"

AIRPORTS_CSV = DATA_DIR / "airports.csv"
NAVAIDS_CSV = DATA_DIR / "navaids.csv"
CITIES500_ZIP = DATA_DIR / "cities500.zip"


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url} ...")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
    print(f"Saved to {dest}")


def _download_cities500() -> Path:
    """Download and extract the Geonames cities500 dataset."""
    CITIES500_ZIP.parent.mkdir(parents=True, exist_ok=True)
    download(CITIES500_URL, CITIES500_ZIP)

    print(f"Extracting {CITIES500_ZIP} ...")
    cities500_txt = CITIES500_ZIP.with_suffix(".txt")
    with zipfile.ZipFile(CITIES500_ZIP, "r") as z:
        for name in z.namelist():
            if name.endswith(".txt") and "cities500" in name:
                z.extract(name, CITIES500_ZIP.parent)
                extracted = CITIES500_ZIP.parent / name
                extracted.rename(cities500_txt)
                break
    print(f"Extracted to {cities500_txt}")
    return cities500_txt


def _load_cities(conn: duckdb.DuckDBPyConnection) -> None:
    """Load city locations from Geonames cities500 + local CSV, deduplicate."""
    conn.execute("DROP TABLE IF EXISTS cities_raw")
    conn.execute("DROP TABLE IF EXISTS cities")

    # Load cities500 from Geonames (TSV, no header)
    # columns: geonameid name asciiname alternatenames lat lon fclass fcode
    #          country cc2 admin1 admin2 admin3 admin4 population elevation dem
    #          timezone moddate
    cities500_txt = _download_cities500()
    conn.execute(
        """
        CREATE TABLE cities_raw AS
        SELECT
            column00::INTEGER AS geonameid,
            column01 AS name,
            column02 AS asciiname,
            TRY_CAST(column04 AS DOUBLE) AS lat,
            TRY_CAST(column05 AS DOUBLE) AS lon,
            column08 AS country_code,
            TRY_CAST(column14 AS BIGINT) AS population
        FROM read_csv(?, header=false, delim='\\t', quote='')
        """,
        [str(cities500_txt)],
    )
    # Keep only rows with valid lat/lon
    conn.execute(
        """
        DELETE FROM cities_raw
        WHERE lat IS NULL OR lon IS NULL
        """
    )
    count = conn.execute("SELECT COUNT(*) FROM cities_raw").fetchone()[0]
    print(f"Loaded {count} cities from Geonames cities500.")

    # Also load local CSV if present
    if CITIES_CSV.exists():
        conn.execute(
            """
            INSERT INTO cities_raw (name, asciiname, lat, lon, country_code, population)
            SELECT name, name, lat, lon, country_code, 0
            FROM read_csv(?, header=true, nullstr='')
            """,
            [str(CITIES_CSV)],
        )
        csv_count = conn.execute(
            "SELECT COUNT(*) FROM cities_raw WHERE population = 0"
        ).fetchone()[0]
        print(f"Also loaded {csv_count} supplemental cities from CSV.")

    # Deduplicate: keep highest population per name+country
    conn.execute(
        """
        CREATE TABLE cities AS
        SELECT
            name,
            country_code,
            lat,
            lon
        FROM (
            SELECT
                name,
                country_code,
                lat,
                lon,
                ROW_NUMBER() OVER (
                    PARTITION BY name, country_code
                    ORDER BY population DESC, geonameid ASC
                ) AS rn
            FROM cities_raw
        )
        WHERE rn = 1
        """
    )
    conn.execute("CREATE INDEX idx_cities_name ON cities(name)")
    conn.execute("CREATE INDEX idx_cities_country ON cities(country_code)")
    count = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    print(f"Deduplicated to {count} unique cities.")


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

        -- Cities from geonames + supplemental CSV
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
