"""Read native Boya attendance and apply the user's completion rules."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

TARGETS = {"德育": 2, "美育": 1, "劳育": 2, "安全健康": 1}


def category_name(name: str) -> str:
    return "劳育" if name in {"劳动教育", "劳育"} else name


def parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        value = datetime.fromisoformat(value)
        return value.replace(tzinfo=ZoneInfo("Asia/Shanghai")) if value.tzinfo is None else value
    except ValueError:
        return None


def course_view(raw: dict, now: datetime | None = None, observed_at: datetime | None = None) -> dict:
    from autoboya.bykc import parse_chosen_course
    course = parse_chosen_course(raw)
    record = course.raw
    known = "signInfo" in record
    info = record.get("signInfo")
    if isinstance(info, str):
        try:
            info = json.loads(info) if info.strip() else None
        except (ValueError, TypeError):
            known = False
    if info is None:
        info = {}
    if not isinstance(info, dict):
        known = False
        info = {}

    def attendance(key: str, action: str) -> dict:
        entry = info.get(key)
        if isinstance(entry, dict) and entry:
            if entry.get("inSignArea") is False:
                return {"state": "warning", "label": f"{action}位置异常"}
            return {"state": "done", "label": f"已{action}"}
        if entry is not None and entry != {}:
            return {"state": "unknown", "label": f"{action}状态未知"}
        return {"state": "missing" if known else "unknown",
                "label": f"暂无{action}记录" if known else f"{action}状态未知"}

    sign_in, sign_out = attendance("signIn", "签到"), attendance("signOut", "签退")
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    # Do not settle a course before either its end or the sign-out window ends.
    deadlines = [parsed for value in (course.course_end, course.sign_config.get("signOutEndDate"))
                 if (parsed := parse_time(value)) is not None]
    deadline = max(deadlines) if deadlines else None
    states = {sign_in["state"], sign_out["state"]}
    if states == {"done"}:
        settlement = {"state": "completed", "label": "已完成 +1", "delta": 1}
    elif deadline is not None and now <= deadline:
        settlement = {"state": "pending", "label": "待完成 · 暂不计次", "delta": 0}
    elif deadline is not None and observed_at is not None and observed_at <= deadline:
        settlement = {"state": "unknown", "label": "待刷新核实", "delta": 0}
    elif deadline is not None and "unknown" not in states:
        settlement = {"state": "failed", "label": "未完成 −1", "delta": -1}
    else:
        settlement = {"state": "unknown", "label": "待核实 · 暂不计次", "delta": 0}

    cancel_end = parse_time(course.cancel_end)
    can_drop = cancel_end is not None and now < cancel_end and (parse_time(course.course_start) is not None and now < parse_time(course.course_start))
    drop_reason = "退选截止时间未知，请刷新" if cancel_end is None else "已过退选期限或课程已开始"
    return {"dropVisible": parse_time(course.course_start) is None or now < parse_time(course.course_start), "cancelEnd": course.cancel_end, "canDrop": can_drop, "dropReason": "" if can_drop else drop_reason,
            "id": course.id, "name": course.name, "category": category_name(course.category),
            "start": course.course_start, "end": course.course_end, "location": course.location,
            "signIn": sign_in, "signOut": sign_out, "settlement": settlement}
