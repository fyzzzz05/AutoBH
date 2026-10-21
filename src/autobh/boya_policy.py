"""Per-person Boya stopping rules, separate from school statistics and credentials."""
from __future__ import annotations

from .storage import atomic_json, read_json

DEFAULT = {"mode": "categories"}


def validate_policy(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("请选择有效的个人定制条件")
    if value.get("mode") == "categories":
        return DEFAULT.copy()
    if value.get("mode") == "total":
        target = value.get("target")
        if type(target) is not int or not 1 <= target <= 10000:
            raise ValueError("净有效次数目标须为 1–10000 的整数")
        return {"mode": "total", "target": target}
    raise ValueError("停止条件仅支持默认分类指标或净有效次数")


def path(store):
    return store.path("autobh/stop-policies.json")


def load_policy(store, username: str) -> dict:
    try:
        policies = read_json(path(store), {})
        return validate_policy(policies.get(username, DEFAULT))
    except (ValueError, TypeError, AttributeError):
        # Corrupt settings must not silently reopen automatic course selection.
        return {"mode": "invalid"}


def save_policy(store, username: str, value: dict) -> dict:
    from .boya_operations import operation_lock
    policy = validate_policy(value)
    with operation_lock(store):
        if store.get_user(username) is None:
            raise ValueError("请先绑定博雅账号")
        policies = read_json(path(store), {})
        if policy["mode"] == "categories":
            policies.pop(username, None)
        else:
            policies[username] = policy
        atomic_json(path(store), policies)
    return policy


def condition(progress: dict, policy: dict) -> dict:
    mode = policy["mode"]
    if mode == "total":
        total, target = progress["totalCount"], policy["target"]
        return {**policy, "label": f"个人定制 · 净有效次数达到 {target} 次",
                "known": total is not None, "met": total is not None and total >= target,
                "remaining": max(0, target - total) if total is not None else None}
    if mode == "categories":
        return {**policy, "label": "默认 · 各类达到学校考核指标",
                "known": not progress["unknown"], "met": progress["met"]}
    return {"mode": "invalid", "label": "个人定制配置异常，已暂停新选课", "known": False, "met": False}


def apply_policy(progress: dict, policy: dict) -> dict:
    progress["stopCondition"] = condition(progress, policy)
    return progress
