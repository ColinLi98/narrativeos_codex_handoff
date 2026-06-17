from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from typing import Any, Callable, Dict, Optional, Protocol, TYPE_CHECKING
from urllib import request as urlrequest
from urllib.parse import quote, urlencode, urlparse

from ..persistence.repositories import SQLAlchemyPlatformRepository

if TYPE_CHECKING:
    from .analytics import AnalyticsService
    from .async_jobs import AsyncJobService

try:  # pragma: no cover - exercised in local py311 env and production runtime
    from vercel.blob import BlobClient as VercelBlobClient
    from vercel._internal.blob.core import construct_blob_url as vercel_construct_blob_url
    from vercel._internal.blob.core import extract_store_id_from_token as vercel_extract_store_id_from_token
except ImportError:  # pragma: no cover - py39 test env intentionally exercises fake storage
    VercelBlobClient = None
    vercel_construct_blob_url = None
    vercel_extract_store_id_from_token = None


ILLUSTRATION_JOB_TYPE = "illustration_generate"
ILLUSTRATION_PROMPT_VERSION = "illustration_prompt/v1"
WORLD_COVER_KIND = "world_cover"
SESSION_COVER_KIND = "session_cover"
CHAPTER_HERO_KIND = "chapter_hero"
ASSET_KIND_SIZES = {
    WORLD_COVER_KIND: "1024x1024",
    SESSION_COVER_KIND: "1024x1024",
    CHAPTER_HERO_KIND: "1536x1024",
}
PRIVATE_MEDIA_ROUTE_PREFIX = "/api/v1/media/assets"
VERCEL_WORLD_STORE_NAME = "world_public"
VERCEL_READER_STORE_NAME = "reader_private"
DEFAULT_BLOB_SIGNED_URL_TTL_SECONDS = 900


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _truthy_env(value: Any, *, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def _guess_mime_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _parse_size(size: str) -> tuple[Optional[int], Optional[int]]:
    normalized = str(size or "").strip().lower()
    if "x" not in normalized:
        return None, None
    width_raw, height_raw = normalized.split("x", 1)
    try:
        return int(width_raw), int(height_raw)
    except ValueError:
        return None, None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_location(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "title", "label", "location_id"):
            if str(value.get(key) or "").strip():
                return str(value.get(key)).strip()
        return str(value)
    return str(value or "").strip()


@dataclass
class IllustrationConfig:
    openai_api_key: str
    image_model: str
    world_blob_token: str
    reader_blob_token: str
    illustrations_enabled: bool

    @classmethod
    def from_env(cls) -> "IllustrationConfig":
        return cls(
            openai_api_key=str(os.getenv("OPENAI_API_KEY", "") or "").strip(),
            image_model=str(os.getenv("NARRATIVEOS_IMAGE_MODEL", "gpt-image-2") or "gpt-image-2").strip(),
            world_blob_token=str(os.getenv("NARRATIVEOS_WORLD_BLOB_READ_WRITE_TOKEN", "") or "").strip(),
            reader_blob_token=str(os.getenv("NARRATIVEOS_READER_BLOB_READ_WRITE_TOKEN", "") or "").strip(),
            illustrations_enabled=_truthy_env(os.getenv("NARRATIVEOS_ILLUSTRATIONS_ENABLED"), default=True),
        )


class ImageClient(Protocol):
    def generate_image_bytes(self, *, prompt: str, size: str) -> tuple[bytes, str]:
        ...


class ObjectStorageClient(Protocol):
    def put_bytes(self, *, storage_key: str, content: bytes, content_type: str) -> str:
        ...

    def get_bytes(self, *, storage_key: str) -> tuple[bytes, str]:
        ...

    def build_public_url(self, *, storage_key: str) -> str:
        ...

    def build_signed_url(self, *, asset_id: str, expires_at: datetime) -> str:
        ...

    def validate_signed_url(self, *, asset_id: str, expires: int, signature: str) -> bool:
        ...


class BlobClientLike(Protocol):
    def put(
        self,
        path: str,
        body: Any,
        *,
        access: str = "public",
        content_type: Optional[str] = None,
        add_random_suffix: bool = False,
        overwrite: bool = False,
        cache_control_max_age: Optional[int] = None,
        multipart: bool = False,
        on_upload_progress: Optional[Callable[..., Any]] = None,
    ) -> Any:
        ...

    def get(
        self,
        url_or_path: str,
        *,
        access: str = "public",
        timeout: Optional[float] = None,
        use_cache: bool = True,
        if_none_match: Optional[str] = None,
    ) -> Any:
        ...

    def head(self, url_or_path: str) -> Any:
        ...


class OpenAIImageClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "gpt-image-2").strip() or "gpt-image-2"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def generate_image_bytes(self, *, prompt: str, size: str) -> tuple[bytes, str]:
        if not self.api_key:
            raise RuntimeError("openai_api_key_missing")
        body = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
        }
        req = urlrequest.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlrequest.urlopen(req) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        image_item = dict((payload.get("data") or [{}])[0] or {})
        if str(image_item.get("b64_json") or "").strip():
            image_bytes = base64.b64decode(str(image_item["b64_json"]))
            return image_bytes, _guess_mime_type(image_bytes)
        image_url = str(image_item.get("url") or "").strip()
        if not image_url:
            raise RuntimeError("openai_image_generation_empty_response")
        download_req = urlrequest.Request(image_url, method="GET")
        with urlrequest.urlopen(download_req) as response:  # noqa: S310
            image_bytes = response.read()
            mime_type = response.headers.get("Content-Type") or _guess_mime_type(image_bytes)
        return image_bytes, str(mime_type or _guess_mime_type(image_bytes))


class VercelBlobStorage:
    def __init__(
        self,
        *,
        world_blob_token: str,
        reader_blob_token: str,
        world_blob_client: Optional[BlobClientLike] = None,
        reader_blob_client: Optional[BlobClientLike] = None,
        signed_url_ttl_seconds: int = DEFAULT_BLOB_SIGNED_URL_TTL_SECONDS,
        signed_route_prefix: str = PRIVATE_MEDIA_ROUTE_PREFIX,
    ) -> None:
        self.world_blob_token = str(world_blob_token or "").strip()
        self.reader_blob_token = str(reader_blob_token or "").strip()
        self.world_blob_client = world_blob_client
        self.reader_blob_client = reader_blob_client
        self.bucket = "vercel_blob"
        self.signed_url_ttl_seconds = max(60, int(signed_url_ttl_seconds or 900))
        self.signed_route_prefix = str(signed_route_prefix or PRIVATE_MEDIA_ROUTE_PREFIX).strip().rstrip("/")
        self._signing_secret = self.reader_blob_token or self.world_blob_token

    @classmethod
    def from_config(cls, config: IllustrationConfig) -> "VercelBlobStorage":
        return cls(
            world_blob_token=config.world_blob_token,
            reader_blob_token=config.reader_blob_token,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.world_blob_token and self.reader_blob_token)

    def _world_store_id(self) -> str:
        if not self.world_blob_token or vercel_extract_store_id_from_token is None:
            return ""
        return str(vercel_extract_store_id_from_token(self.world_blob_token) or "")

    def _reader_store_id(self) -> str:
        if not self.reader_blob_token or vercel_extract_store_id_from_token is None:
            return ""
        return str(vercel_extract_store_id_from_token(self.reader_blob_token) or "")

    def _world_client(self) -> BlobClientLike:
        if self.world_blob_client is not None:
            return self.world_blob_client
        if VercelBlobClient is None or not self.world_blob_token:
            raise RuntimeError("vercel_blob_world_store_not_configured")
        self.world_blob_client = VercelBlobClient(token=self.world_blob_token)
        return self.world_blob_client

    def _reader_client(self) -> BlobClientLike:
        if self.reader_blob_client is not None:
            return self.reader_blob_client
        if VercelBlobClient is None or not self.reader_blob_token:
            raise RuntimeError("vercel_blob_reader_store_not_configured")
        self.reader_blob_client = VercelBlobClient(token=self.reader_blob_token)
        return self.reader_blob_client

    def _is_world_key(self, storage_key: str) -> bool:
        normalized = str(storage_key or "").strip()
        if normalized.startswith("world_versions/"):
            return True
        host = urlparse(normalized).netloc
        store_id = self._world_store_id()
        return bool(store_id and host == f"{store_id}.public.blob.vercel-storage.com")

    def _is_reader_key(self, storage_key: str) -> bool:
        normalized = str(storage_key or "").strip()
        if normalized.startswith("sessions/"):
            return True
        host = urlparse(normalized).netloc
        store_id = self._reader_store_id()
        return bool(store_id and host == f"{store_id}.private.blob.vercel-storage.com")

    def _canonical_url(self, *, storage_key: str, access: str) -> str:
        normalized = str(storage_key or "").strip()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return normalized
        if vercel_construct_blob_url is None:
            return normalized
        store_id = self._world_store_id() if access == "public" else self._reader_store_id()
        if not store_id:
            return normalized
        return str(vercel_construct_blob_url(store_id, normalized, access))

    def put_bytes(self, *, storage_key: str, content: bytes, content_type: str) -> str:
        access = "public" if self._is_world_key(storage_key) else "private"
        client = self._world_client() if access == "public" else self._reader_client()
        result = client.put(
            str(storage_key or "").lstrip("/"),
            content,
            access=access,
            content_type=content_type,
            add_random_suffix=False,
            overwrite=True,
        )
        return str(getattr(result, "url", "") or self._canonical_url(storage_key=storage_key, access=access))

    def get_bytes(self, *, storage_key: str) -> tuple[bytes, str]:
        access = "public" if self._is_world_key(storage_key) else "private"
        client = self._world_client() if access == "public" else self._reader_client()
        result = client.get(storage_key, access=access)
        content = bytes(getattr(result, "content", b"") or b"")
        mime_type = str(getattr(result, "content_type", "") or _guess_mime_type(content))
        return content, mime_type

    def build_public_url(self, *, storage_key: str) -> str:
        return self._canonical_url(storage_key=storage_key, access="public")

    def build_signed_url(self, *, asset_id: str, expires_at: datetime) -> str:
        expires = int(expires_at.timestamp())
        signature = hmac.new(
            str(self._signing_secret or "").encode("utf-8"),
            f"{asset_id}:{expires}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return (
            f"{self.signed_route_prefix}/{quote(str(asset_id or '').strip(), safe='')}"
            f"?{urlencode({'expires': expires, 'signature': signature})}"
        )

    def validate_signed_url(self, *, asset_id: str, expires: int, signature: str) -> bool:
        if not asset_id or not signature:
            return False
        if int(expires or 0) < int(datetime.now(timezone.utc).timestamp()):
            return False
        expected = hmac.new(
            str(self._signing_secret or "").encode("utf-8"),
            f"{asset_id}:{int(expires)}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, str(signature))


class IllustrationPromptBuilder:
    def _worldpack_payload(self, world_version: Any) -> Dict[str, Any]:
        return dict(getattr(world_version, "worldpack_json", {}) or {})

    def _world_metadata(self, worldpack_payload: Dict[str, Any]) -> Dict[str, Any]:
        return dict(worldpack_payload.get("metadata") or {})

    def _illustration_profile(self, worldpack_payload: Dict[str, Any]) -> Dict[str, Any]:
        return dict(self._world_metadata(worldpack_payload).get("illustration_profile") or {})

    def build_world_cover_trace(self, *, world_version: Any) -> Dict[str, Any]:
        worldpack_payload = self._worldpack_payload(world_version)
        world_bible = dict(worldpack_payload.get("world_bible") or {})
        narrative_style_pack = dict(worldpack_payload.get("narrative_style_pack") or {})
        profile = self._illustration_profile(worldpack_payload)
        locations = [
            location
            for location in (_normalize_location(item) for item in list(world_bible.get("locations") or []))
            if location
        ][:4]
        trace = {
            "asset_kind": WORLD_COVER_KIND,
            "title": str(worldpack_payload.get("title") or world_version.world_id),
            "world_id": str(world_version.world_id or ""),
            "world_version_id": str(world_version.world_version_id or ""),
            "premise": str(world_bible.get("premise") or ""),
            "locations": locations,
            "style_prompt": str(profile.get("style_prompt") or ""),
            "negative_prompt": str(profile.get("negative_prompt") or ""),
            "palette_tags": [str(item) for item in list(profile.get("palette_tags") or []) if str(item).strip()],
            "character_anchor_notes": [
                str(item) for item in list(profile.get("character_anchor_notes") or []) if str(item).strip()
            ],
            "narrative_style_pack": {
                "style_pack_id": str(narrative_style_pack.get("style_pack_id") or ""),
                "tonal_lexicon": [str(item) for item in list(narrative_style_pack.get("tonal_lexicon") or [])[:5]],
                "thematic_axis_labels": dict(narrative_style_pack.get("thematic_axis_labels") or {}),
            },
            "size": ASSET_KIND_SIZES[WORLD_COVER_KIND],
        }
        trace["prompt"] = self.render_prompt(trace)
        return trace

    def build_session_cover_trace(
        self,
        *,
        session_id: str,
        reader_id: Optional[str],
        world_version: Any,
    ) -> Dict[str, Any]:
        trace = self.build_world_cover_trace(world_version=world_version)
        trace.update(
            {
                "asset_kind": SESSION_COVER_KIND,
                "session_id": str(session_id or ""),
                "reader_id": str(reader_id or "") or None,
                "size": ASSET_KIND_SIZES[SESSION_COVER_KIND],
            }
        )
        trace["prompt"] = self.render_prompt(trace)
        return trace

    def build_chapter_hero_trace(
        self,
        *,
        session_id: str,
        reader_id: Optional[str],
        chapter_index: int,
        world_version: Any,
        rendered_scene: Dict[str, Any],
    ) -> Dict[str, Any]:
        worldpack_payload = self._worldpack_payload(world_version)
        profile = self._illustration_profile(worldpack_payload)
        trace = {
            "asset_kind": CHAPTER_HERO_KIND,
            "session_id": str(session_id or ""),
            "reader_id": str(reader_id or "") or None,
            "chapter_index": int(chapter_index or 0),
            "title": str(worldpack_payload.get("title") or world_version.world_id),
            "world_id": str(world_version.world_id or ""),
            "world_version_id": str(world_version.world_version_id or ""),
            "scene_title": str(rendered_scene.get("story_title") or ""),
            "visual_prompt": str(rendered_scene.get("visual_prompt") or ""),
            "image_motif": str(rendered_scene.get("image_motif") or ""),
            "palette_hint": str(rendered_scene.get("palette_hint") or ""),
            "story_beats": [str(item) for item in list(rendered_scene.get("story_beats") or []) if str(item).strip()],
            "visual_details": [str(item) for item in list(rendered_scene.get("visual_details") or []) if str(item).strip()],
            "image_caption": str(rendered_scene.get("image_caption") or ""),
            "style_prompt": str(profile.get("style_prompt") or ""),
            "negative_prompt": str(profile.get("negative_prompt") or ""),
            "palette_tags": [str(item) for item in list(profile.get("palette_tags") or []) if str(item).strip()],
            "character_anchor_notes": [
                str(item) for item in list(profile.get("character_anchor_notes") or []) if str(item).strip()
            ],
            "size": ASSET_KIND_SIZES[CHAPTER_HERO_KIND],
        }
        trace["prompt"] = self.render_prompt(trace)
        return trace

    def render_prompt(self, trace: Dict[str, Any]) -> str:
        asset_kind = str(trace.get("asset_kind") or "")
        title = str(trace.get("title") or "").strip()
        sections = [
            "Create an original narrative illustration for NarrativeOS.",
            "No text, no logo, no watermark, no UI overlay, no border.",
        ]
        if asset_kind == WORLD_COVER_KIND:
            sections.append("Asset target: public world cover image.")
            sections.append(f"World title: {title}.")
            if trace.get("premise"):
                sections.append(f"World premise: {trace['premise']}.")
            if trace.get("locations"):
                sections.append("Key locations: %s." % ", ".join(trace["locations"]))
            style_pack = dict(trace.get("narrative_style_pack") or {})
            tonal_lexicon = [str(item) for item in list(style_pack.get("tonal_lexicon") or []) if str(item).strip()]
            if tonal_lexicon:
                sections.append("Narrative tonal lexicon: %s." % ", ".join(tonal_lexicon))
        elif asset_kind == SESSION_COVER_KIND:
            sections.append("Asset target: private reader session cover image.")
            sections.append(f"World title: {title}.")
            if trace.get("premise"):
                sections.append(f"Opening premise: {trace['premise']}.")
            sections.append("Show an inviting opening-frame composition for a reader's personal route into this world.")
        else:
            sections.append("Asset target: private chapter hero image for the latest reader chapter.")
            sections.append(f"World title: {title}.")
            if trace.get("scene_title"):
                sections.append(f"Chapter title: {trace['scene_title']}.")
            if trace.get("visual_prompt"):
                sections.append(f"Scene direction: {trace['visual_prompt']}.")
            if trace.get("image_caption"):
                sections.append(f"Scene caption: {trace['image_caption']}.")
            if trace.get("story_beats"):
                sections.append("Story beats: %s." % ", ".join(trace["story_beats"][:4]))
            if trace.get("visual_details"):
                sections.append("Visual details: %s." % ", ".join(trace["visual_details"][:6]))
            if trace.get("image_motif"):
                sections.append(f"Image motif: {trace['image_motif']}.")
            if trace.get("palette_hint"):
                sections.append(f"Palette hint: {trace['palette_hint']}.")
        if trace.get("style_prompt"):
            sections.append(f"Pack illustration direction: {trace['style_prompt']}.")
        if trace.get("palette_tags"):
            sections.append("Palette tags: %s." % ", ".join(trace["palette_tags"]))
        if trace.get("character_anchor_notes"):
            sections.append("Character anchor notes: %s." % " | ".join(trace["character_anchor_notes"]))
        if trace.get("negative_prompt"):
            sections.append(f"Avoid: {trace['negative_prompt']}.")
        sections.append("Rendered as polished commercial story art with coherent anatomy, lighting, and composition.")
        return " ".join(section.strip() for section in sections if str(section).strip())


class IllustrationService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        analytics_service: Optional["AnalyticsService"] = None,
        async_job_service: Optional["AsyncJobService"] = None,
        storage_client: Optional[ObjectStorageClient] = None,
        openai_client: Optional[ImageClient] = None,
        prompt_builder: Optional[IllustrationPromptBuilder] = None,
        job_scheduler: Optional[Callable[[Callable[..., Any], str], None]] = None,
        prompt_version: str = ILLUSTRATION_PROMPT_VERSION,
        generation_enabled_override: Optional[bool] = None,
    ) -> None:
        config = IllustrationConfig.from_env()
        self.repository = repository
        self.analytics = analytics_service
        self.async_jobs = async_job_service
        self.storage = storage_client or VercelBlobStorage.from_config(config)
        self.image_client = openai_client or OpenAIImageClient(
            api_key=config.openai_api_key,
            model=config.image_model,
        )
        self.prompt_builder = prompt_builder or IllustrationPromptBuilder()
        self.job_scheduler = job_scheduler
        self.prompt_version = prompt_version
        self.image_model = config.image_model
        self.illustrations_env_enabled = bool(config.illustrations_enabled)
        self.generation_enabled_override = generation_enabled_override
        self.generation_enabled = (
            bool(generation_enabled_override)
            if generation_enabled_override is not None
            else self.illustrations_env_enabled
        )

    @property
    def delivery_enabled(self) -> bool:
        return bool(getattr(self.storage, "enabled", True))

    @property
    def enabled(self) -> bool:
        image_enabled = bool(getattr(self.image_client, "enabled", True))
        return self.generation_enabled and self.delivery_enabled and image_enabled and self.async_jobs is not None

    def _latest_succeeded_asset(
        self,
        *,
        asset_kind: str,
        owner_scope: str,
        owner_id: str,
        chapter_index: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        items = self.repository.list_generated_media_assets(
            asset_kind=asset_kind,
            owner_scope=owner_scope,
            owner_id=owner_id,
            generation_status="succeeded",
            limit=100 if chapter_index is not None else 1,
        )
        if chapter_index is None:
            return items[0] if items else None
        resolved_index = int(chapter_index or 0)
        for item in items:
            if int(item.get("chapter_index") or 0) == resolved_index:
                return item
        return None

    def _asset_url(self, asset: Optional[Dict[str, Any]]) -> str:
        if not asset:
            return ""
        if str(asset.get("visibility") or "") == "public":
            return self._public_asset_url(asset)
        return self._private_asset_url(asset)

    def _find_asset_job(self, asset_id: str) -> Optional[Dict[str, Any]]:
        if self.async_jobs is None:
            return None
        for job in self.async_jobs.list_jobs(job_type=ILLUSTRATION_JOB_TYPE, limit=200):
            payload = dict(job.get("payload") or {})
            if str(payload.get("asset_id") or "").strip() == str(asset_id or "").strip():
                return job
        return None

    def _complete_asset_generation(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = str(asset.get("asset_id") or "").strip()
        if not asset_id:
            return dict(asset or {})
        current = self.repository.get_generated_media_asset(asset_id)
        if str(current.get("generation_status") or "") == "succeeded":
            return current
        job = self._find_asset_job(asset_id)
        if job is not None and str(job.get("status") or "") in {"queued", "failed"}:
            self.async_jobs.run_job(str(job.get("job_id") or ""))
        return self.repository.get_generated_media_asset(asset_id)

    def _manual_request_result(
        self,
        *,
        asset_kind: str,
        status: str,
        asset: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_asset = dict(asset or {})
        return {
            "asset_kind": asset_kind,
            "status": status,
            "asset_id": str(resolved_asset.get("asset_id") or "") or None,
            "generation_status": str(resolved_asset.get("generation_status") or "") or None,
            "url": self._asset_url(resolved_asset),
            "reason": str(reason or resolved_asset.get("error") or "") or None,
        }

    def _fingerprint(self, trace: Dict[str, Any]) -> str:
        payload = {
            "prompt_version": self.prompt_version,
            "trace": trace,
        }
        return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()

    def _storage_key(self, *, asset_id: str, asset_kind: str, owner_id: str, chapter_index: Optional[int]) -> str:
        if asset_kind == WORLD_COVER_KIND:
            return f"world_versions/{quote(owner_id, safe='@._-')}/covers/{asset_id}.png"
        if asset_kind == SESSION_COVER_KIND:
            return f"sessions/{quote(owner_id, safe='._-')}/cover/{asset_id}.png"
        chapter_segment = int(chapter_index or 0)
        return f"sessions/{quote(owner_id, safe='._-')}/chapters/{chapter_segment}/{asset_id}.png"

    def _asset_visibility(self, asset_kind: str) -> str:
        return "public" if asset_kind == WORLD_COVER_KIND else "private"

    def _storage_bucket_name(self, asset_kind: str) -> str:
        return VERCEL_WORLD_STORE_NAME if asset_kind == WORLD_COVER_KIND else VERCEL_READER_STORE_NAME

    def _trace_size(self, trace: Dict[str, Any], asset_kind: str) -> str:
        size = str(trace.get("size") or ASSET_KIND_SIZES.get(asset_kind) or "1024x1024").strip()
        return size or "1024x1024"

    def _track(self, event_name: str, *, asset: Dict[str, Any], payload_json: Optional[Dict[str, Any]] = None) -> None:
        if self.analytics is None:
            return
        self.analytics.track(
            event_name,
            reader_id=asset.get("reader_id"),
            session_id=asset.get("session_id"),
            world_id=asset.get("world_id"),
            world_version_id=asset.get("world_version_id"),
            chapter_index=asset.get("chapter_index"),
            payload_json={
                "asset_id": asset.get("asset_id"),
                "asset_kind": asset.get("asset_kind"),
                "owner_scope": asset.get("owner_scope"),
                "owner_id": asset.get("owner_id"),
                "visibility": asset.get("visibility"),
                "generation_status": asset.get("generation_status"),
                **dict(payload_json or {}),
            },
        )

    def _existing_asset_for_trace(
        self,
        *,
        asset_kind: str,
        owner_scope: str,
        owner_id: str,
        source_fingerprint: str,
    ) -> Optional[Dict[str, Any]]:
        for status in ("succeeded", "queued", "running"):
            items = self.repository.list_generated_media_assets(
                asset_kind=asset_kind,
                owner_scope=owner_scope,
                owner_id=owner_id,
                source_fingerprint=source_fingerprint,
                generation_status=status,
                limit=1,
            )
            if items:
                return items[0]
        return None

    def _enqueue_trace(
        self,
        *,
        asset_kind: str,
        owner_scope: str,
        owner_id: str,
        world_id: Optional[str],
        world_version_id: Optional[str],
        session_id: Optional[str],
        chapter_index: Optional[int],
        reader_id: Optional[str],
        trace: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        fingerprint = self._fingerprint(trace)
        existing = self._existing_asset_for_trace(
            asset_kind=asset_kind,
            owner_scope=owner_scope,
            owner_id=owner_id,
            source_fingerprint=fingerprint,
        )
        if existing is not None:
            return existing
        asset_id = "media_%s" % hashlib.sha256(
            f"{asset_kind}:{owner_scope}:{owner_id}:{fingerprint}".encode("utf-8")
        ).hexdigest()[:16]
        size = self._trace_size(trace, asset_kind)
        width, height = _parse_size(size)
        asset = self.repository.save_generated_media_asset(
            {
                "asset_id": asset_id,
                "asset_kind": asset_kind,
                "owner_scope": owner_scope,
                "owner_id": owner_id,
                "world_id": world_id,
                "world_version_id": world_version_id,
                "session_id": session_id,
                "chapter_index": chapter_index,
                "reader_id": reader_id,
                "storage_bucket": self._storage_bucket_name(asset_kind),
                "storage_key": self._storage_key(
                    asset_id=asset_id,
                    asset_kind=asset_kind,
                    owner_id=owner_id,
                    chapter_index=chapter_index,
                ),
                "mime_type": "image/png",
                "width": width,
                "height": height,
                "visibility": self._asset_visibility(asset_kind),
                "generation_status": "queued",
                "model_name": self.image_model,
                "prompt_version": self.prompt_version,
                "source_fingerprint": fingerprint,
                "prompt_trace_json": trace,
                "error": None,
            }
        )
        self._track("illustration_generation_enqueued", asset=asset)
        self.async_jobs.enqueue_job(
            job_type=ILLUSTRATION_JOB_TYPE,
            payload={
                "asset_id": asset["asset_id"],
                "asset_kind": asset_kind,
                "world_id": world_id,
                "world_version_id": world_version_id,
                "session_id": session_id,
                "reader_id": reader_id,
                "chapter_index": chapter_index,
            },
            requested_by="illustration_service",
            account_id=reader_id,
            schedule=self.job_scheduler,
        )
        return asset

    def ensure_world_cover(self, *, world_version_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        world_version = self.repository.get_world_version(world_version_id)
        trace = self.prompt_builder.build_world_cover_trace(world_version=world_version)
        return self._enqueue_trace(
            asset_kind=WORLD_COVER_KIND,
            owner_scope="world_version",
            owner_id=world_version_id,
            world_id=world_version.world_id,
            world_version_id=world_version_id,
            session_id=None,
            chapter_index=None,
            reader_id=None,
            trace=trace,
        )

    def ensure_session_cover(
        self,
        *,
        session_id: str,
        reader_id: Optional[str],
        world_version_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        world_version = self.repository.get_world_version(world_version_id)
        trace = self.prompt_builder.build_session_cover_trace(
            session_id=session_id,
            reader_id=reader_id,
            world_version=world_version,
        )
        return self._enqueue_trace(
            asset_kind=SESSION_COVER_KIND,
            owner_scope="session",
            owner_id=session_id,
            world_id=world_version.world_id,
            world_version_id=world_version_id,
            session_id=session_id,
            chapter_index=None,
            reader_id=reader_id,
            trace=trace,
        )

    def ensure_chapter_hero(
        self,
        *,
        session_id: str,
        reader_id: Optional[str],
        world_version_id: str,
        chapter_index: int,
        rendered_scene: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        world_version = self.repository.get_world_version(world_version_id)
        trace = self.prompt_builder.build_chapter_hero_trace(
            session_id=session_id,
            reader_id=reader_id,
            chapter_index=chapter_index,
            world_version=world_version,
            rendered_scene=rendered_scene,
        )
        return self._enqueue_trace(
            asset_kind=CHAPTER_HERO_KIND,
            owner_scope="session",
            owner_id=session_id,
            world_id=world_version.world_id,
            world_version_id=world_version_id,
            session_id=session_id,
            chapter_index=chapter_index,
            reader_id=reader_id,
            trace=trace,
        )

    def request_world_cover(self, world_version_id: str) -> Dict[str, Any]:
        existing = self._latest_succeeded_asset(
            asset_kind=WORLD_COVER_KIND,
            owner_scope="world_version",
            owner_id=world_version_id,
        )
        if existing is not None:
            return self._manual_request_result(
                asset_kind=WORLD_COVER_KIND,
                status="reused",
                asset=existing,
            )
        asset = self.ensure_world_cover(world_version_id=world_version_id)
        if asset is None:
            return self._manual_request_result(
                asset_kind=WORLD_COVER_KIND,
                status="failed",
                reason="illustration_generation_disabled",
            )
        completed = self._complete_asset_generation(asset)
        generation_status = str(completed.get("generation_status") or "")
        if generation_status == "succeeded":
            return self._manual_request_result(
                asset_kind=WORLD_COVER_KIND,
                status="generated",
                asset=completed,
            )
        if generation_status == "failed":
            return self._manual_request_result(
                asset_kind=WORLD_COVER_KIND,
                status="failed",
                asset=completed,
            )
        return self._manual_request_result(
            asset_kind=WORLD_COVER_KIND,
            status="failed",
            asset=completed,
            reason=f"illustration_generation_incomplete:{generation_status or 'unknown'}",
        )

    def request_session_illustrations(
        self,
        session_id: str,
        *,
        include_session_cover: bool = True,
        include_latest_chapter_hero: bool = True,
    ) -> Dict[str, Any]:
        session_record = self.repository.get_session(session_id)
        metadata = dict(session_record.metadata or {})
        world_version_id = str(metadata.get("world_version_id") or "").strip()
        reader_id = str(metadata.get("reader_id") or "") or str((session_record.player_profile or {}).get("reader_id") or "") or None
        latest_step = self.repository.get_latest_step(session_id)
        results: list[Dict[str, Any]] = []

        if include_session_cover:
            existing_cover = self._latest_succeeded_asset(
                asset_kind=SESSION_COVER_KIND,
                owner_scope="session",
                owner_id=session_id,
            )
            if existing_cover is not None:
                results.append(
                    self._manual_request_result(
                        asset_kind=SESSION_COVER_KIND,
                        status="reused",
                        asset=existing_cover,
                    )
                )
            else:
                asset = self.ensure_session_cover(
                    session_id=session_id,
                    reader_id=reader_id,
                    world_version_id=world_version_id,
                )
                if asset is None:
                    results.append(
                        self._manual_request_result(
                            asset_kind=SESSION_COVER_KIND,
                            status="failed",
                            reason="illustration_generation_disabled",
                        )
                    )
                else:
                    completed = self._complete_asset_generation(asset)
                    generation_status = str(completed.get("generation_status") or "")
                    results.append(
                        self._manual_request_result(
                            asset_kind=SESSION_COVER_KIND,
                            status="generated" if generation_status == "succeeded" else "failed",
                            asset=completed,
                            reason=None if generation_status in {"", "succeeded", "failed"} else f"illustration_generation_incomplete:{generation_status}",
                        )
                    )

        if include_latest_chapter_hero:
            if latest_step is None:
                results.append(
                    self._manual_request_result(
                        asset_kind=CHAPTER_HERO_KIND,
                        status="skipped",
                        reason="latest_step_missing",
                    )
                )
            elif latest_step.rendered_scene is None:
                results.append(
                    self._manual_request_result(
                        asset_kind=CHAPTER_HERO_KIND,
                        status="skipped",
                        reason="latest_step_rendered_scene_missing",
                    )
                )
            else:
                chapter_index = int(latest_step.step_index)
                existing_hero = self._latest_succeeded_asset(
                    asset_kind=CHAPTER_HERO_KIND,
                    owner_scope="session",
                    owner_id=session_id,
                    chapter_index=chapter_index,
                )
                if existing_hero is not None:
                    results.append(
                        self._manual_request_result(
                            asset_kind=CHAPTER_HERO_KIND,
                            status="reused",
                            asset=existing_hero,
                        )
                    )
                else:
                    asset = self.ensure_chapter_hero(
                        session_id=session_id,
                        reader_id=reader_id,
                        world_version_id=world_version_id,
                        chapter_index=chapter_index,
                        rendered_scene=latest_step.rendered_scene.to_dict(),
                    )
                    if asset is None:
                        results.append(
                            self._manual_request_result(
                                asset_kind=CHAPTER_HERO_KIND,
                                status="failed",
                                reason="illustration_generation_disabled",
                            )
                        )
                    else:
                        completed = self._complete_asset_generation(asset)
                        generation_status = str(completed.get("generation_status") or "")
                        results.append(
                            self._manual_request_result(
                                asset_kind=CHAPTER_HERO_KIND,
                                status="generated" if generation_status == "succeeded" else "failed",
                                asset=completed,
                                reason=None if generation_status in {"", "succeeded", "failed"} else f"illustration_generation_incomplete:{generation_status}",
                            )
                        )

        return {
            "session_id": session_id,
            "world_version_id": world_version_id,
            "reader_id": reader_id,
            "latest_step_index": int(latest_step.step_index) if latest_step is not None else None,
            "results": results,
        }

    def run_generation_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        asset_id = str(payload.get("asset_id") or "").strip()
        asset = self.repository.get_generated_media_asset(asset_id)
        trace = dict(asset.get("prompt_trace_json") or {})
        prompt = str(trace.get("prompt") or "").strip()
        size = self._trace_size(trace, str(asset.get("asset_kind") or ""))
        if not prompt:
            error = "illustration_prompt_missing"
            failed_asset = self.repository.save_generated_media_asset(
                {
                    **asset,
                    "generation_status": "failed",
                    "error": error,
                }
            )
            self._track("illustration_generation_failed", asset=failed_asset, payload_json={"error": error})
            return {"asset_id": asset_id, "error": error, "_job_status_override": "failed"}
        try:
            image_bytes, mime_type = self.image_client.generate_image_bytes(prompt=prompt, size=size)
            storage_key = str(asset.get("storage_key") or self._storage_key(
                asset_id=asset_id,
                asset_kind=str(asset.get("asset_kind") or ""),
                owner_id=str(asset.get("owner_id") or ""),
                chapter_index=asset.get("chapter_index"),
            ))
            canonical_storage_key = str(self.storage.put_bytes(
                storage_key=storage_key,
                content=image_bytes,
                content_type=mime_type,
            ) or storage_key)
            succeeded_asset = self.repository.save_generated_media_asset(
                {
                    **asset,
                    "storage_bucket": asset.get("storage_bucket") or self._storage_bucket_name(str(asset.get("asset_kind") or "")),
                    "storage_key": canonical_storage_key,
                    "mime_type": mime_type,
                    "generation_status": "succeeded",
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "error": None,
                }
            )
            self._track(
                "illustration_generation_succeeded",
                asset=succeeded_asset,
                payload_json={"storage_key": canonical_storage_key},
            )
            return {
                "asset_id": asset_id,
                "storage_key": canonical_storage_key,
                "mime_type": mime_type,
                "visibility": succeeded_asset.get("visibility"),
                "artifacts": {"asset_id": asset_id},
            }
        except Exception as exc:  # pragma: no cover - exercised via API/service failure tests
            failed_asset = self.repository.save_generated_media_asset(
                {
                    **asset,
                    "generation_status": "failed",
                    "error": str(exc),
                }
            )
            self._track(
                "illustration_generation_failed",
                asset=failed_asset,
                payload_json={"error": str(exc)},
            )
            return {
                "asset_id": asset_id,
                "error": str(exc),
                "_job_status_override": "failed",
            }

    def _private_asset_url(self, asset: Optional[Dict[str, Any]]) -> str:
        if not asset or str(asset.get("generation_status") or "") != "succeeded":
            return ""
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(getattr(self.storage, "signed_url_ttl_seconds", 900))
        )
        return self.storage.build_signed_url(asset_id=str(asset.get("asset_id") or ""), expires_at=expires_at)

    def _public_asset_url(self, asset: Optional[Dict[str, Any]]) -> str:
        if not asset or str(asset.get("generation_status") or "") != "succeeded":
            return ""
        storage_key = str(asset.get("storage_key") or "").strip()
        if not storage_key:
            return ""
        if storage_key.startswith("http://") or storage_key.startswith("https://"):
            return storage_key
        return self.storage.build_public_url(storage_key=storage_key)

    def world_cover_url(self, *, world_version_id: str) -> str:
        if not self.delivery_enabled:
            return ""
        asset = self.repository.latest_generated_media_asset(
            asset_kind=WORLD_COVER_KIND,
            owner_scope="world_version",
            owner_id=world_version_id,
            generation_status="succeeded",
            default=None,
        )
        return self._public_asset_url(asset)

    def session_cover_url(self, *, session_id: str) -> str:
        if not self.delivery_enabled:
            return ""
        asset = self.repository.latest_generated_media_asset(
            asset_kind=SESSION_COVER_KIND,
            owner_scope="session",
            owner_id=session_id,
            generation_status="succeeded",
            default=None,
        )
        return self._private_asset_url(asset)

    def latest_chapter_hero_url(self, *, session_id: str) -> str:
        if not self.delivery_enabled:
            return ""
        asset = self.repository.latest_generated_media_asset(
            asset_kind=CHAPTER_HERO_KIND,
            owner_scope="session",
            owner_id=session_id,
            generation_status="succeeded",
            default=None,
        )
        return self._private_asset_url(asset)

    def private_asset_response(self, *, asset_id: str, expires: int, signature: str) -> tuple[bytes, str]:
        if not self.storage.validate_signed_url(asset_id=asset_id, expires=expires, signature=signature):
            raise PermissionError("media_asset_signature_invalid")
        asset = self.repository.get_generated_media_asset(asset_id)
        if str(asset.get("visibility") or "") != "private":
            raise PermissionError("media_asset_visibility_invalid")
        if str(asset.get("generation_status") or "") != "succeeded":
            raise KeyError("generated_media_asset_not_ready:%s" % asset_id)
        storage_key = str(asset.get("storage_key") or "").strip()
        if not storage_key:
            raise KeyError("generated_media_asset_missing_storage_key:%s" % asset_id)
        image_bytes, mime_type = self.storage.get_bytes(storage_key=storage_key)
        return image_bytes, str(asset.get("mime_type") or mime_type or _guess_mime_type(image_bytes))
