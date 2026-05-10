from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional


AUTHOR_COLLABORATION_ROLES = frozenset({"author", "reviewer", "ops", "admin", "editor"})
AUTHOR_REVIEW_ROLES = frozenset({"reviewer", "ops", "admin", "editor"})


@dataclass(frozen=True)
class AuthorPermissionRule:
    methods: frozenset[str]
    pattern: re.Pattern[str]
    allowed_roles: frozenset[str]
    require_bearer: bool
    missing_reason: str
    forbidden_reason: str

    def matches(self, *, method: str, path: str) -> bool:
        return method.upper() in self.methods and bool(self.pattern.match(path))


class AuthorPermissionPolicyService:
    def __init__(self) -> None:
        self._rules: tuple[AuthorPermissionRule, ...] = (
            AuthorPermissionRule(
                methods=frozenset({"GET"}),
                pattern=re.compile(r"^/v1/author/reviewer-inbox$"),
                allowed_roles=AUTHOR_REVIEW_ROLES,
                require_bearer=True,
                missing_reason="author_review_session_required",
                forbidden_reason="author_review_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/drafts/[^/]+/approval/decision$"),
                allowed_roles=AUTHOR_REVIEW_ROLES,
                require_bearer=True,
                missing_reason="author_review_session_required",
                forbidden_reason="author_review_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"GET"}),
                pattern=re.compile(r"^/v1/author/drafts/[^/]+/collaboration$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/drafts/[^/]+/comments$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/comments/[^/]+/reply$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/comments/[^/]+/status$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/drafts/[^/]+/approval/request$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/notifications/[^/]+/status$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/notifications/bulk-status$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/comments/[^/]+/watchers$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/comments/[^/]+/watchers/[^/]+/remove$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/drafts/[^/]+/watchers$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/author/drafts/[^/]+/watchers/[^/]+/remove$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
            AuthorPermissionRule(
                methods=frozenset({"GET", "POST"}),
                pattern=re.compile(r"^/v1/author/notification-preferences$"),
                allowed_roles=AUTHOR_COLLABORATION_ROLES,
                require_bearer=True,
                missing_reason="author_collaboration_session_required",
                forbidden_reason="author_collaboration_role_forbidden",
            ),
        )

    def _normalize_role(self, actor_role: Optional[str]) -> str:
        return str(actor_role or "").strip()

    def resolve_rule(self, *, method: str, path: str) -> Optional[AuthorPermissionRule]:
        normalized_method = method.upper()
        normalized_path = path.rstrip("/") or path
        for rule in self._rules:
            if rule.matches(method=normalized_method, path=normalized_path):
                return rule
        return None

    def authorize(
        self,
        *,
        actor_id: Optional[str],
        actor_role: Optional[str],
        identity_source: Optional[str],
        method: str,
        path: str,
    ) -> Optional[dict[str, Optional[str]]]:
        rule = self.resolve_rule(method=method, path=path)
        if rule is None:
            return None
        resolved_actor_id = str(actor_id or "").strip()
        resolved_actor_role = self._normalize_role(actor_role)
        if rule.require_bearer and identity_source not in {"bearer", "cookie"}:
            raise PermissionError(rule.missing_reason)
        if not resolved_actor_id:
            raise PermissionError(rule.missing_reason)
        if resolved_actor_role not in set(rule.allowed_roles):
            raise PermissionError(rule.forbidden_reason)
        return {
            "actor_id": resolved_actor_id,
            "actor_role": resolved_actor_role,
            "identity_source": identity_source,
        }
