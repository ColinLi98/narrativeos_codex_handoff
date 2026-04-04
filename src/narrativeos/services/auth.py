from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional

from ..persistence.repositories import SQLAlchemyPlatformRepository


TOKEN_TTL_DAYS = 14


class AuthService:
    def __init__(self, repository: SQLAlchemyPlatformRepository) -> None:
        self.repository = repository

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _token_hash(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def _password_salt(self) -> str:
        return secrets.token_hex(16)

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
        salt = self._password_salt()
        record = self.repository.save_auth_identity(
            {
                "actor_id": resolved_actor_id,
                "account_id": str(account_id or "").strip() or None,
                "actor_role": str(actor_role or "author").strip() or "author",
                "display_name": display_name,
                "password_hash": self._password_hash(password, salt),
                "password_salt": salt,
                "status": "active",
            }
        )
        return {
            "identity": {
                "actor_id": record["actor_id"],
                "account_id": record.get("account_id"),
                "actor_role": record["actor_role"],
                "display_name": record.get("display_name"),
                "status": record["status"],
                "created_at": record["created_at"],
            }
        }

    def issue_token(self, *, actor_id: str, password: str) -> Dict[str, Any]:
        identity = self.repository.get_auth_identity(actor_id)
        if identity.get("status") != "active":
            raise PermissionError("auth_identity_inactive")
        if not self._verify_password(password, password_hash=identity["password_hash"], salt=identity["password_salt"]):
            raise PermissionError("invalid_credentials")
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
        return {
            "token": {
                "access_token": raw_token,
                "token_type": "bearer",
                "expires_at": expires_at,
            },
            "identity": {
                "actor_id": identity["actor_id"],
                "account_id": identity.get("account_id"),
                "actor_role": identity["actor_role"],
                "display_name": identity.get("display_name"),
            },
            "session": {
                "token_id": token["token_id"],
                "last_used_at": token["last_used_at"],
            },
        }

    def resolve_bearer_token(self, raw_token: str) -> Dict[str, Any]:
        if not str(raw_token or "").strip():
            raise PermissionError("missing_bearer_token")
        token = self.repository.get_auth_token_by_hash(self._token_hash(raw_token))
        if token.get("status") != "active":
            raise PermissionError("inactive_bearer_token")
        expires_at = token.get("expires_at")
        if expires_at:
            normalized = str(expires_at).replace("Z", "+00:00")
            if datetime.fromisoformat(normalized) < datetime.now(timezone.utc):
                self.repository.update_auth_token(token["token_id"], {"status": "expired"})
                raise PermissionError("expired_bearer_token")
        updated = self.repository.update_auth_token(token["token_id"], {"last_used_at": self._utcnow()})
        identity = self.repository.get_auth_identity(updated["actor_id"])
        return {
            "actor_id": identity["actor_id"],
            "account_id": identity.get("account_id"),
            "actor_role": identity["actor_role"],
            "display_name": identity.get("display_name"),
            "token_id": updated["token_id"],
            "expires_at": updated.get("expires_at"),
            "last_used_at": updated.get("last_used_at"),
        }

    def revoke_bearer_token(self, raw_token: str) -> Dict[str, Any]:
        token = self.repository.get_auth_token_by_hash(self._token_hash(raw_token))
        updated = self.repository.update_auth_token(token["token_id"], {"status": "revoked"})
        return {
            "token_id": updated["token_id"],
            "status": updated["status"],
        }
