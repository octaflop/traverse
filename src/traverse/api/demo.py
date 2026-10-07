import random

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.db import get_connection
from traverse.services.search import (
    search_airports,
    search_pois,
    search_user_waypoints,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_METHOD_CYCLE = ["walk", "bike", "transit", "cessna 172"]

_CANDIDATE_CITIES = [
    # Japan
    "Tokyo", "Kyoto", "Osaka", "Hakodate", "Nara", "Takayama",
    # USA
    "Seattle", "Salt Lake City", "Provo", "San Francisco",
    # Australia
    "Brisbane", "Adelaide",
]


def _start_city() -> tuple[str, float, float]:
    """Pick a random candidate city that actually exists in our cities table."""
    conn = get_connection()
    for _ in range(3):
        city = random.choice(_CANDIDATE_CITIES)
        row = conn.execute(
            "SELECT name, lat, lon FROM cities WHERE name ILIKE ? LIMIT 1",
            [city],
        ).fetchone()
        if row:
            return str(row[0]), float(row[1]), float(row[2])
    # Ultimate fallback
    return "Tokyo", 35.6895, 139.6917


def _pick_next_location(all_results: list[dict], exclude_name: str) -> dict | None:
    """Pick a random result that isn't the current location."""
    choices = [r for r in all_results if r.get("name", "").lower() != exclude_name.lower()]
    if not choices:
        return None
    return random.choice(choices)


def _search_all(lat: float, lon: float, method: str) -> list[dict]:
    """Run all search types and tag results with source."""
    results = []
    for item in search_airports(lat, lon, method):
        item["_source"] = "airport"
        results.append(item)
    for item in search_pois(lat, lon, method):
        item["_source"] = "poi"
        results.append(item)
    for item in search_user_waypoints(lat, lon, method):
        item["_source"] = "waypoint"
        results.append(item)
    return results


@router.get("/demo", response_class=HTMLResponse)
async def demo_index(request: Request):
    return templates.TemplateResponse(
        request,
        "demo.html",
        {"started": False},
    )


@router.get("/demo/start", response_class=HTMLResponse)
async def demo_start(request: Request):
    """Pick a random starting city and run the first search."""
    name, lat, lon = _start_city()
    method = _METHOD_CYCLE[0]
    results = _search_all(lat, lon, method)

    return templates.TemplateResponse(
        request,
        "partials/demo_step.html",
        {
            "step": 0,
            "from_name": name,
            "method": method,
            "lat": lat,
            "lon": lon,
            "results": results,
            "done": False,
        },
    )


@router.post("/demo/step", response_class=HTMLResponse)
async def demo_step(
    request: Request,
    from_name: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    method: str = Query(...),
    step: int = Query(0),
):
    """Run the next organic search step."""
    results = _search_all(lat, lon, method)
    next_loc = _pick_next_location(results, from_name)

    if not next_loc or step >= len(_METHOD_CYCLE) - 1:
        # End: no valid next hop or reached max steps
        return templates.TemplateResponse(
            request,
            "partials/demo_step.html",
            {
                "step": step,
                "from_name": from_name,
                "method": method,
                "lat": lat,
                "lon": lon,
                "results": results,
                "done": True,
            },
        )

    # Extract coordinates from next location
    next_lat = next_loc.get("latitude_deg", next_loc.get("lat", lat))
    next_lon = next_loc.get("longitude_deg", next_loc.get("lon", lon))
    next_method = _METHOD_CYCLE[(step + 1) % len(_METHOD_CYCLE)]

    return templates.TemplateResponse(
        request,
        "partials/demo_step.html",
        {
            "step": step,
            "from_name": from_name,
            "method": method,
            "lat": lat,
            "lon": lon,
            "results": results,
            "done": False,
            "next_name": next_loc.get("name", "Unknown"),
            "next_lat": next_lat,
            "next_lon": next_lon,
            "next_method": next_method,
        },
    )
