"""Reuse native Boya automation with a per-user category completion guard."""
from __future__ import annotations

import logging

from autoboya.logging import log_event, mask_username
from autoboya.models import ActionResult, UserRecord
from autoboya.scheduler import AutomationRunner

from .boya import category_name
from .progress import boya_progress, read_boya_cache

logger = logging.getLogger(__name__)


class BoyaRunner(AutomationRunner):
    def refresh_once(self):
        from .boya_operations import operation_lock, refresh_with_client, semester, mark_refresh_error
        users = [user for user in self.store.user_records() if user.enabled]
        if not users:
            return
        with operation_lock(self.store):
            try:
                window, courses = self._with_reauth(users[0].username, lambda client: (semester(client), client.query_courses()))
            except Exception:
                for user in users:
                    mark_refresh_error(self.store, user.username)
                raise
            self.cache.save_courses(courses)
            for user in users:
                try:
                    self._with_reauth(user.username, lambda client: refresh_with_client(self.store, user.username, client, window))
                except Exception:
                    mark_refresh_error(self.store, user.username)
                    log_event(logger, logging.WARNING, "account refresh failed", user=mask_username(user.username))

    def _refresh_user_cache(self, username):
        from .boya_operations import refresh_with_client, mark_refresh_error
        try:
            return self._with_reauth(username, lambda client: refresh_with_client(self.store, username, client))
        except Exception:
            mark_refresh_error(self.store, username)
            raise

    def execute_decisions(self, decisions):
        from .boya_operations import operation_lock
        # Same lock as manual refresh/withdraw; stale cached decisions cannot
        # race withdrawal or overwrite its refreshed cache.
        with operation_lock(self.store):
            return super().execute_decisions(decisions)

    def selection_block_reason(self, username: str, course_id: int) -> str | None:
        from .boya_operations import exclusions, observation
        if str(course_id) in exclusions(self.store).get(username, {}):
            return "已手动退选，禁止自动选回"
        course = next((course for course in self.cache.parsed_courses() if course.id == course_id), None)
        if course is None:
            return "课程缓存缺失，暂不自动选课"
        name = category_name(course.category)
        statistics, selected, observed_at = read_boya_cache(self.store)
        from .boya import parse_time
        info = observation(self.store, username)
        if info.get('error'):
            return "最近刷新失败，暂不自动选课"
        observed_at = parse_time(info.get("updatedAt")) or observed_at
        progress = boya_progress(statistics.get(username, {}), selected.get(username), observed_at=observed_at)
        category = next((row for row in progress["categories"] if row["name"] == name), None)
        if category is None:
            return "课程类别未知，暂不自动选课"
        if category["net"] >= category["required"]:
            return f"{name}已达标（有效 {category['net']}/{category['required']}），跳过新选课"
        if progress["totalCount"] is None or category["unknown"]:
            return f"{name}进度待核实，暂不自动选课"
        return None

    def _select_for_user(self, user: UserRecord, course_id: int) -> ActionResult:
        # Recheck at the submission boundary, including cached decisions and
        # cache updates produced by earlier actions in the same native loop.
        reason = self.selection_block_reason(user.username, course_id)
        if reason:
            log_event(logger, logging.INFO, "auto select skipped", user=mask_username(user.username),
                      course_id=course_id, reason=reason)
            # This is not a completed selection or a terminal school failure.
            # Do not journal it as success or exhaust the native retry counter.
            return ActionResult(user.username, "select", course_id, False, reason)
        return super()._select_for_user(user, course_id)
