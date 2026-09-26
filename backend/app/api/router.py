from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Batch, ConflictLog, Oven, Product
from app.schemas.schemas import (
    BatchCreate,
    BatchOut,
    ConflictOut,
    GanttBlock,
    OvenHoursUpdate,
    OvenOut,
    ProductOut,
    WindowOut,
)
from app.services.oven_engine import (
    Occupancy,
    RecipeDurations,
    build_occupancies,
    find_conflicts,
    fits_operating_hours,
    is_valid_door,
    resolve_oven_hours,
    next_free_window,
)

api_router = APIRouter()


def _recipe(p: Product) -> RecipeDurations:
    return RecipeDurations(p.ferment_min, p.bake_min)


_PHASE_LABEL = {"ferment": "发酵", "bake": "烘烤"}


def _hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _out_of_hours_detail(oven: Oven, candidates: list[Occupancy]) -> str:
    """话术点明是超出该炉自己的门，并指出探出的是哪一段。"""
    lo, hi = resolve_oven_hours(oven.open_min, oven.close_min)
    for cand in candidates:
        iv = cand.interval
        if iv.end <= iv.start:
            continue
        if iv.start < lo:
            side = f"{_PHASE_LABEL.get(cand.phase, cand.phase)}段 {_hm(iv.start)} 早于开门 {_hm(lo)}"
        elif iv.end > hi:
            side = f"{_PHASE_LABEL.get(cand.phase, cand.phase)}段 {_hm(iv.end)} 晚于打烊 {_hm(hi)}"
        else:
            continue
        return (
            f"无法排入「{oven.label}」：{side}；该炉营业时段为半开区间 "
            f"[{_hm(lo)}, {_hm(hi)})，整段占炉（发酵+烘烤）都须落在门内"
        )
    return f"无法排入「{oven.label}」：占炉时段超出该炉营业 [{_hm(lo)}, {_hm(hi)})"


def _all_occupancies(db: Session) -> list[Occupancy]:
    batches = db.scalars(select(Batch)).all()
    out: list[Occupancy] = []
    for b in batches:
        p = db.get(Product, b.product_id)
        if not p:
            continue
        out.extend(build_occupancies(b.oven_id, b.id, b.start_min, _recipe(p)))
    return out


def _batch_out(db: Session, b: Batch) -> BatchOut:
    p = db.get(Product, b.product_id)
    o = db.get(Oven, b.oven_id)
    ferment_end = b.start_min + (p.ferment_min if p else 0)
    bake_end = ferment_end + (p.bake_min if p else 0)
    return BatchOut(
        id=b.id,
        product_id=b.product_id,
        oven_id=b.oven_id,
        code=b.code,
        start_min=b.start_min,
        status=b.status,
        product_name=p.name if p else None,
        oven_label=o.label if o else None,
        ferment_end=ferment_end,
        bake_end=bake_end,
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.id)).all()


@api_router.get("/ovens", response_model=list[OvenOut])
def ovens(db: Session = Depends(get_db)):
    return db.scalars(select(Oven).order_by(Oven.id)).all()


@api_router.patch("/ovens/{oven_id}", response_model=OvenOut)
def update_oven_hours(oven_id: int, body: OvenHoursUpdate, db: Session = Depends(get_db)):
    oven = db.get(Oven, oven_id)
    if not oven:
        raise HTTPException(404, "炉位不存在")
    if not is_valid_door(body.open_min, body.close_min):
        if body.open_min is None or body.close_min is None:
            raise HTTPException(400, "开门与打烊须同时填写，或同时清空以沿用全店 08:00–22:00")
        raise HTTPException(
            400,
            f"非法营业时段：开门 {_hm(body.open_min)} 不早于打烊 {_hm(body.close_min)}，未保存",
        )
    oven.open_min = body.open_min
    oven.close_min = body.close_min
    db.commit()
    db.refresh(oven)
    return oven


@api_router.get("/batches", response_model=list[BatchOut])
def batches(db: Session = Depends(get_db)):
    rows = db.scalars(select(Batch).order_by(Batch.start_min)).all()
    return [_batch_out(db, b) for b in rows]


@api_router.post("/batches", response_model=BatchOut)
def create_batch(body: BatchCreate, db: Session = Depends(get_db)):
    product = db.get(Product, body.product_id)
    oven = db.get(Oven, body.oven_id)
    if not product or not oven:
        raise HTTPException(404, "产品或炉位不存在")
    recipe = _recipe(product)
    candidates = build_occupancies(oven.id, -1, body.start_min, recipe)
    code = body.code or f"BO-{body.start_min}"
    if not fits_operating_hours(candidates, oven.open_min, oven.close_min):
        raise HTTPException(422, _out_of_hours_detail(oven, candidates))
    existing = _all_occupancies(db)
    hits = find_conflicts(existing, candidates)
    if hits:
        ex, cand = hits[0]
        detail = (
            f"该时段在「{oven.label}」与批次#{ex.batch_id} 的 "
            f"{_PHASE_LABEL.get(ex.phase, ex.phase)}段重叠："
            f"[{_hm(cand.interval.start)},{_hm(cand.interval.end)})"
        )
        db.add(ConflictLog(batch_code=code, oven_id=oven.id, detail=detail))
        db.commit()
        raise HTTPException(409, detail)
    batch = Batch(
        product_id=product.id,
        oven_id=oven.id,
        code=code,
        start_min=body.start_min,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_out(db, batch)


@api_router.get("/gantt", response_model=list[GanttBlock])
def gantt(db: Session = Depends(get_db)):
    blocks: list[GanttBlock] = []
    for b in db.scalars(select(Batch).order_by(Batch.start_min)).all():
        p = db.get(Product, b.product_id)
        o = db.get(Oven, b.oven_id)
        if not p or not o:
            continue
        for occ in build_occupancies(b.oven_id, b.id, b.start_min, _recipe(p)):
            blocks.append(
                GanttBlock(
                    batch_id=b.id,
                    code=b.code,
                    oven_id=o.id,
                    oven_label=o.label,
                    phase=occ.phase,
                    start_min=occ.interval.start,
                    end_min=occ.interval.end,
                )
            )
    return blocks


@api_router.get("/conflicts", response_model=list[ConflictOut])
def conflicts(db: Session = Depends(get_db)):
    return db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).all()


@api_router.get("/windows", response_model=list[WindowOut])
def windows(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "产品不存在")
    duration = product.ferment_min + product.bake_min
    existing = _all_occupancies(db)
    out: list[WindowOut] = []
    for oven in db.scalars(select(Oven).order_by(Oven.id)).all():
        lo, hi = resolve_oven_hours(oven.open_min, oven.close_min)
        w = next_free_window(
            existing,
            oven.id,
            duration,
            search_from=lo,
            search_to=hi,
        )
        if w:
            out.append(
                WindowOut(
                    oven_id=oven.id,
                    oven_label=oven.label,
                    start_min=w.start,
                    end_min=w.end,
                    duration_min=duration,
                )
            )
    return out
