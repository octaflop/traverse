from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.services.sources import (
    list_sources,
    preview_source,
    register_source,
    remove_source,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/sources", response_class=HTMLResponse)
async def get_sources(request: Request):
    sources = list_sources()
    return templates.TemplateResponse(
        request,
        "partials/sources.html",
        {"sources": sources},
    )


@router.post("/sources/preview", response_class=HTMLResponse)
async def preview(request: Request, url: str = Form(...)):
    try:
        func, rows = preview_source(url)
        return templates.TemplateResponse(
            request,
            "partials/source_preview.html",
            {"url": url, "read_func": func, "rows": rows, "error": None},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/source_preview.html",
            {"url": url, "read_func": None, "rows": [], "error": str(e)},
        )


@router.post("/sources", response_class=HTMLResponse)
async def create_source(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    materialize: str = Form("false"),
):
    is_materialized = materialize.lower() == "true"
    try:
        register_source(name, url, materialize=is_materialized)
        msg = f"Registered {'snapshot of' if is_materialized else 'live view over'} {name}."
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/sources.html",
            {
                "sources": list_sources(),
                "error": str(e),
            },
        )

    sources = list_sources()
    return templates.TemplateResponse(
        request,
        "partials/sources.html",
        {"sources": sources, "success": msg},
    )


@router.delete("/sources/{source_id}", response_class=HTMLResponse)
async def delete_source(request: Request, source_id: str):
    remove_source(source_id)
    sources = list_sources()
    return templates.TemplateResponse(
        request,
        "partials/sources.html",
        {"sources": sources},
    )
