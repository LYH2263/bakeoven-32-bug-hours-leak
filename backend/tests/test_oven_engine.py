from app.services.oven_engine import (
    Interval,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    find_conflicts,
    fits_operating_hours,
    next_free_window,
)


def test_half_open_no_touch_conflict():
    a = Occupancy(1, Interval(0, 30), "bake", 1)
    b = Occupancy(1, Interval(30, 60), "bake", 2)
    assert find_conflicts([a], [b]) == []


def test_overlap_detected():
    recipe = RecipeDurations(20, 30)
    cand = build_occupancies(1, 9, 10, recipe)
    existing = [Occupancy(1, Interval(25, 40), "bake", 1)]
    assert find_conflicts(existing, cand)


def test_next_free_window_after_busy():
    existing = [
        Occupancy(1, Interval(0, 40), "ferment", 1),
        Occupancy(1, Interval(40, 70), "bake", 1),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(70, 100)


def test_next_free_in_gap():
    existing = [
        Occupancy(1, Interval(0, 20), "bake", 1),
        Occupancy(1, Interval(80, 100), "bake", 2),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(20, 50)


def test_operating_hours_all_segments_inside():
    cand = build_occupancies(1, 9, 600, RecipeDurations(20, 30))  # [600,650)
    assert fits_operating_hours(cand, 480, 1320)


def test_operating_hours_half_open_edges_ok():
    # 开门点开工、打烊点收工都允许（打烊分钟本身不可排，区间端点互斥）
    cand = build_occupancies(1, 9, 480, RecipeDurations(20, 30))  # [480,530)
    assert fits_operating_hours(cand, 480, 1320)
    cand = build_occupancies(1, 9, 1270, RecipeDurations(20, 30))  # [1270,1320)
    assert fits_operating_hours(cand, 480, 1320)


def test_operating_hours_before_open_rejected():
    cand = build_occupancies(1, 9, 470, RecipeDurations(20, 30))  # [470,520)
    assert not fits_operating_hours(cand, 480, 1320)


def test_operating_hours_past_close_rejected():
    cand = build_occupancies(1, 9, 1290, RecipeDurations(20, 30))  # [1290,1340)
    assert not fits_operating_hours(cand, 480, 1320)


def test_operating_hours_ferment_in_bake_out_rejected():
    # 发酵段在营业时段内、烘烤段探出打烊，也算超出
    cand = build_occupancies(1, 9, 1300, RecipeDurations(15, 30))  # bake [1315,1345)
    assert not fits_operating_hours(cand, 480, 1320)


def test_next_free_window_within_custom_hours():
    w = next_free_window([], 1, duration=60, search_from=600, search_to=700)
    assert w == Interval(600, 660)
    assert next_free_window([], 1, duration=120, search_from=600, search_to=700) is None
    # 窗口可恰好收于打烊点
    assert next_free_window([], 1, duration=100, search_from=600, search_to=700) == Interval(600, 700)
