import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.services.geocode import geocode_location
from traverse.services.osm import search_osm_pois
from traverse.services.search import (
    current_season_context,
    search_airports,
    search_pois,
    search_user_waypoints,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    location: str = Form(...),
    method: str = Form("default"),
):
    coords = await geocode_location(location)
    season_ctx = current_season_context()
    if coords is None:
        return templates.TemplateResponse(
            request,
            "partials/results.html",
            {
                "location": location,
                "method": method,
                "season": season_ctx,
                "error": (
                    "Could not geocode that location. "
                    "Try an airport code (e.g. <b>KBFI</b>, <b>KSVR</b>) "
                    "or a major city nearby. "
                    "If you know the exact coordinates, add it as a waypoint below."
                ),
                "airports_json": "[]",
                "pois_json": "[]",
                "waypoints_json": "[]",
            },
        )

    lat, lon = coords
    airports = search_airports(lat, lon, method)
    pois = search_pois(lat, lon, method)
    user_waypoints = search_user_waypoints(lat, lon, method)
    osm_pois = search_osm_pois(lat, lon, method)
    all_pois = pois + osm_pois

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "location": location,
            "method": method,
            "lat": lat,
            "lon": lon,
            "season": season_ctx,
            "airports": airports,
            "pois": pois,
            "osm_pois": osm_pois,
            "user_waypoints": user_waypoints,
            "airports_json": json.dumps(airports),
            "pois_json": json.dumps(all_pois),
            "waypoints_json": json.dumps(user_waypoints),
        },
    )
