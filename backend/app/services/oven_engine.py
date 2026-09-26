"""Oven scheduling with half-open ferment+bake intervals and next free window."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int  # minutes from day origin
    end: int  # exclusive

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class RecipeDurations:
    ferment_min: int
    bake_min: int

    @property
    def total(self) -> int:
        return self.ferment_min + self.bake_min


@dataclass(frozen=True)
class Occupancy:
    oven_id: int
    interval: Interval
    phase: str  # ferment | bake
    batch_id: int


def build_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    recipe: RecipeDurations,
) -> list[Occupancy]:
    ferment = Interval(start_min, start_min + recipe.ferment_min)
    bake = Interval(ferment.end, ferment.end + recipe.bake_min)
    return [
        Occupancy(oven_id, ferment, "ferment", batch_id),
        Occupancy(oven_id, bake, "bake", batch_id),
    ]


def find_conflicts(existing: list[Occupancy], candidates: list[Occupancy]) -> list[tuple[Occupancy, Occupancy]]:
    hits: list[tuple[Occupancy, Occupancy]] = []
    for cand in candidates:
        for ex in existing:
            if ex.oven_id != cand.oven_id:
                continue
            if ex.interval.overlaps(cand.interval):
                hits.append((ex, cand))
    return hits


DEFAULT_OPEN_MIN = 8 * 60
DEFAULT_CLOSE_MIN = 22 * 60


def shop_wide_hours() -> tuple[int, int]:
    """Default search band for free windows (ovens without a configured door)."""
    return DEFAULT_OPEN_MIN, DEFAULT_CLOSE_MIN


def resolve_oven_hours(
    open_min: int | None,
    close_min: int | None,
) -> tuple[int, int]:
    """Resolve an oven's own half-open operating band [open, close).

    Unconfigured ovens (either end missing) and ovens stuck with an invalid
    door (open not strictly before close) fall back to the shop-wide
    08:00–22:00 band.
    """
    if open_min is None or close_min is None:
        return shop_wide_hours()
    if open_min >= close_min:
        return shop_wide_hours()
    return open_min, close_min


def is_valid_door(open_min: int | None, close_min: int | None) -> bool:
    """A door is storable only when both ends are set and open < close.

    (None, None) is the legitimate "unconfigured" state and falls back to
    the shop-wide band; setting only one end is rejected.
    """
    if open_min is None and close_min is None:
        return True
    if open_min is None or close_min is None:
        return False
    return open_min < close_min


def fits_operating_hours(
    candidates: list[Occupancy],
    open_min: int | None,
    close_min: int | None,
) -> bool:
    """Return True only when the whole occupancy (ferment AND bake) lies in
    the oven's half-open band [open, close). Zero-length segments (e.g. a
    recipe with no ferment) do not occupy the oven."""
    lo, hi = resolve_oven_hours(open_min, close_min)
    for cand in candidates:
        start, end = cand.interval.start, cand.interval.end
        if end <= start:
            continue
        if start < lo or end > hi:
            return False
    return True


def hours_band_for_gantt(open_min: int | None, close_min: int | None) -> tuple[int, int]:
    """Operating band drawn for an oven row — its own door, else shop default."""
    return resolve_oven_hours(open_min, close_min)


def next_free_window(
    existing: list[Occupancy],
    oven_id: int,
    duration: int,
    search_from: int = 0,
    search_to: int = 24 * 60,
) -> Interval | None:
    """Find earliest half-open [start, start+duration) free on oven."""
    if duration <= 0:
        return None
    busy = sorted(
        [o.interval for o in existing if o.oven_id == oven_id],
        key=lambda i: i.start,
    )
    cursor = search_from
    for iv in busy:
        if iv.end <= cursor:
            continue
        if iv.start >= cursor + duration:
            end = cursor + duration
            if end <= search_to:
                return Interval(cursor, end)
            return None
        cursor = max(cursor, iv.end)
    if cursor + duration <= search_to:
        return Interval(cursor, cursor + duration)
    return None
