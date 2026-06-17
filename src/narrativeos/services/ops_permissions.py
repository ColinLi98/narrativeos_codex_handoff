from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional


PRIVILEGED_OPS_ROLES = frozenset({"reviewer", "ops", "admin"})
ADMIN_ONLY_OPS_ROLES = frozenset({"admin"})


@dataclass(frozen=True)
class OpsPermissionRule:
    methods: frozenset[str]
    pattern: re.Pattern[str]
    allowed_roles: frozenset[str]
    missing_reason: str
    forbidden_reason: str

    def matches(self, *, method: str, path: str) -> bool:
        return method.upper() in self.methods and bool(self.pattern.match(path))


class OpsPermissionPolicyService:
    def __init__(self) -> None:
        self.read_roles = PRIVILEGED_OPS_ROLES
        self.write_roles = PRIVILEGED_OPS_ROLES
        self._write_rules: tuple[OpsPermissionRule, ...] = (
            OpsPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/ops/runtime-restore/[^/]+/(approve|revoke)$"),
                allowed_roles=ADMIN_ONLY_OPS_ROLES,
                missing_reason="restore_admin_identity_required",
                forbidden_reason="restore_admin_required",
            ),
            OpsPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/ops/jobs/runtime-restores$"),
                allowed_roles=ADMIN_ONLY_OPS_ROLES,
                missing_reason="restore_admin_identity_required",
                forbidden_reason="restore_admin_required",
            ),
            OpsPermissionRule(
                methods=frozenset({"POST"}),
                pattern=re.compile(r"^/v1/ops/runtime-restore$"),
                allowed_roles=ADMIN_ONLY_OPS_ROLES,
                missing_reason="restore_admin_identity_required",
                forbidden_reason="restore_admin_required",
            ),
        )

    def _normalize_role(self, actor_role: Optional[str]) -> str:
        return str(actor_role or "").strip()

    def _authorize_roles(
        self,
        *,
        actor_id: Optional[str],
        actor_role: Optional[str],
        allowed_roles: Iterable[str],
        missing_reason: str,
        forbidden_reason: str,
    ) -> dict[str, Optional[str]]:
        resolved_actor_id = str(actor_id or "").strip()
        resolved_actor_role = self._normalize_role(actor_role)
        if not resolved_actor_id:
            raise PermissionError(missing_reason)
        if resolved_actor_role not in set(allowed_roles):
            raise PermissionError(forbidden_reason)
        return {
            "actor_id": resolved_actor_id,
            "actor_role": resolved_actor_role,
        }

    def authorize_roles(
        self,
        *,
        actor_id: Optional[str],
        actor_role: Optional[str],
        allowed_roles: Iterable[str],
        missing_reason: str,
        forbidden_reason: str,
    ) -> dict[str, Optional[str]]:
        return self._authorize_roles(
            actor_id=actor_id,
            actor_role=actor_role,
            allowed_roles=allowed_roles,
            missing_reason=missing_reason,
            forbidden_reason=forbidden_reason,
        )

    def authorize_read(
        self,
        *,
        actor_id: Optional[str],
        actor_role: Optional[str],
    ) -> dict[str, Optional[str]]:
        return self._authorize_roles(
            actor_id=actor_id,
            actor_role=actor_role,
            allowed_roles=self.read_roles,
            missing_reason="ops_view_identity_required",
            forbidden_reason="ops_view_role_forbidden",
        )

    def resolve_write_rule(self, *, method: str, path: str) -> OpsPermissionRule:
        normalized_method = method.upper()
        normalized_path = path.rstrip("/") or path
        for rule in self._write_rules:
            if rule.matches(method=normalized_method, path=normalized_path):
                return rule
        return OpsPermissionRule(
            methods=frozenset({normalized_method}),
            pattern=re.compile(r".*"),
            allowed_roles=self.write_roles,
            missing_reason="ops_mutation_identity_required",
            forbidden_reason="ops_mutation_role_forbidden",
        )

    def authorize_write(
        self,
        *,
        actor_id: Optional[str],
        actor_role: Optional[str],
        method: str,
        path: str,
    ) -> dict[str, Optional[str]]:
        rule = self.resolve_write_rule(method=method, path=path)
        return self._authorize_roles(
            actor_id=actor_id,
            actor_role=actor_role,
            allowed_roles=rule.allowed_roles,
            missing_reason=rule.missing_reason,
            forbidden_reason=rule.forbidden_reason,
        )
