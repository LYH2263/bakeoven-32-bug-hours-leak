"""API 级校验：该炉营业门约束排产/窗口，非法门不落库。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database import Base, get_db
from app.models.models import Batch, ConflictLog, Oven, Product


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestSession()
    p1 = Product(name="欧包", ferment_min=40, bake_min=20)  # 共 60 分钟
    p2 = Product(name="短烤", ferment_min=0, bake_min=30)
    default_oven = Oven(label="默认门炉", capacity_note="")  # 模型默认 480–1320
    custom_oven = Oven(label="早班炉", capacity_note="", open_min=9 * 60, close_min=20 * 60)
    db.add_all([p1, p2, default_oven, custom_oven])
    db.commit()

    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app), db, p1, p2, default_oven, custom_oven
    db.close()


def test_patch_equal_door_rejected_and_not_persisted(client):
    c, db, _p1, _p2, default_oven, _ = client
    r = c.patch(f"/api/ovens/{default_oven.id}", json={"open_min": 600, "close_min": 600})
    assert r.status_code == 422
    db.expire_all()
    saved = db.get(Oven, default_oven.id)
    assert (saved.open_min, saved.close_min) == (480, 1320)


def test_patch_close_earlier_than_open_rejected(client):
    c, _db, _, _, oven, _ = client
    r = c.patch(f"/api/ovens/{oven.id}", json={"open_min": 1200, "close_min": 600})
    assert r.status_code == 422


def test_patch_valid_door_persists(client):
    c, _db, _, _, oven, _ = client
    r = c.patch(f"/api/ovens/{oven.id}", json={"open_min": 7 * 60, "close_min": 19 * 60})
    assert r.status_code == 200
    assert (r.json()["open_min"], r.json()["close_min"]) == (420, 1140)


def test_batch_straddling_close_rejected_with_door_message(client):
    c, db, p1, _p2, _default, custom = client
    # 早班炉 9:00–20:00；19:30 开工 → 20:30 才收工，探出打烊
    r = c.post(
        "/api/batches",
        json={"product_id": p1.id, "oven_id": custom.id, "start_min": 19 * 60 + 30},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "营业时段" in detail and "20:00" in detail
    # 超门不是撞批次：不进库、不写冲突日志
    assert db.scalars(select(Batch)).all() == []
    assert db.scalars(select(ConflictLog)).all() == []


def test_batch_touching_open_and_close_allowed_half_open(client):
    c, _db, p1, _p2, _default, custom = client
    # 9:00 开门点开工（酵 9:00–9:40，烤 9:40–10:00）
    ok_start = c.post("/api/batches", json={"product_id": p1.id, "oven_id": custom.id, "start_min": 9 * 60})
    assert ok_start.status_code == 200
    # 19:00 开工，恰在 20:00 打烊点收工，半开允许
    ok_end = c.post(
        "/api/batches",
        json={"product_id": p1.id, "oven_id": custom.id, "start_min": 19 * 60, "code": "BO-EDGE"},
    )
    assert ok_end.status_code == 200


def test_batch_before_open_rejected(client):
    c, db, p2, _p1b, _default, custom = client
    # 30 分钟短烤，8:50 开工 → 9:20 收工；发酵段探出开门
    r = c.post("/api/batches", json={"product_id": p2.id, "oven_id": custom.id, "start_min": 8 * 60 + 50})
    assert r.status_code == 422
    assert "营业时段" in r.json()["detail"]
    assert db.scalars(select(Batch)).all() == []


def test_windows_searched_within_each_oven_door(client):
    c, _db, p1, _p2, default_oven, custom_oven = client
    r = c.get(f"/api/windows?product_id={p1.id}")
    assert r.status_code == 200
    rows = {w["oven_id"]: w for w in r.json()}
    # 默认门炉：未改门仍给 8–22 的结果，且从 8:00 起
    assert rows[default_oven.id]["start_min"] == 8 * 60
    assert rows[default_oven.id]["end_min"] == 9 * 60
    # 早班炉：窗口夹在 9:00–20:00 内
    w = rows[custom_oven.id]
    assert 9 * 60 <= w["start_min"] and w["end_min"] <= 20 * 60


def test_windows_none_when_door_shorter_than_recipe(client):
    c, db, p1, _p2, _default, custom_oven = client
    # 把早班炉门缩到只有 30 分钟，配方需 60 分钟 → 该炉无窗口
    r = c.patch(f"/api/ovens/{custom_oven.id}", json={"open_min": 9 * 60, "close_min": 9 * 60 + 30})
    assert r.status_code == 200
    rows = c.get(f"/api/windows?product_id={p1.id}").json()
    assert custom_oven.id not in {w["oven_id"] for w in rows}
