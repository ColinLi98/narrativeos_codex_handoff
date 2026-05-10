from __future__ import annotations

from dataclasses import dataclass
from email.utils import parseaddr
import json
import os
from typing import Any, Dict, Optional

import httpx


def _first_env(*keys: str, default: Optional[str] = None) -> Optional[str]:
    for key in keys:
        value = str(os.getenv(key, "") or "").strip()
        if value:
            return value
    return default


def _normalize_mode(value: Optional[str]) -> str:
    lowered = str(value or "test").strip().lower()
    return "production" if lowered in {"production", "prod", "live"} else "test"


def _normalize_domain_status(value: Optional[str]) -> str:
    lowered = str(value or "unverified").strip().lower()
    if lowered in {"verified", "active", "ready"}:
        return "verified"
    if lowered in {"pending", "verifying"}:
        return "pending"
    return "unverified"


def _split_allowlist(value: Optional[str]) -> tuple[str, ...]:
    entries = []
    for item in str(value or "").replace("\n", ",").split(","):
        normalized = item.strip().lower()
        if normalized:
            entries.append(normalized)
    return tuple(dict.fromkeys(entries))


def _normalize_email(value: Optional[str]) -> Optional[str]:
    _name, email = parseaddr(str(value or "").strip())
    normalized = str(email or "").strip().lower()
    return normalized or None


def _compose_from_display(*, from_name: Optional[str], from_email: Optional[str], legacy_display: Optional[str]) -> Optional[str]:
    email_address = _normalize_email(from_email) or _normalize_email(legacy_display)
    if not email_address:
        return None
    parsed_name, _parsed_email = parseaddr(str(legacy_display or "").strip())
    display_name = str(from_name or parsed_name or "").strip()
    if display_name:
        return f"{display_name} <{email_address}>"
    return email_address


def _response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or response.reason_phrase or "email_provider_error"
    if isinstance(payload, dict):
        return (
            str(payload.get("message") or "").strip()
            or str(payload.get("error") or "").strip()
            or json.dumps(payload, ensure_ascii=False)
        )
    return json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True)
class EmailSenderConfig:
    provider: str
    mode: str
    resend_api_key: Optional[str]
    resend_from_email: Optional[str]
    resend_from_name: Optional[str]
    resend_from_display: Optional[str]
    resend_reply_to: Optional[str]
    verified_domain_status: str
    allowlist: tuple[str, ...]

    @property
    def expose_debug_tokens(self) -> bool:
        return self.mode != "production"

    def as_status(self) -> Dict[str, Any]:
        sender_email = _normalize_email(self.resend_from_email or self.resend_from_display)
        configured = bool(self.resend_api_key and self.resend_from_display)
        return {
            "provider": self.provider,
            "mode": self.mode,
            "configured": configured if self.provider == "resend" else True,
            "from_email": sender_email,
            "from_name": self.resend_from_name,
            "from_display": self.resend_from_display,
            "reply_to": self.resend_reply_to,
            "verified_domain_status": self.verified_domain_status,
            "external_delivery_enabled": bool(
                self.provider == "resend"
                and configured
                and self.mode == "production"
                and self.verified_domain_status == "verified"
            ),
            "recipient_policy": "external_allowed" if self.mode == "production" else "test_only",
            "allowlist": list(self.allowlist),
            "debug_token_echo_enabled": self.expose_debug_tokens,
        }


class EmailDeliveryError(RuntimeError):
    def __init__(
        self,
        *,
        reason: str,
        provider: str,
        retryable: bool = False,
        action_hint: Optional[str] = None,
        provider_status: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.provider = provider
        self.retryable = retryable
        self.action_hint = action_hint
        self.provider_status = dict(provider_status or {})
        self.metadata = dict(metadata or {})

    def detail(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "provider": self.provider,
            "retryable": self.retryable,
            "action_hint": self.action_hint,
            "provider_status": self.provider_status,
            "metadata": self.metadata,
        }


class StubEmailProvider:
    provider_id = "stub"

    def configured(self) -> bool:
        return True

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "configured": True,
            "status": "queued",
            "message_id": f"stub_{abs(hash((to_email, subject))) % 10_000_000}",
            "to_email": to_email,
            "subject": subject,
            "tags": dict(tags or {}),
            "preview_text": text or "",
        }


class ResendEmailProvider:
    provider_id = "resend"
    api_base_url = "https://api.resend.com"

    def __init__(
        self,
        *,
        api_key: Optional[str],
        from_display: Optional[str],
        reply_to: Optional[str] = None,
        provider_status: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.api_key = str(api_key or "").strip() or None
        self.from_display = str(from_display or "").strip() or None
        self.reply_to = str(reply_to or "").strip() or None
        self._provider_status = dict(provider_status or {})

    def configured(self) -> bool:
        return bool(self.api_key and self.from_display)

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.configured():
            raise EmailDeliveryError(
                reason="provider_not_configured",
                provider=self.provider_id,
                action_hint="configure_resend_sender",
                provider_status=self._provider_status,
            )
        payload: Dict[str, Any] = {
            "from": self.from_display,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text
        if self.reply_to:
            payload["reply_to"] = self.reply_to
        if tags:
            payload["tags"] = [{"name": str(key), "value": str(value)} for key, value in dict(tags).items()]
        try:
            response = httpx.post(
                f"{self.api_base_url}/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response = exc.response
            message = _response_error_message(response).lower()
            reason = "provider_rejected"
            action_hint = "retry_delivery_later"
            retryable = response.status_code >= 500 or response.status_code == 429
            if "verify a domain" in message or "domain is not verified" in message:
                reason = "domain_not_verified"
                action_hint = "verify_sender_domain"
                retryable = False
            elif "testing emails" in message or "test emails" in message:
                reason = "test_mode_external_recipient_blocked"
                action_hint = "use_test_recipient_or_verified_domain"
                retryable = False
            raise EmailDeliveryError(
                reason=reason,
                provider=self.provider_id,
                retryable=retryable,
                action_hint=action_hint,
                provider_status=self._provider_status,
                metadata={
                    "response_status": response.status_code,
                    "response_message": _response_error_message(response),
                },
            ) from exc
        except httpx.RequestError as exc:
            raise EmailDeliveryError(
                reason="provider_network_error",
                provider=self.provider_id,
                retryable=True,
                action_hint="retry_delivery_later",
                provider_status=self._provider_status,
                metadata={"request_error": str(exc)},
            ) from exc
        body = response.json()
        return {
            "provider": self.provider_id,
            "configured": True,
            "status": "queued",
            "message_id": body.get("id"),
            "to_email": to_email,
            "subject": subject,
            "tags": dict(tags or {}),
        }


class EmailService:
    def __init__(self) -> None:
        self.config = self._load_config()
        provider_status = self.config.as_status()
        self.stub = StubEmailProvider()
        self.resend = ResendEmailProvider(
            api_key=self.config.resend_api_key,
            from_display=self.config.resend_from_display,
            reply_to=self.config.resend_reply_to,
            provider_status=provider_status,
        )

    def _load_config(self) -> EmailSenderConfig:
        legacy_from = _first_env("NARRATIVEOS_EMAIL_FROM")
        resend_from_email = _first_env("RESEND_FROM_EMAIL")
        resend_from_name = _first_env("RESEND_FROM_NAME")
        resend_from_display = _compose_from_display(
            from_name=resend_from_name,
            from_email=resend_from_email,
            legacy_display=legacy_from,
        )
        parsed_name, _parsed_email = parseaddr(str(legacy_from or "").strip())
        provider = str(_first_env("EMAIL_PROVIDER", "NARRATIVEOS_EMAIL_PROVIDER", default="stub") or "stub").strip() or "stub"
        return EmailSenderConfig(
            provider=provider,
            mode=_normalize_mode(_first_env("EMAIL_MODE", default="test")),
            resend_api_key=_first_env("RESEND_API_KEY"),
            resend_from_email=_normalize_email(resend_from_email or legacy_from),
            resend_from_name=str(resend_from_name or parsed_name or "").strip() or None,
            resend_from_display=resend_from_display,
            resend_reply_to=_first_env("RESEND_REPLY_TO", "NARRATIVEOS_EMAIL_REPLY_TO"),
            verified_domain_status=_normalize_domain_status(_first_env("RESEND_VERIFIED_DOMAIN_STATUS")),
            allowlist=_split_allowlist(_first_env("EMAIL_SEND_ALLOWLIST")),
        )

    def _provider(self):
        return self.resend if self.config.provider == self.resend.provider_id else self.stub

    def _is_test_recipient(self, email_address: str) -> bool:
        normalized = _normalize_email(email_address) or ""
        if not normalized:
            return False
        if normalized.endswith("@resend.dev"):
            return True
        if normalized in self.config.allowlist:
            return True
        domain_entry = f"@{normalized.split('@', 1)[1]}"
        return domain_entry in self.config.allowlist

    def expose_debug_tokens(self) -> bool:
        return self.config.expose_debug_tokens

    def provider_status(self) -> Dict[str, Any]:
        return self.config.as_status()

    def auth_preflight(self, *, to_email: str, flow_type: str) -> Dict[str, Any]:
        normalized_recipient = _normalize_email(to_email)
        if not normalized_recipient:
            raise EmailDeliveryError(
                reason="invalid_recipient_email",
                provider=self.config.provider,
                action_hint="enter_valid_email_address",
                provider_status=self.provider_status(),
            )
        status = self.provider_status()
        if self.config.mode == "test":
            if not self._is_test_recipient(normalized_recipient):
                raise EmailDeliveryError(
                    reason="test_mode_external_recipient_blocked",
                    provider=self.config.provider,
                    action_hint="use_test_recipient_or_verified_domain",
                    provider_status=status,
                    metadata={"flow_type": flow_type, "recipient_email": normalized_recipient},
                )
            if self.config.provider == self.resend.provider_id and not self.resend.configured():
                raise EmailDeliveryError(
                    reason="provider_not_configured",
                    provider=self.config.provider,
                    action_hint="configure_resend_sender",
                    provider_status=status,
                    metadata={"flow_type": flow_type},
                )
            return {
                "recipient_email": normalized_recipient,
                "status": "test_ready",
                "provider_status": status,
            }
        if self.config.provider != self.resend.provider_id or not self.resend.configured():
            raise EmailDeliveryError(
                reason="provider_not_configured",
                provider=self.config.provider,
                action_hint="configure_resend_sender",
                provider_status=status,
                metadata={"flow_type": flow_type},
            )
        if self.config.verified_domain_status != "verified":
            raise EmailDeliveryError(
                reason="domain_not_verified",
                provider=self.config.provider,
                action_hint="verify_sender_domain",
                provider_status=status,
                metadata={"flow_type": flow_type},
            )
        return {
            "recipient_email": normalized_recipient,
            "status": "production_ready",
            "provider_status": status,
        }

    def send_verification_email(
        self,
        *,
        to_email: str,
        display_name: Optional[str],
        verify_token: str,
        app_base_url: str,
    ) -> Dict[str, Any]:
        normalized = self.auth_preflight(to_email=to_email, flow_type="email_verification")["recipient_email"]
        safe_name = display_name or normalized
        verify_url = f"{app_base_url.rstrip('/')}/verify-email?token={verify_token}"
        subject = "Verify your NarrativeOS account"
        html = (
            f"<p>Hello {safe_name},</p>"
            "<p>Please verify your NarrativeOS account before using paid features.</p>"
            f"<p><a href=\"{verify_url}\">Verify email</a></p>"
            f"<p>If the button does not work, use this token: <code>{verify_token}</code></p>"
        )
        text = (
            f"Hello {safe_name},\n\n"
            "Please verify your NarrativeOS account before using paid features.\n"
            f"Verify URL: {verify_url}\n"
            f"Verification token: {verify_token}\n"
        )
        delivery = self._provider().send(
            to_email=normalized,
            subject=subject,
            html=html,
            text=text,
            tags={"flow": "email_verification"},
        )
        return {
            **delivery,
            "mode": self.config.mode,
            "from_email": self.provider_status().get("from_email"),
        }

    def send_password_reset_email(
        self,
        *,
        to_email: str,
        display_name: Optional[str],
        reset_token: str,
        app_base_url: str,
    ) -> Dict[str, Any]:
        normalized = self.auth_preflight(to_email=to_email, flow_type="password_reset")["recipient_email"]
        safe_name = display_name or normalized
        reset_url = f"{app_base_url.rstrip('/')}/reset-password?token={reset_token}"
        subject = "Reset your NarrativeOS password"
        html = (
            f"<p>Hello {safe_name},</p>"
            "<p>Use the link below to reset your NarrativeOS password.</p>"
            f"<p><a href=\"{reset_url}\">Reset password</a></p>"
            f"<p>If the button does not work, use this token: <code>{reset_token}</code></p>"
        )
        text = (
            f"Hello {safe_name},\n\n"
            "Use the link below to reset your NarrativeOS password.\n"
            f"Reset URL: {reset_url}\n"
            f"Reset token: {reset_token}\n"
        )
        delivery = self._provider().send(
            to_email=normalized,
            subject=subject,
            html=html,
            text=text,
            tags={"flow": "password_reset"},
        )
        return {
            **delivery,
            "mode": self.config.mode,
            "from_email": self.provider_status().get("from_email"),
        }

    def send_email_change_email(
        self,
        *,
        to_email: str,
        display_name: Optional[str],
        email_change_token: str,
        app_base_url: str,
    ) -> Dict[str, Any]:
        normalized = self.auth_preflight(to_email=to_email, flow_type="email_change")["recipient_email"]
        safe_name = display_name or normalized
        base_url = app_base_url.rstrip("/")
        if base_url.endswith("/app"):
            base_url = base_url[:-4]
        confirm_url = f"{base_url}/settings/account/email-change/confirm?token={email_change_token}"
        subject = "Confirm your new NarrativeOS email"
        html = (
            f"<p>Hello {safe_name},</p>"
            "<p>Use the link below to confirm this email address for your NarrativeOS account.</p>"
            f"<p><a href=\"{confirm_url}\">Confirm new email</a></p>"
            f"<p>If the button does not work, use this token: <code>{email_change_token}</code></p>"
        )
        text = (
            f"Hello {safe_name},\n\n"
            "Use the link below to confirm this email address for your NarrativeOS account.\n"
            f"Confirm URL: {confirm_url}\n"
            f"Confirmation token: {email_change_token}\n"
        )
        delivery = self._provider().send(
            to_email=normalized,
            subject=subject,
            html=html,
            text=text,
            tags={"flow": "email_change"},
        )
        return {
            **delivery,
            "mode": self.config.mode,
            "from_email": self.provider_status().get("from_email"),
        }
