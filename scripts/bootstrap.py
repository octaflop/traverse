#!/usr/bin/env python3
"""Bootstrap script: download airport data and seed DuckDB."""

import sys
from pathlib import Path

import duckdb
import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "traverse.db"
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
NAVAIDS_URL = "https://davidmegginson.github.io/ourairports-data/navaids.csv"
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


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))

    # Airports
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
        WHERE type IN ('large_airport', 'medium_airport', 'small_airport', 'seaplane_base', 'helioport')
        """,
        [str(AIRPORTS_CSV)],
    )
    conn.execute("CREATE INDEX idx_airports_iata ON airports(iata_code)")
    conn.execute("CREATE INDEX idx_airports_ident ON airports(ident)")
    conn.execute("CREATE INDEX idx_airports_name ON airports(name)")
    count = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
    print(f"Loaded {count} airports.")

    # Navaids
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

    # POIs from CSV
    conn.execute("DROP TABLE IF EXISTS pois")
    if POIS_CSV.exists():
        conn.execute(
            """
            CREATE TABLE pois AS
            SELECT
                poi_id,
                name,
                type,
                lat,
                lon,
                city,
                country,
                tags
            FROM read_csv(?, header=true, nullstr='')
            """,
            [str(POIS_CSV)],
        )
        count = conn.execute("SELECT COUNT(*) FROM pois").fetchone()[0]
        print(f"Loaded {count} POIs.")
    else:
        conn.execute("CREATE TABLE pois (poi_id INTEGER, name VARCHAR, type VARCHAR, lat DOUBLE, lon DOUBLE, city VARCHAR, country VARCHAR, tags VARCHAR)")
        print("No pois.csv found; created empty table.")

    conn.close()
    print(f"Database ready at {DB_PATH}")


def main() -> int:
    download(AIRPORTS_URL, AIRPORTS_CSV)
    download(NAVAIDS_URL, NAVAIDS_CSV)
    init_db()
    return 0


if __name__ == "__main__":
    sys.exit(main())
