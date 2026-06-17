from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import os
import secrets
from typing import Any, Dict, Mapping, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .emailing import EmailDeliveryError, EmailService


TOKEN_TTL_DAYS = 14
DEFAULT_REFRESH_TOKEN_TTL_DAYS = 30
DEFAULT_VERIFICATION_TOKEN_TTL_SECONDS = 48 * 60 * 60
DEFAULT_PASSWORD_RESET_TOKEN_TTL_SECONDS = 2 * 60 * 60
DEFAULT_VERIFICATION_RESEND_COOLDOWN_SECONDS = 60
ADMIN_VIEW_BRIDGE_TTL_HOURS = 1
ADMIN_VIEW_ALLOWED_ROLES = {"reviewer", "ops", "admin"}
AUTH_COOKIE_NAME = "narrativeos_auth"
AUTH_COOKIE_SAMESITE = "lax"

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class AuthServiceError(RuntimeError):
    def __init__(
        self,
        *,
        http_status: int,
        code: str,
        reason: str,
        stage: str,
        retryable: bool = False,
        action_hint: Optional[str] = None,
        account_created: bool = False,
        can_retry_send: bool = False,
        can_resend_verification: bool = False,
        next_allowed_at: Optional[str] = None,
        identity: Optional[Dict[str, Any]] = None,
        email_provider_status: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(reason)
        self.http_status = http_status
        self.code = code
        self.reason = reason
        self.stage = stage
        self.retryable = retryable
        self.action_hint = action_hint
        self.account_created = account_created
        self.can_retry_send = can_retry_send
        self.can_resend_verification = can_resend_verification
        self.next_allowed_at = next_allowed_at
        self.identity = dict(identity or {})
        self.email_provider_status = dict(email_provider_status or {})
        self.extra = dict(extra or {})

    def detail(self) -> Dict[str, Any]:
        payload = {
            "code": self.code,
            "reason": self.reason,
            "stage": self.stage,
            "retryable": self.retryable,
            "action_hint": self.action_hint,
            "account_created": self.account_created,
            "can_retry_send": self.can_retry_send,
            "can_resend_verification": self.can_resend_verification,
            "next_allowed_at": self.next_allowed_at,
            "identity": self.identity or None,
            "email_provider_status": self.email_provider_status or None,
        }
        payload.update(self.extra)
        return {key: value for key, value in payload.items() if value is not None}


class AuthService:
    def __init__(self, repository: SQLAlchemyPlatformRepository, *, email_service: Optional[EmailService] = None) -> None:
        self.repository = repository
        self.email_service = email_service or EmailService()

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Optional[str]) -> Optional[datetime]:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _token_hash(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def _app_base_url(self) -> str:
        return str(
            os.getenv("APP_BASE_URL")
            or os.getenv("NARRATIVEOS_APP_BASE_URL")
            or "http://127.0.0.1:8000/app"
        )

    def _reviewer_app_base_url(self) -> str:
        configured = str(os.getenv("NARRATIVEOS_REVIEWER_APP_BASE_URL", "")).strip()
        if configured:
            return configured
        return self._app_base_url().rstrip("/") + "/reviewer"

    def _password_salt(self) -> str:
        return secrets.token_hex(16)

    def _default_ui_preferences(self) -> Dict[str, Any]:
        return {
            "immersiveEffects": False,
            "autoRenderArt": False,
            "privacyMode": True,
            "streamSpeed": 3,
            "particleDensity": 50,
            "fontSize": "medium",
            "theme": "quantum",
        }

    def _password_hash(self, password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            200_000,
        )
        return digest.hex()

    def _verify_password(self, password: str, *, password_hash: str, salt: str) -> bool:
        candidate = self._password_hash(password, salt)
        return hmac.compare_digest(candidate, password_hash)

    def _looks_like_email(self, value: Optional[str]) -> bool:
        return bool(str(value or "").strip() and "@" in str(value or ""))

    def _is_admin_view_role(self, actor_role: Optional[str]) -> bool:
        return str(actor_role or "").strip() in ADMIN_VIEW_ALLOWED_ROLES

    def _verification_token_ttl_seconds(self) -> int:
        return _env_int("EMAIL_VERIFICATION_TOKEN_TTL", DEFAULT_VERIFICATION_TOKEN_TTL_SECONDS)

    def _password_reset_token_ttl_seconds(self) -> int:
        return _env_int("PASSWORD_RESET_TOKEN_TTL", DEFAULT_PASSWORD_RESET_TOKEN_TTL_SECONDS)

    def _verification_resend_cooldown_seconds(self) -> int:
        return _env_int("EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", DEFAULT_VERIFICATION_RESEND_COOLDOWN_SECONDS)

    def _refresh_token_ttl_days(self) -> int:
        return _env_int("AUTH_REFRESH_TOKEN_TTL_DAYS", DEFAULT_REFRESH_TOKEN_TTL_DAYS)

    def _auth_cookie_name(self) -> str:
        return str(os.getenv("AUTH_COOKIE_NAME", AUTH_COOKIE_NAME) or AUTH_COOKIE_NAME).strip() or AUTH_COOKIE_NAME

    def _auth_cookie_secure(self) -> bool:
        if os.getenv("AUTH_COOKIE_SECURE") is not None:
            return _bool_env("AUTH_COOKIE_SECURE", False)
        return self._app_base_url().startswith("https://")

    def _auth_cookie_domain(self) -> Optional[str]:
        value = str(os.getenv("AUTH_COOKIE_DOMAIN", "") or "").strip()
        return value or None

    def _auth_cookie_samesite(self) -> str:
        value = str(os.getenv("AUTH_COOKIE_SAMESITE", AUTH_COOKIE_SAMESITE) or AUTH_COOKIE_SAMESITE).strip().lower()
        return value if value in {"lax", "strict", "none"} else AUTH_COOKIE_SAMESITE

    def auth_cookie_settings(self) -> Dict[str, Any]:
        return {
            "key": self._auth_cookie_name(),
            "max_age": TOKEN_TTL_DAYS * 24 * 60 * 60,
            "secure": self._auth_cookie_secure(),
            "httponly": True,
            "samesite": self._auth_cookie_samesite(),
            "path": "/",
            "domain": self._auth_cookie_domain(),
        }

    def extract_request_token(
        self,
        *,
        authorization: Optional[str] = None,
        cookies: Optional[Mapping[str, Any]] = None,
    ) -> Optional[str]:
        bearer = str(authorization or "").strip()
        if bearer.lower().startswith("bearer "):
            raw_token = bearer.split(" ", 1)[1].strip()
            if raw_token:
                return raw_token
        cookie_name = self._auth_cookie_name()
        if cookies and cookies.get(cookie_name):
            raw_token = str(cookies.get(cookie_name) or "").strip()
            if raw_token:
                return raw_token
        return None

    def _security_profile(self, *, actor_id: str, account_id: Optional[str]) -> Dict[str, Any]:
        existing = self.repository.get_auth_identity_profile(actor_id, default=None)
        if existing:
            existing.setdefault("ui_preferences_json", dict(self._default_ui_preferences()))
            return existing
        email_address = actor_id if self._looks_like_email(actor_id) else (account_id if self._looks_like_email(account_id) else None)
        return self.repository.save_auth_identity_profile(
            {
                "actor_id": actor_id,
                "account_id": account_id,
                "email_address": email_address,
                "avatar_url": None,
                "pending_email_address": None,
                "email_verified": False if self._looks_like_email(actor_id) else True,
                "verification_required": bool(self._looks_like_email(actor_id)),
                "ui_preferences_json": self._default_ui_preferences(),
                "pending_email_change_requested_at": None,
                "email_change_last_sent_at": None,
            }
        )

    def _verification_send_state(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        sent_at = self._parse_timestamp(profile.get("verification_sent_at"))
        cooldown_seconds = self._verification_resend_cooldown_seconds()
        next_allowed_at = sent_at + timedelta(seconds=cooldown_seconds) if sent_at else None
        can_resend = next_allowed_at is None or next_allowed_at <= datetime.now(timezone.utc)
        return {
            "verification_resend_cooldown_seconds": cooldown_seconds,
            "verification_next_allowed_at": next_allowed_at.isoformat() if next_allowed_at else None,
            "verification_can_resend": can_resend,
        }

    def _serialize_security(self, *, actor_id: str, account_id: Optional[str]) -> Dict[str, Any]:
        profile = self._security_profile(actor_id=actor_id, account_id=account_id)
        ui_preferences = dict(self._default_ui_preferences())
        ui_preferences.update(dict(profile.get("ui_preferences_json") or {}))
        return {
            "email_address": profile.get("email_address"),
            "pending_email_address": profile.get("pending_email_address"),
            "avatar_url": profile.get("avatar_url"),
            "email_verified": bool(profile.get("email_verified")),
            "verification_required": bool(profile.get("verification_required")),
            "verification_sent_at": profile.get("verification_sent_at"),
            "verified_at": profile.get("verified_at"),
            "password_reset_sent_at": profile.get("password_reset_sent_at"),
            "pending_email_change_requested_at": profile.get("pending_email_change_requested_at"),
            "email_change_last_sent_at": profile.get("email_change_last_sent_at"),
            "ui_preferences": ui_preferences,
            "deactivated_at": profile.get("deactivated_at"),
            "deactivated_by": profile.get("deactivated_by"),
            "deactivation_reason": profile.get("deactivation_reason"),
            "email_provider_status": self.email_service.provider_status(),
            **self._verification_send_state(profile),
        }

    def _current_email_address(self, *, identity: Dict[str, Any], security: Optional[Dict[str, Any]] = None) -> Optional[str]:
        resolved_security = security or self._serialize_security(
            actor_id=str(identity.get("actor_id") or ""),
            account_id=identity.get("account_id"),
        )
        candidates = [
            resolved_security.get("email_address"),
            identity.get("account_id"),
            identity.get("actor_id"),
        ]
        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if self._looks_like_email(normalized):
                return normalized
        return None

    def resolve_actor_id_from_identifier(self, identifier: str) -> str:
        normalized = str(identifier or "").strip()
        if not normalized:
            raise ValueError("identifier_required")
        if self._looks_like_email(normalized):
            profile = self.repository.get_auth_identity_profile_by_email_address(normalized, default=None)
            if profile is not None:
                return str(profile.get("actor_id") or normalized)
            identity = self.repository.get_auth_identity_by_account_id(normalized, default=None)
            if identity is not None:
                return str(identity.get("actor_id") or normalized)
            raise KeyError("unknown_auth_identity_for_identifier:%s" % normalized)
        try:
            self.repository.get_auth_identity(normalized)
            return normalized
        except KeyError:
            identity = self.repository.get_auth_identity_by_account_id(normalized, default=None)
            if identity is not None:
                return str(identity.get("actor_id") or normalized)
            raise

    def _revoke_refresh_tokens_for_actor(self, actor_id: str, *, status: str = "revoked") -> None:
        self.repository.update_auth_flow_tokens_for_actor(
            actor_id=actor_id,
            flow_type="auth_refresh",
            statuses=["active"],
            updates={"status": status, "consumed_at": self._utcnow()},
        )

    def _issue_session_tokens(self, *, identity: Dict[str, Any], security: Dict[str, Any]) -> Dict[str, Any]:
        raw_token = f"ntos_{secrets.token_urlsafe(32)}"
        expires_at = (datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)).isoformat()
        token = self.repository.save_auth_token(
            {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                "actor_role": identity["actor_role"],
                "token_hash": self._token_hash(raw_token),
                "status": "active",
                "expires_at": expires_at,
                "last_used_at": self._utcnow(),
            }
        )
        self._supersede_flow_tokens(actor_id=identity["actor_id"], flow_type="auth_refresh")
        refresh = self._issue_flow_token(
            actor_id=identity["actor_id"],
            account_id=identity.get("account_id"),
            flow_type="auth_refresh",
            ttl_seconds=self._refresh_token_ttl_days() * 24 * 60 * 60,
            payload_json={
                "actor_role": identity["actor_role"],
                "issued_from_token_id": token["token_id"],
            },
        )
        return {
            "token": {
                "access_token": raw_token,
                "token_type": "bearer",
                "expires_at": expires_at,
            },
            "refresh": {
                "refresh_token": refresh["token"],
                "expires_at": refresh["expires_at"],
            },
            "identity": {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                "actor_role": identity["actor_role"],
                "display_name": identity.get("display_name"),
                **security,
            },
            "session": {
                "token_id": token["token_id"],
                "last_used_at": token["last_used_at"],
            },
        }

    def _public_flow_token(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "flow_token_id": flow.get("flow_token_id"),
            "flow_type": flow.get("flow_type"),
            "expires_at": flow.get("expires_at"),
        }
        if self.email_service.expose_debug_tokens() and flow.get("token"):
            payload["token"] = flow.get("token")
        return payload

    def _record_delivery_attempt(
        self,
        *,
        identity: Dict[str, Any],
        flow_type: str,
        recipient_email: str,
        status: str,
        delivery: Optional[Dict[str, Any]] = None,
        error: Optional[EmailDeliveryError] = None,
    ) -> Dict[str, Any]:
        provider_status = self.email_service.provider_status()
        payload = {
            "actor_id": identity.get("actor_id"),
            "account_id": identity.get("account_id"),
            "flow_type": flow_type,
            "provider": str((delivery or {}).get("provider") or provider_status.get("provider") or ""),
            "email_mode": str(provider_status.get("mode") or ""),
            "sender_email": provider_status.get("from_email"),
            "recipient_email": recipient_email,
            "status": status,
            "provider_message_id": (delivery or {}).get("message_id"),
            "error_code": error.reason if error else None,
            "error_reason": error.metadata.get("response_message") if error else None,
            "retryable": bool(error.retryable) if error else False,
            "metadata_json": {
                "provider_status": provider_status,
                "delivery": dict(delivery or {}),
                "error": error.detail() if error else None,
            },
        }
        return self.repository.save_auth_delivery_attempt(payload)

    def _issue_flow_token(
        self,
        *,
        actor_id: str,
        account_id: Optional[str],
        flow_type: str,
        ttl_seconds: int,
        payload_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_token = f"nflow_{secrets.token_urlsafe(24)}"
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        try:
            record = self.repository.save_auth_flow_token(
                {
                    "actor_id": actor_id,
                    "account_id": account_id,
                    "flow_type": flow_type,
                    "token_hash": self._token_hash(raw_token),
                    "status": "active",
                    "payload_json": dict(payload_json or {}),
                    "expires_at": expires_at,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive classification
            logger.exception("auth flow token issue failed", extra={"actor_id": actor_id, "flow_type": flow_type, "stage": "token_issue"})
            raise AuthServiceError(
                http_status=503,
                code="auth_token_issue_failed",
                reason="token_issue_failed",
                stage="token_issue",
                retryable=True,
                action_hint="retry_request",
                email_provider_status=self.email_service.provider_status(),
                extra={"flow_type": flow_type},
            ) from exc
        return {
            "token": raw_token,
            "flow_token_id": record["flow_token_id"],
            "flow_type": flow_type,
            "expires_at": expires_at,
        }

    def _resolve_active_flow_token(self, *, raw_token: str, flow_type: str) -> Dict[str, Any]:
        token = self.repository.get_auth_flow_token_by_hash(self._token_hash(raw_token), flow_type=flow_type)
        token_status = str(token.get("status") or "active")
        if token_status != "active":
            if token_status == "consumed":
                raise PermissionError("auth_flow_token_consumed")
            if token_status == "expired":
                raise PermissionError("auth_flow_token_expired")
            if token_status == "superseded":
                raise PermissionError("auth_flow_token_superseded")
            raise PermissionError("auth_flow_token_inactive")
        expires_at = self._parse_timestamp(token.get("expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            self.repository.update_auth_flow_token(token["flow_token_id"], {"status": "expired"})
            raise PermissionError("auth_flow_token_expired")
        return token

    def _supersede_flow_tokens(self, *, actor_id: str, flow_type: str, exclude_flow_token_id: Optional[str] = None) -> None:
        self.repository.update_auth_flow_tokens_for_actor(
            actor_id=actor_id,
            flow_type=flow_type,
            statuses=["active"],
            exclude_flow_token_id=exclude_flow_token_id,
            updates={"status": "superseded"},
        )

    def _send_verification_email(self, *, identity: Dict[str, Any], verification_token: str) -> Dict[str, Any]:
        security = self._serialize_security(actor_id=str(identity.get("actor_id") or ""), account_id=identity.get("account_id"))
        email_address = self._current_email_address(identity=identity, security=security)
        if not self._looks_like_email(email_address):
            raise ValueError("email_verification_not_applicable")
        try:
            delivery = self.email_service.send_verification_email(
                to_email=str(email_address),
                display_name=identity.get("display_name"),
                verify_token=verification_token,
                app_base_url=self._app_base_url(),
            )
        except EmailDeliveryError as exc:
            status = "blocked" if exc.reason in {"provider_not_configured", "test_mode_external_recipient_blocked", "domain_not_verified"} else "failed"
            self._record_delivery_attempt(
                identity=identity,
                flow_type="email_verification",
                recipient_email=str(email_address),
                status=status,
                error=exc,
            )
            logger.warning(
                "verification email send failed",
                extra={"actor_id": identity.get("actor_id"), "flow_type": "email_verification", "reason": exc.reason, "stage": "email_delivery"},
            )
            raise
        self._record_delivery_attempt(
            identity=identity,
            flow_type="email_verification",
            recipient_email=str(email_address),
            status="queued",
            delivery=delivery,
        )
        self.repository.save_auth_identity_profile(
            {
                **self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
                "verification_sent_at": self._utcnow(),
            }
        )
        return delivery

    def _send_password_reset_email(self, *, identity: Dict[str, Any], reset_token: str) -> Dict[str, Any]:
        security = self._serialize_security(actor_id=str(identity.get("actor_id") or ""), account_id=identity.get("account_id"))
        email_address = self._current_email_address(identity=identity, security=security)
        if not self._looks_like_email(email_address):
            raise ValueError("password_reset_not_applicable")
        try:
            delivery = self.email_service.send_password_reset_email(
                to_email=str(email_address),
                display_name=identity.get("display_name"),
                reset_token=reset_token,
                app_base_url=self._app_base_url(),
            )
        except EmailDeliveryError as exc:
            status = "blocked" if exc.reason in {"provider_not_configured", "test_mode_external_recipient_blocked", "domain_not_verified"} else "failed"
            self._record_delivery_attempt(
                identity=identity,
                flow_type="password_reset",
                recipient_email=str(email_address),
                status=status,
                error=exc,
            )
            logger.warning(
                "password reset email send failed",
                extra={"actor_id": identity.get("actor_id"), "flow_type": "password_reset", "reason": exc.reason, "stage": "email_delivery"},
            )
            raise
        self._record_delivery_attempt(
            identity=identity,
            flow_type="password_reset",
            recipient_email=str(email_address),
            status="queued",
            delivery=delivery,
        )
        self.repository.save_auth_identity_profile(
            {
                **self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
                "password_reset_sent_at": self._utcnow(),
            }
        )
        return delivery

    def _send_email_change_email(
        self,
        *,
        identity: Dict[str, Any],
        new_email: str,
        email_change_token: str,
    ) -> Dict[str, Any]:
        if not self._looks_like_email(new_email):
            raise ValueError("email_change_not_applicable")
        try:
            delivery = self.email_service.send_email_change_email(
                to_email=str(new_email),
                display_name=identity.get("display_name"),
                email_change_token=email_change_token,
                app_base_url=self._app_base_url(),
            )
        except EmailDeliveryError as exc:
            status = "blocked" if exc.reason in {"provider_not_configured", "test_mode_external_recipient_blocked", "domain_not_verified"} else "failed"
            self._record_delivery_attempt(
                identity=identity,
                flow_type="email_change",
                recipient_email=str(new_email),
                status=status,
                error=exc,
            )
            logger.warning(
                "email change email send failed",
                extra={"actor_id": identity.get("actor_id"), "flow_type": "email_change", "reason": exc.reason, "stage": "email_delivery"},
            )
            raise
        self._record_delivery_attempt(
            identity=identity,
            flow_type="email_change",
            recipient_email=str(new_email),
            status="queued",
            delivery=delivery,
        )
        self.repository.save_auth_identity_profile(
            {
                **self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
                "email_change_last_sent_at": self._utcnow(),
            }
        )
        return delivery

    def register_identity(
        self,
        *,
        actor_id: str,
        actor_role: str,
        password: str,
        account_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_actor_id = str(actor_id or "").strip()
        if not resolved_actor_id:
            raise ValueError("actor_id_required")
        if not str(password or "").strip():
            raise ValueError("password_required")
        resolved_actor_role = str(actor_role or "author").strip() or "author"
        resolved_account_id = str(account_id or "").strip() or None
        if resolved_actor_role in {"reader", "customer"}:
            if resolved_account_id and resolved_account_id != resolved_actor_id:
                raise ValueError("%s_account_id_must_match_actor_id" % resolved_actor_role)
            resolved_account_id = resolved_actor_id
        try:
            self.repository.get_auth_identity(resolved_actor_id)
        except KeyError:
            pass
        else:
            raise ValueError("actor_id_already_registered")
        if self._looks_like_email(resolved_actor_id):
            try:
                self.email_service.auth_preflight(to_email=resolved_actor_id, flow_type="email_verification")
            except EmailDeliveryError as exc:
                self._record_delivery_attempt(
                    identity={
                        "actor_id": resolved_actor_id,
                        "account_id": resolved_account_id,
                    },
                    flow_type="email_verification",
                    recipient_email=resolved_actor_id,
                    status="blocked",
                    error=exc,
                )
                logger.warning(
                    "auth register blocked before account creation",
                    extra={"actor_id": resolved_actor_id, "reason": exc.reason, "stage": "email_policy"},
                )
                raise AuthServiceError(
                    http_status=403 if exc.reason == "test_mode_external_recipient_blocked" else 503,
                    code="auth_register_delivery_failed",
                    reason=exc.reason,
                    stage="email_policy",
                    retryable=exc.retryable,
                    action_hint=exc.action_hint,
                    email_provider_status=exc.provider_status,
                ) from exc
        salt = self._password_salt()
        try:
            record = self.repository.save_auth_identity(
                {
                    "actor_id": resolved_actor_id,
                    "account_id": resolved_account_id,
                    "actor_role": resolved_actor_role,
                    "display_name": display_name,
                    "password_hash": self._password_hash(password, salt),
                    "password_salt": salt,
                    "status": "active",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive classification
            logger.exception("auth identity create failed", extra={"actor_id": resolved_actor_id, "stage": "db_write"})
            raise AuthServiceError(
                http_status=503,
                code="auth_register_delivery_failed",
                reason="db_write_failed",
                stage="db_write",
                retryable=True,
                action_hint="retry_request",
                email_provider_status=self.email_service.provider_status(),
            ) from exc
        verification = None
        delivery = None
        if self._looks_like_email(resolved_actor_id):
            verification = self._issue_flow_token(
                actor_id=record["actor_id"],
                account_id=record.get("account_id"),
                flow_type="email_verification",
                ttl_seconds=self._verification_token_ttl_seconds(),
            )
            try:
                delivery = self._send_verification_email(identity=record, verification_token=verification["token"])
            except EmailDeliveryError as exc:
                identity_payload = {
                    "actor_id": record["actor_id"],
                    "account_id": record.get("account_id"),
                    "actor_role": record["actor_role"],
                    "display_name": record.get("display_name"),
                    "status": record["status"],
                    "created_at": record["created_at"],
                    **self._serialize_security(actor_id=record["actor_id"], account_id=record.get("account_id")),
                }
                raise AuthServiceError(
                    http_status=503 if exc.reason != "test_mode_external_recipient_blocked" else 403,
                    code="auth_register_delivery_failed",
                    reason=exc.reason,
                    stage="email_delivery",
                    retryable=exc.retryable,
                    action_hint=exc.action_hint,
                    account_created=True,
                    can_retry_send=True,
                    identity=identity_payload,
                    email_provider_status=exc.provider_status,
                ) from exc
        return {
            "identity": {
                "actor_id": record["actor_id"],
                "account_id": record.get("account_id"),
                "actor_role": record["actor_role"],
                "display_name": record.get("display_name"),
                "status": record["status"],
                "created_at": record["created_at"],
                **self._serialize_security(actor_id=record["actor_id"], account_id=record.get("account_id")),
            },
            "verification": self._public_flow_token(verification) if verification else None,
            "delivery": delivery,
        }

    def issue_token(self, *, actor_id: str, password: str) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        if identity.get("status") != "active":
            raise PermissionError("auth_identity_inactive")
        if not self._verify_password(password, password_hash=identity["password_hash"], salt=identity["password_salt"]):
            raise PermissionError("invalid_credentials")
        security = self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        if security.get("verification_required") and not security.get("email_verified"):
            raise AuthServiceError(
                http_status=403,
                code="auth_email_unverified",
                reason="email_verification_required",
                stage="login_policy",
                action_hint="request_verification_email",
                can_resend_verification=bool(security.get("verification_can_resend", True)),
                next_allowed_at=security.get("verification_next_allowed_at"),
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    "actor_role": identity["actor_role"],
                    "display_name": identity.get("display_name"),
                    **security,
                },
                email_provider_status=security.get("email_provider_status"),
            )
        return self._issue_session_tokens(identity=identity, security=security)

    def refresh_access_token(self, *, raw_refresh_token: str) -> Dict[str, Any]:
        resolved = self._resolve_active_flow_token(raw_token=raw_refresh_token, flow_type="auth_refresh")
        identity = self.repository.get_auth_identity(resolved["actor_id"])
        if identity.get("status") != "active":
            self.repository.update_auth_flow_token(
                resolved["flow_token_id"],
                {"status": "revoked", "consumed_at": self._utcnow()},
            )
            raise PermissionError("auth_identity_inactive")
        security = self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        if security.get("verification_required") and not security.get("email_verified"):
            raise AuthServiceError(
                http_status=403,
                code="auth_email_unverified",
                reason="email_verification_required",
                stage="refresh_policy",
                action_hint="request_verification_email",
                can_resend_verification=bool(security.get("verification_can_resend", True)),
                next_allowed_at=security.get("verification_next_allowed_at"),
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    "actor_role": identity["actor_role"],
                    "display_name": identity.get("display_name"),
                    **security,
                },
                email_provider_status=security.get("email_provider_status"),
            )
        self.repository.update_auth_flow_token(
            resolved["flow_token_id"],
            {"status": "consumed", "consumed_at": self._utcnow()},
        )
        return self._issue_session_tokens(identity=identity, security=security)

    def authenticate_identity(self, *, actor_id: str, password: str) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        if identity.get("status") != "active":
            raise PermissionError("auth_identity_inactive")
        if not self._verify_password(password, password_hash=identity["password_hash"], salt=identity["password_salt"]):
            raise PermissionError("invalid_credentials")
        return identity

    def issue_admin_view_bridge(
        self,
        *,
        actor_id: str,
        actor_role: str,
        account_id: Optional[str] = None,
        workspace: str = "review",
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        case_id: Optional[str] = None,
        alert_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_actor_id = str(actor_id or "").strip()
        resolved_actor_role = str(actor_role or "").strip()
        if not resolved_actor_id:
            raise PermissionError("admin_view_identity_required")
        if not self._is_admin_view_role(resolved_actor_role):
            raise PermissionError("admin_view_role_forbidden")
        resolved_workspace = str(workspace or "review").strip() or "review"
        context = {
            "account_id": str(account_id or "").strip() or None,
            "world_id": str(world_id or "").strip() or None,
            "world_version_id": str(world_version_id or "").strip() or None,
            "case_id": str(case_id or "").strip() or None,
            "alert_id": str(alert_id or "").strip() or None,
            "workspace": resolved_workspace,
        }
        token = self._issue_flow_token(
            actor_id=resolved_actor_id,
            account_id=str(account_id or "").strip() or None,
            flow_type="admin_view_bridge",
            ttl_seconds=ADMIN_VIEW_BRIDGE_TTL_HOURS * 60 * 60,
            payload_json={
                **context,
                "actor_role": resolved_actor_role,
            },
        )
        query = [
            "product=ops",
            f"workspace={resolved_workspace}",
            "admin_view=1",
            f"admin_view_bridge={token['token']}",
        ]
        for key in ("account_id", "world_id", "world_version_id", "case_id", "alert_id"):
            value = context.get(key)
            if value:
                query.append(f"{key}={value}")
        return {
            "bridge": self._public_flow_token(token),
            "authorized": True,
            "actor_id": resolved_actor_id,
            "actor_role": resolved_actor_role,
            "context": context,
            "url": f"{self._reviewer_app_base_url()}?{'&'.join(query)}",
        }

    def issue_admin_view_session_bridge(
        self,
        *,
        actor_id: str,
        password: str,
        account_id: Optional[str] = None,
        workspace: str = "review",
        world_id: Optional[str] = None,
        world_version_id: Optional[str] = None,
        case_id: Optional[str] = None,
        alert_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        identity = self.authenticate_identity(actor_id=actor_id, password=password)
        return self.issue_admin_view_bridge(
            actor_id=str(identity.get("actor_id") or ""),
            actor_role=str(identity.get("actor_role") or ""),
            account_id=account_id or identity.get("account_id"),
            workspace=workspace,
            world_id=world_id,
            world_version_id=world_version_id,
            case_id=case_id,
            alert_id=alert_id,
        )

    def resolve_admin_view_bridge_token(self, *, raw_token: str) -> Dict[str, Any]:
        token = self._resolve_active_flow_token(raw_token=raw_token, flow_type="admin_view_bridge")
        payload = dict(token.get("payload_json") or {})
        actor_id = str(token.get("actor_id") or "").strip()
        actor_role = str(payload.get("actor_role") or "").strip()
        if not actor_id:
            raise PermissionError("admin_view_identity_required")
        if not self._is_admin_view_role(actor_role):
            raise PermissionError("admin_view_role_forbidden")
        return {
            "authorized": True,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "account_id": token.get("account_id"),
            "bridge_token_id": token.get("flow_token_id"),
            "expires_at": token.get("expires_at"),
            "context": {
                "account_id": payload.get("account_id"),
                "world_id": payload.get("world_id"),
                "world_version_id": payload.get("world_version_id"),
                "case_id": payload.get("case_id"),
                "alert_id": payload.get("alert_id"),
                "workspace": payload.get("workspace") or "review",
            },
        }

    def resolve_admin_view_bridge(
        self,
        *,
        raw_token: str,
        actor_id: str,
        actor_role: str,
    ) -> Dict[str, Any]:
        resolved_actor_id = str(actor_id or "").strip()
        resolved_actor_role = str(actor_role or "").strip()
        if not resolved_actor_id:
            raise PermissionError("admin_view_identity_required")
        if not self._is_admin_view_role(resolved_actor_role):
            raise PermissionError("admin_view_role_forbidden")
        resolved = self.resolve_admin_view_bridge_token(raw_token=raw_token)
        if str(resolved.get("actor_id") or "").strip() != resolved_actor_id:
            raise PermissionError("admin_view_bridge_actor_mismatch")
        if str(resolved.get("actor_role") or "").strip() != resolved_actor_role:
            raise PermissionError("admin_view_bridge_role_mismatch")
        return resolved

    def resolve_bearer_token(self, raw_token: str) -> Dict[str, Any]:
        if not str(raw_token or "").strip():
            raise PermissionError("missing_bearer_token")
        token = self.repository.get_auth_token_by_hash(self._token_hash(raw_token))
        if token.get("status") != "active":
            raise PermissionError("inactive_bearer_token")
        expires_at = self._parse_timestamp(token.get("expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            self.repository.update_auth_token(token["token_id"], {"status": "expired"})
            raise PermissionError("expired_bearer_token")
        updated = self.repository.update_auth_token(token["token_id"], {"last_used_at": self._utcnow()})
        identity = self.repository.get_auth_identity(updated["actor_id"])
        if identity.get("status") != "active":
            self.repository.update_auth_token(updated["token_id"], {"status": "revoked"})
            raise PermissionError("auth_identity_inactive")
        return {
            "actor_id": identity["actor_id"],
            "account_id": identity.get("account_id"),
            "actor_role": identity["actor_role"],
            "display_name": identity.get("display_name"),
            "token_id": updated["token_id"],
            "expires_at": updated.get("expires_at"),
            "last_used_at": updated.get("last_used_at"),
            **self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
        }

    def revoke_bearer_token(self, raw_token: str) -> Dict[str, Any]:
        token = self.repository.get_auth_token_by_hash(self._token_hash(raw_token))
        updated = self.repository.update_auth_token(token["token_id"], {"status": "revoked"})
        self._revoke_refresh_tokens_for_actor(updated["actor_id"], status="revoked")
        return {
            "token_id": updated["token_id"],
            "status": updated["status"],
        }

    def update_profile(
        self,
        *,
        actor_id: str,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        email_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        security = self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        normalized_display_name = identity.get("display_name")
        if display_name is not None:
            normalized_display_name = str(display_name or "").strip() or identity["actor_id"]
        updated_identity = self.repository.save_auth_identity(
            {
                **identity,
                "display_name": normalized_display_name,
                "status": identity.get("status", "active"),
            }
        )
        normalized_avatar_url = security.get("avatar_url")
        if avatar_url is not None:
            normalized_avatar_url = str(avatar_url or "").strip() or None
        if email_address is not None:
            normalized_email = str(email_address or "").strip()
            current_email = str(security.get("email_address") or "").strip()
            if normalized_email and normalized_email != current_email:
                raise ValueError("auth_profile_email_update_unsupported")
        updated_profile = self.repository.save_auth_identity_profile(
            {
                **security,
                "actor_id": updated_identity["actor_id"],
                "account_id": updated_identity.get("account_id"),
                "avatar_url": normalized_avatar_url,
            }
        )
        return {
            "identity": {
                "actor_id": updated_identity["actor_id"],
                "account_id": updated_identity.get("account_id"),
                "actor_role": updated_identity["actor_role"],
                "display_name": updated_identity.get("display_name"),
                **self._serialize_security(actor_id=updated_identity["actor_id"], account_id=updated_identity.get("account_id")),
            },
            "profile": updated_profile,
        }

    def change_password(
        self,
        *,
        actor_id: str,
        current_password: str,
        new_password: str,
    ) -> Dict[str, Any]:
        if not str(current_password or "").strip():
            raise ValueError("current_password_required")
        if not str(new_password or "").strip():
            raise ValueError("new_password_required")
        identity = self.authenticate_identity(actor_id=actor_id, password=current_password)
        salt = self._password_salt()
        updated_identity = self.repository.save_auth_identity(
            {
                **identity,
                "password_hash": self._password_hash(new_password, salt),
                "password_salt": salt,
                "status": identity.get("status", "active"),
            }
        )
        self.repository.revoke_auth_tokens_for_actor(updated_identity["actor_id"], reason="password_change")
        self._revoke_refresh_tokens_for_actor(updated_identity["actor_id"], status="revoked")
        security = self._serialize_security(actor_id=updated_identity["actor_id"], account_id=updated_identity.get("account_id"))
        return self._issue_session_tokens(identity=updated_identity, security=security)

    def get_user_settings(self, *, actor_id: str) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        security = self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        settings = dict(self._default_ui_preferences())
        settings.update(dict(security.get("ui_preferences_json") or {}))
        return settings

    def update_user_settings(self, *, actor_id: str, settings_updates: Dict[str, Any]) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        security = self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        next_settings = dict(self._default_ui_preferences())
        next_settings.update(dict(security.get("ui_preferences_json") or {}))
        next_settings.update({key: value for key, value in dict(settings_updates or {}).items() if value is not None})
        if next_settings.get("fontSize") not in {"small", "medium", "large"}:
            raise ValueError("auth_settings_font_size_invalid")
        if next_settings.get("theme") not in {"quantum", "neon", "void", "solar"}:
            raise ValueError("auth_settings_theme_invalid")
        try:
            next_settings["streamSpeed"] = int(next_settings.get("streamSpeed", 3))
            next_settings["particleDensity"] = int(next_settings.get("particleDensity", 50))
        except (TypeError, ValueError) as exc:
            raise ValueError("auth_settings_numeric_invalid") from exc
        next_settings["streamSpeed"] = max(1, min(5, next_settings["streamSpeed"]))
        next_settings["particleDensity"] = max(0, min(100, next_settings["particleDensity"]))
        next_settings["immersiveEffects"] = bool(next_settings.get("immersiveEffects"))
        next_settings["autoRenderArt"] = bool(next_settings.get("autoRenderArt"))
        next_settings["privacyMode"] = bool(next_settings.get("privacyMode"))
        self.repository.save_auth_identity_profile(
            {
                **security,
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                "ui_preferences_json": next_settings,
            }
        )
        return next_settings

    def deactivate_account(
        self,
        *,
        actor_id: str,
        requested_by: Optional[str] = None,
        reason: str = "self_service_account_deactivate",
    ) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        if identity.get("status") == "deactivated":
            security = self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
            return {
                "status": "deactivated",
                "identity": {
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    "actor_role": identity["actor_role"],
                    "display_name": identity.get("display_name"),
                    **security,
                },
                "revoked_sessions": [],
            }
        updated_identity = self.repository.save_auth_identity(
            {
                **identity,
                "status": "deactivated",
            }
        )
        security = self._security_profile(actor_id=updated_identity["actor_id"], account_id=updated_identity.get("account_id"))
        updated_profile = self.repository.save_auth_identity_profile(
            {
                **security,
                "actor_id": updated_identity["actor_id"],
                "account_id": updated_identity.get("account_id"),
                "deactivated_at": self._utcnow(),
                "deactivated_by": str(requested_by or updated_identity["actor_id"]).strip() or updated_identity["actor_id"],
                "deactivation_reason": reason,
            }
        )
        revoked_sessions = self.repository.revoke_auth_tokens_for_actor(updated_identity["actor_id"], reason="account_deactivated")
        for flow_type in ["auth_refresh", "email_verification", "password_reset", "admin_view_bridge"]:
            self.repository.update_auth_flow_tokens_for_actor(
                actor_id=updated_identity["actor_id"],
                flow_type=flow_type,
                statuses=["active"],
                updates={"status": "revoked", "consumed_at": self._utcnow()},
            )
        return {
            "status": "deactivated",
            "identity": {
                "actor_id": updated_identity["actor_id"],
                "account_id": updated_identity.get("account_id"),
                "actor_role": updated_identity["actor_role"],
                "display_name": updated_identity.get("display_name"),
                **self._serialize_security(actor_id=updated_identity["actor_id"], account_id=updated_identity.get("account_id")),
            },
            "profile": updated_profile,
            "revoked_sessions": revoked_sessions,
        }

    def request_email_change(
        self,
        *,
        actor_id: str,
        current_password: str,
        new_email: str,
    ) -> Dict[str, Any]:
        identity = self.authenticate_identity(actor_id=actor_id, password=current_password)
        normalized_new_email = str(new_email or "").strip().lower()
        if not self._looks_like_email(normalized_new_email):
            raise ValueError("email_change_invalid_email")
        security = self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        current_email = str(self._current_email_address(identity=identity, security=security) or "").strip().lower()
        if normalized_new_email == current_email:
            raise ValueError("email_change_same_as_current")
        existing_profile = self.repository.get_auth_identity_profile_by_email_address(normalized_new_email, default=None)
        if existing_profile is not None and str(existing_profile.get("actor_id") or "") != identity["actor_id"]:
            raise ValueError("email_change_email_already_in_use")
        existing_identity = self.repository.get_auth_identity_by_account_id(normalized_new_email, default=None)
        if existing_identity is not None and str(existing_identity.get("actor_id") or "") != identity["actor_id"]:
            raise ValueError("email_change_email_already_in_use")
        pending_profile = self.repository.get_auth_identity_profile_by_email_address(normalized_new_email, pending=True, default=None)
        if pending_profile is not None and str(pending_profile.get("actor_id") or "") != identity["actor_id"]:
            raise ValueError("email_change_email_pending_elsewhere")
        try:
            self.email_service.auth_preflight(to_email=normalized_new_email, flow_type="email_change")
        except EmailDeliveryError as exc:
            self._record_delivery_attempt(
                identity=identity,
                flow_type="email_change",
                recipient_email=normalized_new_email,
                status="blocked",
                error=exc,
            )
            raise AuthServiceError(
                http_status=403 if exc.reason == "test_mode_external_recipient_blocked" else 503,
                code="auth_email_change_delivery_failed",
                reason=exc.reason,
                stage="email_policy",
                retryable=exc.retryable,
                action_hint=exc.action_hint,
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    "actor_role": identity["actor_role"],
                    "display_name": identity.get("display_name"),
                    **security,
                },
                email_provider_status=exc.provider_status,
            ) from exc
        self._supersede_flow_tokens(actor_id=identity["actor_id"], flow_type="email_change")
        change = self._issue_flow_token(
            actor_id=identity["actor_id"],
            account_id=identity.get("account_id"),
            flow_type="email_change",
            ttl_seconds=self._verification_token_ttl_seconds(),
            payload_json={"new_email": normalized_new_email},
        )
        try:
            delivery = self._send_email_change_email(
                identity=identity,
                new_email=normalized_new_email,
                email_change_token=change["token"],
            )
        except EmailDeliveryError as exc:
            raise AuthServiceError(
                http_status=503 if exc.reason != "test_mode_external_recipient_blocked" else 403,
                code="auth_email_change_delivery_failed",
                reason=exc.reason,
                stage="email_delivery",
                retryable=exc.retryable,
                action_hint=exc.action_hint,
                can_retry_send=True,
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    "actor_role": identity["actor_role"],
                    "display_name": identity.get("display_name"),
                    **security,
                },
                email_provider_status=exc.provider_status,
            ) from exc
        updated_profile = self.repository.save_auth_identity_profile(
            {
                **self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
                "pending_email_address": normalized_new_email,
                "pending_email_change_requested_at": self._utcnow(),
                "email_change_last_sent_at": self._utcnow(),
            }
        )
        return {
            "status": "email_change_requested",
            "pending_email_address": normalized_new_email,
            "email_change": self._public_flow_token(change),
            "delivery": delivery,
            "identity": {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                "actor_role": identity["actor_role"],
                "display_name": identity.get("display_name"),
                **self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
            },
            "profile": updated_profile,
        }

    def confirm_email_change(self, *, token: str) -> Dict[str, Any]:
        resolved = self._resolve_active_flow_token(raw_token=token, flow_type="email_change")
        identity = self.repository.get_auth_identity(resolved["actor_id"])
        security = self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        normalized_new_email = str((resolved.get("payload_json") or {}).get("new_email") or security.get("pending_email_address") or "").strip().lower()
        if not self._looks_like_email(normalized_new_email):
            raise ValueError("email_change_invalid_email")
        existing_profile = self.repository.get_auth_identity_profile_by_email_address(normalized_new_email, default=None)
        if existing_profile is not None and str(existing_profile.get("actor_id") or "") != identity["actor_id"]:
            raise ValueError("email_change_email_already_in_use")
        existing_identity = self.repository.get_auth_identity_by_account_id(normalized_new_email, default=None)
        if existing_identity is not None and str(existing_identity.get("actor_id") or "") != identity["actor_id"]:
            raise ValueError("email_change_email_already_in_use")
        updated_identity = self.repository.save_auth_identity(
            {
                **identity,
                "account_id": normalized_new_email,
                "status": identity.get("status", "active"),
            }
        )
        updated_profile = self.repository.save_auth_identity_profile(
            {
                **security,
                "actor_id": updated_identity["actor_id"],
                "account_id": normalized_new_email,
                "email_address": normalized_new_email,
                "pending_email_address": None,
                "email_verified": True,
                "verification_required": False,
                "verified_at": self._utcnow(),
                "pending_email_change_requested_at": None,
                "email_change_last_sent_at": None,
            }
        )
        revoked_sessions = self.repository.revoke_auth_tokens_for_actor(updated_identity["actor_id"], reason="email_change")
        self._revoke_refresh_tokens_for_actor(updated_identity["actor_id"], status="revoked")
        self.repository.update_auth_flow_token(
            resolved["flow_token_id"],
            {"status": "consumed", "consumed_at": self._utcnow(), "account_id": normalized_new_email},
        )
        self._supersede_flow_tokens(
            actor_id=updated_identity["actor_id"],
            flow_type="email_change",
            exclude_flow_token_id=resolved["flow_token_id"],
        )
        self.repository.update_auth_flow_tokens_for_actor(
            actor_id=updated_identity["actor_id"],
            flow_type="password_reset",
            statuses=["active"],
            updates={"status": "revoked", "consumed_at": self._utcnow()},
        )
        return {
            "status": "email_change_confirmed",
            "identity": {
                "actor_id": updated_identity["actor_id"],
                "account_id": updated_identity.get("account_id"),
                "actor_role": updated_identity["actor_role"],
                "display_name": updated_identity.get("display_name"),
                **self._serialize_security(actor_id=updated_identity["actor_id"], account_id=updated_identity.get("account_id")),
            },
            "profile": updated_profile,
            "revoked_sessions": revoked_sessions,
        }

    def request_email_verification(self, *, actor_id: str) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        security = self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        if not security.get("verification_required"):
            raise ValueError("email_verification_not_applicable")
        if security.get("email_verified"):
            return {
                "status": "already_verified",
                "identity": {
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    **security,
                },
            }
        next_allowed_at = security.get("verification_next_allowed_at")
        if not security.get("verification_can_resend", True):
            raise AuthServiceError(
                http_status=429,
                code="auth_verification_invalid",
                reason="verification_resend_cooldown",
                stage="rate_limit",
                retryable=True,
                action_hint="wait_before_resend",
                can_retry_send=True,
                next_allowed_at=next_allowed_at,
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    **security,
                },
                email_provider_status=security.get("email_provider_status"),
            )
        self._supersede_flow_tokens(actor_id=identity["actor_id"], flow_type="email_verification")
        verification = self._issue_flow_token(
            actor_id=identity["actor_id"],
            account_id=identity.get("account_id"),
            flow_type="email_verification",
            ttl_seconds=self._verification_token_ttl_seconds(),
        )
        try:
            delivery = self._send_verification_email(identity=identity, verification_token=verification["token"])
        except EmailDeliveryError as exc:
            raise AuthServiceError(
                http_status=503 if exc.reason != "test_mode_external_recipient_blocked" else 403,
                code="auth_verification_delivery_failed",
                reason=exc.reason,
                stage="email_delivery",
                retryable=exc.retryable,
                action_hint=exc.action_hint,
                can_retry_send=True,
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    **security,
                },
                email_provider_status=exc.provider_status,
            ) from exc
        return {
            "status": "verification_sent",
            "verification": self._public_flow_token(verification),
            "delivery": delivery,
            "identity": {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                **self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
            },
        }

    def confirm_email_verification(self, *, token: str) -> Dict[str, Any]:
        resolved = self._resolve_active_flow_token(raw_token=token, flow_type="email_verification")
        identity = self.repository.get_auth_identity(resolved["actor_id"])
        updated_profile = self.repository.save_auth_identity_profile(
            {
                **self._security_profile(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
                "email_address": identity["actor_id"] if self._looks_like_email(identity["actor_id"]) else None,
                "email_verified": True,
                "verification_required": False,
                "verified_at": self._utcnow(),
            }
        )
        self.repository.update_auth_flow_token(
            resolved["flow_token_id"],
            {
                "status": "consumed",
                "consumed_at": self._utcnow(),
            },
        )
        self._supersede_flow_tokens(
            actor_id=identity["actor_id"],
            flow_type="email_verification",
            exclude_flow_token_id=resolved["flow_token_id"],
        )
        return {
            "status": "verified",
            "identity": {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                "actor_role": identity["actor_role"],
                "display_name": identity.get("display_name"),
                **self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id")),
            },
            "profile": updated_profile,
        }

    def request_password_reset(self, *, actor_id: str) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        security = self._serialize_security(actor_id=identity["actor_id"], account_id=identity.get("account_id"))
        if not self._looks_like_email(self._current_email_address(identity=identity, security=security)):
            raise ValueError("password_reset_not_applicable")
        self._supersede_flow_tokens(actor_id=identity["actor_id"], flow_type="password_reset")
        reset = self._issue_flow_token(
            actor_id=identity["actor_id"],
            account_id=identity.get("account_id"),
            flow_type="password_reset",
            ttl_seconds=self._password_reset_token_ttl_seconds(),
        )
        try:
            delivery = self._send_password_reset_email(identity=identity, reset_token=reset["token"])
        except EmailDeliveryError as exc:
            raise AuthServiceError(
                http_status=503 if exc.reason != "test_mode_external_recipient_blocked" else 403,
                code="auth_password_reset_delivery_failed",
                reason=exc.reason,
                stage="email_delivery",
                retryable=exc.retryable,
                action_hint=exc.action_hint,
                can_retry_send=True,
                identity={
                    "actor_id": identity["actor_id"],
                    "account_id": identity.get("account_id"),
                    **security,
                },
                email_provider_status=exc.provider_status,
            ) from exc
        return {
            "status": "password_reset_sent",
            "reset": self._public_flow_token(reset),
            "delivery": delivery,
            "identity": {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                **security,
            },
        }

    def confirm_password_reset(self, *, token: str, new_password: str) -> Dict[str, Any]:
        if not str(new_password or "").strip():
            raise ValueError("password_required")
        resolved = self._resolve_active_flow_token(raw_token=token, flow_type="password_reset")
        identity = self.repository.get_auth_identity(resolved["actor_id"])
        salt = self._password_salt()
        updated_identity = self.repository.save_auth_identity(
            {
                **identity,
                "password_hash": self._password_hash(new_password, salt),
                "password_salt": salt,
                "status": identity.get("status", "active"),
            }
        )
        revoked_sessions = self.repository.revoke_auth_tokens_for_actor(updated_identity["actor_id"], reason="password_reset")
        self._revoke_refresh_tokens_for_actor(updated_identity["actor_id"], status="revoked")
        self.repository.update_auth_flow_token(
            resolved["flow_token_id"],
            {
                "status": "consumed",
                "consumed_at": self._utcnow(),
            },
        )
        self._supersede_flow_tokens(
            actor_id=updated_identity["actor_id"],
            flow_type="password_reset",
            exclude_flow_token_id=resolved["flow_token_id"],
        )
        return {
            "status": "password_reset_confirmed",
            "identity": {
                "actor_id": updated_identity["actor_id"],
                "account_id": updated_identity.get("account_id"),
                "actor_role": updated_identity["actor_role"],
                "display_name": updated_identity.get("display_name"),
                **self._serialize_security(actor_id=updated_identity["actor_id"], account_id=updated_identity.get("account_id")),
            },
            "revoked_sessions": revoked_sessions,
        }
