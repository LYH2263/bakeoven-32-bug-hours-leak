from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _ensure_oven_hour_columns() -> None:
    """Add open_min/close_min to pre-existing ovens tables (create_all won't alter).

    New tables get nullable columns straight from the model; columns added to
    old deployments were NOT NULL, so drop that constraint — NULL means the
    oven has no door configured and falls back to shop-wide 08:00–22:00.
    """
    inspector = inspect(engine)
    if "ovens" not in inspector.get_table_names():
        return
    cols = {c["name"]: c for c in inspector.get_columns("ovens")}
    with engine.begin() as conn:
        if "open_min" not in cols:
            conn.execute(text("ALTER TABLE ovens ADD COLUMN open_min INTEGER"))
        if "close_min" not in cols:
            conn.execute(text("ALTER TABLE ovens ADD COLUMN close_min INTEGER"))
        if engine.dialect.name != "sqlite":
            conn.execute(text("ALTER TABLE ovens ALTER COLUMN open_min DROP NOT NULL"))
            conn.execute(text("ALTER TABLE ovens ALTER COLUMN close_min DROP NOT NULL"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_oven_hour_columns()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="BakeOven", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
