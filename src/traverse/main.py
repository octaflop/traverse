from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from traverse.api.pages import router as pages_router
from traverse.api.search import router as search_router
from traverse.config import settings
from traverse.db import connect_db, disconnect_db, init_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_db()
    init_schema()
    yield
    disconnect_db()


app = FastAPI(title="Traverse", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages_router)
app.include_router(search_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("traverse.main:app", host=settings.api_host, port=settings.api_port, reload=True)
