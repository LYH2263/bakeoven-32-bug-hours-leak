from app.services.oven_engine import (
    Interval,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    find_conflicts,
    fits_operating_hours,
    hours_band_for_gantt,
    is_valid_door,
    next_free_window,
    resolve_oven_hours,
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


def test_resolve_hours_unconfigured_falls_back():
    assert resolve_oven_hours(None, None) == (480, 1320)
    assert resolve_oven_hours(600, None) == (480, 1320)
    assert resolve_oven_hours(None, 1200) == (480, 1320)


def test_resolve_hours_invalid_door_falls_back():
    assert resolve_oven_hours(1200, 1200) == (480, 1320)  # 开门即打烊
    assert resolve_oven_hours(1300, 600) == (480, 1320)   # 打烊更早


def test_resolve_hours_custom_door_kept():
    assert resolve_oven_hours(600, 1200) == (600, 1200)


def test_fits_unconfigured_uses_shop_band():
    recipe = RecipeDurations(20, 30)
    # 未配门：按 8–22 判断，8:00 整开工、22:00 整收工都允许
    assert fits_operating_hours(build_occupancies(1, 9, 480, recipe), None, None)
    assert fits_operating_hours(build_occupancies(1, 9, 1270, recipe), None, None)
    assert not fits_operating_hours(build_occupancies(1, 9, 470, recipe), None, None)
    assert not fits_operating_hours(build_occupancies(1, 9, 1290, recipe), None, None)


def test_fits_custom_door_whole_occupancy_inside():
    recipe = RecipeDurations(30, 30)
    # 炉门 10:00–11:00：[600,660) 整段在内
    assert fits_operating_hours(build_occupancies(1, 9, 600, recipe), 600, 660)
    # 发酵在内但烘烤探出打烊 → 拒绝
    assert not fits_operating_hours(build_occupancies(1, 9, 610, recipe), 600, 660)
    # 早于该炉开门 → 拒绝，即使还在全店 8–22 之内
    assert not fits_operating_hours(build_occupancies(1, 9, 580, recipe), 600, 660)


def test_fits_zero_length_segments_ignored():
    # 发酵时长为 0（布朗尼类配方）：只看烘烤段
    recipe = RecipeDurations(0, 30)
    assert fits_operating_hours(build_occupancies(1, 9, 630, recipe), 600, 660)
    assert not fits_operating_hours(build_occupancies(1, 9, 640, recipe), 600, 660)


def test_gantt_band_matches_oven_door():
    assert hours_band_for_gantt(600, 1200) == (600, 1200)
    assert hours_band_for_gantt(None, None) == (480, 1320)
    assert hours_band_for_gantt(1200, 600) == (480, 1320)


def test_is_valid_door_rules():
    assert is_valid_door(None, None)          # 未配门，合法
    assert is_valid_door(480, 1320)           # 正常门
    assert not is_valid_door(1200, 1200)      # 开门即打烊
    assert not is_valid_door(1300, 600)       # 打烊更早
    assert not is_valid_door(600, None)       # 只填一端
    assert not is_valid_door(None, 1200)
