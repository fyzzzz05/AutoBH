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


def official_count(value, *, signed=False) -> int | None:
    """Accept school integer counts without turning missing/malformed data into zero."""
    import re
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        number = int(value)
    else:
        return None
    return number if signed or number >= 0 else None


def boya_progress(statistics: dict, selected: list | None = None, *, now=None, observed_at=None) -> dict:
    from autoboya.cli import iter_stat_rows
    from .boya import TARGETS, category_name, course_view, parse_time

    categories = {name: {"name": name, "required": None, "completed": None,
                         "failed": None, "pending": None, "known": False}
                  for name in TARGETS}
    records = {}
    seen = set()
    groups = statistics.get("statistical")
    boya_stats = {"statistical": {key: value for key, value in groups.items()
                                  if str(key).split("|", 1)[-1] == "博雅课程"}} if isinstance(groups, dict) else {}
    for category, item in iter_stat_rows(boya_stats):
        name = category_name(category)
        if name in categories:
            row = categories[name]
            row.update(required=official_count(item.get("assessmentCount")),
                       completed=official_count(item.get("completeAssessmentCount")),
                       failed=official_count(item.get("failAssessmentCount")),
                       pending=official_count(item.get("undoneAssessmentCount")))
            row["known"] = name not in seen and row["required"] is not None and row["completed"] is not None
            seen.add(name)
        courses = item.get("courseUserList")
        for raw in courses if isinstance(courses, list) else []:
            if not isinstance(raw, dict):
                continue
            view = course_view(raw, now, observed_at)
            if not view["category"]:
                view["category"] = name
            records[view["id"]] = view
    # Chosen courses update attendance independently of the school's assessment.
    for raw in selected or []:
        view = course_view(raw, now, observed_at)
        previous = records.get(view["id"])
        if previous:
            if not view["category"]:
                view["category"] = previous["category"]
            if previous["settlement"]["state"] in {"completed", "failed"}:
                view["settlement"] = previous["settlement"]
        records[view["id"]] = view
    for row in categories.values():
        row["remaining"] = max(0, row["required"] - row["completed"]) if row["known"] else None
        row["met"] = row["known"] and row["completed"] >= row["required"]
    rows = list(categories.values())

    def course_order(course):
        start = parse_time(course["start"])
        return (start is None, -start.timestamp() if start is not None else 0)

    total = official_count(statistics.get("validCount"), signed=True)
    return {"source": "official", "totalCount": total,
            "completed": sum(row["completed"] or 0 for row in rows),
            "failed": sum(row["failed"] or 0 for row in rows),
            "pending": sum(row["pending"] or 0 for row in rows),
            "unknown": sum(not row["known"] for row in rows),
            "metCategories": sum(row["met"] for row in rows),
            "met": all(row["met"] for row in rows),
            "schoolValidCount": total, "categories": rows,
            "courses": sorted(records.values(), key=course_order)}


def progress_text(feature: str, progress: dict) -> str:
    total = progress["totalCount"]
    if feature == "boya":
        if total is None:
            return "暂无官方统计缓存"
        stop = progress.get("stopCondition", {})
        if stop.get("mode") == "invalid":
            return f"净有效 {total} 次 · 个人定制配置异常"
        if stop.get("mode") == "total":
            state = "个人目标已达标" if stop["met"] else f"还需 {stop['remaining']} 次"
            return f"净有效 {total} / {stop['target']} 次 · {state}"
        text = f"净有效 {total} 次 · 已达标 {progress['metCategories']} / 4 类"
        if progress["unknown"]:
            text += f" · {progress['unknown']} 类待同步"
        return text
    text = f"本学期已完成 {total} 次" if total is not None else "暂无次数缓存"
    if feature == "td":
        text += f" · 今日 {progress['completedToday']} / {progress['targetToday']} 次"
    return text
