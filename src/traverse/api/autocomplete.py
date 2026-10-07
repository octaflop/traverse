from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from traverse.db import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _autocomplete_results(q: str, limit: int = 8):
    conn = get_connection()
    q_clean = q.strip()
    if not q_clean or len(q_clean) < 2:
        return []

    # Deduplicated: pick best-matching row per canonical_name + lat + lon
    res = conn.execute(
        """
        SELECT * FROM (
            SELECT
                source,
                lookup_code,
                canonical_name,
                city,
                country,
                lat,
                lon,
                search_text,
                CASE
                    WHEN UPPER(lookup_code) = UPPER(?) THEN 1
                    WHEN UPPER(canonical_name) = UPPER(?) THEN 2
                    WHEN canonical_name ILIKE ? || '%' THEN 3
                    WHEN city ILIKE ? || '%' THEN 4
                    WHEN search_text ILIKE '%' || ? || '%' THEN 5
                    ELSE 6
                END AS rank,
                ROW_NUMBER() OVER (
                    PARTITION BY canonical_name, lat, lon
                    ORDER BY
                        CASE WHEN UPPER(lookup_code) = UPPER(?) THEN 0 ELSE 1 END,
                        CASE source WHEN 'airport' THEN 0 ELSE 1 END
                ) AS rn
            FROM geocodes
            WHERE UPPER(lookup_code) = UPPER(?)
               OR UPPER(canonical_name) = UPPER(?)
               OR canonical_name ILIKE ? || '%'
               OR city ILIKE ? || '%'
               OR search_text ILIKE '%' || ? || '%'
        )
        WHERE rn = 1
        ORDER BY rank, source='city' DESC, source='poi' DESC, source='airport' DESC
        LIMIT ?
        """,
        [q_clean, q_clean, q_clean, q_clean, q_clean,
         q_clean,
         q_clean, q_clean, q_clean, q_clean, q_clean, limit],
    )
    cols = [desc[0] for desc in res.description]
    return [dict(zip(cols, row)) for row in res.fetchall()]


@router.get("/autocomplete", response_class=HTMLResponse)
async def autocomplete(
    request: Request,
    q: str = Query(default=""),
):
    results = _autocomplete_results(q)
    return templates.TemplateResponse(
        request,
        "partials/autocomplete.html",
        {"q": q, "results": results},
    )
