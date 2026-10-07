from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.services.osm import fetch_and_insert_osm_pois, osm_count, search_osm_pois

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.post("/osm/fetch", response_class=HTMLResponse)
async def fetch_osm_pois(request: Request):
    """HTMX endpoint: fetch OSM POIs for a given lat/lon (passed as query params).

    Usage via HTMX: hx-post="/osm/fetch?lat=35.0&lon=139.0&method=bike"
    """
    lat = float(request.query_params.get("lat", 0))
    lon = float(request.query_params.get("lon", 0))
    method = request.query_params.get("method", "default")

    if not lat or not lon:
        return templates.TemplateResponse(
            request,
            "partials/osm_status.html",
            {"message": "Need a location first. Run a search!", "count": osm_count()},
        )

    inserted = fetch_and_insert_osm_pois(lat, lon, method)
    total = osm_count()
    return templates.TemplateResponse(
        request,
        "partials/osm_status.html",
        {
            "message": f"Fetched {inserted} new POIs from OpenStreetMap ({method} radius).",
            "count": total,
            "lat": lat,
            "lon": lon,
        },
    )


@router.get("/osm/nearby", response_class=HTMLResponse)
async def get_osm_nearby(
    request: Request,
    lat: float = 0,
    lon: float = 0,
    method: str = "default",
):
    """Return HTML partial of nearby OSM POIs."""
    if not lat or not lon:
        return templates.TemplateResponse(
            request,
            "partials/osm_results.html",
            {"results": [], "has_more": True},
        )

    results = search_osm_pois(lat, lon, method, limit=20)
    return templates.TemplateResponse(
        request,
        "partials/osm_results.html",
        {"results": results, "has_more": len(results) >= 20},
    )
