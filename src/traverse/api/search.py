import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.services.geocode import geocode_location
from traverse.services.search import (
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
    if coords is None:
        return templates.TemplateResponse(
            request,
            "partials/results.html",
            {
                "location": location,
                "method": method,
                "error": "Could not geocode that location. Try being more specific (e.g. 'Ikebukuro, Tokyo, Japan').",
                "airports_json": "[]",
                "pois_json": "[]",
                "waypoints_json": "[]",
            },
        )

    lat, lon = coords
    airports = search_airports(lat, lon, method)
    pois = search_pois(lat, lon, method)
    user_waypoints = search_user_waypoints(lat, lon, method)

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "location": location,
            "method": method,
            "lat": lat,
            "lon": lon,
            "airports": airports,
            "pois": pois,
            "user_waypoints": user_waypoints,
            "airports_json": json.dumps(airports),
            "pois_json": json.dumps(pois),
            "waypoints_json": json.dumps(user_waypoints),
        },
    )
