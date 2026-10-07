from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.db import add_user_waypoint, delete_user_waypoint, list_user_waypoints

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/waypoints", response_class=HTMLResponse)
async def get_waypoints(request: Request):
    waypoints = list_user_waypoints()
    return templates.TemplateResponse(
        request, "partials/waypoints.html", {"waypoints": waypoints}
    )


@router.post("/waypoints", response_class=HTMLResponse)
async def create_waypoint(
    request: Request,
    name: str = Form(...),
    type: str = Form(""),
    lat: float = Form(...),
    lon: float = Form(...),
    city: str = Form(""),
    country: str = Form(""),
    tags: str = Form(""),
    methods: str = Form("all"),
    seasons: str = Form("all"),
):
    add_user_waypoint(name, type, lat, lon, city, country, tags, methods, seasons)
    waypoints = list_user_waypoints()
    return templates.TemplateResponse(
        request, "partials/waypoints.html", {"waypoints": waypoints}
    )


@router.delete("/waypoints/{waypoint_id}", response_class=HTMLResponse)
async def remove_waypoint(request: Request, waypoint_id: str):
    delete_user_waypoint(waypoint_id)
    waypoints = list_user_waypoints()
    return templates.TemplateResponse(
        request, "partials/waypoints.html", {"waypoints": waypoints}
    )
