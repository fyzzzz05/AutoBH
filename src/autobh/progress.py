"""Read progress from the native tools' caches without making school requests."""
from __future__ import annotations


def td_progress(username: str, state: dict, users: dict, today: str) -> dict:
    count = state.get("counts", {}).get(username, {})
    daily = state.get("daily_runs", {}).get(today, {}).get("users", {}).get(username, {})
    total = count.get("count")
    return {"totalCount": int(total) if total is not None else None,
            "updatedAt": count.get("updated_at"),
            "completedToday": daily.get("completed_rounds", 0),
            "targetToday": users.get(username, {}).get("rounds", 3)}


def read_boya_cache(store):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from autoboya.cache import CourseCache
    from autoboya.config import SELECTED_CACHE_FILE, STATISTICS_CACHE_FILE
    cache = CourseCache(store)
    times = [store.path(name).stat().st_mtime for name in (SELECTED_CACHE_FILE, STATISTICS_CACHE_FILE)
             if store.path(name).exists()]
    observed_at = datetime.fromtimestamp(min(times), ZoneInfo("Asia/Shanghai")) if times else None
    return cache.load_statistics(), cache.load_selected(), observed_at


def boya_progress(statistics: dict, selected: list | None = None, *, now=None, observed_at=None) -> dict:
    from autoboya.cli import iter_stat_rows
    from .boya import TARGETS, category_name, course_view, parse_time

    categories = {name: {"name": name, "required": required, "completed": 0, "failed": 0,
                         "pending": 0, "unknown": 0} for name, required in TARGETS.items()}
    records = {}
    reported_counts = {}
    category_rows = list(iter_stat_rows(statistics))
    # Statistics contain complete per-category enrollment records. Selected
    # courses provide attendance updates and are merged by the native course ID.
    for category, item in category_rows:
        name = category_name(category)
        rows = item.get("courseUserList")
        if not isinstance(rows, list):
            if name in categories:
                reported = max(int(item.get("selectAssessmentCount") or 0),
                               int(item.get("completeAssessmentCount") or 0) + int(item.get("failAssessmentCount") or 0))
                reported_counts[name] = max(reported_counts.get(name, 0), reported)
            continue
        for raw in rows:
            view = course_view(raw, now, observed_at)
            if not view["category"]:
                view["category"] = name
            records[view["id"]] = view
    for raw in selected or []:
        view = course_view(raw, now, observed_at)
        previous = records.get(view["id"])
        if previous and not view["category"]:
            view["category"] = previous["category"]
        records[view["id"]] = view
    for view in records.values():
        category = categories.get(view["category"])
        if category is not None:
            category[view["settlement"]["state"]] += 1
    for name, reported in reported_counts.items():
        categories[name]["unknown"] += max(0, reported - sum(view["category"] == name for view in records.values()))
    for row in categories.values():
        row["net"] = row["completed"] - row["failed"]
        row["remaining"] = max(0, row["required"] - row["net"])
        row["met"] = row["net"] >= row["required"] and row["unknown"] == 0
    rows = list(categories.values())
    known = bool(category_rows) or selected is not None

    def course_order(course):
        start = parse_time(course["start"])
        return (start is None, -start.timestamp() if start is not None else 0)

    courses = sorted(records.values(), key=course_order)
    return {"totalCount": sum(row["net"] for row in rows) if known else None,
            "completed": sum(row["completed"] for row in rows),
            "failed": sum(row["failed"] for row in rows),
            "unknown": sum(row["unknown"] for row in rows),
            "pending": sum(row["pending"] for row in rows),
            "metCategories": sum(row["met"] for row in rows),
            "met": known and all(row["met"] for row in rows),
            "schoolValidCount": statistics.get("validCount"),
            "categories": rows, "courses": courses}


def progress_text(feature: str, progress: dict) -> str:
    total = progress["totalCount"]
    if feature == "boya":
        if total is None:
            return "暂无进度缓存"
        prefix = "已核实有效" if progress["unknown"] else "有效"
        text = f"{prefix} {total} 次 · 已达标 {progress['metCategories']} / 4 类"
        if progress["unknown"]:
            text += f" · {progress['unknown']} 门待核实"
        return text
    text = f"本学期已完成 {total} 次" if total is not None else "暂无次数缓存"
    if feature == "td":
        text += f" · 今日 {progress['completedToday']} / {progress['targetToday']} 次"
    return text
