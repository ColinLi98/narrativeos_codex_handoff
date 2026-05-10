from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..benchmark.runner import run_benchmark
from ..content_quality_contracts import (
    content_quality_window_metrics,
    diagnostic_issue_codes_for_chapter_payload,
    ensure_chapter_task_quality_contract,
    ensure_scene_quality_contract,
    issue_asset_target,
    resolve_content_quality_contract,
)
from ..content_quality_strategy_execution import execute_strategy_bundle_protocol
from ..content_quality_strategy_bundles import build_strategy_bundle
from ..core.linter import lint_chapter_draft
from ..eval.learned_inference import LearnedInferenceService, default_learned_artifact_dir
from ..eval.learned_shadow import LearnedShadowService
from ..eval.reporting import aggregate_reports
from ..eval.service import evaluate_chapter
from ..eval.taxonomy import ISSUE_TAXONOMY
from ..longform import (
    configure_interactive_longform_runtime,
    configure_longform_runtime,
    evaluate_longform_gate,
    apply_steering_directive,
    record_replan_debt,
)
from ..models import NarrativeState
from ..persistence.repositories import SQLAlchemyPlatformRepository
from ..pipeline import plan_next_turn
from ..providers import StaticCandidateProvider
from ..rendering import TemplateRenderer
from .billing import BillingService
from .longform_capability import (
    band_minimums,
    build_longform_capability_payload,
    longform_structure_counts,
    load_longform_capability_profiles,
    quick_brief_max_target_chapters,
    sync_longform_capability_metadata,
    target_band_for_chapters,
)
from .observability import ObservabilityService
from .provider_routing import ProviderRoutingService
from .training_signal import TrainingSignalService
from ..worldpacks.models import WorldPack, WorldVersion
from ..worldpacks.registry import FileSystemWorldRegistry
from ..worldpacks.validator import validate_worldpack_payload

LONGFORM_CAPABILITY_BAND_ORDER = ("100", "250", "500", "1000")
DEFAULT_LONGFORM_CAPABILITY_PROFILES = {
    "quick_brief_max_target_chapters": 100,
    "structured_longform_bands": ["250", "500", "1000"],
    "bands": {
        "100": {"min_characters": 8, "min_scene_blueprints": 8, "min_locations": 6},
        "250": {"min_characters": 12, "min_scene_blueprints": 12, "min_locations": 8},
        "500": {"min_characters": 16, "min_scene_blueprints": 16, "min_locations": 12},
        "1000": {"min_characters": 24, "min_scene_blueprints": 24, "min_locations": 16},
    },
}
LONGFORM_EXTRA_NAME_COMPONENTS = {
    "jade_court": {
        "surnames": ["沈", "顾", "谢", "韩", "柳", "裴", "周", "季", "宁", "苏", "陆", "程"],
        "givens": ["明漪", "无尘", "持正", "观澜", "知微", "照雪", "怀瑾", "停云", "回霜", "闻秋", "静姝", "见山"],
    },
    "urban_mystery": {
        "surnames": ["林", "周", "许", "宋", "陈", "顾", "沈", "程", "苏", "袁", "裴", "方"],
        "givens": ["知夏", "予安", "闻笙", "照晚", "景澄", "遥川", "宁秋", "亦岚", "清禾", "向晚", "以棠", "见鹿"],
    },
    "xianxia": {
        "surnames": ["顾", "谢", "韩", "柳", "白", "商", "宁", "裴", "季", "岑", "秦", "温"],
        "givens": ["明漪", "无尘", "持正", "观澜", "栖", "寄寒", "照影", "知岸", "孤云", "夜舟", "停雪", "望舒"],
    },
    "synthetic": {
        "surnames": ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸", "子", "丑"],
        "givens": ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"],
    },
}
LONGFORM_EXTRA_LOCATION_POOLS = {
    "jade_court": ["偏厅", "暖阁", "祠堂前庭", "侧门回廊", "马车前", "花窗下", "池畔", "佛堂", "后院石径", "雨廊"],
    "urban_mystery": ["旧仓库", "沿江堤岸", "出租屋楼道", "停车场边角", "地下通道", "医院走廊", "夜班食堂", "地铁换乘口", "江边栏杆", "旧商场顶层"],
    "xianxia": ["藏经阁", "洗剑池", "断桥", "山腰栈道", "药庐", "后山碑林", "渡口舟棚", "禁地石门", "云海台", "观星崖", "寒潭边", "钟楼"],
    "synthetic": ["门前", "石桌旁", "桥下", "楼梯口", "长凳边", "屋檐下", "院墙旁", "空廊尽头"],
}
LONGFORM_EXTRA_ROLE_CYCLE = [
    "supporting",
    "mentor",
    "rival",
    "observer",
    "guardian",
    "outsider",
    "scholar",
    "messenger",
]
LONGFORM_EXTRA_WOUND_POOL = [
    "总在残局里替别人收尾，却没人替自己留退路",
    "被更大的秩序拿走过一次最重要的选择",
    "曾经说迟了一句真话，从此总怕再晚一步",
    "习惯先看全局，结果总把自己留在代价最后",
]
LONGFORM_EXTRA_PUBLIC_SELF_POOL = [
    "我先稳住局势",
    "我只是来把事情看清",
    "我只讲分寸，不讲私心",
    "先把眼前这一层压住再说",
]
LONGFORM_EXTRA_SHADOW_DESIRE_POOL = [
    "有人也替我考虑一次",
    "被平等地选一次",
    "能在不失去彼此的前提下把真话说完",
    "不再总在局势外面看着别人做决定",
]
LONGFORM_EXTRA_VOW_POOL = [
    "不再把最重的一句拖到下一次再说",
    "先把真相看清，再决定站在哪一边",
    "这一次不替任何人把后果遮回去",
    "如果代价一定要落下，也要先认清它落在谁身上",
]
LONGFORM_SCENE_TEMPLATE_CATALOG = [
    ("threshold_watch", "setup", ["入场观察", "气压收紧", "旧事回响", "留下钩子"]),
    ("public_pressure", "trust_test", ["旁人施压", "关系试探", "局面转紧", "收尾余波"]),
    ("private_reckoning", "discovery", ["私下对峙", "旧话翻出", "代价显形", "留下未尽之意"]),
    ("misread_crossfire", "reversal", ["误会升级", "嘴硬回避", "裂口扩大", "各退半步"]),
    ("oath_echo", "temptation", ["旧誓回响", "心意动摇", "后果逼近", "强行压下"]),
    ("debt_collection", "trust_test", ["旧债追上来", "关系重新算账", "局势翻转", "留下一层新亏欠"]),
    ("false_peace", "setup", ["表面稳住", "暗流未散", "细节露口", "下一步更难回避"]),
    ("choice_corridor", "discovery", ["逼近选择", "各执一词", "无人先退", "后续分岔"]),
    ("world_pressure", "setup", ["外部异变", "规则压下", "人物应对", "留下更大问题"]),
    ("alliance_test", "trust_test", ["短暂联手", "分歧暴露", "关系变调", "留下隐患"]),
    ("memory_return", "discovery", ["旧记忆回返", "真相补全", "情绪反噬", "重写关系站位"]),
    ("trial_window", "temptation", ["试探底线", "代价浮起", "有人动摇", "悬而未决"]),
    ("witness_break", "reversal", ["旁证出现", "叙事翻面", "旧判断失效", "连锁后果启动"]),
    ("aftershock_room", "reversal", ["余波扩散", "沉默堆高", "关系错位", "逼出后续动作"]),
    ("pursuit_edge", "setup", ["追索线索", "边缘逼近", "风险抬升", "留下更重悬念"]),
    ("faction_barter", "trust_test", ["势力交换", "条件抬价", "人物拉扯", "留下账目"]),
    ("threshold_gate", "setup", ["来到门槛前", "旧规则再现", "退路收窄", "必须表态"]),
    ("confession_pivot", "discovery", ["一句真话落地", "关系偏转", "代价重新分配", "下一章继续追上"]),
    ("fracture_walk", "reversal", ["并肩不再同路", "旧默契断裂", "余波扩大", "后续更难和解"]),
    ("archive_dig", "discovery", ["翻旧档案", "补齐因果", "多出新的空白", "把人推回主线"]),
    ("return_to_scene", "setup", ["重回旧地", "细节复现", "关系失衡", "留下更大问号"]),
    ("cliff_ledger", "temptation", ["代价盘点", "选择逼近", "无人能免", "把结尾钩子压实"]),
    ("signal_transfer", "setup", ["消息转手", "误差扩大", "立场偏移", "下一幕更危险"]),
    ("night_bridge", "discovery", ["深夜重逢", "误会变形", "心意露口", "留下回身索账"]),
]
INTERACTIVE_WINDOW_ISSUE_CODES = ("Q03", "Q04", "Q05", "Q09")


def _percentile(values: List[float], quantile: float) -> float:
    cleaned = sorted(float(item) for item in values if item is not None)
    if not cleaned:
        return 0.0
    if len(cleaned) == 1:
        return round(cleaned[0], 3)
    index = max(0, min(len(cleaned) - 1, int(round((len(cleaned) - 1) * float(quantile)))))
    return round(cleaned[index], 3)


class AuthoringService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        registry: Optional[FileSystemWorldRegistry] = None,
        training_signal_service: Optional[TrainingSignalService] = None,
        learned_inference_service: Optional[LearnedInferenceService] = None,
        learned_shadow_service: Optional[LearnedShadowService] = None,
        billing_service: Optional[BillingService] = None,
        provider_routing_service: Optional[ProviderRoutingService] = None,
        observability_service: Optional[ObservabilityService] = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or FileSystemWorldRegistry()
        self.base_dir = Path(__file__).resolve().parents[3]
        self.training_signal = training_signal_service or TrainingSignalService(repository)
        self.billing = billing_service or BillingService(repository)
        self.learned_inference = learned_inference_service or LearnedInferenceService(default_learned_artifact_dir(self.base_dir))
        self.learned_shadow = learned_shadow_service or LearnedShadowService(
            default_learned_artifact_dir(self.base_dir),
            learned_inference_service=self.learned_inference,
        )
        self.provider_routing = provider_routing_service
        self.observability = observability_service
        self.promise_editor_states = [
            "watch",
            "defer",
            "plan_payoff",
            "resolved_intentional",
            "escalate",
        ]
        self.continuity_override_states = [
            "watch",
            "intentional",
            "accepted_tradeoff",
            "needs_rewrite",
            "escalate",
        ]
        self._longform_capability_profiles_cache: Optional[Dict[str, Any]] = None

    def _longform_capability_profiles(self) -> Dict[str, Any]:
        if self._longform_capability_profiles_cache is None:
            self._longform_capability_profiles_cache = load_longform_capability_profiles(self.base_dir)
        return dict(self._longform_capability_profiles_cache)

    def _target_band_for_chapters(self, target_total_chapters: int) -> str:
        return target_band_for_chapters(target_total_chapters)

    def _band_rank(self, band: Optional[str]) -> int:
        normalized = str(band or "").strip()
        if normalized not in LONGFORM_CAPABILITY_BAND_ORDER:
            return -1
        return LONGFORM_CAPABILITY_BAND_ORDER.index(normalized)

    def _band_minimums(self, band: str) -> Dict[str, int]:
        return band_minimums(self._longform_capability_profiles(), band)

    def _quick_brief_max_target_chapters(self) -> int:
        return quick_brief_max_target_chapters(self._longform_capability_profiles())

    def _longform_entry_mode(self, metadata: Dict[str, Any]) -> str:
        stored = str(metadata.get("entry_mode") or "").strip()
        if stored:
            return stored
        if metadata.get("generated_from_brief"):
            return "quick_brief"
        return "structured_longform"

    def _longform_structure_counts(self, worldpack_payload: Dict[str, Any]) -> Dict[str, int]:
        return longform_structure_counts(worldpack_payload)

    def _supported_target_band(self, *, counts: Dict[str, int], entry_mode: str) -> Optional[str]:
        highest: Optional[str] = None
        for band in LONGFORM_CAPABILITY_BAND_ORDER:
            minimums = self._band_minimums(band)
            if (
                counts["character_count"] >= minimums["min_characters"]
                and counts["scene_blueprint_count"] >= minimums["min_scene_blueprints"]
                and counts["location_count"] >= minimums["min_locations"]
            ):
                highest = band
        if highest is None:
            return None
        if entry_mode == "quick_brief" and self._band_rank(highest) > self._band_rank("100"):
            return "100"
        return highest

    def _extract_open_promises_from_issue(self, issue: Dict[str, Any]) -> Optional[int]:
        for evidence in list(issue.get("evidence") or []):
            text = str(evidence or "")
            if text.startswith("open_promises="):
                try:
                    return int(text.split("=", 1)[1])
                except ValueError:
                    return None
        return None

    def _latest_longform_runway_guard(self, version: WorldVersion) -> Optional[Dict[str, Any]]:
        brief = dict(((version.worldpack_json or {}).get("metadata") or {}).get("author_brief") or {})
        target_total_chapters = max(1, int(brief.get("target_total_chapters") or ((version.worldpack_json or {}).get("series_plan") or {}).get("total_chapter_target") or 100))
        if target_total_chapters < 100:
            return None
        works = self.repository.list_author_works(account_id=version.author_id, world_version_id=version.world_version_id, limit=20)
        if not works:
            return None
        active_work = next((item for item in works if item.get("is_active_line")), None) or works[0]
        revisions = self.repository.list_author_work_revisions(work_id=active_work["work_id"], limit=20)
        blocked_revision = next((item for item in revisions if item.get("revision_type") == "quality_guard_blocked"), None)
        if not blocked_revision:
            return None
        snapshot = dict(blocked_revision.get("snapshot_json") or {})
        quality_gate = dict(snapshot.get("quality_gate") or {})
        issues = [dict(item or {}) for item in list(quality_gate.get("issues") or [])]
        issue_codes = {str(item.get("issue_code") or "").strip() for item in issues if str(item.get("issue_code") or "").strip()}
        if "Q09" not in issue_codes:
            return None
        chapter_index = int(snapshot.get("chapter_index") or 0)
        if chapter_index <= 0 or chapter_index >= int(target_total_chapters * 0.8):
            return None
        open_promises = None
        for issue in issues:
            open_promises = self._extract_open_promises_from_issue(issue)
            if open_promises is not None:
                break
        if open_promises is None or open_promises > 0:
            return None
        return {
            "key": "longform_structure_exhaustion",
            "severity": "high",
            "message": f"当前长线在第 {chapter_index} 章附近出现续航耗空信号：开放 promises 已归零，继续盲跑更容易触发节奏塌陷。",
            "chapter_index": chapter_index,
            "work_id": active_work.get("work_id"),
            "pacing": dict(quality_gate.get("scores") or {}).get("pacing"),
            "issue_codes": sorted(issue_codes),
            "recommended_actions": [
                "bootstrap_structured_longform",
                "expand_character_and_scene_lattice",
                "rebuild_promise_lattice",
            ],
        }

    def _build_longform_capability_payload(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        version: Optional[WorldVersion] = None,
    ) -> Dict[str, Any]:
        return build_longform_capability_payload(
            base_dir=self.base_dir,
            repository=self.repository,
            worldpack_payload=worldpack_payload,
            version=version,
        )

    def _sync_longform_capability_metadata(self, worldpack_payload: Dict[str, Any], *, version: Optional[WorldVersion] = None) -> Dict[str, Any]:
        return sync_longform_capability_metadata(
            base_dir=self.base_dir,
            repository=self.repository,
            worldpack_payload=worldpack_payload,
            version=version,
        )

    def _apply_longform_asset_enrichment(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        target_band: str,
    ) -> None:
        minimums = self._band_minimums(target_band)
        metadata = self._ensure_metadata(worldpack_payload)
        brief = dict(metadata.get("author_brief") or {})
        preset_id = str(brief.get("genre_preset") or "urban_mystery")
        life_theme = str(
            brief.get("life_theme")
            or ((worldpack_payload.get("series_plan") or {}).get("theme_statement") or "")
            or ((worldpack_payload.get("title") or "长篇故事"))
        )
        existing_characters = [dict(item) for item in list(worldpack_payload.get("characters") or [])]
        worldpack_payload["characters"] = existing_characters + _next_longform_character_blueprints(
            preset_id=preset_id,
            life_theme=life_theme,
            existing_character_ids=[str(item.get("character_id") or "") for item in existing_characters],
            current_count=len(existing_characters),
            target_count=minimums["min_characters"],
        )
        target_scene_count = max(
            minimums["min_scene_blueprints"],
            minimums.get("min_scene_family_count", 0),
            minimums.get("min_distinct_role_pairs", 0),
        )
        character_ids = [str(item.get("character_id") or "") for item in worldpack_payload.get("characters") or [] if str(item.get("character_id") or "").strip()]
        next_scenes = _next_longform_scene_blueprints(
            preset_id=preset_id,
            existing_scenes=list(worldpack_payload.get("scene_blueprints") or []),
            character_ids=character_ids,
            target_count=target_scene_count,
            desired_scene_family_count=minimums.get("min_scene_family_count", 0),
            desired_role_pair_count=minimums.get("min_distinct_role_pairs", 0),
        )
        while True:
            probe_payload = {
                **worldpack_payload,
                "scene_blueprints": next_scenes,
            }
            counts = self._longform_structure_counts(probe_payload)
            if (
                counts["scene_blueprint_count"] >= minimums["min_scene_blueprints"]
                and counts["scene_family_count"] >= minimums.get("min_scene_family_count", 0)
                and counts["distinct_role_pair_count"] >= minimums.get("min_distinct_role_pairs", 0)
            ):
                break
            next_scenes = _next_longform_scene_blueprints(
                preset_id=preset_id,
                existing_scenes=next_scenes,
                character_ids=character_ids,
                target_count=len(next_scenes) + 1,
                desired_scene_family_count=minimums.get("min_scene_family_count", 0),
                desired_role_pair_count=minimums.get("min_distinct_role_pairs", 0),
            )
        worldpack_payload["scene_blueprints"] = next_scenes
        world_bible = dict(worldpack_payload.get("world_bible") or {})
        world_bible["locations"] = _next_longform_locations(
            preset_id=preset_id,
            existing_locations=list(world_bible.get("locations") or []),
            target_count=minimums["min_locations"],
        )
        worldpack_payload["world_bible"] = world_bible
        worldpack_payload["sensory_grounding_policies"] = _build_sensory_policies_for_preset(preset_id, list(world_bible.get("locations") or []))
        _ensure_character_asset_coverage(worldpack_payload, preset_id=preset_id)
        metadata["longform_asset_enrichment"] = {
            "band": target_band,
            "character_count": len(list(worldpack_payload.get("characters") or [])),
            "scene_blueprint_count": len(list(worldpack_payload.get("scene_blueprints") or [])),
            "location_count": len(list((worldpack_payload.get("world_bible") or {}).get("locations") or [])),
        }

    def _should_persist_longform_capability_metadata(self, worldpack_payload: Dict[str, Any]) -> bool:
        metadata = dict(worldpack_payload.get("metadata") or {})
        return bool(
            metadata.get("author_brief")
            or metadata.get("generated_from_brief")
            or metadata.get("entry_mode")
            or metadata.get("requested_target_chapters")
            or metadata.get("claim_safe_band")
            or metadata.get("longform_readiness")
            or metadata.get("longform_workbench_bootstrapped")
        )

    def _normalize_repair_loop_context(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        context = dict(payload or {})
        targeted_chapters = []
        for item in context.get("targeted_chapters", []) or []:
            chapter = dict(item or {})
            chapter_index = int(chapter.get("chapter_index", 0) or 0)
            if chapter_index <= 0:
                continue
            targeted_chapters.append(
                {
                    "chapter_index": chapter_index,
                    "chapter_title": str(chapter.get("chapter_title") or ""),
                }
            )
        return {
            "issue_code": str(context.get("issue_code") or "").strip(),
            "issue_label": str(context.get("issue_label") or "").strip(),
            "asset_type": str(context.get("asset_type") or "").strip(),
            "asset_label": str(context.get("asset_label") or "").strip(),
            "target_label": str(context.get("target_label") or "").strip(),
            "validation_panel": str(context.get("validation_panel") or "").strip(),
            "validation_panel_label": str(context.get("validation_panel_label") or "").strip(),
            "validation_reason": str(context.get("validation_reason") or "").strip(),
            "character_id": str(context.get("character_id") or "").strip(),
            "scene_id": str(context.get("scene_id") or "").strip(),
            "scene_function": str(context.get("scene_function") or "").strip(),
            "chapter_task_id": str(context.get("chapter_task_id") or "").strip(),
            "arc_id": str(context.get("arc_id") or "").strip(),
            "volume_id": str(context.get("volume_id") or "").strip(),
            "chapter_index": int(context.get("chapter_index", 0) or 0) or None,
            "chapter_title": str(context.get("chapter_title") or "").strip(),
            "window_label": str(context.get("window_label") or "").strip(),
            "window_range_start": int(context.get("window_range_start", 0) or 0) or None,
            "window_range_end": int(context.get("window_range_end", 0) or 0) or None,
            "window_breach_kind": str(context.get("window_breach_kind") or "").strip(),
            "baseline_issue_count": int(context.get("baseline_issue_count", 0) or 0),
            "baseline_worst_decision": str(context.get("baseline_worst_decision") or "").strip(),
            "contract_failed_checks": [str(item) for item in context.get("contract_failed_checks", []) if str(item)],
            "targeted_chapters": targeted_chapters,
            "targeted_chapter_indices": (
                [int(item) for item in context.get("targeted_chapter_indices", []) if int(item or 0) > 0]
                or [item["chapter_index"] for item in targeted_chapters]
            ),
        }

    def _normalize_change_context(self, change_context: Optional[Dict[str, Any]], *, default_source: str, default_label: str) -> Dict[str, Any]:
        payload = dict(change_context or {})
        normalized = {
            "source": str(payload.get("source") or default_source),
            "label": str(payload.get("label") or default_label),
        }
        repair_loop_context = self._normalize_repair_loop_context(payload.get("repair_loop_context"))
        if any(repair_loop_context.values()):
            normalized["repair_loop_context"] = repair_loop_context
        return normalized

    def _revision_history(self, worldpack_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return list((worldpack_payload.get("metadata") or {}).get("revision_history", []))

    def _ensure_metadata(self, worldpack_payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(worldpack_payload.get("metadata", {}))
        worldpack_payload["metadata"] = metadata
        return metadata

    def _promise_state_overrides(self, metadata: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        workbench = dict(metadata.get("longform_workbench", {}) or {})
        raw_overrides = dict(workbench.get("promise_state_overrides", {}) or {})
        normalized: Dict[str, Dict[str, Any]] = {}
        for promise_id, payload in raw_overrides.items():
            if not str(promise_id):
                continue
            normalized[str(promise_id)] = dict(payload or {})
        return normalized

    def _set_promise_state_override(
        self,
        metadata: Dict[str, Any],
        *,
        promise_id: str,
        editor_state: str,
        notes: str = "",
        chapter_index: Optional[int] = None,
        chapter_task_id: Optional[str] = None,
        arc_id: Optional[str] = None,
        volume_id: Optional[str] = None,
    ) -> None:
        workbench = dict(metadata.get("longform_workbench", {}) or {})
        overrides = dict(workbench.get("promise_state_overrides", {}) or {})
        state_value = str(editor_state or "").strip()
        note_value = str(notes or "").strip()
        if not state_value and not note_value:
            overrides.pop(promise_id, None)
        else:
            overrides[promise_id] = {
                "editor_state": state_value,
                "notes": note_value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "chapter_index": int(chapter_index) if chapter_index else None,
                "chapter_task_id": chapter_task_id,
                "arc_id": arc_id,
                "volume_id": volume_id,
            }
        workbench["promise_state_overrides"] = overrides
        metadata["longform_workbench"] = workbench

    def _continuity_overrides(self, metadata: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        workbench = dict(metadata.get("longform_workbench", {}) or {})
        raw_overrides = dict(workbench.get("continuity_overrides", {}) or {})
        normalized: Dict[str, Dict[str, Any]] = {}
        for chapter_key, payload in raw_overrides.items():
            if not str(chapter_key):
                continue
            normalized[str(chapter_key)] = dict(payload or {})
        return normalized

    def _set_continuity_override(
        self,
        metadata: Dict[str, Any],
        *,
        chapter_index: int,
        override_state: str,
        notes: str = "",
        issue_scope: Optional[List[str]] = None,
        chapter_task_id: Optional[str] = None,
        arc_id: Optional[str] = None,
        volume_id: Optional[str] = None,
    ) -> None:
        workbench = dict(metadata.get("longform_workbench", {}) or {})
        overrides = dict(workbench.get("continuity_overrides", {}) or {})
        chapter_key = str(int(chapter_index))
        state_value = str(override_state or "").strip()
        note_value = str(notes or "").strip()
        scope_values = [str(item).strip() for item in (issue_scope or []) if str(item).strip()]
        if not state_value and not note_value and not scope_values:
            overrides.pop(chapter_key, None)
        else:
            overrides[chapter_key] = {
                "override_state": state_value,
                "notes": note_value,
                "issue_scope": scope_values,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "chapter_task_id": chapter_task_id,
                "arc_id": arc_id,
                "volume_id": volume_id,
            }
        workbench["continuity_overrides"] = overrides
        metadata["longform_workbench"] = workbench

    def _snapshot_summary(self, snapshot: Dict[str, Any]) -> str:
        characters = len(snapshot.get("characters", []))
        scenes = len(snapshot.get("scene_blueprints", []))
        genres = "/".join((snapshot.get("manifest") or {}).get("genres", []))
        return f"{snapshot.get('title', snapshot.get('world_id', '-'))} · {genres or '-'} · 角色 {characters} · 场景 {scenes}"

    def _diff_sections(self, previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        sections = [
            "manifest",
            "world_bible",
            "characters",
            "scene_blueprints",
            "voice_profiles",
            "response_cadence_profiles",
            "emotion_action_policies",
            "sensory_grounding_policies",
            "scene_realization_contracts",
        ]
        changed_sections = [section for section in sections if previous.get(section) != current.get(section)]

        character_changes = []
        previous_characters = {item.get("character_id"): item for item in previous.get("characters", [])}
        current_characters = {item.get("character_id"): item for item in current.get("characters", [])}
        for character_id in sorted(set(previous_characters) | set(current_characters)):
            before = previous_characters.get(character_id)
            after = current_characters.get(character_id)
            if before != after:
                changed_fields = []
                if (before or {}).get("display_name") != (after or {}).get("display_name"):
                    changed_fields.append("display_name")
                if (before or {}).get("role") != (after or {}).get("role"):
                    changed_fields.append("role")
                if ((before or {}).get("destiny_contract") or {}).get("life_theme") != ((after or {}).get("destiny_contract") or {}).get("life_theme"):
                    changed_fields.append("life_theme")
                if ((before or {}).get("wound_profile") or {}).get("core_wound") != ((after or {}).get("wound_profile") or {}).get("core_wound"):
                    changed_fields.append("core_wound")
                if ((before or {}).get("wound_profile") or {}).get("public_self") != ((after or {}).get("wound_profile") or {}).get("public_self"):
                    changed_fields.append("public_self")
                if ((before or {}).get("wound_profile") or {}).get("shadow_desire") != ((after or {}).get("wound_profile") or {}).get("shadow_desire"):
                    changed_fields.append("shadow_desire")
                if ((before or {}).get("vow_profile") or {}).get("vows") != ((after or {}).get("vow_profile") or {}).get("vows"):
                    changed_fields.append("vows")
                character_changes.append({"character_id": character_id, "changed_fields": changed_fields or ["structure"]})

        scene_changes = []
        previous_scenes = {item.get("scene_id"): item for item in previous.get("scene_blueprints", [])}
        current_scenes = {item.get("scene_id"): item for item in current.get("scene_blueprints", [])}
        for scene_id in sorted(set(previous_scenes) | set(current_scenes)):
            before = previous_scenes.get(scene_id)
            after = current_scenes.get(scene_id)
            if before != after:
                changed_fields = []
                if (before or {}).get("scene_function") != (after or {}).get("scene_function"):
                    changed_fields.append("scene_function")
                if (before or {}).get("required_roles") != (after or {}).get("required_roles"):
                    changed_fields.append("required_roles")
                if (before or {}).get("beats_template") != (after or {}).get("beats_template"):
                    changed_fields.append("beats_template")
                scene_changes.append({"scene_id": scene_id, "changed_fields": changed_fields or ["structure"]})

        capability_sections = [
            "voice_profiles",
            "response_cadence_profiles",
            "emotion_action_policies",
            "sensory_grounding_policies",
            "scene_realization_contracts",
        ]
        capability_changes = [section for section in capability_sections if previous.get(section) != current.get(section)]
        summary_parts = []
        if character_changes:
            summary_parts.append(f"角色卡 {len(character_changes)} 处改动")
        if scene_changes:
            summary_parts.append(f"scene blueprint {len(scene_changes)} 处改动")
        if capability_changes:
            summary_parts.append(f"{'/'.join(capability_changes)} 已更新")
        if not summary_parts and changed_sections:
            summary_parts.append(f"{len(changed_sections)} 个 section 发生变化")
        if not summary_parts:
            summary_parts.append("未检测到结构差异")
        return {
            "changed_sections": changed_sections,
            "character_changes": character_changes,
            "scene_changes": scene_changes,
            "capability_changes": capability_changes,
            "summary_text": "；".join(summary_parts),
        }

    def _append_revision(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        change_context: Dict[str, Any],
        diff_summary: Dict[str, Any],
        simulation_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = self._ensure_metadata(worldpack_payload)
        revision_history = list(metadata.get("revision_history", []))
        revision_history.append(
            {
                "revision_id": "rev_%s" % uuid4().hex[:10],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": change_context["source"],
                "label": change_context["label"],
                "change_context": copy.deepcopy(change_context),
                "summary": diff_summary["summary_text"],
                "changed_sections": list(diff_summary.get("changed_sections", [])),
                "diff_summary": copy.deepcopy(diff_summary),
                "worldpack_snapshot": copy.deepcopy(worldpack_payload),
                "simulation_delta": dict(simulation_delta or {}),
                "repair_loop_context": copy.deepcopy(change_context.get("repair_loop_context") or {}),
            }
        )
        metadata["revision_history"] = revision_history[-10:]
        metadata["latest_diff_summary"] = dict(diff_summary)

    def _build_diff_drilldown(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        drilldown: List[Dict[str, Any]] = []
        previous_snapshot: Dict[str, Any] = {}
        for index, revision in enumerate(revisions):
            snapshot = dict(revision.get("worldpack_snapshot") or {})
            if revision.get("diff_summary"):
                diff_summary = dict(revision.get("diff_summary") or {})
            elif index == 0:
                diff_summary = {
                    "changed_sections": list(revision.get("changed_sections", [])),
                    "character_changes": [],
                    "scene_changes": [],
                    "capability_changes": [],
                    "summary_text": revision.get("summary", ""),
                }
            else:
                diff_summary = self._diff_sections(previous_snapshot, snapshot)
                if not diff_summary.get("summary_text"):
                    diff_summary["summary_text"] = revision.get("summary", "")
            drilldown.append(
                {
                    "revision_id": revision.get("revision_id"),
                    "created_at": revision.get("created_at"),
                    "source": revision.get("source"),
                    "label": revision.get("label"),
                    "summary": revision.get("summary"),
                    "snapshot_summary": self._snapshot_summary(snapshot) if snapshot else "-",
                    "character_count": len(snapshot.get("characters", [])),
                    "scene_count": len(snapshot.get("scene_blueprints", [])),
                    "diff_summary": diff_summary,
                    "simulation_delta": dict(revision.get("simulation_delta") or {}),
                }
            )
            previous_snapshot = snapshot
        current_diff = dict(metadata.get("latest_diff_summary", {}))
        if not current_diff and drilldown:
            current_diff = dict(drilldown[-1].get("diff_summary") or {})
        section_change_counts = {
            "sections": len(current_diff.get("changed_sections", [])),
            "characters": len(current_diff.get("character_changes", [])),
            "scenes": len(current_diff.get("scene_changes", [])),
            "capabilities": len(current_diff.get("capability_changes", [])),
        }
        recommended_next_actions: List[str] = []
        if current_diff.get("character_changes"):
            recommended_next_actions.append("re_simulate_for_character_consistency")
        if current_diff.get("scene_changes"):
            recommended_next_actions.append("re_simulate_for_pacing_and_chapter_shape")
        if current_diff.get("capability_changes"):
            recommended_next_actions.append("re_simulate_for_voice_action_sensory_regression_check")
        if not recommended_next_actions and current_diff.get("changed_sections"):
            recommended_next_actions.append("review_structural_diff_before_next_step")
        return {
            "current_diff": current_diff,
            "section_change_counts": section_change_counts,
            "recommended_next_actions": recommended_next_actions,
            "revisions": drilldown,
        }

    def _build_validation_drilldown(self, validation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not validation_report:
            return {}
        guidance = {
            "schema": ("schema", "high", "修正 worldpack 顶层 schema 字段"),
            "runtime_world_bible": ("runtime_world_bible", "high", "检查 runtime_world_bible 与世界设定"),
            "runtime_initial_state": ("runtime_initial_state", "high", "检查 runtime_initial_state 与状态 schema"),
            "runtime_event_atoms": ("runtime_event_atoms", "high", "检查 runtime_event_atoms 与 event atom schema"),
            "scene_blueprints_missing": ("scene_blueprints", "high", "至少补一个 scene blueprint"),
            "characters_missing": ("characters", "high", "至少补一个角色"),
            "runtime_world_bible_missing": ("runtime_world_bible", "medium", "可选补 runtime_world_bible，减少 synthesize 偏差"),
            "runtime_initial_state_missing": ("runtime_initial_state", "medium", "可选补 runtime_initial_state，减少 synthesize 偏差"),
            "runtime_event_atoms_missing": ("runtime_event_atoms", "medium", "可选补 runtime_event_atoms，减少 synthesize 偏差"),
        }
        blockers = []
        warning_groups = []
        next_actions: List[str] = []
        for entry in list(validation_report.get("errors", [])):
            key = str(entry).split(":", 1)[0]
            category, severity, action = guidance.get(key, ("unknown", "high", "检查 validation error 并修正对应结构"))
            blockers.append(
                {
                    "key": key,
                    "category": category,
                    "severity": severity,
                    "message": str(entry),
                    "recommended_action": action,
                }
            )
            if action not in next_actions:
                next_actions.append(action)
        for entry in list(validation_report.get("warnings", [])):
            key = str(entry).split(":", 1)[0]
            category, severity, action = guidance.get(key, ("unknown", "medium", "按需补齐 runtime 资产"))
            warning_groups.append(
                {
                    "key": key,
                    "category": category,
                    "severity": severity,
                    "message": str(entry),
                    "recommended_action": action,
                }
            )
            if action not in next_actions:
                next_actions.append(action)
        return {
            "ok": bool(validation_report.get("ok")),
            "error_count": len(validation_report.get("errors", [])),
            "warning_count": len(validation_report.get("warnings", [])),
            "blockers": blockers,
            "warning_groups": warning_groups,
            "next_actions": next_actions,
        }

    def _build_simulation_drilldown(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_evaluations = list(simulation_report.get("chapter_evaluations", []))
        chapter_trace_map = {
            item.get("chapter_id"): dict(item)
            for item in simulation_report.get("chapter_trace", [])
            if item.get("chapter_id")
        }
        issue_counts: Dict[str, Dict[str, Any]] = {}
        module_counts: Dict[str, Dict[str, Any]] = {}
        chapter_breakdown: List[Dict[str, Any]] = []
        quality_actions: Dict[str, int] = {}
        for index, payload in enumerate(chapter_evaluations, start=1):
            scores = dict(payload.get("scores") or {})
            issues = list(payload.get("issues") or [])
            lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            trace = chapter_trace_map.get(chapter_id, {})
            issue_codes = []
            for issue in issues:
                issue_code = str(issue.get("issue_code") or "")
                if not issue_code:
                    continue
                issue_codes.append(issue_code)
                issue_entry = issue_counts.setdefault(
                    issue_code,
                    {
                        "issue_code": issue_code,
                        "count": 0,
                        "owning_module": issue.get("owning_module", ""),
                    },
                )
                issue_entry["count"] += 1
                module_name = str(issue.get("owning_module") or "unknown")
                module_entry = module_counts.setdefault(
                    module_name,
                    {
                        "owning_module": module_name,
                        "count": 0,
                        "issue_codes": set(),
                    },
                )
                module_entry["count"] += 1
                module_entry["issue_codes"].add(issue_code)
            for action in trace.get("quality_pass_actions", []):
                quality_actions[action] = quality_actions.get(action, 0) + 1
            chapter_breakdown.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_index": index,
                    "chapter_title": trace.get("chapter_title") or chapter_id,
                    "scene_function": trace.get("scene_function", ""),
                    "decision": payload.get("decision", {}).get("decision", "rewrite"),
                    "overall_score": round(float(scores.get("overall_score", 0.0)), 3),
                    "issue_codes": issue_codes,
                    "summary": payload.get("summary", ""),
                    "quality_pass_applied": bool(trace.get("quality_pass_applied", False)),
                    "quality_pass_actions": list(trace.get("quality_pass_actions", [])),
                    "signal_snapshot": {
                        "pacing": round(float(scores.get("pacing", 0.0)), 3),
                        "hook_quality": round(float(scores.get("hook_quality", 0.0)), 3),
                        "scene_density": round(float(scores.get("scene_density", 0.0)), 3),
                        "choice_distinctness": round(float(scores.get("choice_distinctness", 0.0)), 3),
                        "repetition_score": round(float(lint_metrics.get("repetition_score", 0.0)), 3),
                        "exposition_ratio": round(float(lint_metrics.get("exposition_ratio", 0.0)), 3),
                        "dialogue_plus_action_ratio": round(float(lint_metrics.get("dialogue_plus_action_ratio", 0.0)), 3),
                        "concrete_detail_density": round(float(lint_metrics.get("concrete_detail_density", 0.0)), 3),
                    },
                    "choices_preview": list(trace.get("choices_preview", [])),
                    "critic_signal_count": int(trace.get("critic_signal_count", 0)),
                }
            )
        weakest_chapters = sorted(
            chapter_breakdown,
            key=lambda item: (
                {"block": 0, "rewrite": 1, "pass": 2}.get(str(item.get("decision")), 3),
                float(item.get("overall_score", 0.0)),
                -len(item.get("issue_codes", [])),
                -float(item.get("signal_snapshot", {}).get("exposition_ratio", 0.0)),
            ),
        )[:3]
        issue_histogram = sorted(
            issue_counts.values(),
            key=lambda item: (-int(item.get("count", 0)), str(item.get("issue_code", ""))),
        )
        module_histogram = [
            {
                "owning_module": key,
                "count": int(value.get("count", 0)),
                "issue_codes": sorted(value.get("issue_codes", set())),
            }
            for key, value in sorted(
                module_counts.items(),
                key=lambda item: (-int(item[1].get("count", 0)), item[0]),
            )
        ]
        decision_histogram: Dict[str, int] = {}
        story_phase_histogram: Dict[str, int] = {}
        scene_function_histogram: Dict[str, int] = {}
        for item in chapter_breakdown:
            decision = str(item.get("decision") or "unknown")
            decision_histogram[decision] = decision_histogram.get(decision, 0) + 1
            story_phase = str(chapter_trace_map.get(item["chapter_id"], {}).get("story_phase") or "unknown")
            story_phase_histogram[story_phase] = story_phase_histogram.get(story_phase, 0) + 1
            scene_function = str(item.get("scene_function") or "unknown")
            scene_function_histogram[scene_function] = scene_function_histogram.get(scene_function, 0) + 1
        issue_focus_queue = []
        for item in issue_histogram[:4]:
            impacted = [
                chapter
                for chapter in chapter_breakdown
                if item["issue_code"] in chapter.get("issue_codes", [])
            ][:3]
            issue_focus_queue.append(
                {
                    "issue_code": item["issue_code"],
                    "count": item["count"],
                    "owning_module": item.get("owning_module", ""),
                    "fix_hint": ISSUE_TAXONOMY.get(item["issue_code"], {}).get("fix_hint", ""),
                    "chapter_targets": [
                        {
                            "chapter_index": chapter["chapter_index"],
                            "chapter_title": chapter["chapter_title"],
                            "scene_function": chapter.get("scene_function"),
                            "decision": chapter.get("decision"),
                        }
                        for chapter in impacted
                    ],
                }
            )
        return {
            "chapter_budget": simulation_report.get("chapter_budget"),
            "completed_chapters": simulation_report.get("completed_chapters", 0),
            "completion_ratio": simulation_report.get("completion_ratio"),
            "stop_reason": simulation_report.get("stop_reason"),
            "latest_decision": simulation_report.get("latest_decision"),
            "issue_histogram": issue_histogram,
            "module_histogram": module_histogram,
            "decision_histogram": decision_histogram,
            "story_phase_histogram": story_phase_histogram,
            "scene_function_histogram": scene_function_histogram,
            "issue_focus_queue": issue_focus_queue,
            "weakest_chapters": weakest_chapters,
            "chapter_breakdown": chapter_breakdown,
            "quality_pass_summary": {
                "chapters_touched": sum(1 for item in chapter_breakdown if item.get("quality_pass_applied")),
                "action_histogram": [
                    {"action": action, "count": count}
                    for action, count in sorted(quality_actions.items(), key=lambda item: (-item[1], item[0]))
                ],
            },
            "next_actions": list((simulation_report.get("evaluation_summary") or {}).get("next_actions", [])),
        }

    def _build_longform_drilldown(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        longform_summary = dict(simulation_report.get("longform_summary") or {})
        plan_snapshot = dict(simulation_report.get("longform_plan_snapshot") or {})
        series_plan = dict(plan_snapshot.get("series_plan") or {})
        volume_plans = sorted(
            [dict(item) for item in plan_snapshot.get("volume_plans", [])],
            key=lambda item: int(item.get("order", 0)),
        )
        arc_plans = sorted(
            [dict(item) for item in plan_snapshot.get("arc_plans", [])],
            key=lambda item: (str(item.get("volume_id") or ""), int(item.get("order", 0))),
        )
        chapter_trace = [dict(item) for item in simulation_report.get("chapter_trace", [])]
        volume_map: Dict[str, List[Dict[str, Any]]] = {}
        arc_map: Dict[str, List[Dict[str, Any]]] = {}
        duty_histogram: Dict[str, int] = {}
        ending_gate_blocks = 0
        fallback_chapters = 0
        for item in chapter_trace:
            volume_id = str(item.get("volume_id") or "")
            arc_id = str(item.get("arc_id") or "")
            chapter_task = dict(item.get("chapter_task") or {})
            execution = dict(item.get("chapter_task_execution_summary") or {})
            if volume_id:
                volume_map.setdefault(volume_id, []).append(item)
            if arc_id:
                arc_map.setdefault(arc_id, []).append(item)
            duty = str(chapter_task.get("duty_type") or "")
            if duty:
                duty_histogram[duty] = duty_histogram.get(duty, 0) + 1
            if bool(execution.get("ending_gate_blocked", False)):
                ending_gate_blocks += 1
            if bool(execution.get("used_fallback", False)):
                fallback_chapters += 1
        volume_progress = []
        for volume in volume_plans:
            volume_id = str(volume.get("volume_id") or "")
            chapters = volume_map.get(volume_id, [])
            target = max(1, int(volume.get("target_chapters", 1)))
            completion_ratio = round(len(chapters) / float(target), 3)
            volume_progress.append(
                {
                    "volume_id": volume_id,
                    "title": volume.get("title"),
                    "order": int(volume.get("order", 0)),
                    "target_chapters": target,
                    "completed_chapters": len(chapters),
                    "completion_ratio": completion_ratio,
                    "status": "completed" if len(chapters) >= target else ("in_progress" if chapters else "pending"),
                    "first_chapter": chapters[0].get("chapter_id") if chapters else None,
                    "last_chapter": chapters[-1].get("chapter_id") if chapters else None,
                    "dominant_duty": max(
                        (
                            (duty, sum(1 for chapter in chapters if (chapter.get("chapter_task") or {}).get("duty_type") == duty))
                            for duty in {str((chapter.get("chapter_task") or {}).get("duty_type") or "") for chapter in chapters}
                            if duty
                        ),
                        default=(None, 0),
                        key=lambda item: item[1],
                    )[0],
                }
            )
        arc_progress = []
        for arc in arc_plans:
            arc_id = str(arc.get("arc_id") or "")
            chapters = arc_map.get(arc_id, [])
            target = max(1, int(arc.get("target_chapters", 1)))
            avg_score = 0.0
            if chapters:
                scored = [
                    float((chapter.get("evaluation") or {}).get("overall_score", 0.0))
                    for chapter in chapters
                    if chapter.get("evaluation")
                ]
                if scored:
                    avg_score = round(sum(scored) / float(len(scored)), 3)
            arc_progress.append(
                {
                    "arc_id": arc_id,
                    "volume_id": arc.get("volume_id"),
                    "title": arc.get("title"),
                    "order": int(arc.get("order", 0)),
                    "target_chapters": target,
                    "completed_chapters": len(chapters),
                    "completion_ratio": round(len(chapters) / float(target), 3),
                    "status": "completed" if len(chapters) >= target else ("in_progress" if chapters else "pending"),
                    "average_score": avg_score,
                    "duty_histogram": [
                        {
                            "duty_type": duty,
                            "count": sum(1 for chapter in chapters if (chapter.get("chapter_task") or {}).get("duty_type") == duty),
                        }
                        for duty in sorted(
                            {
                                str((chapter.get("chapter_task") or {}).get("duty_type") or "")
                                for chapter in chapters
                                if (chapter.get("chapter_task") or {}).get("duty_type")
                            }
                        )
                    ],
                }
            )
        weakest_arcs = sorted(
            [item for item in arc_progress if item.get("completed_chapters")],
            key=lambda item: (
                float(item.get("average_score", 0.0)),
                float(item.get("completion_ratio", 0.0)),
            ),
        )[:3]
        gate = dict(simulation_report.get("longform_gate") or {})
        promise_runway_summary = self._build_promise_runway_summary(simulation_report)
        midrun_signal_window = self._build_longform_midrun_signal_window(simulation_report)
        structure_exhaustion = None
        target_chapters = int(series_plan.get("total_chapter_target", longform_summary.get("target_chapters", 0) or 0))
        completed_chapters = int(simulation_report.get("completed_chapters", 0))
        top_issue_codes = {
            str(item.get("issue_code") or "")
            for item in list((simulation_report.get("evaluation_summary") or {}).get("top_issue_categories") or [])
            if str(item.get("issue_code") or "")
        }
        trigger_issue_codes = sorted(
            {
                issue_code
                for issue_code in (top_issue_codes | set(midrun_signal_window.get("issue_codes") or []))
                if issue_code in {"Q04", "Q09"}
            }
        )
        runway_exhausted = (
            promise_runway_summary.get("runway_status") == "exhausted"
            or int(midrun_signal_window.get("open_promises_at_end", 0) or 0) <= 0
        )
        weak_midrun_shape = (
            float(midrun_signal_window.get("avg_pacing", 1.0) or 1.0) < 0.34
            or float(midrun_signal_window.get("avg_hook_quality", 1.0) or 1.0) < 0.5
            or float(midrun_signal_window.get("avg_exposition_ratio", 0.0) or 0.0) > 0.5
            or float(midrun_signal_window.get("scene_family_repeat_ratio", 0.0) or 0.0) > 0.45
        )
        if (
            target_chapters >= 100
            and completed_chapters < int(target_chapters * 0.8)
            and runway_exhausted
            and weak_midrun_shape
            and trigger_issue_codes
        ):
            structure_exhaustion = {
                "key": "longform_structure_exhaustion",
                "status": "blocked",
                "message": (
                    f"当前长线在第 {completed_chapters} 章附近出现 promise runway 耗空，"
                    "同时 pacing / hook / exposition 已进入中段塌陷窗口。"
                ),
                "trigger_issue_codes": trigger_issue_codes,
                "signal_window": midrun_signal_window,
                "recommended_actions": [
                    "bootstrap_structured_longform",
                    "expand_character_and_scene_lattice",
                    "rebuild_promise_lattice",
                ],
            }
        return {
            "series_id": series_plan.get("series_id") or longform_summary.get("series_id"),
            "series_title": series_plan.get("title"),
            "target_chapters": target_chapters,
            "completed_chapters": completed_chapters,
            "volume_progress": volume_progress,
            "arc_progress": arc_progress,
            "weakest_arcs": weakest_arcs,
            "duty_histogram": [
                {"duty_type": duty, "count": count}
                for duty, count in sorted(duty_histogram.items(), key=lambda item: (-item[1], item[0]))
            ],
            "ending_gate_blocks": ending_gate_blocks,
            "fallback_chapters": fallback_chapters,
            "gate_status": gate.get("status"),
            "gate_failed_checks": list(gate.get("failed_checks", [])),
            "promise_runway_summary": promise_runway_summary,
            "runway_status": promise_runway_summary.get("runway_status"),
            "midrun_signal_window": midrun_signal_window,
            "longform_structure_exhaustion": structure_exhaustion,
            "next_actions": [
                f"repair_{name}"
                for name in gate.get("failed_checks", [])
            ] or (structure_exhaustion.get("recommended_actions", []) if structure_exhaustion else ["continue_longform_simulation"]),
        }

    def _build_promise_ledger_workbench(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        final_state = dict(simulation_report.get("final_state_snapshot") or {})
        open_promises = [dict(item) for item in final_state.get("open_promises", [])]
        state_metadata = dict(final_state.get("metadata") or {})
        closed_promise_ids = [str(item) for item in state_metadata.get("closed_promise_ids", []) if str(item)]
        chapter_trace = [dict(item) for item in simulation_report.get("chapter_trace", [])]
        first_seen: Dict[str, int] = {}
        last_seen: Dict[str, int] = {}
        for index, item in enumerate(chapter_trace, start=1):
            for promise_id in item.get("open_promise_ids", []) or []:
                if promise_id not in first_seen:
                    first_seen[promise_id] = index
                last_seen[promise_id] = index
        current_turn = int(final_state.get("turn_index", simulation_report.get("completed_chapters", 0)) or 0)
        open_items = []
        overdue_count = 0
        for promise in open_promises:
            due_by_turn = int(promise.get("due_by_turn", current_turn) or current_turn)
            is_overdue = due_by_turn <= current_turn
            if is_overdue:
                overdue_count += 1
            promise_id = str(promise.get("promise_id") or "")
            open_items.append(
                {
                    "promise_id": promise_id,
                    "description": promise.get("description", ""),
                    "holders": list(promise.get("holders", [])),
                    "stakes": promise.get("stakes"),
                    "status": promise.get("status"),
                    "opened_at_turn": promise.get("opened_at_turn"),
                    "due_by_turn": promise.get("due_by_turn"),
                    "is_overdue": is_overdue,
                    "first_seen_chapter": first_seen.get(promise_id),
                    "last_seen_chapter": last_seen.get(promise_id),
                    "anchor": {
                        "anchor_type": "simulation",
                        "anchor_key": str(last_seen.get(promise_id) or first_seen.get(promise_id) or simulation_report.get("completed_chapters", 0)),
                    },
                }
            )
        return {
            "available": True,
            "status": "active" if open_items else "clear",
            "open_count": len(open_items),
            "closed_count": len(closed_promise_ids),
            "overdue_count": overdue_count,
            "open_promises": open_items,
            "recently_closed_ids": closed_promise_ids[-10:],
            "next_actions": (
                ["comment_or_fix_overdue_promises"] if overdue_count else (["review_open_promises"] if open_items else ["continue_longform_simulation"])
            ),
        }

    def _build_promise_runway_summary(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        ledger = self._build_promise_ledger_workbench(simulation_report)
        if not ledger:
            return {}
        chapter_trace = self._chapter_trace_with_promise_deltas(simulation_report)
        current_turn = int(dict(simulation_report.get("final_state_snapshot") or {}).get("turn_index", simulation_report.get("completed_chapters", 0)) or 0)
        chapters_with_new_promises = [
            int(item.get("simulation_chapter_index", 0) or 0)
            for item in chapter_trace
            if list(item.get("open_promise_ids", []) or [])
        ]
        last_new_promise_chapter = chapters_with_new_promises[-1] if chapters_with_new_promises else None
        chapters_since_last_new_promise = (
            max(0, current_turn - int(last_new_promise_chapter))
            if last_new_promise_chapter is not None
            else current_turn
        )
        due_values = [
            int(item.get("due_by_turn", 0) or 0)
            for item in ledger.get("open_promises", [])
            if int(item.get("due_by_turn", 0) or 0) > 0
        ]
        chapters_until_next_due_cluster = (
            max(0, min(due_values) - current_turn)
            if due_values
            else None
        )
        open_count = int(ledger.get("open_count", 0) or 0)
        overdue_count = int(ledger.get("overdue_count", 0) or 0)
        if open_count <= 0:
            runway_status = "exhausted"
        elif overdue_count > 0 or chapters_since_last_new_promise >= 6 or open_count < 2:
            runway_status = "thinning"
        else:
            runway_status = "healthy"
        return {
            "available": True,
            "open_count": open_count,
            "overdue_count": overdue_count,
            "chapters_since_last_new_promise": chapters_since_last_new_promise,
            "chapters_until_next_due_cluster": chapters_until_next_due_cluster,
            "runway_status": runway_status,
            "last_new_promise_chapter": last_new_promise_chapter,
        }

    def _build_longform_midrun_signal_window(
        self,
        simulation_report: Dict[str, Any],
        *,
        window_size: int = 5,
    ) -> Dict[str, Any]:
        chapter_trace_map = {
            str(item.get("chapter_id") or ""): dict(item)
            for item in list(simulation_report.get("chapter_trace") or [])
            if str(item.get("chapter_id") or "")
        }
        chapter_snapshots: List[Dict[str, Any]] = []
        for index, payload in enumerate(list(simulation_report.get("chapter_evaluations") or []), start=1):
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            trace = chapter_trace_map.get(chapter_id, {})
            scores = dict(payload.get("scores") or {})
            lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
            execution = dict(trace.get("chapter_task_execution_summary") or {})
            chapter_snapshots.append(
                {
                    "chapter_index": int(execution.get("series_chapter_index", index) or index),
                    "scene_function": str(trace.get("scene_function") or ""),
                    "pacing": round(float(scores.get("pacing", 0.0) or 0.0), 3),
                    "hook_quality": round(float(scores.get("hook_quality", 0.0) or 0.0), 3),
                    "exposition_ratio": round(float(lint_metrics.get("exposition_ratio", 0.0) or 0.0), 3),
                    "issue_codes": [
                        str(issue.get("issue_code") or "")
                        for issue in list(payload.get("issues") or [])
                        if str(issue.get("issue_code") or "")
                    ],
                }
            )
        if not chapter_snapshots:
            return {"available": False}
        tail = chapter_snapshots[-min(window_size, len(chapter_snapshots)) :]
        repeated_transitions = 0
        transition_count = 0
        previous_scene_function: Optional[str] = None
        for snapshot in tail:
            scene_function = str(snapshot.get("scene_function") or "")
            if previous_scene_function is not None and scene_function:
                transition_count += 1
                if previous_scene_function == scene_function:
                    repeated_transitions += 1
            if scene_function:
                previous_scene_function = scene_function
        final_state = dict(simulation_report.get("final_state_snapshot") or {})
        open_promises = list(final_state.get("open_promises") or [])
        return {
            "available": True,
            "window_size": len(tail),
            "window_start_chapter": int(tail[0].get("chapter_index", 0) or 0),
            "window_end_chapter": int(tail[-1].get("chapter_index", 0) or 0),
            "avg_pacing": round(sum(float(item.get("pacing", 0.0) or 0.0) for item in tail) / float(max(1, len(tail))), 3),
            "avg_hook_quality": round(sum(float(item.get("hook_quality", 0.0) or 0.0) for item in tail) / float(max(1, len(tail))), 3),
            "avg_exposition_ratio": round(sum(float(item.get("exposition_ratio", 0.0) or 0.0) for item in tail) / float(max(1, len(tail))), 3),
            "scene_family_repeat_ratio": round(repeated_transitions / float(max(1, transition_count)), 3),
            "open_promises_at_end": len(open_promises),
            "issue_codes": sorted(
                {
                    str(issue_code)
                    for item in tail
                    for issue_code in list(item.get("issue_codes") or [])
                    if str(issue_code)
                }
            ),
        }

    def _chapter_trace_with_promise_deltas(self, simulation_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        chapter_trace = [dict(item) for item in simulation_report.get("chapter_trace", [])]
        seen_closed: set[str] = set()
        for index, item in enumerate(chapter_trace, start=1):
            execution = dict(item.get("chapter_task_execution_summary") or {})
            chapter_index = int(execution.get("series_chapter_index", index) or index)
            cumulative_closed = [str(promise_id) for promise_id in item.get("closed_promise_ids", []) if str(promise_id)]
            closed_delta = [promise_id for promise_id in cumulative_closed if promise_id not in seen_closed]
            seen_closed.update(closed_delta)
            item["simulation_chapter_index"] = chapter_index
            item["open_promise_ids"] = [str(promise_id) for promise_id in item.get("open_promise_ids", []) if str(promise_id)]
            item["closed_promise_ids_delta"] = closed_delta
            item["anchor"] = {
                "anchor_type": "simulation",
                "anchor_key": str(chapter_index),
            }
        return chapter_trace

    def _promise_catalog_from_simulation(
        self, simulation_report: Dict[str, Any], chapter_trace: List[Dict[str, Any]]
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int], Dict[str, int]]:
        final_state = dict(simulation_report.get("final_state_snapshot") or {})
        current_turn = int(final_state.get("turn_index", simulation_report.get("completed_chapters", 0)) or 0)
        open_promises = [dict(item) for item in final_state.get("open_promises", [])]
        promise_catalog: Dict[str, Dict[str, Any]] = {}
        for promise in open_promises:
            promise_id = str(promise.get("promise_id") or "")
            if not promise_id:
                continue
            due_by_turn = int(promise.get("due_by_turn", current_turn) or current_turn)
            promise_catalog[promise_id] = {
                "promise_id": promise_id,
                "description": promise.get("description", ""),
                "holders": list(promise.get("holders", [])),
                "stakes": promise.get("stakes"),
                "status": promise.get("status"),
                "opened_at_turn": promise.get("opened_at_turn"),
                "due_by_turn": promise.get("due_by_turn"),
                "is_overdue": due_by_turn <= current_turn,
                "source": "open",
            }
        first_seen: Dict[str, int] = {}
        last_seen: Dict[str, int] = {}
        for item in chapter_trace:
            chapter_index = int(item.get("simulation_chapter_index", 0) or 0)
            touched_promise_ids = sorted(
                {
                    *[str(promise_id) for promise_id in item.get("open_promise_ids", []) if str(promise_id)],
                    *[str(promise_id) for promise_id in item.get("closed_promise_ids_delta", []) if str(promise_id)],
                }
            )
            for promise_id in touched_promise_ids:
                if promise_id not in first_seen:
                    first_seen[promise_id] = chapter_index
                last_seen[promise_id] = chapter_index
                promise_catalog.setdefault(
                    promise_id,
                    {
                        "promise_id": promise_id,
                        "description": "",
                        "holders": [],
                        "stakes": None,
                        "status": "closed",
                        "opened_at_turn": None,
                        "due_by_turn": None,
                        "is_overdue": False,
                        "source": "closed_only",
                    },
                )
        return promise_catalog, first_seen, last_seen

    def _materialize_promise_items(
        self,
        promise_ids: List[str],
        promise_catalog: Dict[str, Dict[str, Any]],
        first_seen: Dict[str, int],
        last_seen: Dict[str, int],
        *,
        promise_state_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        items = []
        overrides = promise_state_overrides or {}
        for promise_id in promise_ids:
            if not promise_id:
                continue
            payload = dict(
                promise_catalog.get(
                    promise_id,
                    {
                        "promise_id": promise_id,
                        "description": "",
                        "holders": [],
                        "stakes": None,
                        "status": "unknown",
                        "opened_at_turn": None,
                        "due_by_turn": None,
                        "is_overdue": False,
                        "source": "unknown",
                    },
                )
            )
            payload["first_seen_chapter"] = first_seen.get(promise_id)
            payload["last_seen_chapter"] = last_seen.get(promise_id)
            payload["anchor"] = {
                "anchor_type": "simulation",
                "anchor_key": str(last_seen.get(promise_id) or first_seen.get(promise_id) or ""),
            }
            override = dict(overrides.get(promise_id) or {})
            payload["editor_state"] = override.get("editor_state", "")
            payload["editor_notes"] = override.get("notes", "")
            payload["editor_updated_at"] = override.get("updated_at")
            payload["editor_context"] = {
                "chapter_index": override.get("chapter_index"),
                "chapter_task_id": override.get("chapter_task_id"),
                "arc_id": override.get("arc_id"),
                "volume_id": override.get("volume_id"),
            }
            payload["has_editor_override"] = bool(override)
            items.append(payload)
        return items

    def _build_promise_state_workbench(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_trace = self._chapter_trace_with_promise_deltas(simulation_report)
        promise_catalog, first_seen, last_seen = self._promise_catalog_from_simulation(simulation_report, chapter_trace)
        overrides = self._promise_state_overrides(metadata)
        editable_ids = sorted(
            promise_catalog.keys(),
            key=lambda promise_id: (
                0 if promise_catalog.get(promise_id, {}).get("status") == "open" else 1,
                first_seen.get(promise_id, 10**9),
                promise_id,
            ),
        )
        editable_promises = self._materialize_promise_items(
            editable_ids,
            promise_catalog,
            first_seen,
            last_seen,
            promise_state_overrides=overrides,
        )
        return {
            "available": True,
            "state_options": list(self.promise_editor_states),
            "override_count": sum(1 for item in editable_promises if item.get("has_editor_override")),
            "editable_promises": editable_promises,
            "next_actions": (
                ["review_escalated_promises", "resolve_or_defer_open_promises"]
                if any(item.get("editor_state") == "escalate" for item in editable_promises)
                else (["review_open_promises"] if editable_promises else ["run_longform_simulation"])
            ),
        }

    def _build_series_volume_arc_promise_mapping(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_trace = self._chapter_trace_with_promise_deltas(simulation_report)
        plan_snapshot = dict(simulation_report.get("longform_plan_snapshot") or {})
        series_plan = dict(plan_snapshot.get("series_plan") or {})
        volume_plans = [dict(item) for item in plan_snapshot.get("volume_plans", [])]
        arc_plans = [dict(item) for item in plan_snapshot.get("arc_plans", [])]
        promise_catalog, first_seen, last_seen = self._promise_catalog_from_simulation(simulation_report, chapter_trace)
        promise_state_overrides = self._promise_state_overrides(dict(simulation_report.get("_draft_metadata", {}) or {}))

        def _scope_summary(trace_items: List[Dict[str, Any]]) -> Dict[str, Any]:
            chapter_indexes = [int(item.get("simulation_chapter_index", 0) or 0) for item in trace_items]
            open_ids = sorted(
                {
                    str(promise_id)
                    for item in trace_items
                    for promise_id in item.get("open_promise_ids", [])
                    if str(promise_id)
                }
            )
            closed_ids = sorted(
                {
                    str(promise_id)
                    for item in trace_items
                    for promise_id in item.get("closed_promise_ids_delta", [])
                    if str(promise_id)
                }
            )
            mapped_ids = sorted(set(open_ids) | set(closed_ids))
            return {
                "simulated_chapter_count": len(trace_items),
                "first_simulation_chapter": min(chapter_indexes) if chapter_indexes else None,
                "last_simulation_chapter": max(chapter_indexes) if chapter_indexes else None,
                "open_promise_ids": open_ids,
                "closed_promise_ids": closed_ids,
                "mapped_promises": self._materialize_promise_items(
                    mapped_ids,
                    promise_catalog,
                    first_seen,
                    last_seen,
                    promise_state_overrides=promise_state_overrides,
                ),
            }

        volume_maps = []
        for volume in volume_plans:
            trace_items = [item for item in chapter_trace if item.get("volume_id") == volume.get("volume_id")]
            scope = _scope_summary(trace_items)
            volume_maps.append(
                {
                    "volume_id": volume.get("volume_id"),
                    "order": volume.get("order"),
                    "title": volume.get("title"),
                    "goal": volume.get("goal"),
                    "target_chapters": volume.get("target_chapters"),
                    "climax_definition": volume.get("climax_definition"),
                    "end_state": volume.get("end_state"),
                    "arc_ids": [str(arc.get("arc_id")) for arc in arc_plans if arc.get("volume_id") == volume.get("volume_id")],
                    **scope,
                    "anchor": {
                        "anchor_type": "simulation",
                        "anchor_key": str(scope.get("first_simulation_chapter") or ""),
                    },
                }
            )

        arc_maps = []
        for arc in arc_plans:
            trace_items = [item for item in chapter_trace if item.get("arc_id") == arc.get("arc_id")]
            scope = _scope_summary(trace_items)
            arc_maps.append(
                {
                    "arc_id": arc.get("arc_id"),
                    "volume_id": arc.get("volume_id"),
                    "order": arc.get("order"),
                    "title": arc.get("title"),
                    "goal": arc.get("goal"),
                    "conflict": arc.get("conflict"),
                    "target_chapters": arc.get("target_chapters"),
                    "reveal_budget": arc.get("reveal_budget"),
                    "payoff_targets": list(arc.get("payoff_targets", [])),
                    "completion_conditions": list(arc.get("completion_conditions", [])),
                    "chapter_task_ids": [
                        str(task.get("chapter_task_id"))
                        for task in arc.get("chapter_tasks", [])
                        if task.get("chapter_task_id")
                    ],
                    **scope,
                    "anchor": {
                        "anchor_type": "simulation",
                        "anchor_key": str(scope.get("first_simulation_chapter") or ""),
                    },
                }
            )

        series_scope = _scope_summary(chapter_trace)
        return {
            "available": True,
            "series_summary": {
                "series_id": series_plan.get("series_id"),
                "title": series_plan.get("title"),
                "theme_statement": series_plan.get("theme_statement"),
                "target_chapters": series_plan.get("total_chapter_target"),
                "target_word_count": series_plan.get("target_word_count"),
                "volume_count": len(volume_plans),
                "arc_count": len(arc_plans),
                **series_scope,
            },
            "volumes": volume_maps,
            "arcs": arc_maps,
            "next_actions": (
                ["review_arc_promise_map", "review_task_simulation_links"]
                if chapter_trace
                else ["run_longform_simulation"]
            ),
        }

    def _build_chapter_task_simulation_linking(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_trace = self._chapter_trace_with_promise_deltas(simulation_report)
        chapter_compare = self._build_before_after_chapter_compare(dict(simulation_report.get("_draft_metadata", {}) or {}))
        chapter_compare_map = {
            int(chapter_index): dict(payload)
            for chapter_index, payload in dict(chapter_compare.get("chapter_compare_map", {}) or {}).items()
        }
        plan_snapshot = dict(simulation_report.get("longform_plan_snapshot") or {})
        volume_plans = {str(item.get("volume_id")): dict(item) for item in plan_snapshot.get("volume_plans", [])}
        arc_plans = [dict(item) for item in plan_snapshot.get("arc_plans", [])]
        promise_catalog, first_seen, last_seen = self._promise_catalog_from_simulation(simulation_report, chapter_trace)
        promise_state_overrides = self._promise_state_overrides(dict(simulation_report.get("_draft_metadata", {}) or {}))

        task_links = []
        for arc in arc_plans:
            volume = volume_plans.get(str(arc.get("volume_id") or ""), {})
            for task_order, task in enumerate(arc.get("chapter_tasks", []), start=1):
                task_id = str(task.get("chapter_task_id") or "")
                trace_items = [
                    item
                    for item in chapter_trace
                    if str((item.get("chapter_task") or {}).get("chapter_task_id") or "") == task_id
                ]
                linked_open_ids = sorted(
                    {
                        str(promise_id)
                        for item in trace_items
                        for promise_id in item.get("open_promise_ids", [])
                        if str(promise_id)
                    }
                )
                linked_closed_ids = sorted(
                    {
                        str(promise_id)
                        for item in trace_items
                        for promise_id in item.get("closed_promise_ids_delta", [])
                        if str(promise_id)
                    }
                )
                linked_chapters = [
                    {
                        "chapter_index": int(item.get("simulation_chapter_index", 0) or 0),
                        "chapter_id": item.get("chapter_id"),
                        "chapter_title": item.get("chapter_title"),
                        "scene_function": item.get("scene_function"),
                        "decision": dict(item.get("evaluation") or {}).get("decision"),
                        "overall_score": float(dict(item.get("evaluation") or {}).get("overall_score", 0.0)),
                        "issue_codes": list(dict(item.get("evaluation") or {}).get("issue_codes", [])),
                        "open_promise_ids": list(item.get("open_promise_ids", [])),
                        "closed_promise_ids": list(item.get("closed_promise_ids_delta", [])),
                        "anchor": dict(item.get("anchor") or {}),
                    }
                    for item in trace_items
                ]
                compare_chapters = [
                    dict(chapter_compare_map.get(int(item.get("chapter_index", 0) or 0)) or {})
                    for item in linked_chapters
                    if chapter_compare_map.get(int(item.get("chapter_index", 0) or 0))
                ]
                issue_codes_added = sorted(
                    {
                        str(issue_code)
                        for item in compare_chapters
                        for issue_code in item.get("issue_codes_added", [])
                        if str(issue_code)
                    }
                )
                issue_codes_removed = sorted(
                    {
                        str(issue_code)
                        for item in compare_chapters
                        for issue_code in item.get("issue_codes_removed", [])
                        if str(issue_code)
                    }
                )
                average_score_delta = round(
                    sum(float(item.get("overall_score_delta", 0.0)) for item in compare_chapters) / float(max(1, len(compare_chapters))),
                    3,
                ) if compare_chapters else 0.0
                strongest_compare = sorted(
                    compare_chapters,
                    key=lambda item: (
                        -abs(float(item.get("overall_score_delta", 0.0))),
                        int(item.get("chapter_index", 0) or 0),
                    ),
                )[0] if compare_chapters else {}
                planned_ids = [str(item) for item in task.get("promise_targets", []) if str(item)]
                observed_ids = [str(item.get("promise_id")) for item in self._materialize_promise_items(
                    sorted(set(linked_open_ids) | set(linked_closed_ids)),
                    promise_catalog,
                    first_seen,
                    last_seen,
                    promise_state_overrides=promise_state_overrides,
                ) if str(item.get("promise_id"))]
                matched_ids = sorted(set(planned_ids) & set(observed_ids))
                planned_only_ids = sorted(set(planned_ids) - set(observed_ids))
                observed_only_ids = sorted(set(observed_ids) - set(planned_ids))
                if not planned_ids and not observed_ids:
                    drift_status = "no_signal"
                elif planned_only_ids and observed_only_ids:
                    drift_status = "diverged"
                elif planned_only_ids:
                    drift_status = "planned_only"
                elif observed_only_ids:
                    drift_status = "observed_only"
                else:
                    drift_status = "aligned"
                coverage_ratio = (
                    round(len(matched_ids) / float(max(1, len(planned_ids))), 3)
                    if planned_ids
                    else (1.0 if not observed_only_ids else 0.0)
                )
                planned_promises = self._materialize_promise_items(
                    planned_ids,
                    promise_catalog,
                    first_seen,
                    last_seen,
                    promise_state_overrides=promise_state_overrides,
                )
                observed_promises = self._materialize_promise_items(
                    sorted(set(linked_open_ids) | set(linked_closed_ids)),
                    promise_catalog,
                    first_seen,
                    last_seen,
                    promise_state_overrides=promise_state_overrides,
                )
                remediation_suggestions: List[Dict[str, Any]] = []
                if planned_only_ids:
                    remediation_suggestions.append(
                        {
                            "action": "split_targets_or_expand_scene",
                            "summary": "计划中的 promise targets 还没在 simulation 中命中。",
                            "details": f"planned only: {', '.join(planned_only_ids)}",
                        }
                    )
                if observed_only_ids:
                    remediation_suggestions.append(
                        {
                            "action": "merge_observed_promises",
                            "summary": "simulation 出现了 task 计划外的 promise。",
                            "details": f"observed only: {', '.join(observed_only_ids)}",
                        }
                    )
                if issue_codes_added:
                    remediation_suggestions.append(
                        {
                            "action": "rewrite_from_compare",
                            "summary": "章节对照里出现新增 issue，建议从 compare 回写 task。",
                            "details": f"issues added: {', '.join(issue_codes_added)}",
                        }
                    )
                first_linked_chapter_index = (
                    int(dict(linked_chapters[0]).get("chapter_index", 0) or 0)
                    if linked_chapters
                    else 0
                )
                rewrite_target_chapter_index = (
                    int(strongest_compare.get("chapter_index", 0) or 0)
                    or first_linked_chapter_index
                )
                suggested_override_state = (
                    "needs_rewrite"
                    if issue_codes_added or drift_status in {"diverged", "planned_only"}
                    else ("accepted_tradeoff" if drift_status == "observed_only" else "watch")
                )
                rewrite_focus = []
                if planned_only_ids:
                    rewrite_focus.append(f"补上未命中的 promise：{' / '.join(planned_only_ids)}")
                if observed_only_ids:
                    rewrite_focus.append(f"决定是否并入新出现的 promise：{' / '.join(observed_only_ids)}")
                if issue_codes_added:
                    rewrite_focus.append(f"处理新增 issue：{' / '.join(issue_codes_added)}")
                if not rewrite_focus:
                    rewrite_focus.append("保持当前任务目标与章节对照的一致性。")
                suggested_objective = (
                    f"{task.get('objective') or '推进当前任务。'} "
                    f"{'；'.join(rewrite_focus)}"
                ).strip()
                task_links.append(
                    {
                        "chapter_task_id": task_id,
                        "task_order": task_order,
                        "status": "linked" if linked_chapters else "planned_only",
                        "volume_id": arc.get("volume_id"),
                        "volume_title": volume.get("title"),
                        "arc_id": arc.get("arc_id"),
                        "arc_title": arc.get("title"),
                        "duty_type": task.get("duty_type"),
                        "objective": task.get("objective"),
                        "target_words": task.get("target_words"),
                        "reveal_budget": task.get("reveal_budget"),
                        "promise_actions": list(task.get("promise_actions", [])),
                        "promise_targets": list(task.get("promise_targets", [])),
                        "planned_promises": planned_promises,
                        "allow_terminal": bool(task.get("allow_terminal")),
                        "simulated_chapter_count": len(linked_chapters),
                        "linked_chapters": linked_chapters,
                        "compare_available": bool(compare_chapters),
                        "compare_chapters": compare_chapters,
                        "compare_summary": {
                            "compared_chapter_count": len(compare_chapters),
                            "average_score_delta": average_score_delta,
                            "issue_codes_added": issue_codes_added,
                            "issue_codes_removed": issue_codes_removed,
                            "strongest_compare_chapter_index": strongest_compare.get("chapter_index"),
                            "strongest_compare_delta": float(strongest_compare.get("overall_score_delta", 0.0)),
                        },
                        "linked_open_promise_ids": linked_open_ids,
                        "linked_closed_promise_ids": linked_closed_ids,
                        "mapped_promises": observed_promises,
                        "promise_drift": {
                            "status": drift_status,
                            "coverage_ratio": coverage_ratio,
                            "planned_target_count": len(planned_ids),
                            "observed_target_count": len(observed_ids),
                            "matched_target_count": len(matched_ids),
                            "planned_target_ids": planned_ids,
                            "observed_target_ids": observed_ids,
                            "matched_target_ids": matched_ids,
                            "planned_only_ids": planned_only_ids,
                            "observed_only_ids": observed_only_ids,
                            "recommended_actions": (
                                ["split_or_trim_planned_targets", "merge_observed_promises"]
                                if drift_status == "diverged"
                                else (["merge_observed_promises"] if drift_status == "observed_only" else (["review_unhit_targets"] if drift_status == "planned_only" else ["continue"]))
                            ),
                        },
                        "remediation_suggestions": remediation_suggestions,
                        "rewrite_workflow": {
                            "available": bool(linked_chapters or compare_chapters or remediation_suggestions),
                            "rewrite_target_chapter_index": rewrite_target_chapter_index or None,
                            "suggested_override_state": suggested_override_state,
                            "issue_scope": issue_codes_added,
                            "suggested_task_objective": suggested_objective,
                            "suggested_bulk_notes": "先查看章节对照，再更新当前 task 的 objective / promise targets，并重新运行 simulation。",
                            "suggested_promise_targets": sorted(set(planned_ids) | set(observed_ids)),
                            "next_actions": ["jump_to_compare", "apply_rewrite_prefill", "save_longform_workbench", "re_simulate"],
                        },
                        "next_actions": (
                            ["review_task_compare_diff", "review_promise_drift", "review_linked_chapters", "review_linked_promises", "apply_rewrite_prefill"]
                            if linked_chapters
                            else ["run_longform_simulation_for_task"]
                        ),
                    }
                )

        return {
            "available": True,
            "task_links": task_links,
            "linked_task_count": sum(1 for item in task_links if item.get("status") == "linked"),
            "planned_only_task_count": sum(1 for item in task_links if item.get("status") != "linked"),
            "next_actions": (
                ["review_task_simulation_links"]
                if any(item.get("status") == "linked" for item in task_links)
                else ["run_longform_simulation"]
            ),
        }

    def _apply_continuity_override(self, payload: Dict[str, Any], overrides: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        chapter_key = str(int(payload.get("chapter_index", 0) or 0))
        override = dict(overrides.get(chapter_key) or {})
        merged = dict(payload)
        merged["override_state"] = override.get("override_state", "")
        merged["override_notes"] = override.get("notes", "")
        merged["override_issue_scope"] = list(override.get("issue_scope", []) or [])
        merged["override_updated_at"] = override.get("updated_at")
        merged["has_override"] = bool(override)
        return merged

    def _build_continuity_override_workbench(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        continuity = self._build_continuity_diff_workbench(metadata, simulation_report)
        if not continuity.get("available"):
            return {}
        chapter_compare = self._build_before_after_chapter_compare(metadata)
        overrides = self._continuity_overrides(metadata)
        chapter_trace = self._chapter_trace_with_promise_deltas(simulation_report)
        candidates: List[Dict[str, Any]] = []
        seen: set[int] = set()

        def _push(items: List[Dict[str, Any]], source: str) -> None:
            for item in items:
                chapter_index = int(item.get("chapter_index", 0) or 0)
                if not chapter_index or chapter_index in seen:
                    continue
                seen.add(chapter_index)
                merged = self._apply_continuity_override(item, overrides)
                merged["source"] = source
                candidates.append(merged)

        _push(list(chapter_compare.get("top_changed_chapters", [])), "compare")
        _push(list(continuity.get("drifting_characters", [])), "drift")
        _push(list(continuity.get("causal_breaks", [])), "causal")
        _push(list(continuity.get("promise_risks", [])), "promise")
        for item in chapter_trace[:8]:
            chapter_index = int(item.get("simulation_chapter_index", 0) or 0)
            if not chapter_index or chapter_index in seen:
                continue
            seen.add(chapter_index)
            merged = self._apply_continuity_override(
                {
                    "chapter_index": chapter_index,
                    "chapter_title": item.get("chapter_title"),
                    "scene_function": item.get("scene_function"),
                    "issue_codes": list(dict(item.get("evaluation") or {}).get("issue_codes", [])),
                    "chapter_task_id": str((item.get("chapter_task") or {}).get("chapter_task_id") or ""),
                    "arc_id": item.get("arc_id"),
                    "volume_id": item.get("volume_id"),
                },
                overrides,
            )
            merged["source"] = "trace"
            candidates.append(merged)
        for chapter_key in sorted(overrides.keys(), key=lambda value: int(value)):
            chapter_index = int(chapter_key)
            if chapter_index in seen:
                continue
            seen.add(chapter_index)
            merged = self._apply_continuity_override({"chapter_index": chapter_index}, overrides)
            merged["source"] = "override_only"
            candidates.append(merged)

        return {
            "available": True,
            "state_options": list(self.continuity_override_states),
            "override_count": sum(1 for item in candidates if item.get("has_override")),
            "candidate_chapters": candidates,
            "next_actions": (
                ["review_escalated_continuity", "jump_to_compare_chapter"]
                if any(item.get("override_state") == "escalate" for item in candidates)
                else (["review_compare_chapters"] if candidates else ["run_longform_simulation"])
            ),
        }

    def _build_continuity_diff_workbench(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_compare = self._build_before_after_chapter_compare(metadata)
        continuity_overrides = self._continuity_overrides(metadata)
        chapter_trace = {
            item.get("chapter_id"): dict(item)
            for item in simulation_report.get("chapter_trace", [])
            if item.get("chapter_id")
        }
        chapter_evaluations = list(simulation_report.get("chapter_evaluations", []))
        drifting_characters = []
        causal_breaks = []
        promise_risks = []
        for index, payload in enumerate(chapter_evaluations, start=1):
            issues = list(payload.get("issues", []))
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            trace = chapter_trace.get(chapter_id, {})
            issue_codes = [str(item.get("issue_code") or "") for item in issues if item.get("issue_code")]
            if "Q06" in issue_codes:
                drifting_characters.append(
                    self._apply_continuity_override(
                    {
                        "chapter_index": index,
                        "chapter_title": trace.get("chapter_title") or chapter_id,
                        "scene_function": trace.get("scene_function"),
                        "issue_codes": issue_codes,
                    },
                    continuity_overrides,
                    )
                )
            if "Q07" in issue_codes:
                causal_breaks.append(
                    self._apply_continuity_override(
                    {
                        "chapter_index": index,
                        "chapter_title": trace.get("chapter_title") or chapter_id,
                        "scene_function": trace.get("scene_function"),
                        "issue_codes": issue_codes,
                    },
                    continuity_overrides,
                    )
                )
            if "Q09" in issue_codes:
                promise_risks.append(
                    self._apply_continuity_override(
                    {
                        "chapter_index": index,
                        "chapter_title": trace.get("chapter_title") or chapter_id,
                        "issue_codes": issue_codes,
                    },
                    continuity_overrides,
                    )
                )
        top_changed_chapters = [
            self._apply_continuity_override(item, continuity_overrides)
            for item in list(chapter_compare.get("top_changed_chapters", []))
        ]
        return {
            "available": True,
            "simulation_freshness": self._simulation_freshness(metadata, simulation_report),
            "drifting_characters": drifting_characters[:6],
            "causal_breaks": causal_breaks[:6],
            "promise_risks": promise_risks[:6],
            "top_changed_chapters": top_changed_chapters[:6],
            "revision_compare": self._build_revision_compare(metadata, simulation_report),
            "next_actions": (
                ["re_simulate_for_continuity"]
                if drifting_characters or causal_breaks or promise_risks
                else (["review_before_after_compare"] if top_changed_chapters else ["continuity_stable"])
            ),
        }

    def _build_character_fidelity_remediation_framework(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {}
        chapter_trace = {
            str(item.get("chapter_id") or ""): dict(item)
            for item in simulation_report.get("chapter_trace", [])
            if str(item.get("chapter_id") or "")
        }
        chapter_evaluations = list(simulation_report.get("chapter_evaluations", []))
        q06_chapters: List[Dict[str, Any]] = []
        character_hotspots: Dict[str, Dict[str, Any]] = {}
        duty_hotspots: Dict[str, Dict[str, Any]] = {}
        low_fidelity_count = 0
        for index, payload in enumerate(chapter_evaluations, start=1):
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            trace = chapter_trace.get(chapter_id, {})
            score_block = dict(payload.get("scores") or {})
            issue_codes = [str(item.get("issue_code") or "") for item in payload.get("issues", []) if str(item.get("issue_code") or "")]
            fidelity_score = float(score_block.get("character_fidelity", 0.0) or 0.0)
            if fidelity_score < 0.34:
                low_fidelity_count += 1
            if "Q06" not in issue_codes and fidelity_score >= 0.34:
                continue
            chapter_index = int(
                dict(trace.get("chapter_task_execution_summary") or {}).get("series_chapter_index")
                or str(chapter_id).rsplit("_", 1)[-1]
                or index
            )
            actor_ids = [str(item) for item in ((trace.get("chosen_event") or {}).get("actors", []) or trace.get("actor_ids", []) or []) if str(item)]
            chapter_task = dict(trace.get("chapter_task") or {})
            duty_type = str(chapter_task.get("duty_type") or "unknown")
            q06_chapters.append(
                {
                    "chapter_index": chapter_index,
                    "chapter_id": chapter_id,
                    "chapter_title": trace.get("chapter_title") or chapter_id,
                    "scene_function": trace.get("scene_function"),
                    "duty_type": duty_type,
                    "actor_ids": actor_ids,
                    "character_fidelity": round(fidelity_score, 3),
                    "issue_codes": issue_codes,
                    "chapter_task_id": chapter_task.get("chapter_task_id"),
                }
            )
            duty_entry = duty_hotspots.setdefault(
                duty_type,
                {"duty_type": duty_type, "count": 0, "lowest_fidelity": 1.0},
            )
            duty_entry["count"] += 1
            duty_entry["lowest_fidelity"] = min(float(duty_entry["lowest_fidelity"]), fidelity_score)
            for actor_id in actor_ids:
                character_entry = character_hotspots.setdefault(
                    actor_id,
                    {"character_id": actor_id, "count": 0, "lowest_fidelity": 1.0},
                )
                character_entry["count"] += 1
                character_entry["lowest_fidelity"] = min(float(character_entry["lowest_fidelity"]), fidelity_score)
        ranked_characters = sorted(
            character_hotspots.values(),
            key=lambda item: (-int(item["count"]), float(item["lowest_fidelity"]), str(item["character_id"])),
        )
        ranked_duties = sorted(
            duty_hotspots.values(),
            key=lambda item: (-int(item["count"]), float(item["lowest_fidelity"]), str(item["duty_type"])),
        )
        q06_share = round(len(q06_chapters) / float(max(1, len(chapter_evaluations))), 3) if chapter_evaluations else 0.0
        return {
            "available": True,
            "status": "active" if q06_chapters else "clear",
            "q06_chapter_count": len(q06_chapters),
            "q06_chapter_share": q06_share,
            "low_fidelity_chapter_count": low_fidelity_count,
            "top_character_hotspots": [
                {
                    **item,
                    "lowest_fidelity": round(float(item["lowest_fidelity"]), 3),
                }
                for item in ranked_characters[:6]
            ],
            "top_duty_hotspots": [
                {
                    **item,
                    "lowest_fidelity": round(float(item["lowest_fidelity"]), 3),
                }
                for item in ranked_duties[:6]
            ],
            "priority_chapters": sorted(q06_chapters, key=lambda item: (float(item["character_fidelity"]), int(item["chapter_index"])))[:8],
            "suggested_asset_focus": [
                {"asset": "characters", "reason": "tighten vow/wound/destiny alignment for hotspot actors"},
                {"asset": "emotion_action_policies", "reason": "align reaction defaults with current pressure and duty"},
                {"asset": "scene_blueprints", "reason": "reduce duty-level drift in Q06-heavy task patterns"},
            ],
            "next_actions": (
                ["inspect_q06_priority_chapters", "tighten_character_cards", "tighten_emotion_action_policies"]
                if q06_chapters
                else ["character_fidelity_stable"]
            ),
        }

    def _build_steering_checkpoint_summary(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        checkpoints = [dict(item) for item in simulation_report.get("steering_checkpoints", [])]
        if not checkpoints:
            return {}
        return {
            "available": True,
            "count": len(checkpoints),
            "latest": checkpoints[-1],
            "scenario_kinds": sorted({str(item.get("scenario_kind") or "") for item in checkpoints if str(item.get("scenario_kind") or "")}),
        }

    def _build_replan_history_summary(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        history = [dict(item) for item in simulation_report.get("replan_history", [])]
        if not history:
            return {}
        return {
            "available": True,
            "count": len(history),
            "latest": history[-1],
            "entries": history[-10:],
        }

    def _build_memory_patch_summary_view(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        summary = dict(simulation_report.get("memory_patch_summary") or {})
        return {"available": bool(summary), **summary} if summary else {}

    def _character_label_lookup(self, worldpack_payload: Dict[str, Any], final_state: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        lookup: Dict[str, Dict[str, str]] = {}
        for character in worldpack_payload.get("characters", []) or []:
            payload = dict(character or {})
            character_id = str(payload.get("character_id") or "").strip()
            if not character_id:
                continue
            lookup[character_id] = {
                "label": str(payload.get("display_name") or payload.get("name") or character_id),
                "role": str(payload.get("role") or ""),
            }
        for character_id, payload in dict(final_state.get("characters") or {}).items():
            state_payload = dict(payload or {})
            lookup[str(character_id)] = {
                "label": str(
                    state_payload.get("name")
                    or state_payload.get("display_name")
                    or lookup.get(str(character_id), {}).get("label")
                    or character_id
                ),
                "role": str(state_payload.get("role") or lookup.get(str(character_id), {}).get("role") or ""),
            }
        return lookup

    def _issue_asset_priority_templates(self, issue_code: str) -> List[Dict[str, str]]:
        templates: Dict[str, List[Dict[str, str]]] = {
            "Q03": [
                {"asset_type": "scene_blueprint", "label": "场景蓝图", "reason": "先改 beats 和 required roles，把重复段落模板拆开。"},
                {"asset_type": "chapter_task", "label": "章节任务", "reason": "如果重复来自 duty/objective 雷同，再拆目标和 reveal budget。"},
                {"asset_type": "character_card", "label": "角色卡", "reason": "如果说话和反应还像同一个人，再补角色差异。"},
            ],
            "Q04": [
                {"asset_type": "scene_blueprint", "label": "场景蓝图", "reason": "先把解释改成对白、动作和环境触发的 scene beats。"},
                {"asset_type": "character_card", "label": "角色卡", "reason": "再收紧人物的 public self / shadow desire，让台词更含蓄。"},
                {"asset_type": "chapter_task", "label": "章节任务", "reason": "如果这一章承载过多说明，再收窄 objective。"},
            ],
            "Q05": [
                {"asset_type": "scene_blueprint", "label": "场景蓝图", "reason": "先补物件、动作、声响和空间触感。"},
                {"asset_type": "character_card", "label": "角色卡", "reason": "再补人物的动作习惯和身体反应，让细节落到人身上。"},
                {"asset_type": "chapter_task", "label": "章节任务", "reason": "如果细节不足来自章节负担过重，再调字数和 reveal budget。"},
            ],
            "Q09": [
                {"asset_type": "chapter_task", "label": "章节任务", "reason": "先改 objective / reveal budget / allow_terminal，修正章节收束速度。"},
                {"asset_type": "scene_blueprint", "label": "场景蓝图", "reason": "再补 hook、counter-reaction 和 payoff beat。"},
                {"asset_type": "character_card", "label": "角色卡", "reason": "如果角色愿望导致过早收束，再检查 vow / wound / destiny。"},
            ],
        }
        return [dict(item) for item in templates.get(issue_code, [])]

    def _asset_validation_panel(self, asset_type: str) -> Dict[str, str]:
        mapping = {
            "scene_blueprint": {
                "validation_panel": "compare",
                "validation_panel_label": "Compare",
                "validation_reason": "改完 scene beats 后回 Compare，看章节前后差异是否真的消掉了问题。",
            },
            "chapter_task": {
                "validation_panel": "task_linking",
                "validation_panel_label": "Task Linking",
                "validation_reason": "改完任务后回 Task Linking，看章节覆盖、promise drift 和 compare summary 是否回正。",
            },
            "character_card": {
                "validation_panel": "continuity",
                "validation_panel_label": "Continuity Diff",
                "validation_reason": "改完角色卡后回 Continuity，看角色/因果/承诺漂移是否稳定。",
            },
        }
        return dict(mapping.get(asset_type, {}))

    def _build_issue_priority_groups(self, chapter_heatmap: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        severity_order = {"critical": 0, "watch": 1, "stable": 2}
        groups: List[Dict[str, Any]] = []
        for issue_code in ("Q03", "Q04", "Q05", "Q09"):
            impacted = [
                dict(item)
                for item in chapter_heatmap
                if issue_code in list(item.get("issue_codes") or [])
            ]
            if not impacted:
                continue
            impacted = sorted(
                impacted,
                key=lambda item: (
                    severity_order.get(str(item.get("severity") or "stable"), 3),
                    float(item.get("overall_score", 0.0) or 0.0),
                    -int(item.get("issue_count", 0) or 0),
                ),
            )
            lead = impacted[0]
            recommendations: List[Dict[str, Any]] = []
            for priority, template in enumerate(self._issue_asset_priority_templates(issue_code), start=1):
                asset_type = template["asset_type"]
                recommendation: Dict[str, Any] = {
                    "priority": priority,
                    "asset_type": asset_type,
                    "label": template["label"],
                    "reason": template["reason"],
                    "available": False,
                    **self._asset_validation_panel(asset_type),
                    "chapter_index": lead.get("chapter_index"),
                    "chapter_title": lead.get("chapter_title", ""),
                }
                if asset_type == "scene_blueprint" and (lead.get("scene_id") or lead.get("scene_function")):
                    recommendation.update(
                        {
                            "available": True,
                            "scene_id": lead.get("scene_id", ""),
                            "scene_function": lead.get("scene_function", ""),
                            "target_label": lead.get("scene_id") or lead.get("scene_function") or "scene",
                        }
                    )
                elif asset_type == "chapter_task" and (lead.get("chapter_task_id") or lead.get("arc_id") or lead.get("volume_id")):
                    recommendation.update(
                        {
                            "available": True,
                            "chapter_task_id": lead.get("chapter_task_id", ""),
                            "arc_id": lead.get("arc_id", ""),
                            "volume_id": lead.get("volume_id", ""),
                            "target_label": lead.get("chapter_task_id") or lead.get("arc_id") or lead.get("volume_id") or "task",
                        }
                    )
                elif asset_type == "character_card" and list(lead.get("related_character_ids") or []):
                    recommendation.update(
                        {
                            "available": True,
                            "character_id": lead["related_character_ids"][0],
                            "character_ids": list(lead.get("related_character_ids") or []),
                            "target_label": (lead.get("related_characters") or [lead["related_character_ids"][0]])[0],
                        }
                    )
                recommendations.append(recommendation)
            primary = next((item for item in recommendations if item.get("available")), recommendations[0] if recommendations else {})
            groups.append(
                {
                    "issue_code": issue_code,
                    "label": ISSUE_TAXONOMY.get(issue_code, {}).get("label", issue_code),
                    "chapter_count": len(impacted),
                    "fix_hint": ISSUE_TAXONOMY.get(issue_code, {}).get("fix_hint", ""),
                    "primary_asset_type": primary.get("asset_type", ""),
                    "primary_asset": dict(primary),
                    "primary_validation_panel": primary.get("validation_panel", ""),
                    "primary_validation_panel_label": primary.get("validation_panel_label", ""),
                    "asset_priorities": recommendations,
                    "chapters": [
                        {
                            "chapter_index": item.get("chapter_index"),
                            "chapter_title": item.get("chapter_title"),
                            "scene_function": item.get("scene_function"),
                            "scene_id": item.get("scene_id"),
                            "chapter_task_id": item.get("chapter_task_id"),
                            "arc_id": item.get("arc_id"),
                            "volume_id": item.get("volume_id"),
                            "related_character_ids": list(item.get("related_character_ids") or []),
                            "related_characters": list(item.get("related_characters") or []),
                        }
                        for item in impacted[:3]
                    ],
                }
            )
        return groups

    def _decision_severity(self, decision: str) -> int:
        return {
            "pass": 0,
            "rewrite": 1,
            "block": 2,
        }.get(str(decision or "pass"), 0)

    def _resolve_related_character_ids(
        self,
        *,
        matched_scene: Dict[str, Any],
        role_to_character_ids: Dict[str, List[str]],
        character_lookup: Dict[str, Dict[str, str]],
    ) -> List[str]:
        related: List[str] = []
        for role_or_id in list((matched_scene or {}).get("required_roles") or []):
            key = str(role_or_id or "").strip()
            if not key:
                continue
            if key in role_to_character_ids:
                related.extend([str(item) for item in role_to_character_ids.get(key, []) if str(item)])
                continue
            if key in character_lookup:
                related.append(key)
        return list(dict.fromkeys(related))

    def _content_quality_window_metrics(self, worldpack_payload: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        existing = dict(simulation_report.get("content_quality_contract_window_metrics") or {})
        if existing:
            return existing
        target_chapters = int(
            ((simulation_report.get("longform_plan_snapshot") or {}).get("series_plan") or {}).get("total_chapter_target")
            or ((worldpack_payload.get("series_plan") or {}).get("total_chapter_target") or 0)
            or simulation_report.get("chapter_budget")
            or 0
        )
        return content_quality_window_metrics(
            chapter_report_payloads=list(simulation_report.get("chapter_evaluations") or []),
            world_metrics={"target_chapters": target_chapters},
        )

    def _content_quality_window_range(self, *, target_chapters: int, window_label: str) -> Dict[str, int]:
        contract = resolve_content_quality_contract(target_chapters=target_chapters)
        window = dict((contract.get("windows") or {}).get(window_label) or {})
        return {
            "start": int(window.get("start", 0) or 0),
            "end": int(window.get("end", 0) or 0),
        }

    def _contract_issue_codes_from_failed_checks(self, failed_checks: List[str]) -> List[str]:
        mapping = {
            "repetition_score_cap": "Q03",
            "rolling_window_repeat_breach": "Q03",
            "exposition_ratio_cap": "Q04",
            "dialogue_action_floor": "Q04",
            "detail_density_floor": "Q05",
            "mid_window_detail_breach": "Q05",
            "late_window_detail_breach": "Q05",
            "continuation_pressure_floor": "Q09",
            "premature_terminal_forbidden": "Q09",
            "late_window_q09_breach": "Q09",
            "q09_pre_end": "Q09",
        }
        ordered = []
        for issue_code in ("Q09", "Q05", "Q04", "Q03"):
            if any(mapping.get(str(name)) == issue_code for name in failed_checks):
                ordered.append(issue_code)
        return ordered

    def _content_quality_primary_asset_target(
        self,
        *,
        issue_code: str,
        targeted_chapters: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        base = issue_asset_target(issue_code)
        if issue_code in {"Q03", "Q04"}:
            ranked = sorted(
                [dict(item) for item in targeted_chapters if str(item.get("scene_id") or "") or str(item.get("scene_function") or "")],
                key=lambda item: (
                    0 if str(item.get("scene_id") or "") else 1,
                    -int(item.get("issue_count", 0) or 0),
                    float(item.get("overall_score", 0.0) or 0.0),
                ),
            )
            primary = ranked[0] if ranked else {}
            return {
                **base,
                "target_label": str(primary.get("scene_id") or primary.get("scene_function") or base.get("asset_label") or ""),
                "scene_id": str(primary.get("scene_id") or ""),
                "scene_function": str(primary.get("scene_function") or ""),
            }
        ranked_tasks = sorted(
            [dict(item) for item in targeted_chapters if str(item.get("chapter_task_id") or "") or str(item.get("arc_id") or "")],
            key=lambda item: (
                0 if str(item.get("chapter_task_id") or "") else 1,
                -int(item.get("issue_count", 0) or 0),
                float(item.get("overall_score", 0.0) or 0.0),
            ),
        )
        primary = ranked_tasks[0] if ranked_tasks else {}
        return {
            **base,
            "target_label": str(primary.get("chapter_task_id") or primary.get("arc_id") or base.get("asset_label") or ""),
            "chapter_task_id": str(primary.get("chapter_task_id") or ""),
            "arc_id": str(primary.get("arc_id") or ""),
            "volume_id": str(primary.get("volume_id") or ""),
        }

    def _scene_required_character_ids(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        scene_id: str,
    ) -> List[str]:
        scene = next(
            (
                dict(item or {})
                for item in list(worldpack_payload.get("scene_blueprints") or [])
                if str((dict(item or {})).get("scene_id") or "") == str(scene_id or "")
            ),
            {},
        )
        character_ids = {
            str((dict(item or {})).get("character_id") or "")
            for item in list(worldpack_payload.get("characters") or [])
            if str((dict(item or {})).get("character_id") or "")
        }
        resolved: List[str] = []
        for role_or_id in list(scene.get("required_roles") or []):
            candidate = str(role_or_id or "")
            if candidate in character_ids and candidate not in resolved:
                resolved.append(candidate)
        return resolved

    def _content_quality_secondary_asset_targets(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        issue_code: str,
        targeted_chapters: List[Dict[str, Any]],
        primary_asset_target: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        primary_scene_id = str(primary_asset_target.get("scene_id") or "")
        primary_scene_function = str(primary_asset_target.get("scene_function") or "")
        if issue_code in {"Q03", "Q04"} and primary_scene_function:
            return [
                {
                    "asset_type": "scene_realization_contracts",
                    "asset_label": "场景实现合同",
                    "validation_panel": "compare",
                    "validation_panel_label": "Compare",
                    "target_label": f'default::{primary_scene_function}',
                    "contract_id": "default",
                    "scene_function": primary_scene_function,
                },
                {
                    "asset_type": "emotion_action_policies",
                    "asset_label": "情绪动作策略",
                    "validation_panel": "compare",
                    "validation_panel_label": "Compare",
                    "target_label": f'default::{primary_scene_function}',
                    "policy_id": "default",
                    "scene_function": primary_scene_function,
                },
            ]

        character_ids: List[str] = []
        if primary_scene_id:
            character_ids.extend(self._scene_required_character_ids(worldpack_payload=worldpack_payload, scene_id=primary_scene_id))
        for chapter in targeted_chapters:
            for item in chapter.get("related_character_ids", []) or []:
                candidate = str(item or "")
                if candidate and candidate not in character_ids:
                    character_ids.append(candidate)
        if issue_code == "Q03" and character_ids:
            character_id = character_ids[0]
            return [
                {
                    "asset_type": "voice_profiles",
                    "asset_label": "角色声音配置",
                    "validation_panel": "compare",
                    "validation_panel_label": "Compare",
                    "target_label": character_id,
                    "character_id": character_id,
                },
                {
                    "asset_type": "response_cadence_profiles",
                    "asset_label": "对白节奏配置",
                    "validation_panel": "compare",
                    "validation_panel_label": "Compare",
                    "target_label": character_id,
                    "character_id": character_id,
                },
            ]
        if issue_code == "Q04" and character_ids:
            character_id = character_ids[0]
            return [
                {
                    "asset_type": "character_card",
                    "asset_label": "角色卡",
                    "validation_panel": "continuity",
                    "validation_panel_label": "Continuity Diff",
                    "target_label": character_id,
                    "character_id": character_id,
                },
                {
                    "asset_type": "response_cadence_profiles",
                    "asset_label": "对白节奏配置",
                    "validation_panel": "compare",
                    "validation_panel_label": "Compare",
                    "target_label": character_id,
                    "character_id": character_id,
                },
            ]
        if issue_code == "Q03":
            return []
        if issue_code == "Q04":
            return []
        if issue_code == "Q09":
            for chapter in targeted_chapters:
                arc_id = str(chapter.get("arc_id") or "")
                if arc_id:
                    return [
                        {
                            "asset_type": "arc_plan",
                            "asset_label": "弧线计划",
                            "validation_panel": "task_linking",
                            "validation_panel_label": "Task Linking",
                            "target_label": arc_id,
                            "arc_id": arc_id,
                            "volume_id": str(chapter.get("volume_id") or ""),
                        }
                    ]
        return []

    def _find_arc_payload(self, worldpack_payload: Dict[str, Any], arc_id: str) -> Dict[str, Any]:
        for arc in list(worldpack_payload.get("arc_plans") or []):
            if str((dict(arc or {})).get("arc_id") or "") == str(arc_id or ""):
                return dict(arc or {})
        return {}

    def _content_quality_suggested_field_edits(
        self,
        *,
        worldpack_payload: Dict[str, Any],
        issue_code: str,
        primary_asset_target: Dict[str, Any],
        secondary_asset_targets: List[Dict[str, Any]],
        window_label: str,
    ) -> List[Dict[str, Any]]:
        edits: List[Dict[str, Any]] = []
        if issue_code == "Q03":
            scene_id = str(primary_asset_target.get("scene_id") or primary_asset_target.get("target_label") or "")
            if scene_id:
                edits.extend(
                    [
                        {
                            "path": f'scene_blueprints[scene_id="{scene_id}"].quality_contract.variation_axes',
                            "operation": "replace",
                            "suggested_value": ["voice", "movement", "object_state", "information_reveal", "consequence"],
                            "reason": "给同一窗口里的连续章节提供更稳定的 scene-level variation 轴。",
                        },
                        {
                            "path": f'scene_blueprints[scene_id="{scene_id}"].beats_template',
                            "operation": "rewrite",
                            "suggested_value": ["切换动作触发", "切换物件状态", "切换信息揭示", "切换后果落点"],
                            "reason": "避免连续章节围绕同一 motif 反复回声。",
                        },
                    ]
                )
            for secondary_asset_target in secondary_asset_targets:
                scene_function = str(secondary_asset_target.get("scene_function") or primary_asset_target.get("scene_function") or "")
                character_id = str(secondary_asset_target.get("character_id") or "")
                if secondary_asset_target.get("asset_type") == "scene_realization_contracts" and scene_function:
                    edits.extend(
                        [
                            {
                                "path": f'scene_realization_contracts["default"].scene_openings.{scene_function}',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组更依赖具体物件、空间状态和信息落点的 opening。",
                                    "避免每章都用同一种抽象暗潮开场。",
                                ],
                                "reason": "让同一 scene function 在窗口内拥有更强的 opening 变体。",
                            },
                            {
                                "path": f'scene_realization_contracts["default"].scene_hooks.{scene_function}',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组更具体的 hook，直接把下一章的问题、代价或证据推到台前。"
                                ],
                                "reason": "避免章节尾声总是靠相似的抽象回响撑住。",
                            },
                        ]
                    )
                if secondary_asset_target.get("asset_type") == "emotion_action_policies" and scene_function:
                    edits.extend(
                        [
                            {
                                "path": f'emotion_action_policies["default"].action_map.{scene_function}.entry',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组以手势、物件和位置变化触发的 entry 动作。"
                                ],
                                "reason": "降低窗口内 entry 动作的重复形状。",
                            },
                            {
                                "path": f'emotion_action_policies["default"].action_map.{scene_function}.pressure',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组更具体的 pressure 动作，不再只靠抽象停顿和压场。"
                                ],
                                "reason": "让压力位更多通过动作差异推进，而不是同一句法回声。",
                            },
                        ]
                    )
                if secondary_asset_target.get("asset_type") == "voice_profiles" and character_id:
                    edits.extend(
                        [
                            {
                                "path": f'voice_profiles["{character_id}"].opening_style',
                                "operation": "expand",
                                "suggested_value": ["补一组与当前窗口主冲突不同的开场句式，避免同一章法反复开口。"],
                                "reason": "降低窗口内首句雷同，给 compare 面板更明显的 voice diff。",
                            },
                            {
                                "path": f'voice_profiles["{character_id}"].signature_replies',
                                "operation": "expand",
                                "suggested_value": ["补一组与当前窗口主冲突不同的应答句式，减少重复回声。"],
                                "reason": "降低窗口内对白雷同，给 compare 面板更明显的 voice diff。",
                            },
                        ]
                    )
                if secondary_asset_target.get("asset_type") == "response_cadence_profiles" and character_id:
                    edits.extend(
                        [
                            {
                                "path": f'response_cadence_profiles["{character_id}"].reaction_lines.entry',
                                "operation": "expand",
                                "suggested_value": ["补一组更依赖动作、物件和停顿的反应句。"],
                                "reason": "让窗口内 reaction 不再反复使用同一种解释式停顿。",
                            },
                            {
                                "path": f'response_cadence_profiles["{character_id}"].reply_lines.pressure',
                                "operation": "expand",
                                "suggested_value": ["补一组更短、更具压迫感的 pressure reply。"],
                                "reason": "减少压力位对白的解释感，压低 exposition ratio。",
                            },
                        ]
                    )
        elif issue_code == "Q04":
            scene_id = str(primary_asset_target.get("scene_id") or primary_asset_target.get("target_label") or "")
            if scene_id:
                edits.extend(
                    [
                        {
                            "path": f'scene_blueprints[scene_id="{scene_id}"].quality_contract.dialogue_pressure',
                            "operation": "replace",
                            "suggested_value": "high",
                            "reason": "提高 scene-facing dialogue pressure，减少解释句比重。",
                        },
                        {
                            "path": f'scene_blueprints[scene_id="{scene_id}"].quality_contract.detail_anchor_types',
                            "operation": "replace",
                            "suggested_value": ["object", "sound", "body_motion", "ambient_signal", "object_state"],
                            "reason": "强制每章用物件/声响/身体动作承接情绪，而不是只靠解释。",
                        },
                    ]
                )
            chapter_task_id = str(primary_asset_target.get("chapter_task_id") or "")
            arc_id = str(primary_asset_target.get("arc_id") or "")
            if chapter_task_id and arc_id:
                edits.append(
                    {
                        "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].quality_contract.max_exposition_ratio',
                        "operation": "replace",
                        "suggested_value": 0.48,
                        "reason": "收紧当前窗口任务允许的 exposition 上限。",
                    }
                )
            for secondary_asset_target in secondary_asset_targets:
                scene_function = str(secondary_asset_target.get("scene_function") or primary_asset_target.get("scene_function") or "")
                character_id = str(secondary_asset_target.get("character_id") or "")
                if secondary_asset_target.get("asset_type") == "scene_realization_contracts" and scene_function:
                    edits.extend(
                        [
                            {
                                "path": f'scene_realization_contracts["default"].scene_openings.{scene_function}',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组更具体的 opening，把物件、位置、关系债直接推到眼前。"
                                ],
                                "reason": "压低 opening 里的说明性总结句。",
                            },
                            {
                                "path": f'scene_realization_contracts["default"].scene_hooks.{scene_function}',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组更直接的 hook，减少抽象的情绪总结。",
                                ],
                                "reason": "让章节结尾更像下一步动作，而不是解释性收束。",
                            },
                        ]
                    )
                if secondary_asset_target.get("asset_type") == "emotion_action_policies" and scene_function:
                    edits.extend(
                        [
                            {
                                "path": f'emotion_action_policies["default"].action_map.{scene_function}.pressure',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组更短、更具体的 pressure 动作。"
                                ],
                                "reason": "让压力位先靠动作落地，再让对白补足，不靠说明句撑场。"
                            },
                            {
                                "path": f'emotion_action_policies["default"].action_map.{scene_function}.pivot',
                                "operation": "replace",
                                "suggested_value": [
                                    "补三组通过物件、身体反应和空间位移完成 pivot 的动作。"
                                ],
                                "reason": "减少 pivot 位的解释性转折句。"
                            },
                        ]
                    )
                if secondary_asset_target.get("asset_type") == "character_card" and character_id:
                    edits.extend(
                        [
                            {
                                "path": f'characters[character_id="{character_id}"].wound_profile.defense_style',
                                "operation": "rewrite",
                                "suggested_value": "让动作、拒答和场面压力承担冲突，不靠长段解释维持。",
                                "reason": "如果角色卡本身把冲突压成说明，就会持续推高 Q04。",
                            },
                            {
                                "path": f'characters[character_id="{character_id}"].speech_traits',
                                "operation": "replace",
                                "suggested_value": ["短句", "拒答", "先让动作承接情绪"],
                                "reason": "让角色说话更短、更含蓄，减少解释句惯性。",
                            },
                            {
                                "path": f'characters[character_id="{character_id}"].action_traits',
                                "operation": "replace",
                                "suggested_value": ["先停手", "看物件", "用动作把话堵回去"],
                                "reason": "把情绪和冲突压到动作上，而不是直接说透。",
                            },
                        ]
                    )
                if secondary_asset_target.get("asset_type") == "response_cadence_profiles" and character_id:
                    edits.extend(
                        [
                            {
                                "path": f'response_cadence_profiles["{character_id}"].reaction_lines.pressure',
                                "operation": "expand",
                                "suggested_value": ["补一组更短、少解释、更多动作停顿的 pressure 反应句。"],
                                "reason": "让对白压力位更依赖反应而不是解释。",
                            },
                            {
                                "path": f'response_cadence_profiles["{character_id}"].reply_lines.pivot',
                                "operation": "expand",
                                "suggested_value": ["补一组用拒答、反问、短促承认来完成 pivot 的 reply。"],
                                "reason": "减少 pivot 位的说明性总结句。",
                            },
                        ]
                    )
        elif issue_code == "Q05":
            scene_id = str(primary_asset_target.get("scene_id") or primary_asset_target.get("target_label") or "")
            if scene_id:
                edits.extend(
                    [
                        {
                            "path": f'scene_blueprints[scene_id="{scene_id}"].quality_contract.detail_anchor_types',
                            "operation": "replace",
                            "suggested_value": ["object", "sound", "body_motion", "ambient_signal", "object_state"],
                            "reason": "让同类场景稳定输出可感知的物件、声响、身体动作和环境细节。",
                        },
                        {
                            "path": f'scene_blueprints[scene_id="{scene_id}"].beats_template',
                            "operation": "rewrite",
                            "suggested_value": ["物件状态变化", "空间细节落地", "身体动作承压", "余波追上来"],
                            "reason": "避免章节只剩结论和说明，把细节落到 beat 级别。",
                        },
                    ]
                )
            chapter_task_id = str(primary_asset_target.get("chapter_task_id") or "")
            arc_id = str(primary_asset_target.get("arc_id") or "")
            if chapter_task_id and arc_id:
                edits.append(
                    {
                        "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].quality_contract.min_detail_density',
                        "operation": "replace",
                        "suggested_value": 0.045,
                        "reason": "把当前任务的最小 detail density 抬到 200 章诊断合同标准。",
                    }
                )
        elif issue_code == "Q09":
            chapter_task_id = str(primary_asset_target.get("chapter_task_id") or "")
            arc_id = str(primary_asset_target.get("arc_id") or "")
            if chapter_task_id and arc_id:
                edits.extend(
                    [
                        {
                            "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].quality_contract.continuation_pressure_required',
                            "operation": "replace",
                            "suggested_value": True,
                            "reason": "强制当前任务结尾必须推出下一章问题。",
                        },
                        {
                            "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].quality_contract.delayed_payoff_window',
                            "operation": "replace",
                            "suggested_value": {"min_chapters": 1, "max_chapters": 4},
                            "reason": "把 payoff 拉回更近窗口，减少 late 窗口掉速。",
                        },
                        {
                            "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].allow_terminal',
                            "operation": "replace",
                            "suggested_value": False,
                            "reason": "在非最终收束阶段收紧 premature terminal。",
                        },
                        {
                            "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].objective',
                            "operation": "rewrite",
                            "suggested_value": f"保持 {window_label} 窗口的 continuation pressure，结尾必须把下一章问题推出去。",
                            "reason": "让任务目标直接承担 Q09 修复，而不是留给 writer 自行解释。",
                        },
                    ]
                )
                arc_payload = self._find_arc_payload(worldpack_payload, arc_id)
                arc_promise_ids = [
                    str(item.get("promise_id") or "")
                    for item in list(arc_payload.get("arc_promises") or [])
                    if str(item.get("promise_id") or "")
                ]
                if arc_promise_ids:
                    edits.append(
                        {
                            "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].promise_targets',
                            "operation": "replace",
                            "suggested_value": arc_promise_ids,
                            "reason": "让当前任务直接绑定本弧 promises，减少后段没有可追账目标的空转。",
                        }
                    )
                edits.append(
                    {
                        "path": f'arc_plans[arc_id="{arc_id}"].chapter_tasks[chapter_task_id="{chapter_task_id}"].notes',
                        "operation": "append",
                        "suggested_value": f"contract_q09_repair_window={window_label}",
                        "reason": "把这次 repair campaign 的窗口语义回写到任务备注里，便于 compare/task_linking 复盘。",
                    }
                )
            secondary_arc_id = str((secondary_asset_targets[0] if secondary_asset_targets else {}).get("arc_id") or "")
            if secondary_arc_id:
                edits.append(
                    {
                        "path": f'arc_plans[arc_id="{secondary_arc_id}"].completion_conditions',
                        "operation": "replace",
                        "suggested_value": ["main_conflict_shifted", "new_debt_or_promise_opened", "next_chapter_hook_intensified"],
                        "reason": "让同弧多章触发 Q09 时，弧线计划本身也承担 hook 义务。",
                    }
                )
        return edits

    def _content_quality_suggested_actions(
        self,
        *,
        issue_code: str,
        window_label: str,
        targeted_chapter_indices: List[int],
        secondary_asset_targets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if issue_code == "Q03":
            actions = [
                {
                    "action": "expand_scene_variation_axes",
                    "summary": "扩 scene-level variation 轴，优先打散连续章节里的同一 motif 回声。",
                    "details": f"窗口 {window_label} · 章节 {targeted_chapter_indices[:6]}",
                },
                {
                    "action": "rewrite_beats_for_rotation",
                    "summary": "重写 beats_template，让动作/物件/信息揭示在连续章节里轮换。",
                    "details": "不要让同一 scene family 连续用同一种 entry-pressure-pivot 形状。",
                },
            ]
            for secondary_asset_target in secondary_asset_targets:
                if secondary_asset_target.get("asset_type") == "scene_realization_contracts":
                    actions.append(
                        {
                            "action": "diversify_scene_realization_contracts",
                            "summary": "为目标 scene function 扩 opening / hook 变体，减少抽象性重复开场和结尾。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
                if secondary_asset_target.get("asset_type") == "emotion_action_policies":
                    actions.append(
                        {
                            "action": "diversify_emotion_action_policies",
                            "summary": "为目标 scene function 扩 entry / pressure 动作变体，让重复不再只靠对白承接。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
                if secondary_asset_target.get("asset_type") == "voice_profiles":
                    actions.append(
                        {
                            "action": "differentiate_voice_profiles",
                            "summary": "为目标角色补一组不重复的 signature replies / openings。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
                if secondary_asset_target.get("asset_type") == "response_cadence_profiles":
                    actions.append(
                        {
                            "action": "diversify_response_cadence",
                            "summary": "为目标角色补一组 entry / pressure 的 reaction 和 reply 节奏变体。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
            return actions
        if issue_code == "Q04":
            actions = [
                {
                    "action": "raise_dialogue_pressure",
                    "summary": "提高 scene 的 dialogue pressure，让冲突更多通过对白和动作推进。",
                    "details": f"窗口 {window_label} · 章节 {targeted_chapter_indices[:6]}",
                },
                {
                    "action": "expand_detail_anchors",
                    "summary": "扩 detail anchors，用物件/声响/身体动作承接情绪。",
                    "details": "优先压低 exposition ratio，而不是只补字数。",
                },
            ]
            for secondary_asset_target in secondary_asset_targets:
                if secondary_asset_target.get("asset_type") == "scene_realization_contracts":
                    actions.append(
                        {
                            "action": "tighten_scene_realization_contracts",
                            "summary": "把 opening / hook 从说明句改成更具体的物件、位置与后果推进。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
                if secondary_asset_target.get("asset_type") == "emotion_action_policies":
                    actions.append(
                        {
                            "action": "concretize_emotion_action_policies",
                            "summary": "让 pressure / pivot 位先靠动作落地，再由对白补足冲突。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
                if secondary_asset_target.get("asset_type") == "character_card":
                    actions.append(
                        {
                            "action": "tighten_character_card",
                            "summary": "检查目标角色的 vow / wound 是否在逼章节靠解释维持。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
                if secondary_asset_target.get("asset_type") == "response_cadence_profiles":
                    actions.append(
                        {
                            "action": "shorten_response_cadence",
                            "summary": "收紧目标角色的 reaction / reply 节奏，让说明句退到动作后面。",
                            "details": str(secondary_asset_target.get("target_label") or ""),
                        }
                    )
            return actions
        return [
            {
                "action": "tighten_continuation_pressure",
                "summary": "强制任务结尾推出下一章问题，禁止后段无钩子收束。",
                "details": f"窗口 {window_label} · 章节 {targeted_chapter_indices[:6]}",
            },
            {
                "action": "rebalance_delayed_payoff",
                "summary": "把 payoff 拉回更近窗口，并收紧 allow_terminal。",
                "details": "优先减少 late window 的 Q09 breach。",
            },
            {
                "action": "raise_arc_level_hook_obligation",
                "summary": "同弧多章持续触发 Q09 时，把 hook 义务提升到 arc plan。",
                "details": str((secondary_asset_targets[0] if secondary_asset_targets else {}).get("target_label") or ""),
            },
        ]

    def _build_content_quality_repair_workbench(
        self,
        worldpack_payload: Dict[str, Any],
        simulation_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not simulation_report:
            return {"available": False, "windows": {}, "default_campaign": {}, "campaigns": [], "next_actions": []}
        window_metrics = self._content_quality_window_metrics(worldpack_payload, simulation_report)
        if not bool(window_metrics.get("enabled")):
            return {"available": False, "windows": {}, "default_campaign": {}, "campaigns": [], "next_actions": []}
        creative_cockpit = dict(
            simulation_report.get("creative_cockpit")
            or self._build_creative_cockpit(worldpack_payload, simulation_report)
        )
        chapter_heatmap = [dict(item) for item in list((creative_cockpit.get("chapter_heatmap") or {}).get("chapters") or [])]
        issue_priority_groups = {
            str(item.get("issue_code") or ""): dict(item)
            for item in list((creative_cockpit.get("chapter_heatmap") or {}).get("issue_priority_groups") or [])
            if str(item.get("issue_code") or "")
        }
        target_chapters = int(
            ((simulation_report.get("longform_plan_snapshot") or {}).get("series_plan") or {}).get("total_chapter_target")
            or ((worldpack_payload.get("series_plan") or {}).get("total_chapter_target") or 0)
            or simulation_report.get("chapter_budget")
            or 0
        )
        contract_failed_chapters = [dict(item) for item in list(window_metrics.get("contract_failed_chapters") or [])]
        campaign_order = {"late": 0, "mid": 1, "early": 2}
        issue_order = {"Q09": 0, "Q04": 1, "Q03": 2}
        campaigns: List[Dict[str, Any]] = []
        windows_payload: Dict[str, Any] = {}

        for window_label in ("early", "mid", "late"):
            window_range = self._content_quality_window_range(target_chapters=target_chapters, window_label=window_label)
            start = int(window_range.get("start", 0) or 0)
            end = int(window_range.get("end", 0) or 0)
            window_failed = [
                item
                for item in contract_failed_chapters
                if start <= int(item.get("chapter_index", 0) or 0) <= end
            ]
            window_issue_codes = []
            for item in window_failed:
                for issue_code in self._contract_issue_codes_from_failed_checks(list(item.get("failed_checks") or [])):
                    if issue_code in {"Q03", "Q04", "Q09"} and issue_code not in window_issue_codes:
                        window_issue_codes.append(issue_code)
            metric_key = {
                "early": "early_window_q03_q04_share",
                "mid": "mid_window_repeat_breach_rate",
                "late": "late_window_q09_breach_rate",
            }.get(window_label, "")
            windows_payload[window_label] = {
                "window_label": window_label,
                "window_range": {"start": start, "end": end},
                "metrics": {
                    "early_window_q03_q04_share": float(window_metrics.get("early_window_q03_q04_share", 0.0) or 0.0),
                    "mid_window_repeat_breach_rate": float(window_metrics.get("mid_window_repeat_breach_rate", 0.0) or 0.0),
                    "mid_window_exposition_breach_rate": float(window_metrics.get("mid_window_exposition_breach_rate", 0.0) or 0.0),
                    "late_window_q09_breach_rate": float(window_metrics.get("late_window_q09_breach_rate", 0.0) or 0.0),
                },
                "thresholds": dict(window_metrics.get("thresholds") or {}),
                "failed_chapter_count": len(window_failed),
                "issue_codes": window_issue_codes,
                "primary_metric_key": metric_key,
            }
            for issue_code in window_issue_codes:
                targeted_chapters = [
                    dict(item)
                    for item in chapter_heatmap
                    if start <= int(item.get("chapter_index", 0) or 0) <= end
                    and issue_code in list(item.get("issue_codes") or [])
                ]
                issue_failed = [
                    item
                    for item in window_failed
                    if issue_code in self._contract_issue_codes_from_failed_checks(list(item.get("failed_checks") or []))
                ]
                targeted_indices = sorted(
                    {
                        int(item.get("chapter_index", 0) or 0)
                        for item in issue_failed
                        if int(item.get("chapter_index", 0) or 0) > 0
                    }
                    or {
                        int(item.get("chapter_index", 0) or 0)
                        for item in targeted_chapters
                        if int(item.get("chapter_index", 0) or 0) > 0
                    }
                )
                if not targeted_indices:
                    continue
                baseline_worst_decision = max(
                    (str(item.get("decision") or "pass") for item in issue_failed),
                    key=self._decision_severity,
                    default=max(
                        (str(item.get("decision") or "pass") for item in targeted_chapters),
                        key=self._decision_severity,
                        default="pass",
                    ),
                )
                average_score = round(
                    sum(float(item.get("overall_score", 0.0) or 0.0) for item in targeted_chapters) / float(max(1, len(targeted_chapters))),
                    3,
                )
                primary_asset_target = self._content_quality_primary_asset_target(
                    issue_code=issue_code,
                    targeted_chapters=targeted_chapters,
                )
                secondary_asset_targets = self._content_quality_secondary_asset_targets(
                    worldpack_payload=worldpack_payload,
                    issue_code=issue_code,
                    targeted_chapters=targeted_chapters,
                    primary_asset_target=primary_asset_target,
                )
                breach_kind = {
                    ("early", "Q03"): "early_window_q03_q04_share",
                    ("early", "Q04"): "early_window_q03_q04_share",
                    ("mid", "Q03"): "mid_window_repeat_breach_rate",
                    ("mid", "Q04"): "mid_window_exposition_breach_rate",
                    ("late", "Q09"): "late_window_q09_breach_rate",
                }.get((window_label, issue_code), str((issue_failed[0].get("failed_checks") or [""])[0] if issue_failed else ""))
                suggested_field_edits = self._content_quality_suggested_field_edits(
                    worldpack_payload=worldpack_payload,
                    issue_code=issue_code,
                    primary_asset_target=primary_asset_target,
                    secondary_asset_targets=secondary_asset_targets,
                    window_label=window_label,
                )
                suggested_actions = self._content_quality_suggested_actions(
                    issue_code=issue_code,
                    window_label=window_label,
                    targeted_chapter_indices=targeted_indices,
                    secondary_asset_targets=secondary_asset_targets,
                )
                strategy_bundle = build_strategy_bundle(
                    issue_codes=([issue_code] + [item for item in window_issue_codes if item != issue_code]),
                    window_label=window_label,
                    primary_asset_target=primary_asset_target,
                    secondary_asset_targets=secondary_asset_targets,
                    suggested_actions=suggested_actions,
                    suggested_field_edits=suggested_field_edits,
                    targeted_chapter_indices=targeted_indices,
                )
                group = dict(issue_priority_groups.get(issue_code) or {})
                repair_loop_context = {
                    "issue_code": issue_code,
                    "issue_label": ISSUE_TAXONOMY.get(issue_code, {}).get("label", issue_code),
                    "asset_type": primary_asset_target.get("asset_type", ""),
                    "asset_label": primary_asset_target.get("asset_label", ""),
                    "target_label": primary_asset_target.get("target_label", ""),
                    "validation_panel": primary_asset_target.get("validation_panel", ""),
                    "validation_panel_label": primary_asset_target.get("validation_panel_label", ""),
                    "window_label": window_label,
                    "window_range_start": start,
                    "window_range_end": end,
                    "window_breach_kind": breach_kind,
                    "baseline_issue_count": len(issue_failed),
                    "baseline_worst_decision": baseline_worst_decision,
                    "targeted_chapters": [
                        {
                            "chapter_index": index,
                            "chapter_title": next(
                                (item.get("chapter_title", "") for item in targeted_chapters if int(item.get("chapter_index", 0) or 0) == index),
                                "",
                            ),
                        }
                        for index in targeted_indices
                    ],
                    "targeted_chapter_indices": targeted_indices,
                    "contract_failed_checks": sorted(
                        {
                            str(name)
                            for item in issue_failed
                            for name in list(item.get("failed_checks") or [])
                            if str(name)
                        }
                    ),
                    "scene_id": primary_asset_target.get("scene_id", ""),
                    "scene_function": primary_asset_target.get("scene_function", ""),
                    "chapter_task_id": primary_asset_target.get("chapter_task_id", ""),
                    "arc_id": primary_asset_target.get("arc_id", ""),
                    "volume_id": primary_asset_target.get("volume_id", ""),
                }
                campaigns.append(
                    {
                        "campaign_id": f"content_quality::{window_label}::{issue_code}",
                        "window_label": window_label,
                        "window_range": {"start": start, "end": end},
                        "issue_code": issue_code,
                        "issue_label": ISSUE_TAXONOMY.get(issue_code, {}).get("label", issue_code),
                        "breach_kind": breach_kind,
                        "targeted_chapter_indices": targeted_indices,
                        "baseline_issue_count": len(issue_failed),
                        "baseline_worst_decision": baseline_worst_decision,
                        "failed_chapter_count": len(issue_failed),
                        "average_score": average_score,
                        "primary_asset_type": primary_asset_target.get("asset_type", ""),
                        "primary_asset_target": primary_asset_target,
                        "secondary_asset_target": dict(secondary_asset_targets[0]) if secondary_asset_targets else {},
                        "secondary_asset_targets": secondary_asset_targets,
                        "validation_panel": primary_asset_target.get("validation_panel", ""),
                        "validation_panel_label": primary_asset_target.get("validation_panel_label", ""),
                        "suggested_actions": suggested_actions,
                        "suggested_field_edits": suggested_field_edits,
                        "strategy_bundle_id": strategy_bundle.get("strategy_bundle_id", ""),
                        "strategy_bundle": strategy_bundle,
                        "current_window_metrics": {
                            **dict(window_metrics.get("thresholds") or {}),
                            "early_window_q03_q04_share": float(window_metrics.get("early_window_q03_q04_share", 0.0) or 0.0),
                            "mid_window_repeat_breach_rate": float(window_metrics.get("mid_window_repeat_breach_rate", 0.0) or 0.0),
                            "mid_window_exposition_breach_rate": float(window_metrics.get("mid_window_exposition_breach_rate", 0.0) or 0.0),
                            "late_window_q09_breach_rate": float(window_metrics.get("late_window_q09_breach_rate", 0.0) or 0.0),
                        },
                        "rerun_scope": {
                            "mode": "full_100_rerun",
                            "reason": "longform_state_dependency",
                            "focus_window": window_label,
                            "compare_mode": "window_slice",
                        },
                        "repair_loop_context": repair_loop_context,
                        "group_primary_asset_type": group.get("primary_asset_type", ""),
                    }
                )

        if not campaigns:
            drilldown = self._build_simulation_drilldown(simulation_report)
            quality_histogram = [dict(item) for item in list((drilldown.get("quality_pass_summary") or {}).get("action_histogram") or [])]
            q03_action_count = sum(
                int(item.get("count", 0) or 0)
                for item in quality_histogram
                if str(item.get("action") or "").startswith("q03_")
            )
            if q03_action_count > 0:
                targeted_chapters = [
                    {
                        **dict(item),
                        "issue_count": 1,
                        "scene_id": str(item.get("scene_id") or ""),
                        "scene_function": str(item.get("scene_function") or ""),
                    }
                    for item in list(drilldown.get("weakest_chapters") or drilldown.get("chapter_breakdown") or [])[:3]
                ]
                targeted_indices = [
                    int(item.get("chapter_index", 0) or 0)
                    for item in targeted_chapters
                    if int(item.get("chapter_index", 0) or 0) > 0
                ]
                if targeted_indices:
                    issue_code = "Q03"
                    window_label = "early" if max(targeted_indices) <= max(1, int(target_chapters * 0.35 or 1)) else "mid"
                    window_range = self._content_quality_window_range(target_chapters=target_chapters, window_label=window_label)
                    primary_asset_target = self._content_quality_primary_asset_target(
                        issue_code=issue_code,
                        targeted_chapters=targeted_chapters,
                    )
                    secondary_asset_targets = self._content_quality_secondary_asset_targets(
                        worldpack_payload=worldpack_payload,
                        issue_code=issue_code,
                        targeted_chapters=targeted_chapters,
                        primary_asset_target=primary_asset_target,
                    )
                    suggested_field_edits = self._content_quality_suggested_field_edits(
                        worldpack_payload=worldpack_payload,
                        issue_code=issue_code,
                        primary_asset_target=primary_asset_target,
                        secondary_asset_targets=secondary_asset_targets,
                        window_label=window_label,
                    )
                    suggested_actions = self._content_quality_suggested_actions(
                        issue_code=issue_code,
                        window_label=window_label,
                        targeted_chapter_indices=targeted_indices,
                        secondary_asset_targets=secondary_asset_targets,
                    )
                    strategy_bundle = build_strategy_bundle(
                        issue_codes=[issue_code],
                        window_label=window_label,
                        primary_asset_target=primary_asset_target,
                        secondary_asset_targets=secondary_asset_targets,
                        suggested_actions=suggested_actions,
                        suggested_field_edits=suggested_field_edits,
                        targeted_chapter_indices=targeted_indices,
                    )
                    repair_loop_context = {
                        "issue_code": issue_code,
                        "issue_label": ISSUE_TAXONOMY.get(issue_code, {}).get("label", issue_code),
                        "asset_type": primary_asset_target.get("asset_type", ""),
                        "asset_label": primary_asset_target.get("asset_label", ""),
                        "target_label": primary_asset_target.get("target_label", ""),
                        "validation_panel": primary_asset_target.get("validation_panel", ""),
                        "validation_panel_label": primary_asset_target.get("validation_panel_label", ""),
                        "window_label": window_label,
                        "window_range_start": int(window_range.get("start", 0) or 0),
                        "window_range_end": int(window_range.get("end", 0) or 0),
                        "window_breach_kind": "quality_pass_q03_repair_burden",
                        "baseline_issue_count": 0,
                        "baseline_worst_decision": "pass",
                        "baseline_quality_pass_q03_action_count": q03_action_count,
                        "preventive_quality_pass_campaign": True,
                        "targeted_chapters": [
                            {
                                "chapter_index": int(item.get("chapter_index", 0) or 0),
                                "chapter_title": item.get("chapter_title", ""),
                            }
                            for item in targeted_chapters
                        ],
                        "targeted_chapter_indices": targeted_indices,
                        "contract_failed_checks": ["quality_pass_q03_repair_burden"],
                        "scene_id": primary_asset_target.get("scene_id", ""),
                        "scene_function": primary_asset_target.get("scene_function", ""),
                        "chapter_task_id": primary_asset_target.get("chapter_task_id", ""),
                        "arc_id": primary_asset_target.get("arc_id", ""),
                        "volume_id": primary_asset_target.get("volume_id", ""),
                    }
                    campaigns.append(
                        {
                            "campaign_id": f"content_quality::{window_label}::{issue_code}:quality_pass_preventive",
                            "window_label": window_label,
                            "window_range": {"start": int(window_range.get("start", 0) or 0), "end": int(window_range.get("end", 0) or 0)},
                            "issue_code": issue_code,
                            "issue_label": ISSUE_TAXONOMY.get(issue_code, {}).get("label", issue_code),
                            "breach_kind": "quality_pass_q03_repair_burden",
                            "targeted_chapter_indices": targeted_indices,
                            "baseline_issue_count": 0,
                            "baseline_worst_decision": "pass",
                            "failed_chapter_count": 0,
                            "average_score": round(
                                sum(float(item.get("overall_score", 0.0) or 0.0) for item in targeted_chapters) / float(max(1, len(targeted_chapters))),
                                3,
                            ),
                            "primary_asset_type": primary_asset_target.get("asset_type", ""),
                            "primary_asset_target": primary_asset_target,
                            "secondary_asset_target": dict(secondary_asset_targets[0]) if secondary_asset_targets else {},
                            "secondary_asset_targets": secondary_asset_targets,
                            "validation_panel": primary_asset_target.get("validation_panel", ""),
                            "validation_panel_label": primary_asset_target.get("validation_panel_label", ""),
                            "suggested_actions": suggested_actions,
                            "suggested_field_edits": suggested_field_edits,
                            "strategy_bundle_id": strategy_bundle.get("strategy_bundle_id", ""),
                            "strategy_bundle": strategy_bundle,
                            "current_window_metrics": {
                                **dict(window_metrics.get("thresholds") or {}),
                                "quality_pass_q03_action_count": q03_action_count,
                            },
                            "rerun_scope": {
                                "mode": "full_100_rerun",
                                "reason": "quality_pass_repair_burden",
                                "focus_window": window_label,
                                "compare_mode": "window_slice",
                            },
                            "repair_loop_context": repair_loop_context,
                            "group_primary_asset_type": "",
                        }
                    )

        campaigns = sorted(
            campaigns,
            key=lambda item: (
                campaign_order.get(str(item.get("window_label") or ""), 9),
                issue_order.get(str(item.get("issue_code") or ""), 9),
                -int(item.get("failed_chapter_count", 0) or 0),
                -self._decision_severity(str(item.get("baseline_worst_decision") or "pass")),
                float(item.get("average_score", 0.0) or 0.0),
            ),
        )
        for window_label in windows_payload:
            windows_payload[window_label]["campaign_count"] = sum(
                1 for item in campaigns if str(item.get("window_label") or "") == window_label
            )
        default_campaign = dict(campaigns[0]) if campaigns else {}
        return {
            "available": bool(campaigns),
            "windows": windows_payload,
            "default_campaign": default_campaign,
            "campaigns": campaigns,
            "next_actions": (
                ["review_content_quality_campaign", "apply_repair_prefill", "save_longform_workbench", "re_simulate"]
                if campaigns
                else []
            ),
        }

    def _latest_strategy_bundle_execution(
        self,
        revisions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        for revision in range(len(revisions) - 1, -1, -1):
            execution = dict((revisions[revision] or {}).get("strategy_bundle_execution") or {})
            if execution:
                return execution
        return {}

    def _strategy_bundle_execution_history(self, revisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        for revision in reversed(revisions):
            execution = dict(revision.get("strategy_bundle_execution") or {})
            if not execution:
                continue
            history.append(
                {
                    "revision_id": revision.get("revision_id"),
                    "created_at": revision.get("created_at"),
                    "source": revision.get("source"),
                    "label": revision.get("label"),
                    "strategy_bundle_execution": execution,
                }
            )
        return history[:5]

    def _matching_strategy_bundle_executions(
        self,
        revisions: List[Dict[str, Any]],
        *,
        campaign_id: str,
        strategy_bundle_id: str,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for revision in reversed(revisions):
            execution = dict(revision.get("strategy_bundle_execution") or {})
            if not execution:
                continue
            if str(execution.get("campaign_id") or "") != campaign_id:
                continue
            if str(execution.get("strategy_bundle_id") or "") != strategy_bundle_id:
                continue
            matches.append(execution)
        return matches

    def _parse_strategy_edit_path(self, path: str) -> List[Dict[str, Any]]:
        tokens: List[Dict[str, Any]] = []
        buffer = ""
        index = 0
        while index < len(path):
            current = path[index]
            if current == ".":
                if buffer:
                    tokens.append({"kind": "key", "value": buffer})
                    buffer = ""
                index += 1
                continue
            if current == "[":
                if buffer:
                    tokens.append({"kind": "key", "value": buffer})
                    buffer = ""
                closing = path.find("]", index)
                if closing < 0:
                    return []
                raw_selector = path[index + 1 : closing]
                if raw_selector.startswith('"') and raw_selector.endswith('"'):
                    tokens.append({"kind": "map_key", "value": raw_selector[1:-1]})
                elif "=" in raw_selector:
                    selector_field, selector_value = raw_selector.split("=", 1)
                    tokens.append(
                        {
                            "kind": "selector",
                            "field": selector_field.strip(),
                            "value": selector_value.strip().strip('"'),
                        }
                    )
                elif raw_selector.isdigit():
                    tokens.append({"kind": "index", "value": int(raw_selector)})
                else:
                    return []
                index = closing + 1
                continue
            buffer += current
            index += 1
        if buffer:
            tokens.append({"kind": "key", "value": buffer})
        return tokens

    def _descend_strategy_path_token(
        self,
        current: Any,
        token: Dict[str, Any],
        *,
        next_token: Optional[Dict[str, Any]] = None,
    ) -> tuple[Any, Optional[str]]:
        token_kind = str(token.get("kind") or "")
        default_child: Any = [] if str((next_token or {}).get("kind") or "") in {"selector", "index"} else {}
        if token_kind == "key":
            if not isinstance(current, dict):
                return None, "non_dict_parent"
            key = str(token.get("value") or "")
            if key not in current or current[key] is None:
                current[key] = copy.deepcopy(default_child)
            return current[key], None
        if token_kind == "map_key":
            if not isinstance(current, dict):
                return None, "non_dict_parent"
            key = str(token.get("value") or "")
            if key not in current or current[key] is None:
                current[key] = copy.deepcopy(default_child)
            return current[key], None
        if token_kind == "selector":
            if not isinstance(current, list):
                return None, "non_list_parent"
            selector_field = str(token.get("field") or "")
            selector_value = str(token.get("value") or "")
            matched = next(
                (
                    item
                    for item in current
                    if str(dict(item or {}).get(selector_field) or "") == selector_value
                ),
                None,
            )
            if matched is None:
                return None, "selector_target_missing"
            return matched, None
        if token_kind == "index":
            if not isinstance(current, list):
                return None, "non_list_parent"
            target_index = int(token.get("value", -1) or -1)
            if target_index < 0 or target_index >= len(current):
                return None, "index_out_of_range"
            return current[target_index], None
        return None, "unsupported_token"

    def _read_strategy_path_value(
        self,
        parent: Any,
        token: Dict[str, Any],
    ) -> tuple[bool, Any]:
        token_kind = str(token.get("kind") or "")
        if token_kind in {"key", "map_key"} and isinstance(parent, dict):
            key = str(token.get("value") or "")
            return key in parent, copy.deepcopy(parent.get(key))
        if token_kind == "index" and isinstance(parent, list):
            target_index = int(token.get("value", -1) or -1)
            if 0 <= target_index < len(parent):
                return True, copy.deepcopy(parent[target_index])
            return False, None
        if token_kind == "selector" and isinstance(parent, list):
            selector_field = str(token.get("field") or "")
            selector_value = str(token.get("value") or "")
            matched = next(
                (
                    item
                    for item in parent
                    if str(dict(item or {}).get(selector_field) or "") == selector_value
                ),
                None,
            )
            return matched is not None, copy.deepcopy(matched)
        return False, None

    def _write_strategy_path_value(
        self,
        parent: Any,
        token: Dict[str, Any],
        value: Any,
    ) -> bool:
        token_kind = str(token.get("kind") or "")
        if token_kind in {"key", "map_key"} and isinstance(parent, dict):
            parent[str(token.get("value") or "")] = copy.deepcopy(value)
            return True
        if token_kind == "index" and isinstance(parent, list):
            target_index = int(token.get("value", -1) or -1)
            if 0 <= target_index < len(parent):
                parent[target_index] = copy.deepcopy(value)
                return True
        if token_kind == "selector" and isinstance(parent, list):
            selector_field = str(token.get("field") or "")
            selector_value = str(token.get("value") or "")
            for index, item in enumerate(parent):
                if str(dict(item or {}).get(selector_field) or "") == selector_value:
                    parent[index] = copy.deepcopy(value)
                    return True
        return False

    def _strategy_edit_preview(self, value: Any) -> Any:
        if isinstance(value, list):
            return value[:3]
        if isinstance(value, dict):
            return {key: value[key] for key in list(value.keys())[:3]}
        if isinstance(value, str) and len(value) > 120:
            return f"{value[:117]}..."
        return value

    def _apply_strategy_edit_operation(
        self,
        *,
        existing_value: Any,
        operation: str,
        suggested_value: Any,
        exists: bool,
    ) -> Any:
        if operation in {"replace", "rewrite"}:
            return copy.deepcopy(suggested_value)
        if operation in {"append", "expand"}:
            if isinstance(existing_value, list):
                next_value = list(existing_value)
                additions = list(suggested_value) if isinstance(suggested_value, list) else [suggested_value]
                for item in additions:
                    if item not in next_value:
                        next_value.append(copy.deepcopy(item))
                return next_value
            if isinstance(existing_value, str):
                additions = list(suggested_value) if isinstance(suggested_value, list) else [suggested_value]
                addition_text = "\n".join(str(item) for item in additions if str(item))
                if not addition_text:
                    return existing_value
                if addition_text in existing_value:
                    return existing_value
                if not existing_value:
                    return addition_text
                separator = "" if existing_value.endswith("\n") else "\n"
                return f"{existing_value}{separator}{addition_text}"
            if exists and existing_value not in {None, ""}:
                return copy.deepcopy(suggested_value)
            if isinstance(suggested_value, list):
                return copy.deepcopy(suggested_value)
            if operation == "append":
                return copy.deepcopy(suggested_value)
            return [copy.deepcopy(suggested_value)]
        return copy.deepcopy(suggested_value)

    def _apply_strategy_field_edit(
        self,
        worldpack_payload: Dict[str, Any],
        edit: Dict[str, Any],
    ) -> Dict[str, Any]:
        path = str(edit.get("path") or "")
        operation = str(edit.get("operation") or "replace")
        suggested_value = copy.deepcopy(edit.get("suggested_value"))
        reason = str(edit.get("reason") or "")
        tokens = self._parse_strategy_edit_path(path)
        if not tokens:
            return {
                "path": path,
                "operation": operation,
                "status": "skipped",
                "reason": reason,
                "error": "invalid_path",
            }
        current: Any = worldpack_payload
        for index, token in enumerate(tokens[:-1]):
            current, error = self._descend_strategy_path_token(
                current,
                token,
                next_token=tokens[index + 1],
            )
            if error:
                return {
                    "path": path,
                    "operation": operation,
                    "status": "skipped",
                    "reason": reason,
                    "error": error,
                }
        exists, before_value = self._read_strategy_path_value(current, tokens[-1])
        next_value = self._apply_strategy_edit_operation(
            existing_value=before_value,
            operation=operation,
            suggested_value=suggested_value,
            exists=exists,
        )
        changed = before_value != next_value or not exists
        if not self._write_strategy_path_value(current, tokens[-1], next_value):
            return {
                "path": path,
                "operation": operation,
                "status": "skipped",
                "reason": reason,
                "error": "write_failed",
            }
        return {
            "path": path,
            "operation": operation,
            "status": "applied" if changed else "noop",
            "reason": reason,
            "before_type": type(before_value).__name__ if exists else "",
            "after_type": type(next_value).__name__,
            "before_preview": self._strategy_edit_preview(before_value),
            "after_preview": self._strategy_edit_preview(next_value),
        }

    def _apply_strategy_bundle_step(
        self,
        worldpack_payload: Dict[str, Any],
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        edit_receipts = [
            self._apply_strategy_field_edit(worldpack_payload, dict(edit or {}))
            for edit in list(step.get("suggested_field_edits") or [])
        ]
        applied_receipts = [item for item in edit_receipts if str(item.get("status") or "") == "applied"]
        noop_receipts = [item for item in edit_receipts if str(item.get("status") or "") == "noop"]
        skipped_receipts = [item for item in edit_receipts if str(item.get("status") or "") == "skipped"]
        if applied_receipts:
            status = "applied"
        elif noop_receipts and not skipped_receipts:
            status = "noop"
        else:
            status = "skipped"
        return {
            "step_id": str(step.get("step_id") or ""),
            "apply_order": int(step.get("apply_order", 0) or 0),
            "asset_type": str(step.get("asset_type") or ""),
            "target": dict(step.get("target") or {}),
            "validation_panel": str(step.get("validation_panel") or ""),
            "validation_panel_label": str(step.get("validation_panel_label") or ""),
            "status": status,
            "applied_edit_count": len(applied_receipts),
            "noop_edit_count": len(noop_receipts),
            "skipped_edit_count": len(skipped_receipts),
            "applied_paths": [str(item.get("path") or "") for item in applied_receipts],
            "skipped_paths": [str(item.get("path") or "") for item in skipped_receipts],
            "edit_receipts": edit_receipts,
            "post_apply_validation": list(step.get("post_apply_validation") or []),
        }

    def _strategy_metric_value(self, simulation_report: Dict[str, Any], metric_name: str) -> float:
        for payload in (
            dict(simulation_report.get("content_quality_contract_window_metrics") or {}),
            dict(simulation_report.get("longform_summary") or {}),
            dict(simulation_report.get("evaluation_summary") or {}),
            dict(simulation_report or {}),
        ):
            if metric_name in payload:
                try:
                    return round(float(payload.get(metric_name, 0.0) or 0.0), 3)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def _build_strategy_bundle_result_attribution(
        self,
        *,
        strategy_bundle: Dict[str, Any],
        baseline_report: Dict[str, Any],
        rerun_report: Dict[str, Any],
        step_receipts: List[Dict[str, Any]],
        latest_repair_loop_outcome: Dict[str, Any],
    ) -> Dict[str, Any]:
        rerun_config = dict(strategy_bundle.get("rerun_attribution") or {})
        metric_receipt: List[Dict[str, Any]] = []
        improved_metrics: List[str] = []
        regressed_metrics: List[str] = []
        flat_metrics: List[str] = []
        for metric_payload in list(rerun_config.get("metrics_to_watch") or []):
            metric_name = str(metric_payload.get("metric") or "")
            direction = str(metric_payload.get("direction") or "decrease")
            baseline_value = self._strategy_metric_value(baseline_report, metric_name)
            current_value = self._strategy_metric_value(rerun_report, metric_name)
            delta = round(current_value - baseline_value, 3)
            if abs(delta) <= 0.001:
                status = "flat"
                flat_metrics.append(metric_name)
            elif (direction == "increase" and delta > 0) or (direction == "decrease" and delta < 0):
                status = "improved"
                improved_metrics.append(metric_name)
            else:
                status = "regressed"
                regressed_metrics.append(metric_name)
            metric_receipt.append(
                {
                    "metric": metric_name,
                    "direction": direction,
                    "baseline": baseline_value,
                    "current": current_value,
                    "delta": delta,
                    "status": status,
                }
            )
        if improved_metrics and regressed_metrics:
            overall_status = "mixed"
        elif improved_metrics:
            overall_status = "improved"
        elif regressed_metrics:
            overall_status = "regressed"
        else:
            overall_status = "flat"
        primary_signal = next(
            (
                item
                for item in metric_receipt
                if str(item.get("status") or "") == "improved"
            ),
            metric_receipt[0] if metric_receipt else {},
        )
        applied_asset_sequence = [
            str(item.get("asset_type") or "")
            for item in step_receipts
            if str(item.get("status") or "") == "applied"
        ]
        summary = (
            f"bundle rerun {overall_status}: improved={improved_metrics or []}, "
            f"regressed={regressed_metrics or []}, ready_for_validation={bool(latest_repair_loop_outcome.get('ready_for_validation', False))}"
        )
        return {
            "available": bool(metric_receipt),
            "rerun_scope": str(rerun_config.get("rerun_scope") or ""),
            "compare_scope": str(rerun_config.get("compare_scope") or ""),
            "window_label": str(rerun_config.get("window_label") or ""),
            "attribution_rule": str(rerun_config.get("attribution_rule") or ""),
            "metric_receipt": metric_receipt,
            "improved_metrics": improved_metrics,
            "regressed_metrics": regressed_metrics,
            "flat_metrics": flat_metrics,
            "overall_status": overall_status,
            "primary_signal": dict(primary_signal or {}),
            "candidate_contributors": applied_asset_sequence[:3],
            "ready_for_validation": bool(latest_repair_loop_outcome.get("ready_for_validation", False)),
            "summary": summary,
        }

    def _build_strategy_bundle_stop_decision(
        self,
        *,
        stop_condition: Dict[str, Any],
        result_attribution: Dict[str, Any],
        prior_executions: List[Dict[str, Any]],
        latest_repair_loop_outcome: Dict[str, Any],
    ) -> Dict[str, Any]:
        rule_id = str(stop_condition.get("rule_id") or "")
        overall_status = str(result_attribution.get("overall_status") or "flat")
        ready_for_validation = bool(
            latest_repair_loop_outcome.get("ready_for_validation", False)
            or result_attribution.get("ready_for_validation", False)
        )
        prior_flat_or_regressed = [
            item
            for item in prior_executions
            if str(dict(item.get("result_attribution") or {}).get("overall_status") or "") in {"flat", "regressed"}
        ]
        escalation_target = {
            "upgrade_to_planner_or_pack_contract_if_two_reruns_flat": "planner_or_pack_contract",
            "upgrade_to_task_coupling_if_flat": "task_coupling",
            "upgrade_to_budget_and_task_balance_if_flat": "budget_and_task_balance",
            "upgrade_to_planner_contract_if_flat": "planner_contract",
        }.get(rule_id, "manual_review")
        if ready_for_validation or overall_status == "improved":
            return {
                "decision": "stop",
                "reason": "bundle_improved_window_metrics",
                "tripwire": "",
                "escalation_target": "",
                "next_actions": ["review_compare_after_simulation", "decide_publish_or_next_bundle"],
            }
        if rule_id == "upgrade_to_planner_or_pack_contract_if_two_reruns_flat":
            if overall_status in {"flat", "regressed"} and prior_flat_or_regressed:
                return {
                    "decision": "escalate",
                    "reason": "two_reruns_flat_or_regressed",
                    "tripwire": str(stop_condition.get("tripwire") or ""),
                    "escalation_target": escalation_target,
                    "next_actions": ["escalate_bundle_scope", "open_planner_or_pack_contract_fix"],
                }
            return {
                "decision": "continue",
                "reason": "first_flat_rerun",
                "tripwire": "",
                "escalation_target": "",
                "next_actions": ["run_next_bundle_pass", "inspect_compare_panel"],
            }
        if overall_status in {"flat", "regressed"}:
            return {
                "decision": "escalate",
                "reason": "stop_condition_flat_triggered",
                "tripwire": str(stop_condition.get("tripwire") or ""),
                "escalation_target": escalation_target,
                "next_actions": ["escalate_bundle_scope", "inspect_next_strategy_layer"],
            }
        return {
            "decision": "continue",
            "reason": "mixed_signal_requires_followup",
            "tripwire": "",
            "escalation_target": "",
            "next_actions": ["inspect_metric_receipt", "run_followup_bundle_pass"],
        }

    def _strategy_bundle_ready_for_validation_override(
        self,
        *,
        metadata: Dict[str, Any],
        simulation_report: Dict[str, Any],
        execution_receipt: Dict[str, Any],
    ) -> Dict[str, Any]:
        result_attribution = dict(execution_receipt.get("result_attribution") or {})
        repair_outcome = dict(simulation_report.get("latest_repair_loop_outcome") or {})
        receipt_outcome = dict(execution_receipt.get("repair_loop_outcome") or {})
        repair_loop_context = dict(execution_receipt.get("repair_loop_context") or {})
        if not repair_outcome and receipt_outcome:
            repair_outcome = dict(receipt_outcome)

        def _count_improved(prefix: str) -> bool:
            try:
                baseline = int(repair_outcome.get(f"baseline_{prefix}_issue_count", 0) or 0)
                current = int(repair_outcome.get(f"current_{prefix}_issue_count", 0) or 0)
            except (TypeError, ValueError):
                return False
            return baseline > 0 and current < baseline

        severity_trend = str(repair_outcome.get("severity_trend") or receipt_outcome.get("severity_trend") or "")
        preventive_quality_pass_improved = bool(
            repair_loop_context.get("preventive_quality_pass_campaign")
            and str(result_attribution.get("overall_status") or "") != "regressed"
            and not list(result_attribution.get("regressed_metrics") or [])
        )
        issue_or_severity_improved = bool(
            _count_improved("targeted")
            or _count_improved("window")
            or severity_trend in {"improved", "resolved"}
            or preventive_quality_pass_improved
            or (
                str(result_attribution.get("overall_status") or "") == "improved"
                and not list(result_attribution.get("regressed_metrics") or [])
            )
        )
        freshness = self._simulation_freshness(metadata, simulation_report)
        compare = self._build_before_after_chapter_compare(metadata)
        revision_compare = self._build_revision_compare(metadata, simulation_report)
        block_rate = float((simulation_report.get("evaluation_summary") or {}).get("block_rate", 0.0) or 0.0)
        latest_decision = str(simulation_report.get("latest_decision") or "").lower()
        ready = bool(
            int(execution_receipt.get("applied_edit_count", 0) or 0) > 0
            and (bool(compare.get("available")) or bool(revision_compare.get("available")))
            and issue_or_severity_improved
            and freshness.get("status") == "fresh"
            and block_rate <= 0.0
            and latest_decision not in {"block", "blocked", "failed"}
        )
        return {
            "ready": ready,
            "issue_or_severity_improved": issue_or_severity_improved,
            "preventive_quality_pass_improved": preventive_quality_pass_improved,
            "simulation_freshness": freshness,
            "compare_available": bool(compare.get("available")),
            "revision_compare_available": bool(revision_compare.get("available")),
            "no_new_hard_blocker": block_rate <= 0.0 and latest_decision not in {"block", "blocked", "failed"},
        }

    def _attach_strategy_bundle_execution(
        self,
        *,
        world_version_id: str,
        revision_id: str,
        execution_receipt: Dict[str, Any],
    ) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        metadata = self._ensure_metadata(version.worldpack_json)
        revision_history = list(metadata.get("revision_history") or [])
        for revision in revision_history:
            if str(revision.get("revision_id") or "") == revision_id:
                revision["strategy_bundle_execution"] = copy.deepcopy(execution_receipt)
                break
        metadata["revision_history"] = revision_history[-10:]
        version.worldpack_json["metadata"] = metadata
        simulation_report = dict(version.simulation_report_json or {})
        ready_override = self._strategy_bundle_ready_for_validation_override(
            metadata=metadata,
            simulation_report=simulation_report,
            execution_receipt=execution_receipt,
        )
        if bool(ready_override.get("ready")):
            repair_outcome = dict(simulation_report.get("latest_repair_loop_outcome") or {})
            receipt_outcome = dict(execution_receipt.get("repair_loop_outcome") or {})
            repair_outcome.update(
                {
                    "available": True,
                    "ready_for_validation": True,
                    "severity_trend": repair_outcome.get("severity_trend") or receipt_outcome.get("severity_trend") or "improved",
                    "ready_for_validation_reason": "strategy_bundle_effective_after_fresh_rerun",
                    "strategy_bundle_execution_id": execution_receipt.get("execution_id"),
                    "strategy_bundle_id": execution_receipt.get("strategy_bundle_id"),
                    "validation_evidence": {
                        "repair_receipt_present": True,
                        "before_after_delta_visible": bool(ready_override.get("compare_available") or ready_override.get("revision_compare_available")),
                        "issue_or_severity_improved": bool(ready_override.get("issue_or_severity_improved")),
                        "preventive_quality_pass_improved": bool(ready_override.get("preventive_quality_pass_improved")),
                        "simulation_freshness": dict(ready_override.get("simulation_freshness") or {}),
                        "no_new_hard_blocker": bool(ready_override.get("no_new_hard_blocker")),
                    },
                }
            )
            simulation_report["latest_repair_loop_outcome"] = repair_outcome
            result_attribution = dict(execution_receipt.get("result_attribution") or {})
            result_attribution["ready_for_validation"] = True
            execution_receipt["result_attribution"] = result_attribution
            execution_receipt["repair_loop_outcome"] = {
                **receipt_outcome,
                "ready_for_validation": True,
                "severity_trend": repair_outcome.get("severity_trend") or "improved",
                "validation_evidence": repair_outcome.get("validation_evidence"),
            }
            stop_decision = dict(execution_receipt.get("stop_decision") or {})
            if str(stop_decision.get("decision") or "") != "stop":
                execution_receipt["stop_decision"] = {
                    **stop_decision,
                    "decision": "stop",
                    "reason": "strategy_bundle_ready_for_validation",
                    "next_actions": ["review_compare_after_simulation", "submit_for_review"],
                }
            for revision in revision_history:
                if str(revision.get("revision_id") or "") == revision_id:
                    revision["repair_loop_outcome"] = copy.deepcopy(repair_outcome)
                    revision["strategy_bundle_execution"] = copy.deepcopy(execution_receipt)
                    break
            metadata["revision_history"] = revision_history[-10:]
            version.worldpack_json["metadata"] = metadata
        simulation_report["latest_strategy_bundle_execution"] = copy.deepcopy(execution_receipt)
        simulation_report["strategy_bundle_execution_history"] = self._strategy_bundle_execution_history(revision_history)
        version.simulation_report_json = simulation_report
        self.repository.save_world_version(version, publish=False)
        return {
            "latest_strategy_bundle_execution": copy.deepcopy(execution_receipt),
            "strategy_bundle_execution_history": simulation_report["strategy_bundle_execution_history"],
        }

    def execute_content_quality_strategy_bundle(
        self,
        world_version_id: str,
        *,
        campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        worldpack_payload = copy.deepcopy(version.worldpack_json or {})
        baseline_report = copy.deepcopy(version.simulation_report_json or {})
        workbench = self._build_content_quality_repair_workbench(worldpack_payload, baseline_report)
        if not bool(workbench.get("available")):
            raise ValueError("content_quality_strategy_bundle_unavailable")
        campaigns = [dict(item or {}) for item in list(workbench.get("campaigns") or [])]
        selected_campaign = next(
            (
                item
                for item in campaigns
                if str(item.get("campaign_id") or "") == str(campaign_id or "")
            ),
            dict(workbench.get("default_campaign") or {}),
        )
        if not selected_campaign:
            raise ValueError("content_quality_strategy_bundle_campaign_not_found")
        strategy_bundle = dict(selected_campaign.get("strategy_bundle") or {})
        if not bool(strategy_bundle.get("execution_protocol_enabled")):
            raise ValueError("content_quality_strategy_bundle_execution_disabled")
        strategy_bundle_id = str(strategy_bundle.get("strategy_bundle_id") or "")
        selected_campaign_id = str(selected_campaign.get("campaign_id") or "")
        previous_executions = self._matching_strategy_bundle_executions(
            list((worldpack_payload.get("metadata") or {}).get("revision_history") or []),
            campaign_id=selected_campaign_id,
            strategy_bundle_id=strategy_bundle_id,
        )
        revision_id = ""

        def _persistent_simulation_runner(mutated_worldpack_payload: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal revision_id
            updated_draft = self.update_draft(
                world_version_id,
                mutated_worldpack_payload,
                change_context={
                    "source": "strategy_bundle_executor",
                    "label": f"执行策略包：{strategy_bundle.get('strategy_bundle_label') or strategy_bundle_id}",
                    "repair_loop_context": dict(selected_campaign.get("repair_loop_context") or {}),
                },
            )
            revision_id = str((updated_draft.get("revision_history") or [{}])[-1].get("revision_id") or "")
            return copy.deepcopy(self.run_simulation_for_world_version(world_version_id))

        execution_receipt = execute_strategy_bundle_protocol(
            worldpack_payload=worldpack_payload,
            baseline_simulation_report=baseline_report,
            campaign=selected_campaign,
            strategy_bundle=strategy_bundle,
            execution_mode="persistent_draft",
            simulation_runner=_persistent_simulation_runner,
            apply_step=self._apply_strategy_bundle_step,
            build_result_attribution=self._build_strategy_bundle_result_attribution,
            build_stop_decision=self._build_strategy_bundle_stop_decision,
            prior_executions=previous_executions,
        )
        execution_receipt["repair_loop_revision_id"] = revision_id
        execution_receipt["repair_loop_context"] = dict(selected_campaign.get("repair_loop_context") or {})
        execution_receipt.pop("mutated_worldpack_payload", None)
        execution_receipt.pop("rerun_report", None)
        self._attach_strategy_bundle_execution(
            world_version_id=world_version_id,
            revision_id=revision_id,
            execution_receipt=execution_receipt,
        )
        return self.get_draft(world_version_id)

    def _latest_repair_loop_revision(
        self,
        revisions: List[Dict[str, Any]],
    ) -> tuple[Optional[int], Optional[Dict[str, Any]]]:
        for index in range(len(revisions) - 1, -1, -1):
            revision = dict(revisions[index] or {})
            if dict(revision.get("repair_loop_context") or {}):
                return index, revision
        return None, None

    def _repair_loop_history(self, revisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        history = []
        for revision in reversed(revisions):
            context = dict(revision.get("repair_loop_context") or {})
            if not context:
                continue
            history.append(
                {
                    "revision_id": revision.get("revision_id"),
                    "created_at": revision.get("created_at"),
                    "source": revision.get("source"),
                    "label": revision.get("label"),
                    "summary": revision.get("summary"),
                    "repair_loop_context": context,
                    "repair_loop_outcome": dict(revision.get("repair_loop_outcome") or {}),
                }
            )
        return history[:5]

    def _build_repair_loop_outcome(
        self,
        revisions: List[Dict[str, Any]],
        *,
        current_issue_groups: List[Dict[str, Any]],
        current_chapter_heatmap: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        active_index, active_revision = self._latest_repair_loop_revision(revisions)
        if active_revision is None:
            return {}
        repair_loop_context = dict(active_revision.get("repair_loop_context") or {})
        issue_code = str(repair_loop_context.get("issue_code") or "").strip()
        if not issue_code:
            return {}

        baseline_snapshot = dict(active_revision.get("simulation_snapshot") or {})
        if not baseline_snapshot:
            for revision in reversed(revisions[:active_index]):
                snapshot = dict(revision.get("simulation_snapshot") or {})
                if snapshot:
                    baseline_snapshot = snapshot
                    break
        if not baseline_snapshot:
            return {}

        baseline_issue_chapters = [
            dict(item)
            for item in list(baseline_snapshot.get("chapter_snapshots") or [])
            if issue_code in list(item.get("issue_codes") or [])
        ]
        current_issue_chapters = [
            dict(item)
            for item in current_chapter_heatmap
            if issue_code in list(item.get("issue_codes") or [])
        ]
        current_issue_group = next(
            (dict(item) for item in current_issue_groups if str(item.get("issue_code") or "") == issue_code),
            {},
        )
        targeted_indices = [
            int(item)
            for item in (
                repair_loop_context.get("targeted_chapter_indices")
                or [repair_loop_context.get("chapter_index")]
            )
            if int(item or 0) > 0
        ]
        baseline_targeted = [
            item for item in baseline_issue_chapters if int(item.get("chapter_index", 0) or 0) in targeted_indices
        ]
        current_targeted = [
            item for item in current_issue_chapters if int(item.get("chapter_index", 0) or 0) in targeted_indices
        ]
        baseline_worst_decision = max(
            (str(item.get("decision") or "pass") for item in baseline_issue_chapters),
            key=self._decision_severity,
            default="pass",
        )
        current_worst_decision = max(
            (str(item.get("decision") or "pass") for item in current_issue_chapters),
            key=self._decision_severity,
            default="pass",
        )
        baseline_issue_map = {
            int(item.get("chapter_index", 0) or 0): dict(item)
            for item in baseline_issue_chapters
            if int(item.get("chapter_index", 0) or 0) > 0
        }
        current_issue_map = {
            int(item.get("chapter_index", 0) or 0): dict(item)
            for item in current_issue_chapters
            if int(item.get("chapter_index", 0) or 0) > 0
        }
        resolved_indices = sorted(set(baseline_issue_map) - set(current_issue_map))
        remaining_indices = sorted(current_issue_map)
        baseline_issue_count = len(baseline_issue_chapters)
        current_issue_count = len(current_issue_chapters)
        count_delta = int(current_issue_count - baseline_issue_count)
        baseline_worst_score = self._decision_severity(baseline_worst_decision)
        current_worst_score = self._decision_severity(current_worst_decision)
        baseline_window_worst_decision = max(
            (str(item.get("decision") or "pass") for item in baseline_targeted),
            key=self._decision_severity,
            default=baseline_worst_decision,
        )
        current_window_worst_decision = max(
            (str(item.get("decision") or "pass") for item in current_targeted),
            key=self._decision_severity,
            default=current_worst_decision,
        )
        baseline_window_worst_score = self._decision_severity(baseline_window_worst_decision)
        current_window_worst_score = self._decision_severity(current_window_worst_decision)
        if baseline_issue_count > 0 and current_issue_count == 0:
            severity_trend = "resolved"
        elif current_issue_count < baseline_issue_count or current_worst_score < baseline_worst_score:
            severity_trend = "improved"
        elif current_issue_count > baseline_issue_count or current_worst_score > baseline_worst_score:
            severity_trend = "regressed"
        else:
            severity_trend = "flat"
        baseline_window_issue_count = len(baseline_targeted)
        current_window_issue_count = len(current_targeted)
        ready_for_validation = bool(
            current_window_issue_count < baseline_window_issue_count
            or current_window_worst_score < baseline_window_worst_score
            or (
                baseline_window_issue_count == 0
                and (
                    current_issue_count < baseline_issue_count
                    or current_worst_score < baseline_worst_score
                )
            )
        )
        return {
            "available": True,
            "repair_loop_revision_id": active_revision.get("revision_id"),
            "repair_loop_created_at": active_revision.get("created_at"),
            "issue_code": issue_code,
            "issue_label": repair_loop_context.get("issue_label") or ISSUE_TAXONOMY.get(issue_code, {}).get("label", issue_code),
            "asset_type": repair_loop_context.get("asset_type", ""),
            "asset_label": repair_loop_context.get("asset_label", ""),
            "target_label": repair_loop_context.get("target_label", ""),
            "validation_panel": repair_loop_context.get("validation_panel", ""),
            "validation_panel_label": repair_loop_context.get("validation_panel_label", ""),
            "validation_reason": repair_loop_context.get("validation_reason", ""),
            "character_id": repair_loop_context.get("character_id", ""),
            "scene_id": repair_loop_context.get("scene_id", ""),
            "scene_function": repair_loop_context.get("scene_function", ""),
            "chapter_task_id": repair_loop_context.get("chapter_task_id", ""),
            "arc_id": repair_loop_context.get("arc_id", ""),
            "volume_id": repair_loop_context.get("volume_id", ""),
            "chapter_index": repair_loop_context.get("chapter_index"),
            "chapter_title": repair_loop_context.get("chapter_title", ""),
            "targeted_chapter_indices": targeted_indices,
            "window_label": repair_loop_context.get("window_label", ""),
            "window_breach_kind": repair_loop_context.get("window_breach_kind", ""),
            "contract_failed_checks": list(repair_loop_context.get("contract_failed_checks", []) or []),
            "baseline_issue_count": baseline_issue_count,
            "current_issue_count": current_issue_count,
            "count_delta": count_delta,
            "baseline_targeted_issue_count": len(baseline_targeted),
            "current_targeted_issue_count": len(current_targeted),
            "baseline_window_issue_count": baseline_window_issue_count,
            "current_window_issue_count": current_window_issue_count,
            "baseline_worst_decision": baseline_worst_decision,
            "current_worst_decision": current_worst_decision,
            "baseline_window_worst_decision": baseline_window_worst_decision,
            "current_window_worst_decision": current_window_worst_decision,
            "severity_trend": severity_trend,
            "resolved_chapters": [
                {
                    "chapter_index": chapter_index,
                    "chapter_title": baseline_issue_map[chapter_index].get("chapter_title", ""),
                }
                for chapter_index in resolved_indices
            ],
            "remaining_chapters": [
                {
                    "chapter_index": chapter_index,
                    "chapter_title": current_issue_map[chapter_index].get("chapter_title", ""),
                }
                for chapter_index in remaining_indices
            ],
            "resolved_window_chapters": [
                {
                    "chapter_index": int(item.get("chapter_index", 0) or 0),
                    "chapter_title": item.get("chapter_title", ""),
                }
                for item in baseline_targeted
                if int(item.get("chapter_index", 0) or 0) not in {int(chapter.get("chapter_index", 0) or 0) for chapter in current_targeted}
            ],
            "remaining_window_chapters": [
                {
                    "chapter_index": int(item.get("chapter_index", 0) or 0),
                    "chapter_title": item.get("chapter_title", ""),
                }
                for item in current_targeted
            ],
            "ready_for_validation": ready_for_validation,
            "fix_hint": ISSUE_TAXONOMY.get(issue_code, {}).get("fix_hint", ""),
            "group_chapter_count": int(current_issue_group.get("chapter_count", current_issue_count) or current_issue_count),
            "group_primary_asset_type": current_issue_group.get("primary_asset_type", ""),
        }

    def _prepare_interactive_scenarios(
        self,
        version: WorldVersion,
        interactive_scenarios: Optional[List[Dict[str, Any]]],
        *,
        max_chapters: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        previous_completed = int((version.simulation_report_json or {}).get("completed_chapters", 0) or 0)
        default_trigger_chapter = max(1, previous_completed + 1)
        prepared: List[Dict[str, Any]] = []
        effective_budget = max(1, int(max_chapters))
        for index, item in enumerate(interactive_scenarios or [], start=1):
            scenario = dict(item or {})
            if not scenario:
                continue
            directive = dict(scenario.get("steering_directive") or {})
            scenario_kind = str(
                scenario.get("scenario_kind")
                or directive.get("steering_type")
                or ("memory_steer" if directive.get("memory_patch_note") else "mild_steer")
            )
            trigger_chapter = scenario.get("trigger_chapter")
            resolved_trigger = (
                max(1, int(trigger_chapter))
                if trigger_chapter not in (None, "")
                else default_trigger_chapter
            )
            prepared_scenario = {
                "scenario_id": str(scenario.get("scenario_id") or f"author_steering_{index}"),
                "scenario_kind": scenario_kind,
                "label": str(
                    scenario.get("label")
                    or directive.get("summary")
                    or directive.get("current_user_intent")
                    or scenario_kind
                ),
                "trigger_chapter": resolved_trigger,
                "steering_directive": directive,
            }
            prepared.append(prepared_scenario)
            effective_budget = max(effective_budget, resolved_trigger)
        return prepared, effective_budget

    def _build_creative_cockpit(self, worldpack_payload: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {"available": False}

        final_state = dict(simulation_report.get("final_state_snapshot") or {})
        character_lookup = self._character_label_lookup(worldpack_payload, final_state)
        scene_blueprints = [dict(item) for item in worldpack_payload.get("scene_blueprints", []) or []]
        scene_by_function: Dict[str, Dict[str, Any]] = {}
        for scene in scene_blueprints:
            scene_function = str(scene.get("scene_function") or "")
            if scene_function and scene_function not in scene_by_function:
                scene_by_function[scene_function] = scene
        role_to_character_ids: Dict[str, List[str]] = {}
        for character in worldpack_payload.get("characters", []) or []:
            role = str((dict(character or {})).get("role") or "").strip()
            character_id = str((dict(character or {})).get("character_id") or "").strip()
            if role and character_id:
                role_to_character_ids.setdefault(role, []).append(character_id)
        relationship_graph = [dict(item) for item in final_state.get("relationship_graph", [])]
        metric_labels = {
            "attachment": "牵引",
            "resentment": "怨气",
            "shame": "羞耻",
            "obligation": "亏欠",
            "projection": "投射",
            "possession": "占有",
            "gratitude": "感激",
            "fear": "恐惧",
        }
        conflict_metrics = ("resentment", "shame", "projection", "possession", "fear")
        ranked_edges: List[Dict[str, Any]] = []
        for index, edge in enumerate(relationship_graph, start=1):
            metrics = {
                metric: round(float(edge.get(metric, 0.0) or 0.0), 3)
                for metric in metric_labels
            }
            dominant_metric = max(metrics.items(), key=lambda item: item[1])[0]
            debt_entries = [dict(item) for item in edge.get("debts", [])]
            debt_total = round(sum(float(item.get("magnitude", 0.0) or 0.0) for item in debt_entries), 3)
            notes_preview = [str(note).strip() for note in edge.get("notes", []) if str(note).strip()][:2]
            intensity = round(sum(metrics.values()) / float(max(1, len(metrics))), 3)
            conflict = round(
                sum(metrics.get(metric, 0.0) for metric in conflict_metrics) / float(len(conflict_metrics)),
                3,
            )
            score = round(max(intensity, conflict) + min(1.0, debt_total) * 0.2, 3)
            source_id = str(edge.get("source") or "")
            target_id = str(edge.get("target") or "")
            ranked_edges.append(
                {
                    "edge_id": f"edge_{index}",
                    "source": source_id,
                    "target": target_id,
                    "source_label": character_lookup.get(source_id, {}).get("label", source_id),
                    "target_label": character_lookup.get(target_id, {}).get("label", target_id),
                    "dominant_metric": dominant_metric,
                    "dominant_metric_label": metric_labels.get(dominant_metric, dominant_metric),
                    "dominant_metric_value": metrics.get(dominant_metric, 0.0),
                    "intensity": intensity,
                    "conflict": conflict,
                    "debt_count": len(debt_entries),
                    "debt_total": debt_total,
                    "note_count": len([note for note in edge.get("notes", []) if str(note).strip()]),
                    "notes_preview": notes_preview,
                    "score": score,
                }
            )
        ranked_edges = sorted(ranked_edges, key=lambda item: (-float(item["score"]), item["edge_id"]))

        referenced_character_ids = {
            character_id
            for item in ranked_edges
            for character_id in (item.get("source"), item.get("target"))
            if str(character_id)
        }
        referenced_character_ids.update(str(character.get("character_id") or "") for character in worldpack_payload.get("characters", []) or [])
        nodes = [
            {
                "character_id": character_id,
                "label": character_lookup.get(character_id, {}).get("label", character_id),
                "role": character_lookup.get(character_id, {}).get("role", ""),
            }
            for character_id in sorted(referenced_character_ids)
            if character_id
        ]

        checkpoints = [dict(item) for item in simulation_report.get("steering_checkpoints", [])]
        replan_history = [dict(item) for item in simulation_report.get("replan_history", [])]
        memory_patch_summary = dict(simulation_report.get("memory_patch_summary") or {})
        chapter_trace = [dict(item) for item in simulation_report.get("chapter_trace", [])]
        chapter_trace_by_index: Dict[int, Dict[str, Any]] = {}
        for item in chapter_trace:
            execution = dict(item.get("chapter_task_execution_summary") or {})
            chapter_index = int(
                execution.get("series_chapter_index", 0)
                or str(item.get("chapter_id") or "chapter_0").rsplit("_", 1)[-1]
                or 0
            )
            if chapter_index > 0 and chapter_index not in chapter_trace_by_index:
                chapter_trace_by_index[chapter_index] = item
        steering_entries = [
            {
                **(
                    lambda trace, task, matched_scene: {
                        "scene_id": str((matched_scene or {}).get("scene_id") or ""),
                        "scene_function": str(trace.get("scene_function") or (matched_scene or {}).get("scene_function") or ""),
                        "chapter_task_id": str(task.get("chapter_task_id") or task.get("task_id") or ""),
                        "arc_id": str(trace.get("arc_id") or item.get("affected_arc_id") or ""),
                        "volume_id": str(trace.get("volume_id") or ""),
                    }
                )(
                    dict(chapter_trace_by_index.get(int(item.get("chapter_index", 0) or 0)) or {}),
                    dict((dict(chapter_trace_by_index.get(int(item.get("chapter_index", 0) or 0)) or {})).get("chapter_task") or {}),
                    scene_by_function.get(str((dict(chapter_trace_by_index.get(int(item.get("chapter_index", 0) or 0)) or {})).get("scene_function") or "")),
                ),
                "entry_type": "checkpoint",
                "chapter_index": int(item.get("chapter_index", 0) or 0),
                "title": str(item.get("summary") or item.get("scenario_kind") or "Steering"),
                "summary": str(item.get("summary") or ""),
                "status": "checkpoint",
                "scenario_kind": str(item.get("scenario_kind") or ""),
                "impacted_character_ids": [str(character_id) for character_id in item.get("impacted_character_ids", []) if str(character_id)],
                "impacted_characters": [
                    character_lookup.get(str(character_id), {}).get("label", str(character_id))
                    for character_id in item.get("impacted_character_ids", [])
                    if str(character_id)
                ],
            }
            for item in checkpoints
        ] + [
            {
                "entry_type": "replan",
                "chapter_index": int(item.get("chapter_index", 0) or 0),
                "title": f"{'强调整' if str(item.get('mode') or '') == 'strong' else '软调整'} Replan",
                "summary": str(item.get("reason") or ""),
                "status": str(item.get("mode") or "soft"),
                "scenario_kind": str(item.get("reason") or ""),
                "impacted_character_ids": [],
                "impacted_characters": [],
                "scene_id": "",
                "scene_function": "",
                "chapter_task_id": "",
                "arc_id": str(item.get("arc_id") or ""),
                "volume_id": str(item.get("volume_id") or ""),
            }
            for item in replan_history
        ]
        steering_entries = sorted(
            steering_entries,
            key=lambda item: (int(item.get("chapter_index", 0) or 0), 0 if item.get("entry_type") == "checkpoint" else 1),
        )

        chapter_breakdown = list(
            (simulation_report.get("simulation_drilldown") or {}).get("chapter_breakdown")
            or self._build_simulation_drilldown(simulation_report).get("chapter_breakdown", [])
        )
        chapter_heatmap = []
        for item in chapter_breakdown:
            issue_codes = list(item.get("issue_codes") or [])
            decision = str(item.get("decision") or "rewrite")
            severity = "critical" if decision == "block" else ("watch" if decision == "rewrite" else "stable")
            trace = dict(chapter_trace_by_index.get(int(item.get("chapter_index", 0) or 0)) or {})
            chapter_task = dict(trace.get("chapter_task") or {})
            matched_scene = scene_by_function.get(str(trace.get("scene_function") or item.get("scene_function") or ""))
            related_character_ids = self._resolve_related_character_ids(
                matched_scene=dict(matched_scene or {}),
                role_to_character_ids=role_to_character_ids,
                character_lookup=character_lookup,
            )
            chapter_heatmap.append(
                {
                    "chapter_index": int(item.get("chapter_index", 0) or 0),
                    "chapter_title": str(item.get("chapter_title") or item.get("chapter_id") or ""),
                    "decision": decision,
                    "severity": severity,
                    "overall_score": round(float(item.get("overall_score", 0.0) or 0.0), 3),
                    "issue_count": len(issue_codes),
                    "issue_codes": issue_codes,
                    "dominant_issue": issue_codes[0] if issue_codes else "",
                    "scene_function": str(item.get("scene_function") or ""),
                    "scene_id": str((matched_scene or {}).get("scene_id") or ""),
                    "chapter_task_id": str(chapter_task.get("chapter_task_id") or chapter_task.get("task_id") or ""),
                    "arc_id": str(trace.get("arc_id") or ""),
                    "volume_id": str(trace.get("volume_id") or ""),
                    "related_character_ids": related_character_ids,
                    "related_characters": [
                        character_lookup.get(character_id, {}).get("label", character_id)
                        for character_id in related_character_ids
                    ],
                }
            )
        volume_plans = sorted(
            [dict(item) for item in (simulation_report.get("longform_plan_snapshot") or {}).get("volume_plans", [])],
            key=lambda item: int(item.get("order", 0) or 0),
        )
        arc_plans = sorted(
            [dict(item) for item in (simulation_report.get("longform_plan_snapshot") or {}).get("arc_plans", [])],
            key=lambda item: (str(item.get("volume_id") or ""), int(item.get("order", 0) or 0)),
        )
        volume_snapshots = [dict(item) for item in final_state.get("volume_memory_snapshots", [])]
        series_snapshots = [dict(item) for item in final_state.get("series_memory_snapshots", [])]
        series_ending_checkpoint = dict(final_state.get("series_ending_checkpoint") or {})
        replan_stability_metrics = dict(final_state.get("replan_stability_metrics") or {})

        volume_progress = []
        for volume in volume_plans:
            volume_id = str(volume.get("volume_id") or "")
            volume_chapters = [item for item in chapter_trace if str(item.get("volume_id") or "") == volume_id]
            snapshot = next((item for item in volume_snapshots if str(item.get("volume_id") or "") == volume_id), {})
            status = "completed" if snapshot else ("active" if series_ending_checkpoint.get("current_volume_id") == volume_id else "planned")
            volume_arc = next((arc for arc in arc_plans if str(arc.get("volume_id") or "") == volume_id), {})
            volume_progress.append(
                {
                    "volume_id": volume_id,
                    "title": str(volume.get("title") or volume_id),
                    "first_arc_id": str((volume_arc or {}).get("arc_id") or ""),
                    "target_chapters": int(volume.get("target_chapters", 0) or 0),
                    "simulated_chapter_count": len(volume_chapters),
                    "first_simulation_chapter": (
                        min(int(dict(item.get("chapter_task_execution_summary") or {}).get("series_chapter_index", 0) or 0) for item in volume_chapters)
                        if volume_chapters
                        else None
                    ),
                    "last_simulation_chapter": (
                        max(int(dict(item.get("chapter_task_execution_summary") or {}).get("series_chapter_index", 0) or 0) for item in volume_chapters)
                        if volume_chapters
                        else None
                    ),
                    "memory_snapshot_count": 1 if snapshot else 0,
                    "status": status,
                }
            )

        arc_progress = []
        for arc in arc_plans:
            arc_id = str(arc.get("arc_id") or "")
            arc_chapters = [item for item in chapter_trace if str(item.get("arc_id") or "") == arc_id]
            arc_progress.append(
                {
                    "arc_id": arc_id,
                    "title": str(arc.get("title") or arc_id),
                    "volume_id": str(arc.get("volume_id") or ""),
                    "first_task_id": str(((arc.get("chapter_tasks") or [{}])[0] or {}).get("chapter_task_id") or ""),
                    "target_chapters": int(arc.get("target_chapters", 0) or 0),
                    "simulated_chapter_count": len(arc_chapters),
                    "status": "active" if series_ending_checkpoint.get("current_arc_id") == arc_id else ("completed" if arc_chapters else "planned"),
                }
            )

        available = bool(
            ranked_edges
            or checkpoints
            or replan_history
            or chapter_heatmap
            or volume_progress
            or series_snapshots
            or series_ending_checkpoint
        )
        return {
            "available": available,
            "relationship_network": {
                "available": bool(nodes or ranked_edges),
                "node_count": len(nodes),
                "edge_count": len(ranked_edges),
                "nodes": nodes,
                "edges": ranked_edges,
            },
            "relationship_hotspots": {
                "available": bool(ranked_edges),
                "items": ranked_edges[:6],
            },
            "steering_timeline": {
                "available": bool(steering_entries or memory_patch_summary),
                "checkpoint_count": len(checkpoints),
                "replan_event_count": len(replan_history),
                "memory_patch_summary": {
                    "pending_count": int(memory_patch_summary.get("pending_count", 0) or 0),
                    "adopted_count": int(memory_patch_summary.get("adopted_count", 0) or 0),
                    "characters_with_pending": [
                        character_lookup.get(str(character_id), {}).get("label", str(character_id))
                        for character_id in memory_patch_summary.get("characters_with_pending", [])
                        if str(character_id)
                    ],
                    "characters_with_adopted": [
                        character_lookup.get(str(character_id), {}).get("label", str(character_id))
                        for character_id in memory_patch_summary.get("characters_with_adopted", [])
                        if str(character_id)
                    ],
                },
                "entries": steering_entries[-12:],
            },
            "chapter_heatmap": {
                "available": bool(chapter_heatmap),
                "chapters": chapter_heatmap,
                "decision_histogram": dict((simulation_report.get("simulation_drilldown") or {}).get("decision_histogram") or {}),
                "issue_priority_groups": self._build_issue_priority_groups(chapter_heatmap),
            },
            "story_structure_snapshot": {
                "available": bool(volume_progress or arc_progress or series_snapshots or series_ending_checkpoint),
                "volumes": volume_progress,
                "arcs": arc_progress[:10],
                "volume_snapshot_count": len(volume_snapshots),
                "series_snapshot_count": len(series_snapshots),
                "series_snapshots": series_snapshots[-3:],
                "series_ending_checkpoint": series_ending_checkpoint,
                "replan_stability_metrics": replan_stability_metrics,
            },
        }

    def _build_simulation_diff_checkpoint(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        if not revisions:
            return {"available": False}
        simulation_freshness = self._simulation_freshness(metadata, simulation_report)
        latest_revision = revisions[-1]
        latest_revision_id = latest_revision.get("revision_id")
        last_simulated_revision_id = simulation_freshness.get("last_simulated_revision_id")
        chapter_compare = self._build_before_after_chapter_compare(metadata)
        pending_resimulation = bool(
            latest_revision_id
            and latest_revision_id != last_simulated_revision_id
        )
        checkpoint_status = (
            "pending_resimulation"
            if pending_resimulation
            else ("ready" if chapter_compare.get("available") else "baseline_only")
        )
        return {
            "available": True,
            "status": checkpoint_status,
            "auto_resimulate_suggested": pending_resimulation,
            "suggested_action": "simulate_draft" if pending_resimulation else ("review_compare" if chapter_compare.get("available") else "run_simulation"),
            "latest_revision_id": latest_revision_id,
            "latest_revision_label": latest_revision.get("label"),
            "latest_revision_source": latest_revision.get("source"),
            "latest_revision_summary": latest_revision.get("summary"),
            "last_simulated_revision_id": last_simulated_revision_id,
            "simulation_freshness": simulation_freshness,
            "compare_available": bool(chapter_compare.get("available")),
            "top_changed_chapter_count": len(chapter_compare.get("top_changed_chapters", [])),
            "next_actions": (
                ["re_simulate_for_checkpoint", "review_compare_after_simulation"]
                if pending_resimulation
                else (["review_compare_after_simulation"] if chapter_compare.get("available") else ["run_simulation_checkpoint"])
            ),
        }

    def _decorate_draft_payload(self, version: WorldVersion) -> dict[str, Any]:
        metadata = dict((version.worldpack_json or {}).get("metadata", {}))
        simulation_report = dict(version.simulation_report_json or {})
        simulation_report["_draft_metadata"] = metadata
        content_quality_repair_workbench = self._build_content_quality_repair_workbench(
            dict(version.worldpack_json or {}),
            simulation_report,
        )
        revision_compare = self._build_revision_compare(metadata, simulation_report)
        before_after = self._build_before_after_chapter_compare(metadata)
        capability = self._build_longform_capability_payload(worldpack_payload=dict(version.worldpack_json or {}), version=version)
        runway_minimums = self._band_minimums("100")
        structure_counts = dict(capability["structure_counts"] or {})
        latest_repair_loop_outcome = dict(simulation_report.get("latest_repair_loop_outcome") or {})
        revision_history = list(metadata.get("revision_history", []))
        latest_strategy_bundle_execution = (
            dict(simulation_report.get("latest_strategy_bundle_execution") or {})
            or self._latest_strategy_bundle_execution(revision_history)
        )
        strategy_bundle_execution_history = (
            list(simulation_report.get("strategy_bundle_execution_history") or [])
            or self._strategy_bundle_execution_history(revision_history)
        )
        quick_brief_gaps = []
        for key, label in (
            ("character_count", "角色"),
            ("scene_blueprint_count", "场景"),
            ("location_count", "地点"),
            ("scene_family_count", "scene family"),
            ("distinct_role_pair_count", "role pairs"),
        ):
            threshold_key = {
                "character_count": "min_characters",
                "scene_blueprint_count": "min_scene_blueprints",
                "location_count": "min_locations",
                "scene_family_count": "min_scene_family_count",
                "distinct_role_pair_count": "min_distinct_role_pairs",
            }[key]
            if int(structure_counts.get(key, 0) or 0) < int(runway_minimums.get(threshold_key, 0) or 0):
                quick_brief_gaps.append(f"{label} {structure_counts.get(key, 0)}/{runway_minimums.get(threshold_key, 0)}")
        quick_brief_runway_status = "ready" if not quick_brief_gaps else ("thin" if len(quick_brief_gaps) <= 2 else "insufficient")
        default_campaign = dict(content_quality_repair_workbench.get("default_campaign") or {})
        return {
            "world_version_id": version.world_version_id,
            "world_id": version.world_id,
            "status": version.status,
            "worldpack": version.worldpack_json,
            "entry_mode": capability["entry_mode"],
            "requested_target_chapters": capability["requested_target_chapters"],
            "requested_target_band": capability["requested_target_band"],
            "supported_target_band": capability["supported_target_band"],
            "claim_safe_band": capability["claim_safe_band"],
            "requires_structured_longform": capability["requires_structured_longform"],
            "longform_readiness": capability["longform_readiness"],
            "longform_structure_counts": capability["structure_counts"],
            "quick_brief_runway_summary": {
                "status": quick_brief_runway_status,
                "character_count": structure_counts.get("character_count", 0),
                "scene_blueprint_count": structure_counts.get("scene_blueprint_count", 0),
                "location_count": structure_counts.get("location_count", 0),
                "scene_family_count": structure_counts.get("scene_family_count", 0),
                "distinct_role_pair_count": structure_counts.get("distinct_role_pair_count", 0),
                "gaps": quick_brief_gaps,
            },
            "validation_report": version.validation_report_json,
            "validation_drilldown": self._build_validation_drilldown(dict(version.validation_report_json or {})),
            "simulation_report": version.simulation_report_json,
            "revision_history": revision_history,
            "latest_diff_summary": dict(metadata.get("latest_diff_summary", {})),
            "diff_drilldown": {
                **self._build_diff_drilldown(metadata),
                "simulation_freshness": self._simulation_freshness(metadata, simulation_report),
            },
            "simulation_drilldown": self._build_simulation_drilldown(simulation_report),
            "longform_drilldown": self._build_longform_drilldown(simulation_report),
            "promise_ledger_workbench": self._build_promise_ledger_workbench(simulation_report),
            "promise_runway_summary": self._build_promise_runway_summary(simulation_report),
            "promise_state_workbench": self._build_promise_state_workbench(metadata, simulation_report),
            "series_volume_arc_promise_mapping": self._build_series_volume_arc_promise_mapping(simulation_report),
            "chapter_task_simulation_linking": self._build_chapter_task_simulation_linking(simulation_report),
            "continuity_diff_workbench": self._build_continuity_diff_workbench(metadata, simulation_report),
            "character_fidelity_remediation_framework": self._build_character_fidelity_remediation_framework(simulation_report),
            "continuity_override_workbench": self._build_continuity_override_workbench(metadata, simulation_report),
            "simulation_diff_checkpoint": self._build_simulation_diff_checkpoint(metadata, simulation_report),
            "steering_checkpoint_summary": self._build_steering_checkpoint_summary(simulation_report),
            "replan_history": self._build_replan_history_summary(simulation_report),
            "memory_patch_summary": self._build_memory_patch_summary_view(simulation_report),
            "latest_repair_loop_outcome": latest_repair_loop_outcome,
            "repair_loop_history": self._repair_loop_history(revision_history),
            "latest_strategy_bundle_execution": latest_strategy_bundle_execution,
            "strategy_bundle_execution_history": strategy_bundle_execution_history,
            "hard_constraint_status": "blocked" if latest_repair_loop_outcome.get("issue_code") or default_campaign.get("issue_code") else "clear",
            "blocking_dimension": str(latest_repair_loop_outcome.get("issue_code") or default_campaign.get("issue_code") or ""),
            "window_breach_kind": str(latest_repair_loop_outcome.get("window_breach_kind") or default_campaign.get("breach_kind") or ""),
            "ready_for_validation": (
                bool(latest_repair_loop_outcome.get("ready_for_validation", False))
                if latest_repair_loop_outcome
                else not bool(default_campaign)
            ),
            "content_quality_repair_workbench": content_quality_repair_workbench,
            "creative_cockpit": dict(
                simulation_report.get("creative_cockpit")
                or self._build_creative_cockpit(version.worldpack_json, simulation_report)
            ),
            "memory_compression_summary": dict(
                simulation_report.get("longform_1000_summary")
                or simulation_report.get("longform_500_summary")
                or simulation_report.get("longform_250_summary")
                or {}
            ),
            "volume_memory_snapshots": list((simulation_report.get("final_state_snapshot") or {}).get("volume_memory_snapshots", [])),
            "series_memory_snapshots": list((simulation_report.get("final_state_snapshot") or {}).get("series_memory_snapshots", [])),
            "replan_stability_metrics": dict((simulation_report.get("final_state_snapshot") or {}).get("replan_stability_metrics", {})),
            "series_ending_checkpoint": dict((simulation_report.get("final_state_snapshot") or {}).get("series_ending_checkpoint", {})),
            "longform_250_evidence": dict(simulation_report.get("longform_250_evidence") or {}),
            "longform_500_evidence": dict(simulation_report.get("longform_500_evidence") or {}),
            "longform_1000_evidence": dict(simulation_report.get("longform_1000_evidence") or {}),
            "revision_compare": revision_compare,
            "before_after_chapter_compare": before_after,
        }

    def update_promise_state(
        self,
        world_version_id: str,
        *,
        promise_id: str,
        editor_state: str,
        notes: str = "",
        chapter_index: Optional[int] = None,
        chapter_task_id: Optional[str] = None,
        arc_id: Optional[str] = None,
        volume_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        payload = copy.deepcopy(version.worldpack_json)
        metadata = self._ensure_metadata(payload)
        self._set_promise_state_override(
            metadata,
            promise_id=promise_id,
            editor_state=editor_state,
            notes=notes,
            chapter_index=chapter_index,
            chapter_task_id=chapter_task_id,
            arc_id=arc_id,
            volume_id=volume_id,
        )
        return self.update_draft(
            world_version_id,
            payload,
            change_context={"source": "promise_state_editor", "label": "保存 Promise 状态"},
        )

    def update_continuity_override(
        self,
        world_version_id: str,
        *,
        chapter_index: int,
        override_state: str,
        notes: str = "",
        issue_scope: Optional[List[str]] = None,
        chapter_task_id: Optional[str] = None,
        arc_id: Optional[str] = None,
        volume_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        payload = copy.deepcopy(version.worldpack_json)
        metadata = self._ensure_metadata(payload)
        self._set_continuity_override(
            metadata,
            chapter_index=chapter_index,
            override_state=override_state,
            notes=notes,
            issue_scope=issue_scope,
            chapter_task_id=chapter_task_id,
            arc_id=arc_id,
            volume_id=volume_id,
        )
        return self.update_draft(
            world_version_id,
            payload,
            change_context={"source": "continuity_override_editor", "label": "保存 Continuity Override"},
        )

    def bulk_apply_task_continuity_override(
        self,
        world_version_id: str,
        *,
        chapter_indices: List[int],
        override_state: str,
        notes: str = "",
        issue_scope: Optional[List[str]] = None,
        chapter_task_id: Optional[str] = None,
        arc_id: Optional[str] = None,
        volume_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        payload = copy.deepcopy(version.worldpack_json)
        metadata = self._ensure_metadata(payload)
        normalized_indices = sorted({int(item) for item in chapter_indices if int(item) > 0})
        for chapter_index in normalized_indices:
            self._set_continuity_override(
                metadata,
                chapter_index=chapter_index,
                override_state=override_state,
                notes=notes,
                issue_scope=issue_scope,
                chapter_task_id=chapter_task_id,
                arc_id=arc_id,
                volume_id=volume_id,
            )
        return self.update_draft(
            world_version_id,
            payload,
            change_context={"source": "task_bulk_apply", "label": "批量应用 Task -> Simulation"},
        )

    def _workflow_target_version(self, *, account_id: Optional[str], world_version_id: Optional[str]) -> Optional[WorldVersion]:
        if world_version_id:
            return self.repository.get_world_version(world_version_id)
        if not account_id:
            return None
        for status in ("draft", "submitted"):
            for item in self.repository.list_world_versions(status=status):
                version = self.repository.get_world_version(item["world_version_id"])
                if version.author_id == account_id:
                    return version
        return None

    def _simulation_freshness(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        if not simulation_report:
            return {
                "status": "missing",
                "is_fresh": False,
                "latest_revision_id": revisions[-1].get("revision_id") if revisions else None,
                "latest_revision_at": revisions[-1].get("created_at") if revisions else None,
                "last_simulated_revision_id": None,
                "last_simulated_at": None,
            }
        latest_revision = revisions[-1] if revisions else {}
        last_simulated = next(
            (
                revision
                for revision in reversed(revisions)
                if dict(revision.get("simulation_delta") or {})
            ),
            None,
        )
        is_fresh = bool(last_simulated and latest_revision and last_simulated.get("revision_id") == latest_revision.get("revision_id"))
        return {
            "status": "fresh" if is_fresh else "stale",
            "is_fresh": is_fresh,
            "latest_revision_id": latest_revision.get("revision_id"),
            "latest_revision_at": latest_revision.get("created_at"),
            "last_simulated_revision_id": last_simulated.get("revision_id") if last_simulated else None,
            "last_simulated_at": last_simulated.get("created_at") if last_simulated else None,
        }

    def _validation_summary(self, validation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not validation_report:
            return {
                "available": False,
                "ok": False,
                "status": "missing",
                "error_count": 0,
                "warning_count": 0,
                "errors": [],
                "warnings": [],
            }
        return {
            "available": True,
            "ok": bool(validation_report.get("ok")),
            "status": "ok" if validation_report.get("ok") else "blocked",
            "error_count": len(validation_report.get("errors", [])),
            "warning_count": len(validation_report.get("warnings", [])),
            "errors": list(validation_report.get("errors", [])),
            "warnings": list(validation_report.get("warnings", [])),
        }

    def _simulation_summary(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        if not simulation_report:
            return {
                "available": False,
                "ok": False,
                "latest_decision": None,
                "completed_chapters": 0,
                "pass_rate": 0.0,
                "rewrite_rate": 0.0,
                "block_rate": 0.0,
                "stop_reason": None,
                "next_actions": [],
            }
        evaluation = dict(simulation_report.get("evaluation_summary") or {})
        return {
            "available": True,
            "ok": bool(simulation_report.get("ok")),
            "latest_decision": simulation_report.get("latest_decision"),
            "completed_chapters": int(simulation_report.get("completed_chapters", 0)),
            "pass_rate": float(evaluation.get("pass_rate", 0.0)),
            "rewrite_rate": float(evaluation.get("rewrite_rate", 0.0)),
            "block_rate": float(evaluation.get("block_rate", 0.0)),
            "stop_reason": simulation_report.get("stop_reason"),
            "next_actions": list(evaluation.get("next_actions", [])),
        }

    def _workflow_blockers(
        self,
        *,
        version: Optional[WorldVersion],
        access: Dict[str, Any],
        validation_summary: Dict[str, Any],
        simulation_summary: Dict[str, Any],
        simulation_freshness: Dict[str, Any],
        longform_readiness: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        blockers: List[Dict[str, Any]] = []
        actions = dict(access.get("actions", {}))
        if version is None:
            create_access = actions.get("draft_from_brief", {})
            if create_access and not create_access.get("allowed", True):
                blockers.append(
                    {
                        "key": "draft_from_brief_access",
                        "severity": "high",
                        "message": f"根据 Brief 生成 Draft 当前被阻止：{create_access.get('reason') or 'author_access_blocked'}",
                    }
                )
            return blockers
        for item in list(dict(longform_readiness or {}).get("blockers") or []):
            blocker = dict(item or {})
            if blocker:
                blockers.append(blocker)
        if validation_summary.get("available") and not validation_summary.get("ok", False):
            blockers.append(
                {
                    "key": "validation_errors",
                    "severity": "high",
                    "message": f"当前 Draft 仍有 {validation_summary.get('error_count', 0)} 个 validation errors。",
                }
            )
        if simulation_freshness.get("status") == "stale":
            blockers.append(
                {
                    "key": "stale_simulation",
                    "severity": "medium",
                    "message": "当前 simulation 已过期，最新 revision 还没有重新模拟。",
                }
            )
        if simulation_summary.get("available") and simulation_summary.get("latest_decision") not in {None, "pass"}:
            blockers.append(
                {
                    "key": "simulation_requires_revision",
                    "severity": "medium",
                    "message": f"当前 simulation 最新结论为 {simulation_summary.get('latest_decision')}，建议先修后再送审。",
                }
            )
        for action_name in ("simulate", "submit_draft", "update_draft"):
            action_access = actions.get(action_name, {})
            if action_access and not action_access.get("allowed", True):
                blockers.append(
                    {
                        "key": f"{action_name}_access",
                        "severity": "high",
                        "message": f"{action_name} 当前被阻止：{action_access.get('reason') or 'author_access_blocked'}",
                    }
                )
        return blockers

    def _workflow_stage_and_action(
        self,
        *,
        version: Optional[WorldVersion],
        validation_summary: Dict[str, Any],
        simulation_summary: Dict[str, Any],
        simulation_freshness: Dict[str, Any],
        longform_readiness: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        readiness = dict(longform_readiness or {})
        if version is None:
            return "brief", "create_from_brief"
        if readiness.get("status") == "blocked":
            if any(dict(item or {}).get("key") == "structured_longform_required" for item in list(readiness.get("blockers") or [])):
                return "draft_created", "bootstrap_structured_longform"
            return "draft_created", "focus_longform"
        if readiness.get("status") == "needs_enrichment":
            if str(readiness.get("band") or "100") == "100":
                return "draft_created", "bootstrap_quick_brief_enrich"
            return "draft_created", "bootstrap_structured_longform"
        if version.status == "submitted":
            return "submitted", "wait_for_review"
        if not validation_summary.get("available"):
            return "draft_created", "validate"
        if not validation_summary.get("ok"):
            return "draft_created", "fix_validation"
        if not simulation_summary.get("available"):
            return "validated", "simulate"
        if simulation_freshness.get("status") == "stale":
            return "revised_after_simulation", "re_simulate"
        if simulation_summary.get("latest_decision") != "pass" or simulation_summary.get("rewrite_rate", 0.0) > 0 or simulation_summary.get("block_rate", 0.0) > 0:
            return "simulated", "revise"
        return "ready_to_submit", "submit"

    def _workflow_stages(
        self,
        *,
        stage: str,
        version: Optional[WorldVersion],
        validation_summary: Dict[str, Any],
        simulation_summary: Dict[str, Any],
        simulation_freshness: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        stage_defs = [
            ("brief", "写 Brief"),
            ("draft_created", "创建 Draft"),
            ("validated", "校验通过"),
            ("simulated", "完成 Simulation"),
            ("revised_after_simulation", "修改后待重跑"),
            ("review_requested", "已请求内部审批"),
            ("changes_requested", "需要先处理修改意见"),
            ("approved_for_submit", "内部已批准，可送审"),
            ("ready_to_submit", "准备送审"),
            ("submitted", "已提交审核"),
        ]
        statuses: Dict[str, str] = {key: "pending" for key, _label in stage_defs}
        if version is None:
            statuses["brief"] = "current"
        else:
            statuses["brief"] = "complete"
            statuses["draft_created"] = "complete"
            if validation_summary.get("available") and validation_summary.get("ok"):
                statuses["validated"] = "complete"
            elif validation_summary.get("available"):
                statuses["validated"] = "blocked"
            if simulation_summary.get("available"):
                statuses["simulated"] = "complete"
            if simulation_freshness.get("status") == "stale":
                statuses["revised_after_simulation"] = "current"
            if stage == "ready_to_submit":
                statuses["ready_to_submit"] = "current"
            if version.status == "submitted":
                statuses["ready_to_submit"] = "complete"
                statuses["submitted"] = "current"
            elif stage == "simulated":
                statuses["simulated"] = "current"
            elif stage == "validated":
                statuses["validated"] = "current"
            elif stage == "draft_created":
                statuses["draft_created"] = "current"
        if stage == "brief":
            statuses["brief"] = "current"
        return [{"key": key, "label": label, "status": statuses[key]} for key, label in stage_defs]

    def _workflow_cta_actions(
        self,
        *,
        recommended_action: str,
        access: Dict[str, Any],
        version: Optional[WorldVersion],
        longform_readiness: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        actions = dict(access.get("actions", {}))
        readiness = dict(longform_readiness or {})

        def _access_enabled(action_key: str) -> tuple[bool, Optional[str]]:
            action_access = actions.get(action_key, {})
            return bool(action_access.get("allowed", True)), action_access.get("reason")

        ctas: List[Dict[str, Any]] = []
        if recommended_action == "create_from_brief":
            allowed, reason = _access_enabled("draft_from_brief")
            ctas.append({"action_id": "create_from_brief", "label": "根据 Brief 生成 Draft", "primary": True, "enabled": allowed, "reason": reason})
            save_allowed, save_reason = _access_enabled("save_draft")
            ctas.append({"action_id": "copy_current_world", "label": "从当前世界复制 Draft", "primary": False, "enabled": save_allowed, "reason": save_reason})
        elif recommended_action == "bootstrap_quick_brief_enrich":
            ctas.append(
                {
                    "action_id": "bootstrap_quick_brief_enrich",
                    "label": "补齐 100 章骨架",
                    "primary": True,
                    "enabled": True,
                    "reason": "当前 quick brief 的角色 / 场景 / 地点骨架还不足以安全承诺 100 章。",
                }
            )
            ctas.append({"action_id": "focus_longform", "label": "查看长篇规划", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "bootstrap_structured_longform":
            ctas.append(
                {
                    "action_id": "bootstrap_structured_longform",
                    "label": f"进入 {readiness.get('band') or '结构化'} 长篇蓝图",
                    "primary": True,
                    "enabled": True,
                    "reason": "当前目标长度已经超出 quick brief 可直接承诺的范围，需要先补齐结构化长篇骨架。",
                }
            )
            ctas.append({"action_id": "focus_longform", "label": "查看长篇规划", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "validate":
            allowed, reason = _access_enabled("validate_draft")
            ctas.append({"action_id": "validate_draft", "label": "运行校验", "primary": True, "enabled": allowed, "reason": reason})
        elif recommended_action == "fix_validation":
            ctas.append({"action_id": "focus_validation", "label": "查看校验问题", "primary": True, "enabled": True, "reason": None})
            ctas.append({"action_id": "focus_revision", "label": "跳到编辑区", "primary": False, "enabled": True, "reason": None})
        elif recommended_action in {"simulate", "re_simulate"}:
            allowed, reason = _access_enabled("simulate")
            ctas.append({"action_id": "simulate_draft", "label": "重新运行 Simulation" if recommended_action == "re_simulate" else "运行 Simulation", "primary": True, "enabled": allowed, "reason": reason})
            if recommended_action == "re_simulate":
                ctas.append({"action_id": "focus_diff", "label": "查看最近改动", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "revise":
            ctas.append({"action_id": "focus_simulation", "label": "查看模拟问题", "primary": True, "enabled": True, "reason": None})
            ctas.append({"action_id": "focus_diff", "label": "查看最近改动", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "submit":
            allowed, reason = _access_enabled("submit_draft")
            ctas.append({"action_id": "submit_draft", "label": "送审", "primary": True, "enabled": allowed, "reason": reason})
            ctas.append({"action_id": "focus_version_history", "label": "查看版本轨迹", "primary": False, "enabled": True, "reason": None})
        elif recommended_action == "wait_for_review":
            ctas.append({"action_id": "focus_version_history", "label": "查看审核状态", "primary": True, "enabled": True, "reason": None})
        elif recommended_action == "focus_longform":
            ctas.append({"action_id": "focus_longform", "label": "打开长篇规划", "primary": True, "enabled": True, "reason": None})
        if version is not None:
            ctas.append({"action_id": "focus_draft_detail", "label": "查看当前 Draft", "primary": False, "enabled": True, "reason": None})
        return ctas

    def _approval_summary(self, world_version_id: str) -> Dict[str, Any]:
        records = self.repository.list_author_approval_records(world_version_id=world_version_id)
        latest = records[0] if records else None
        return {
            "available": bool(records),
            "latest_status": latest.get("status") if latest else None,
            "latest_record": latest,
            "history": records,
        }

    def _collaboration_summary(self, world_version_id: str) -> Dict[str, Any]:
        threads = self.repository.list_author_comment_threads(world_version_id=world_version_id)
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in threads:
            key = f"{item.get('anchor_type')}:{item.get('anchor_key')}"
            grouped.setdefault(key, []).append(item)
        threads_by_anchor = [
            {
                "anchor": key,
                "anchor_type": key.split(":", 1)[0],
                "anchor_key": key.split(":", 1)[1] if ":" in key else "",
                "thread_count": len(items),
                "open_count": sum(1 for thread in items if thread.get("status") == "open"),
                "blocking_count": sum(1 for thread in items if thread.get("status") == "open" and thread.get("severity") in {"blocker", "high"}),
                "threads": items,
            }
            for key, items in sorted(grouped.items())
        ]
        open_thread_count = sum(1 for item in threads if item.get("status") == "open")
        blocking_thread_count = sum(1 for item in threads if item.get("status") == "open" and item.get("severity") in {"blocker", "high"})
        return {
            "open_thread_count": open_thread_count,
            "blocking_thread_count": blocking_thread_count,
            "queue_summary": {
                "open_thread_count": open_thread_count,
                "blocking_thread_count": blocking_thread_count,
                "status_counts": {
                    status: sum(1 for item in threads if item.get("status") == status)
                    for status in sorted({str(item.get("status") or "unknown") for item in threads})
                },
            },
            "threads": threads,
            "threads_by_anchor": threads_by_anchor,
        }

    def _simulation_snapshot(self, simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        chapter_trace_map = {
            item.get("chapter_id"): dict(item)
            for item in simulation_report.get("chapter_trace", [])
            if item.get("chapter_id")
        }
        chapter_snapshots = []
        for index, payload in enumerate(simulation_report.get("chapter_evaluations", []), start=1):
            chapter_id = str(payload.get("chapter_id") or f"chapter_{index}")
            scores = dict(payload.get("scores") or {})
            lint_metrics = dict((payload.get("hard_validator_results") or {}).get("lint_metrics") or {})
            trace = chapter_trace_map.get(chapter_id, {})
            chapter_snapshots.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_index": index,
                    "chapter_title": trace.get("chapter_title") or chapter_id,
                    "decision": payload.get("decision", {}).get("decision", "rewrite"),
                    "overall_score": round(float(scores.get("overall_score", 0.0)), 3),
                    "issue_codes": [issue.get("issue_code") for issue in payload.get("issues", []) if issue.get("issue_code")],
                    "signal_snapshot": {
                        "pacing": round(float(scores.get("pacing", 0.0)), 3),
                        "hook_quality": round(float(scores.get("hook_quality", 0.0)), 3),
                        "scene_density": round(float(scores.get("scene_density", 0.0)), 3),
                        "repetition_score": round(float(lint_metrics.get("repetition_score", 0.0)), 3),
                        "exposition_ratio": round(float(lint_metrics.get("exposition_ratio", 0.0)), 3),
                        "concrete_detail_density": round(float(lint_metrics.get("concrete_detail_density", 0.0)), 3),
                    },
                    "body_excerpt": trace.get("body_excerpt", ""),
                }
            )
        return {
            "completed_chapters": simulation_report.get("completed_chapters", 0),
            "latest_decision": simulation_report.get("latest_decision"),
            "chapter_snapshots": chapter_snapshots,
        }

    def _build_revision_compare(self, metadata: Dict[str, Any], simulation_report: Dict[str, Any]) -> Dict[str, Any]:
        revisions = list(metadata.get("revision_history", []))
        if len(revisions) < 2:
            return {"available": False}
        before = revisions[-2]
        after = revisions[-1]
        return {
            "available": True,
            "before_revision_id": before.get("revision_id"),
            "after_revision_id": after.get("revision_id"),
            "before_label": before.get("label"),
            "after_label": after.get("label"),
            "before_summary": before.get("summary"),
            "after_summary": after.get("summary"),
            "after_diff_summary": dict(after.get("diff_summary") or {}),
            "section_counts": {
                "before_changed_sections": len((before.get("diff_summary") or {}).get("changed_sections", [])),
                "after_changed_sections": len((after.get("diff_summary") or {}).get("changed_sections", [])),
            },
            "simulation_delta": dict(after.get("simulation_delta") or {}),
            "simulation_freshness": self._simulation_freshness(metadata, simulation_report),
        }

    def _build_before_after_chapter_compare(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        simulated_revisions = [
            revision
            for revision in metadata.get("revision_history", [])
            if dict(revision.get("simulation_snapshot") or {})
        ]
        if len(simulated_revisions) < 2:
            return {"available": False}
        before = simulated_revisions[-2]
        after = simulated_revisions[-1]
        before_map = {
            int(item.get("chapter_index")): dict(item)
            for item in (before.get("simulation_snapshot") or {}).get("chapter_snapshots", [])
        }
        after_map = {
            int(item.get("chapter_index")): dict(item)
            for item in (after.get("simulation_snapshot") or {}).get("chapter_snapshots", [])
        }
        compares = []
        for chapter_index in sorted(set(before_map) & set(after_map)):
            left = before_map[chapter_index]
            right = after_map[chapter_index]
            left_issues = set(left.get("issue_codes", []))
            right_issues = set(right.get("issue_codes", []))
            left_signals = dict(left.get("signal_snapshot") or {})
            right_signals = dict(right.get("signal_snapshot") or {})
            compares.append(
                {
                    "chapter_index": chapter_index,
                    "before_title": left.get("chapter_title"),
                    "after_title": right.get("chapter_title"),
                    "before_decision": left.get("decision"),
                    "after_decision": right.get("decision"),
                    "overall_score_delta": round(float(right.get("overall_score", 0.0)) - float(left.get("overall_score", 0.0)), 3),
                    "issue_codes_added": sorted(right_issues - left_issues),
                    "issue_codes_removed": sorted(left_issues - right_issues),
                    "signal_deltas": {
                        key: round(float(right_signals.get(key, 0.0)) - float(left_signals.get(key, 0.0)), 3)
                        for key in {"pacing", "hook_quality", "scene_density", "repetition_score", "exposition_ratio", "concrete_detail_density"}
                    },
                    "before_excerpt": left.get("body_excerpt", ""),
                    "after_excerpt": right.get("body_excerpt", ""),
                }
            )
        compares.sort(key=lambda item: (-abs(float(item.get("overall_score_delta", 0.0))), item["chapter_index"]))
        return {
            "available": bool(compares),
            "before_revision_id": before.get("revision_id"),
            "after_revision_id": after.get("revision_id"),
            "chapter_compares": compares,
            "top_changed_chapters": compares[:5],
            "chapter_compare_map": {
                str(item.get("chapter_index")): dict(item)
                for item in compares
                if item.get("chapter_index") is not None
            },
        }

    def workflow_summary(
        self,
        *,
        account_id: Optional[str],
        world_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_account_id = self.billing.resolve_account_id(account_id=account_id) or account_id
        version = self._workflow_target_version(account_id=resolved_account_id, world_version_id=world_version_id)
        if not resolved_account_id and version is not None:
            resolved_account_id = version.author_id
        resolved_account_id = resolved_account_id or "web_author"
        selected_world_version_id = version.world_version_id if version else world_version_id
        access = self.billing.author_access_snapshot(
            account_id=resolved_account_id,
            world_version_id=selected_world_version_id,
        )
        validation_report = dict(version.validation_report_json or {}) if version else {}
        simulation_report = dict(version.simulation_report_json or {}) if version else {}
        metadata = dict((version.worldpack_json or {}).get("metadata", {})) if version else {}
        validation_summary = self._validation_summary(validation_report)
        simulation_summary = self._simulation_summary(simulation_report)
        simulation_freshness = self._simulation_freshness(metadata, simulation_report)
        simulation_longform_drilldown = self._build_longform_drilldown(simulation_report)
        longform_capability = self._build_longform_capability_payload(
            worldpack_payload=dict(version.worldpack_json or {}) if version else {},
            version=version,
        ) if version else {
            "entry_mode": "quick_brief",
            "requested_target_chapters": self._quick_brief_max_target_chapters(),
            "requested_target_band": "100",
            "supported_target_band": None,
            "claim_safe_band": None,
            "requires_structured_longform": False,
            "structure_counts": {"character_count": 0, "scene_blueprint_count": 0, "location_count": 0},
            "longform_readiness": {
                "band": "100",
                "status": "blocked",
                "blockers": [],
                "recommended_actions": ["create_from_brief"],
                "minimums": self._band_minimums("100"),
            },
        }
        if simulation_longform_drilldown.get("longform_structure_exhaustion"):
            longform_capability["longform_readiness"] = {
                **dict(longform_capability.get("longform_readiness") or {}),
                "status": "blocked",
                "blockers": list(dict(longform_capability.get("longform_readiness") or {}).get("blockers") or [])
                + [dict(simulation_longform_drilldown.get("longform_structure_exhaustion") or {})],
                "recommended_actions": list((simulation_longform_drilldown.get("longform_structure_exhaustion") or {}).get("recommended_actions") or []),
            }
        collaboration_summary = self._collaboration_summary(version.world_version_id) if version else {
            "open_thread_count": 0,
            "blocking_thread_count": 0,
            "threads": [],
            "threads_by_anchor": [],
        }
        approval_summary = self._approval_summary(version.world_version_id) if version else {
            "available": False,
            "latest_status": None,
            "latest_record": None,
            "history": [],
        }
        stage, recommended_action = self._workflow_stage_and_action(
            version=version,
            validation_summary=validation_summary,
            simulation_summary=simulation_summary,
            simulation_freshness=simulation_freshness,
            longform_readiness=longform_capability["longform_readiness"],
        )
        latest_approval_status = approval_summary.get("latest_status")
        if collaboration_summary.get("blocking_thread_count", 0) > 0:
            stage = "changes_requested"
            recommended_action = "revise"
        elif latest_approval_status == "requested":
            stage = "review_requested"
            recommended_action = "wait_for_review"
        elif latest_approval_status == "changes_requested":
            stage = "changes_requested"
            recommended_action = "revise"
        elif latest_approval_status == "approved" and simulation_freshness.get("status") == "fresh" and stage == "ready_to_submit":
            stage = "approved_for_submit"
            recommended_action = "submit"
        blockers = self._workflow_blockers(
            version=version,
            access=access,
            validation_summary=validation_summary,
            simulation_summary=simulation_summary,
            simulation_freshness=simulation_freshness,
            longform_readiness=longform_capability["longform_readiness"],
        )
        return {
            "account_id": resolved_account_id,
            "world_version_id": version.world_version_id if version else None,
            "world_id": version.world_id if version else None,
            "draft_title": (version.worldpack_json or {}).get("title") if version else None,
            "status": version.status if version else "no_draft",
            "entry_mode": longform_capability["entry_mode"],
            "requested_target_chapters": longform_capability["requested_target_chapters"],
            "requested_target_band": longform_capability["requested_target_band"],
            "supported_target_band": longform_capability["supported_target_band"],
            "claim_safe_band": longform_capability["claim_safe_band"],
            "requires_structured_longform": longform_capability["requires_structured_longform"],
            "longform_readiness": longform_capability["longform_readiness"],
            "longform_structure_counts": longform_capability["structure_counts"],
            "quick_brief_runway_summary": (
                self.get_draft(version.world_version_id).get("quick_brief_runway_summary")
                if version is not None
                else {}
            ),
            "promise_runway_summary": (
                self._build_promise_runway_summary(simulation_report)
                if simulation_report
                else {"available": False}
            ),
            "stage": stage,
            "recommended_action": recommended_action,
            "blockers": blockers,
            "stages": self._workflow_stages(
                stage=stage,
                version=version,
                validation_summary=validation_summary,
                simulation_summary=simulation_summary,
                simulation_freshness=simulation_freshness,
            ),
            "access": access,
            "collaboration_summary": collaboration_summary,
            "approval_summary": approval_summary,
            "open_blocking_threads": collaboration_summary.get("blocking_thread_count", 0),
            "can_request_approval": bool(version and validation_summary.get("ok") and simulation_summary.get("available") and version.status != "submitted"),
            "can_submit": bool(
                version
                and version.status != "submitted"
                and simulation_freshness.get("status") == "fresh"
                and latest_approval_status not in {"requested", "changes_requested"}
                and collaboration_summary.get("blocking_thread_count", 0) == 0
                and recommended_action == "submit"
            ),
            "validation_summary": validation_summary,
            "simulation_summary": simulation_summary,
            "simulation_freshness": simulation_freshness,
            "interactive_longform_signoff": dict((simulation_report.get("cross_pack_summary") or {}).get("interactive_longform_signoff") or {}),
            "longform_250_interactive_signoff": dict((simulation_report.get("cross_pack_summary") or {}).get("longform_250_interactive_signoff") or {}),
            "longform_500_interactive_signoff": dict((simulation_report.get("cross_pack_summary") or {}).get("longform_500_interactive_signoff") or {}),
            "cta_actions": self._workflow_cta_actions(
                recommended_action=recommended_action,
                access=access,
                version=version,
                longform_readiness=longform_capability["longform_readiness"],
            ),
        }

    def save_draft(self, worldpack: dict[str, Any], *, change_context: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        pack = WorldPack.from_dict(worldpack)
        pack_payload = pack.to_dict()
        if self._should_persist_longform_capability_metadata(pack_payload):
            self._sync_longform_capability_metadata(pack_payload)
        _ensure_character_asset_coverage(pack_payload)
        context = self._normalize_change_context(change_context, default_source="manual_update", default_label="创建 draft")
        self._append_revision(
            worldpack_payload=pack_payload,
            change_context=context,
            diff_summary={
                "changed_sections": ["manifest", "world_bible", "characters", "scene_blueprints"],
                "character_changes": [],
                "scene_changes": [],
                "capability_changes": [],
                "summary_text": context["label"],
            },
        )
        normalized_pack = WorldPack.from_dict(pack_payload)
        report = validate_worldpack_payload(pack_payload)
        world_version_id = "%s@%s" % (normalized_pack.world_id, normalized_pack.version)
        version = WorldVersion.from_worldpack(
            worldpack=normalized_pack,
            world_version_id=world_version_id,
            status="draft",
            validation_report_json=report,
        )
        self.repository.save_world_version(version, publish=False)
        return self.get_draft(world_version_id)

    def get_brief_template(self) -> dict[str, Any]:
        template_path = self.base_dir / "examples" / "worldpacks" / "author_brief_template.yaml"
        template_text = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        preset_ids = ["jade_court", "urban_mystery", "xianxia", "synthetic"]
        return {
            "template_text": template_text,
            "defaults": {
                "world_title": "",
                "genre_preset": "urban_mystery",
                "target_audience": "喜欢连续阅读型章节故事的读者",
                "genres": [],
                "core_premise": "",
                "life_theme": "",
                "lead_name": "主角",
                "counterpart_name": "对手",
                "supporting_name": "",
                "locations": "",
                "trial_chapters": 2,
                "paid_after": 3,
                "risk_rating": "PG-13",
                "author_id": "web_author",
                "target_total_chapters": 100,
                "target_total_volumes": 5,
                "target_word_count": 200000,
            },
            "quick_brief_max_target_chapters": self._quick_brief_max_target_chapters(),
            "structured_longform_bands": list(self._longform_capability_profiles().get("structured_longform_bands") or []),
            "longform_capability_profiles": dict(self._longform_capability_profiles().get("bands") or {}),
            "genre_presets": [
                {"id": "jade_court", "label": "权门伦理", "description": "家门、体面、师长压力与真心拉扯。"},
                {"id": "urban_mystery", "label": "都市情感悬疑", "description": "旧巷、隐瞒、关系债与真相回潮。"},
                {"id": "xianxia", "label": "仙侠誓愿", "description": "旧誓、反噬、修行与天命的取舍。"},
                {"id": "synthetic", "label": "极简实验", "description": "最小世界，用于快速试验 narrative kernel。"},
            ],
            "preset_defaults": {
                preset_id: {
                    "world_title": _genre_preset(preset_id)["title"],
                    "genre_preset": preset_id,
                    "core_premise": _genre_preset(preset_id)["premise"],
                    "life_theme": _genre_preset(preset_id)["life_theme"],
                    "lead_name": _genre_preset(preset_id)["lead_name"],
                    "counterpart_name": _genre_preset(preset_id)["counterpart_name"],
                    "supporting_name": _genre_preset(preset_id).get("supporting_name", ""),
                    "locations": "\n".join(_genre_preset(preset_id)["locations"]),
                }
                for preset_id in preset_ids
            },
        }

    def create_draft_from_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        worldpack_payload = self._worldpack_from_brief(brief)
        metadata = self._ensure_metadata(worldpack_payload)
        requested_target_chapters = max(24, int(brief.get("target_total_chapters") or 100))
        metadata["entry_mode"] = "quick_brief"
        metadata["requested_target_chapters"] = requested_target_chapters
        metadata["generated_from_brief"] = True
        if requested_target_chapters <= self._quick_brief_max_target_chapters():
            self._apply_longform_asset_enrichment(worldpack_payload=worldpack_payload, target_band="100")
            metadata["longform_program_stage"] = "L1_foundation_enriched"
            metadata["quick_brief_enriched"] = True
            metadata["quick_brief_enriched_band"] = "100"
        else:
            metadata["quick_brief_enriched"] = False
            metadata["quick_brief_enriched_band"] = None
        self._sync_longform_capability_metadata(worldpack_payload)
        pack = WorldPack.from_dict(worldpack_payload)
        return self.save_draft(
            pack.to_dict(),
            change_context={"source": "brief_create", "label": "从 brief 生成 draft"},
        )

    def _worldpack_from_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        template_path = self.base_dir / "examples" / "worldpacks" / "world_template_minimal.json"
        payload = json.loads(template_path.read_text(encoding="utf-8"))
        preset_id = str(brief.get("genre_preset") or "urban_mystery")
        preset = _genre_preset(preset_id)
        world_title = str(brief.get("world_title") or preset["title"])
        lead_name = str(brief.get("lead_name") or preset["lead_name"])
        counterpart_name = str(brief.get("counterpart_name") or preset["counterpart_name"])
        supporting_name = str(brief.get("supporting_name") or preset.get("supporting_name") or "").strip()
        locations = [line.strip() for line in str(brief.get("locations") or "").splitlines() if line.strip()] or list(preset["locations"])
        version = "0.1.0-draft-%s" % uuid4().hex[:6]
        world_id = _slugify_world_id(world_title)
        genres = list(brief.get("genres") or []) or list(preset["genres"])
        core_premise = str(brief.get("core_premise") or preset["premise"])
        life_theme = str(brief.get("life_theme") or preset["life_theme"])
        risk_rating = str(brief.get("risk_rating") or "PG-13")
        trial_chapters = int(brief.get("trial_chapters") or 2)
        paid_after = int(brief.get("paid_after") or 3)
        author_id = str(brief.get("author_id") or "web_author")
        target_total_chapters = max(12, int(brief.get("target_total_chapters") or 100))
        target_total_volumes = max(1, int(brief.get("target_total_volumes") or 5))
        target_word_count = max(20000, int(brief.get("target_word_count") or (target_total_chapters * 2000)))

        payload["world_id"] = world_id
        payload["title"] = world_title
        payload["version"] = version
        payload["manifest"]["author_id"] = author_id
        payload["manifest"]["genres"] = genres
        payload["manifest"]["risk_rating"] = risk_rating
        payload["manifest"]["monetization_policy"] = {
            "trial_chapters": trial_chapters,
            "paid_after": paid_after,
        }
        payload["world_bible"] = {
            "premise": core_premise,
            "canon_rules": list(preset["canon_rules"]),
            "forbidden_moves": list(preset["forbidden_moves"]),
            "locations": locations,
        }
        payload["style_pack"] = dict(preset["style_pack"])
        payload["risk_policy"] = {
            "shareable": True,
            "requires_manual_review": False,
        }
        payload["characters"] = _build_characters_for_preset(
            preset_id=preset_id,
            lead_name=lead_name,
            counterpart_name=counterpart_name,
            supporting_name=supporting_name,
            life_theme=life_theme,
        )
        payload["scene_blueprints"] = _build_scene_blueprints_for_preset(preset_id)
        payload["dialogue_realism_policy"] = dict(preset["dialogue_realism_policy"])
        payload["voice_profiles"] = _build_voice_profiles_for_preset(preset_id)
        payload["response_cadence_profiles"] = _build_response_profiles_for_preset(preset_id)
        payload["pressure_response_styles"] = _build_pressure_styles_for_preset(preset_id)
        payload["emotion_action_policies"] = _build_action_policies_for_preset(preset_id)
        payload["sensory_grounding_policies"] = _build_sensory_policies_for_preset(preset_id, locations)
        payload["scene_realization_contracts"] = _build_scene_realization_for_preset(preset_id)
        longform_structure = _build_longform_structure(
            world_id=world_id,
            world_title=world_title,
            life_theme=life_theme,
            target_total_chapters=target_total_chapters,
            target_total_volumes=target_total_volumes,
            target_word_count=target_word_count,
        )
        payload["series_plan"] = longform_structure["series_plan"]
        payload["volume_plans"] = longform_structure["volume_plans"]
        payload["arc_plans"] = longform_structure["arc_plans"]
        payload["chapter_budget_policy"] = longform_structure["chapter_budget_policy"]
        payload["series_storyline_contract"] = _build_storyline_contract_from_brief(
            world_title=world_title,
            core_premise=core_premise,
            life_theme=life_theme,
            volume_plans=payload["volume_plans"],
        )
        payload["character_memory_profiles"] = _build_character_memory_profiles_from_characters(payload["characters"])
        payload["steering_guardrails"] = _default_steering_guardrails()
        payload["memory_compression_policy"] = _default_memory_compression_policy(target_total_volumes)
        payload["metadata"] = {
            "author_brief": dict(brief),
            "generated_from_brief": True,
            "longform_program_stage": "L1_foundation",
        }
        payload["narrative_style_pack"] = {
            "style_pack_id": "%s_style" % preset_id,
            "tonal_lexicon": list(preset["tonal_lexicon"]),
            "thematic_axis_labels": dict(preset["thematic_axis_labels"]),
            "hook_templates": list(preset["hook_templates"]),
            "goal_labels": {},
            "tag_labels": {genre: preset["thematic_axis_labels"].get(genre, genre.replace("_", " ")) for genre in genres},
            "dialogue": {
                **payload["dialogue_realism_policy"],
                "voice_profiles": payload["voice_profiles"],
                "response_profiles": payload["response_cadence_profiles"],
                "pressure_styles": payload["pressure_response_styles"],
            },
            "emotion_actions": payload["emotion_action_policies"]["default"],
            "sensory_grounding": payload["sensory_grounding_policies"]["default"],
            "scene_realization": payload["scene_realization_contracts"]["default"],
        }
        return payload

    def get_draft(self, world_version_id: str) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        return self._decorate_draft_payload(version)

    def update_draft(self, world_version_id: str, worldpack: dict[str, Any], *, change_context: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        previous_worldpack = copy.deepcopy(version.worldpack_json)
        pack = WorldPack.from_dict(worldpack)
        next_payload = pack.to_dict()
        if self._should_persist_longform_capability_metadata(next_payload):
            self._sync_longform_capability_metadata(next_payload, version=version)
        _ensure_character_asset_coverage(next_payload)
        normalized_pack = WorldPack.from_dict(next_payload)
        context = self._normalize_change_context(change_context, default_source="manual_update", default_label="手动更新 draft")
        diff_summary = self._diff_sections(previous_worldpack, next_payload)
        self._append_revision(
            worldpack_payload=next_payload,
            change_context=context,
            diff_summary=diff_summary,
        )
        version.worldpack_json = next_payload
        version.manifest_json = normalized_pack.manifest.to_dict()
        version.validation_report_json = validate_worldpack_payload(next_payload)
        version.status = "draft"
        self.repository.save_world_version(version, publish=False)
        return self.get_draft(world_version_id)

    def bootstrap_longform_workbench(
        self,
        world_version_id: str,
        *,
        mode: str = "structured_longform",
        target_band: Optional[str] = None,
    ) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        payload = copy.deepcopy(version.worldpack_json)
        normalized_mode = str(mode or "structured_longform").strip() or "structured_longform"
        if normalized_mode not in {"quick_brief_enrich", "structured_longform"}:
            raise ValueError("invalid_longform_bootstrap_mode")
        resolved_target_band = str(target_band or "").strip() or self._target_band_for_chapters(
            int(((payload.get("metadata") or {}).get("author_brief") or {}).get("target_total_chapters") or ((payload.get("series_plan") or {}).get("total_chapter_target") or 100))
        )
        if resolved_target_band not in LONGFORM_CAPABILITY_BAND_ORDER:
            raise ValueError("invalid_longform_target_band")
        if normalized_mode == "quick_brief_enrich":
            resolved_target_band = "100"
        if payload.get("series_plan") and payload.get("volume_plans") and payload.get("arc_plans"):
            payload.setdefault(
                "series_storyline_contract",
                _build_storyline_contract_from_brief(
                    world_title=str(payload.get("title") or version.world_id),
                    core_premise=str((payload.get("world_bible") or {}).get("premise") or payload.get("title") or version.world_id),
                    life_theme=str((payload.get("metadata") or {}).get("author_brief", {}).get("life_theme") or ""),
                    volume_plans=list(payload.get("volume_plans") or []),
                ),
            )
        else:
            structure = _bootstrap_longform_structure_payload(
                worldpack_payload=payload,
                runtime_world_title=str(payload.get("title") or version.world_id),
            )
            payload["series_plan"] = dict(structure["series_plan"])
            payload["volume_plans"] = [dict(item) for item in structure["volume_plans"]]
            payload["arc_plans"] = [dict(item) for item in structure["arc_plans"]]
            payload["chapter_budget_policy"] = dict(structure["chapter_budget_policy"])
        structure = _bootstrap_longform_structure_payload(
            worldpack_payload=payload,
            runtime_world_title=str(payload.get("title") or version.world_id),
        )
        payload["series_storyline_contract"] = _build_storyline_contract_from_brief(
            world_title=str(payload.get("title") or version.world_id),
            core_premise=str((payload.get("world_bible") or {}).get("premise") or payload.get("title") or version.world_id),
            life_theme=str((payload.get("metadata") or {}).get("author_brief", {}).get("life_theme") or ""),
            volume_plans=list(payload.get("volume_plans") or []),
        )
        payload["steering_guardrails"] = _default_steering_guardrails()
        payload["memory_compression_policy"] = _default_memory_compression_policy(len(payload.get("volume_plans") or []))
        self._apply_longform_asset_enrichment(worldpack_payload=payload, target_band=resolved_target_band)
        metadata = self._ensure_metadata(payload)
        metadata["entry_mode"] = normalized_mode if normalized_mode == "quick_brief_enrich" else "structured_longform"
        metadata["longform_program_stage"] = "L2_workbench" if normalized_mode == "structured_longform" else "L1_foundation_enriched"
        metadata["longform_workbench_bootstrapped"] = True
        metadata["longform_workbench_plan_source"] = structure.get("plan_source", "workbench_bootstrap")
        metadata["structured_longform_target_band"] = resolved_target_band if normalized_mode == "structured_longform" else metadata.get("structured_longform_target_band")
        metadata["quick_brief_enriched"] = normalized_mode == "quick_brief_enrich"
        metadata["quick_brief_enriched_band"] = resolved_target_band if normalized_mode == "quick_brief_enrich" else metadata.get("quick_brief_enriched_band")
        self._sync_longform_capability_metadata(payload)
        return self.update_draft(
            world_version_id,
            payload,
            change_context={
                "source": "longform_workbench_bootstrap" if normalized_mode == "structured_longform" else "quick_brief_enrich",
                "label": "生成 Longform Workbench 规划" if normalized_mode == "structured_longform" else "补齐 100 章 quick brief 长线骨架",
            },
        )

    def _select_candidate_world_version_id(self, world_id: str) -> str:
        versions = self.repository.list_world_versions(world_id=world_id)
        candidate = next((item for item in versions if item["status"] == "draft"), None) or (versions[0] if versions else None)
        if candidate is None:
            raise KeyError("unknown_world:%s" % world_id)
        return candidate["world_version_id"]

    def _baseline(self) -> Dict[str, Any] | None:
        baseline_path = self.base_dir / "tests" / "benchmark_baseline.json"
        if baseline_path.exists():
            return json.loads(baseline_path.read_text(encoding="utf-8"))
        return None

    def _build_cross_pack_summary(self, world_id: str, world_version_id: str, *, benchmark_mode: Optional[str] = None, max_chapters: int = 6) -> Dict[str, Any]:
        def _simulation_runner(
            benchmark_world_id: str,
            benchmark_world_version_id: str,
            interactive_scenarios: Optional[List[Dict[str, Any]]] = None,
        ) -> Dict[str, Any]:
            return self.run_simulation_for_world_version(
                benchmark_world_version_id,
                include_cross_pack=False,
                max_chapters=max_chapters,
                interactive_scenarios=interactive_scenarios,
            )

        summary = run_benchmark(
            repository=self.repository,
            golden_dir=self.base_dir / "tests" / "golden_routes",
            worldpack="all",
            baseline=self._baseline(),
            world_version_overrides={world_id: world_version_id},
            benchmark_mode=benchmark_mode,
            max_chapters=max_chapters,
            simulation_runner=_simulation_runner,
        )
        return {
            "cross_pack_pass_rate": summary.get("cross_pack_pass_rate", 0.0),
            "top_failing_packs": summary.get("top_failing_packs", []),
            "delta_summary": summary.get("delta_summary", {}),
            "worlds": summary.get("worlds", []),
            "weakest_pack_polish_program": summary.get("weakest_pack_polish_program", {}),
            "longform_l1_signoff": summary.get("longform_l1_signoff", {}),
            "interactive_longform_signoff": summary.get("interactive_longform_signoff", {}),
            "longform_250_signoff": summary.get("longform_250_signoff", {}),
            "longform_250_interactive_signoff": summary.get("longform_250_interactive_signoff", {}),
            "longform_250_human_review_closeout": summary.get("longform_250_human_review_closeout", {}),
            "longform_250_evidence": summary.get("longform_250_evidence", {}),
            "longform_500_signoff": summary.get("longform_500_signoff", {}),
            "longform_500_interactive_signoff": summary.get("longform_500_interactive_signoff", {}),
            "longform_500_human_review_closeout": summary.get("longform_500_human_review_closeout", {}),
            "longform_500_ending_signoff": summary.get("longform_500_ending_signoff", {}),
            "longform_500_evidence": summary.get("longform_500_evidence", {}),
            "longform_1000_readiness": summary.get("longform_1000_readiness", {}),
            "longform_1000_interactive_signoff": summary.get("longform_1000_interactive_signoff", {}),
            "longform_1000_human_review_closeout": summary.get("longform_1000_human_review_closeout", {}),
            "longform_1000_feasibility": summary.get("longform_1000_feasibility", {}),
            "longform_1000_evidence": summary.get("longform_1000_evidence", {}),
            "character_fidelity_remediation_framework": summary.get("character_fidelity_remediation_framework", {}),
            "review_sample_coverage_250": summary.get("review_sample_coverage_250", {}),
            "review_sample_coverage_500": summary.get("review_sample_coverage_500", {}),
            "review_sample_coverage_1000": summary.get("review_sample_coverage_1000", {}),
        }

    def run_simulation_for_world_version(
        self,
        world_version_id: str,
        *,
        include_cross_pack: bool = True,
        max_chapters: int = 6,
        min_end_turn_override: int | None = None,
        interactive_scenarios: Optional[List[Dict[str, Any]]] = None,
        longform_setup_override: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Any] = None,
    ) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        prepared_interactive_scenarios, max_chapters = self._prepare_interactive_scenarios(
            version,
            interactive_scenarios,
            max_chapters=max_chapters,
        )
        runtime = self.repository.get_runtime_bundle(world_version_id)
        state = NarrativeState.from_dict(runtime.initial_state.to_dict())
        if min_end_turn_override is not None:
            state.min_end_turn = max(int(min_end_turn_override), int(state.min_end_turn))
        if max_chapters >= 1000:
            state.metadata["longform_diagnostics_mode"] = "longform_1000"
        worldpack_payload = dict(version.worldpack_json or {})
        longform_structure = _resolve_longform_structure(
            worldpack_payload=worldpack_payload,
            runtime_world_title=runtime.world_record.world.title,
            max_chapters=max_chapters,
        )
        series_plan = dict(longform_structure.get("series_plan") or {})
        volume_plans = list(longform_structure.get("volume_plans") or [])
        arc_plans = list(longform_structure.get("arc_plans") or [])
        chapter_budget_policy = dict(longform_structure.get("chapter_budget_policy") or {})
        plan_source = str(longform_structure.get("plan_source") or "worldpack")
        setup_override = dict(longform_setup_override or {})
        resolved_memory_compression_policy = dict(
            worldpack_payload.get("memory_compression_policy")
            or _default_memory_compression_policy(len(volume_plans))
        )
        series_storyline_contract = {
            **dict(worldpack_payload.get("series_storyline_contract") or {}),
            **dict(setup_override.get("series_storyline_contract") or {}),
        }
        character_memory_profiles = {
            **dict(worldpack_payload.get("character_memory_profiles") or {}),
            **dict(setup_override.get("character_memory_profiles") or {}),
        }
        steering_guardrails = {
            **_default_steering_guardrails(),
            **dict(worldpack_payload.get("steering_guardrails") or {}),
            **dict(setup_override.get("steering_guardrails") or {}),
        }
        configure_longform_runtime(
            state,
            series_plan=series_plan,
            volume_plans=volume_plans,
            arc_plans=arc_plans,
            chapter_budget_policy=chapter_budget_policy,
            memory_compression_policy=resolved_memory_compression_policy,
            world=runtime.world_record.world,
        )
        configure_interactive_longform_runtime(
            state,
            series_storyline_contract=series_storyline_contract,
            character_memory_profiles=character_memory_profiles,
            steering_guardrails=steering_guardrails,
        )
        completed_chapters = 0
        leak_detected = False
        latest_title = None
        reports = []
        chapter_trace = []
        stop_reason = "chapter_budget_reached"
        scenario_queue = sorted(
            [dict(item) for item in prepared_interactive_scenarios],
            key=lambda item: int(item.get("trigger_chapter", 0) or 0),
        )
        has_interactive_scenarios = bool(prepared_interactive_scenarios)
        steering_checkpoints: List[Dict[str, Any]] = []
        replan_history: List[Dict[str, Any]] = []

        for _ in range(max_chapters):
            next_chapter_index = int(state.chapter_index or 0) + 1
            if progress_callback is not None and (
                next_chapter_index == 1 or next_chapter_index % 25 == 0 or next_chapter_index == max_chapters
            ):
                try:
                    progress_callback(
                        "chapter_start",
                        chapter_index=next_chapter_index,
                        max_chapters=max_chapters,
                    )
                except Exception:
                    pass
            while scenario_queue and int(scenario_queue[0].get("trigger_chapter", 0) or 0) == next_chapter_index:
                scenario = scenario_queue.pop(0)
                directive = dict(scenario.get("steering_directive") or {})
                directive.setdefault("steering_type", scenario.get("scenario_kind"))
                directive.setdefault("summary", scenario.get("label") or scenario.get("scenario_kind") or "interactive_steer")
                checkpoint = apply_steering_directive(
                    state,
                    directive,
                    world=runtime.world_record.world,
                )
                if checkpoint.get("applied"):
                    steering_checkpoints.append(
                        {
                            "scenario_id": str(scenario.get("scenario_id") or f"scenario_{len(steering_checkpoints) + 1}"),
                            "scenario_kind": str(scenario.get("scenario_kind") or directive.get("steering_type") or "mild_steer"),
                            "chapter_index": next_chapter_index,
                            "summary": str(directive.get("summary") or ""),
                            "impacted_character_ids": list(checkpoint.get("entry", {}).get("impacted_character_ids", [])),
                        }
                    )
                    replan_history.append(dict(state.replan_checkpoint or {}))
            candidate_provider = (
                self.provider_routing.build_candidate_provider(
                    runtime.event_atoms,
                    surface="authoring_simulation",
                    account_id=str((version.worldpack_json or {}).get("manifest", {}).get("author_id") or "") or None,
                    session_id="simulation:%s" % version.world_id,
                    world_id=runtime.worldpack.world_id,
                    world_version_id=world_version_id,
                )
                if self.provider_routing
                else StaticCandidateProvider(runtime.event_atoms)
            )
            active_renderer = (
                self.provider_routing.build_renderer(
                    surface="authoring_simulation",
                    account_id=str((version.worldpack_json or {}).get("manifest", {}).get("author_id") or "") or None,
                    session_id="simulation:%s" % version.world_id,
                    world_id=runtime.worldpack.world_id,
                    world_version_id=world_version_id,
                )
                if self.provider_routing
                else TemplateRenderer()
            )
            diagnostics_light_debug = max_chapters >= 1000
            started = perf_counter()
            result = plan_next_turn(
                state,
                world=runtime.world_record.world,
                candidate_provider=candidate_provider,
                renderer=active_renderer,
                debug=not diagnostics_light_debug,
            )
            runtime_latency_ms = round((perf_counter() - started) * 1000.0, 3)
            if result["status"] != "ok":
                stop_reason = str(result.get("status", "stopped"))
                if progress_callback is not None:
                    try:
                        progress_callback(
                            "chapter_blocked",
                            chapter_index=next_chapter_index,
                            max_chapters=max_chapters,
                            stop_reason=stop_reason,
                        )
                    except Exception:
                        pass
                break
            completed_chapters += 1
            latest_title = result["reader_view"]["chapter_title"]
            leak_detected = leak_detected or ("event_id" in result["reader_view"]["body"] or "seed_id" in result["reader_view"]["body"])
            state = NarrativeState.from_dict(result["updated_state"])
            lint_started = perf_counter()
            lint_report = lint_chapter_draft(result["reader_view"]["body"])
            lint_latency_ms = round((perf_counter() - lint_started) * 1000.0, 3)
            chosen_candidate_summary = dict(result.get("chosen_candidate_summary") or {})
            evaluation_started = perf_counter()
            report = evaluate_chapter(
                chapter_id="simulation_%s_%s" % (world_version_id, completed_chapters),
                world_version_id=world_version_id,
                session_id="simulation:%s" % version.world_id,
                body=result["reader_view"]["body"],
                paragraphs=result["reader_view"]["body"].split("\n\n"),
                dialogue_count=int(lint_report["dialogue_count"]),
                action_count=int(lint_report["action_count"]),
                detail_count=int(lint_report["detail_count"]),
                character_fidelity_score=float(
                    dict(chosen_candidate_summary.get("components") or {}).get(
                        "character_fidelity",
                        max(
                            [item["components"].get("character_fidelity", 0.0) for item in result.get("scored_candidates", [])],
                            default=0.0,
                        ),
                    )
                    or 0.0
                ),
                state_after=state,
                ending_ready=bool(result["chapter_plan"]["ending_ready"]) if result.get("chapter_plan") else False,
                choices=result["reader_view"]["choices"],
                paywall_required=False,
                coverage_context={
                    "selected_event_ids": list((result.get("chapter_plan") or {}).get("selected_event_ids", [])),
                    "scene_beats": list(result.get("scene_beats") or []),
                    "chapter_task": dict((result.get("chapter_plan") or {}).get("chapter_task") or {}),
                },
            )
            evaluation_latency_ms = round((perf_counter() - evaluation_started) * 1000.0, 3)
            record_replan_debt(
                state,
                chapter_index=completed_chapters,
                issue_codes=[issue.issue_code for issue in report.issues],
            )
            reports.append(report)
            rendered_debug = dict((result.get("rendered_scene") or {}).get("debug") or {})
            draft_metadata = dict(rendered_debug.get("draft_metadata") or {})
            render_timing_ms = dict(rendered_debug.get("timing_ms") or {})
            quality_pass_timing_ms = dict(draft_metadata.get("quality_pass_timing_ms") or {})
            evaluation_payload = report.to_dict()
            chapter_trace.append(
                {
                    "chapter_id": "simulation_%s_%s" % (world_version_id, completed_chapters),
                    "chapter_title": result["reader_view"].get("chapter_title"),
                    "scene_function": (result.get("chosen_event") or {}).get("scene_function", ""),
                    "chosen_event_title": (result.get("chosen_event") or {}).get("title", ""),
                    "body_excerpt": (result.get("reader_view") or {}).get("body", "")[:280],
                    "beat_count": (result.get("chapter_plan") or {}).get("beat_count", 0),
                    "story_phase": (result.get("updated_state_summary") or {}).get("story_phase"),
                    "choices_preview": list((result.get("reader_view") or {}).get("choices", []))[:3],
                    "quality_pass_applied": bool(draft_metadata.get("quality_pass_applied", False)),
                    "quality_pass_actions": list(draft_metadata.get("quality_pass_actions", [])),
                    "quality_pass_timing_ms": quality_pass_timing_ms,
                    "critic_signal_count": len(result.get("critic_trace") or []),
                    "series_id": (result.get("updated_state") or {}).get("current_series_id"),
                    "volume_id": (result.get("updated_state") or {}).get("current_volume_id"),
                    "arc_id": (result.get("updated_state") or {}).get("current_arc_id"),
                    "chapter_task": dict((result.get("chapter_plan") or {}).get("chapter_task") or {}),
                    "chapter_task_execution_summary": dict((result.get("chapter_plan") or {}).get("chapter_task_execution_summary") or {}),
                    "open_promise_ids": [promise.promise_id for promise in state.open_promises],
                    "open_promise_count": len(state.open_promises),
                    "closed_promise_ids": list((state.metadata or {}).get("closed_promise_ids", [])),
                    "evaluation": {
                        "decision": evaluation_payload.get("decision", {}).get("decision"),
                        "overall_score": float((evaluation_payload.get("scores") or {}).get("overall_score", 0.0)),
                        "issue_codes": [issue.get("issue_code") for issue in evaluation_payload.get("issues", []) if issue.get("issue_code")],
                    },
                    "candidate_backend_routing": dict((result.get("candidate_batch") or {}).get("debug", {}).get("backend_routing") or {}),
                    "renderer_backend_routing": dict((result.get("rendered_scene") or {}).get("debug", {}).get("backend_routing") or {}),
                    "renderer_attempt_count": int(rendered_debug.get("renderer_attempt_count") or 0),
                    "renderer_fallback_reason": rendered_debug.get("renderer_fallback_reason"),
                    "llm_payload_gate": dict(rendered_debug.get("llm_payload_gate") or {}),
                    "llm_length_gate": dict(rendered_debug.get("llm_length_gate") or {}),
                    "runtime_latency_ms": runtime_latency_ms,
                    "lint_latency_ms": lint_latency_ms,
                    "evaluation_latency_ms": evaluation_latency_ms,
                    "render_timing_ms": render_timing_ms,
                    "planner_trace_summary": dict(result.get("planner_trace_summary") or {}),
                    "chosen_candidate_summary": chosen_candidate_summary,
                }
            )
            if progress_callback is not None and (
                completed_chapters == 1 or completed_chapters % 25 == 0 or completed_chapters == max_chapters
            ):
                try:
                    progress_callback(
                        "chapter_complete",
                        chapter_index=completed_chapters,
                        max_chapters=max_chapters,
                        runtime_latency_ms=runtime_latency_ms,
                        lint_latency_ms=lint_latency_ms,
                        evaluation_latency_ms=evaluation_latency_ms,
                        quality_pass_ms=round(float(quality_pass_timing_ms.get("total_ms", 0.0) or 0.0), 3),
                        issue_codes=[issue.get("issue_code") for issue in evaluation_payload.get("issues", []) if issue.get("issue_code")],
                    )
                except Exception:
                    pass
            if self.observability is not None:
                manifest = dict((version.worldpack_json or {}).get("manifest", {}))
                author_account_id = str(manifest.get("author_id") or "") or None
                self.observability.record_runtime_receipt(
                    surface="authoring_simulation",
                    action="run_simulation",
                    response_status="ok",
                    world_id=runtime.worldpack.world_id,
                    world_version_id=world_version_id,
                    session_id="simulation:%s" % version.world_id,
                    account_id=author_account_id,
                    reader_id=author_account_id,
                    candidate_batch=result.get("candidate_batch"),
                    rendered_scene=result.get("rendered_scene"),
                    reader_view=result.get("reader_view"),
                    estimated_cost=round(max(1, len(result["reader_view"]["body"])) / 1200.0, 3),
                    runtime_latency_ms=runtime_latency_ms,
                )

        aggregate = aggregate_reports(reports)
        simulation_report = {
            "ok": completed_chapters >= 3 and not leak_detected and aggregate["block_rate"] == 0.0,
            "world_version_id": world_version_id,
            "world_id": version.world_id,
            "completed_chapters": completed_chapters,
            "chapter_budget": max_chapters,
            "completion_ratio": round(completed_chapters / float(max(1, max_chapters)), 3),
            "min_end_turn_target": state.min_end_turn,
            "stop_reason": stop_reason if completed_chapters < max_chapters else "chapter_budget_reached",
            "terminated_by_budget": completed_chapters >= max_chapters,
            "latest_title": latest_title,
            "early_ending": completed_chapters < 3,
            "reader_leak_detected": leak_detected,
            "risk_flags": [] if not leak_detected else ["reader_leak"],
            "cost_estimate": round(0.18 * completed_chapters, 2),
            "evaluation_summary": aggregate,
            "latest_decision": reports[-1].decision.decision if reports else "rewrite",
            "chapter_evaluations": [report_item.to_dict() for report_item in reports],
            "chapter_trace": chapter_trace,
            "final_state_snapshot": state.to_dict(),
            "longform_plan_snapshot": {
                "series_plan": dict(series_plan),
                "volume_plans": [dict(item) for item in volume_plans],
                "arc_plans": [dict(item) for item in arc_plans],
                "chapter_budget_policy": dict(chapter_budget_policy),
                "memory_compression_policy": resolved_memory_compression_policy,
                "plan_source": plan_source,
            },
            "steering_checkpoints": steering_checkpoints,
            "replan_history": replan_history,
            "memory_patch_summary": _build_memory_patch_summary(state),
        }

        if include_cross_pack:
            benchmark_mode = (
                "longform_1000_interactive"
                if max_chapters >= 1000 and has_interactive_scenarios
                else (
                    "longform_1000_diagnostics"
                    if max_chapters >= 1000
                    else (
                        "longform_500_interactive"
                        if max_chapters >= 500 and has_interactive_scenarios
                        else (
                        "longform_500"
                        if max_chapters >= 500
                        else (
                            "longform_250_interactive"
                            if max_chapters >= 250 and has_interactive_scenarios
                            else (
                                "longform_250"
                                if max_chapters >= 250
                                else ("longform_100_interactive" if has_interactive_scenarios else ("longform_100" if max_chapters >= 100 else None))
                            )
                        )
                        )
                    )
                )
            )
            cross_pack_summary = self._build_cross_pack_summary(
                version.world_id,
                world_version_id,
                benchmark_mode=benchmark_mode,
                max_chapters=max_chapters,
            )
            simulation_report["cross_pack_summary"] = cross_pack_summary
            simulation_report["top_failing_packs"] = cross_pack_summary.get("top_failing_packs", [])
            simulation_report["metric_deltas"] = (
                cross_pack_summary.get("delta_summary", {})
                .get("world_deltas", {})
                .get(version.world_id, {})
            )

        evaluator_examples = self.training_signal.evaluator_examples_from_reports(
            simulation_report["chapter_evaluations"],
            world_id=version.world_id,
        )
        simulation_report["learned_evaluation_summary"] = self.learned_inference.summarize_examples(evaluator_examples)
        simulation_report["learned_shadow_summary"] = self.learned_shadow.summarize(
            simulation_report["learned_evaluation_summary"]
        )
        q09_incidence_rate = round(
            sum(
                1
                for payload in simulation_report["chapter_evaluations"]
                if any(issue.get("issue_code") == "Q09" for issue in payload.get("issues", []))
            )
            / float(max(1, completed_chapters or 1)),
            3,
        )
        character_drift_rate = round(
            sum(
                1
                for payload in simulation_report["chapter_evaluations"]
                if any(issue.get("issue_code") == "Q06" for issue in payload.get("issues", []))
            )
            / float(max(1, completed_chapters or 1)),
            3,
        )
        volume_climax_spacing_error = _volume_climax_spacing_error(chapter_trace, volume_plans)
        premature_ending_trigger_rate = q09_incidence_rate
        pass_windows = _longform_pass_windows(simulation_report["chapter_evaluations"])
        simulation_report["longform_summary"] = {
            "series_id": series_plan.get("series_id"),
            "plan_source": plan_source,
            "volume_count": len(volume_plans),
            "arc_count": len(arc_plans),
            "target_chapters": int(series_plan.get("total_chapter_target", max_chapters) or max_chapters),
            "chapter_budget_target_words": state.word_budget,
            "character_drift_rate": character_drift_rate,
            "promise_unresolved_rate": round(len(state.open_promises) / float(max(1, completed_chapters or 1)), 3),
            "arc_task_repeat_rate": _chapter_task_repeat_rate(chapter_trace),
            "q09_incidence_rate": q09_incidence_rate,
            "mid_arc_pass_rate": float(pass_windows["mid_arc_pass_rate"]),
            "late_arc_pass_rate": float(pass_windows["late_arc_pass_rate"]),
            "premature_ending_trigger_rate": premature_ending_trigger_rate,
            "volume_climax_spacing_error": volume_climax_spacing_error,
        }
        gate_target_chapters = (
            int(simulation_report["longform_summary"]["target_chapters"])
            if max_chapters >= 100
            else int(max_chapters)
        )
        simulation_report["longform_gate"] = evaluate_longform_gate(
            target_chapters=gate_target_chapters,
            completed_chapters=completed_chapters,
            pass_rate=float(aggregate.get("pass_rate", 0.0)),
            block_rate=float(aggregate.get("block_rate", 0.0)),
            stop_reason=str(simulation_report.get("stop_reason", "")),
            completion_ratio=float(simulation_report.get("completion_ratio", 0.0)),
            mid_arc_pass_rate=float(pass_windows["mid_arc_pass_rate"]),
            q09_incidence_rate=q09_incidence_rate,
            character_drift_rate=character_drift_rate,
            promise_unresolved_rate=float(simulation_report["longform_summary"]["promise_unresolved_rate"]),
            arc_task_repeat_rate=float(simulation_report["longform_summary"]["arc_task_repeat_rate"]),
            premature_ending_trigger_rate=premature_ending_trigger_rate,
            volume_climax_spacing_error=volume_climax_spacing_error,
        )
        if max_chapters >= 250:
            completed_volume_ids = [
                snapshot.get("volume_id")
                for snapshot in list(state.volume_memory_snapshots or [])
                if snapshot.get("volume_id")
            ]
            completed_volume_count = len({str(item) for item in completed_volume_ids})
            target_volume_count = max(1, len(volume_plans))
            replan_metrics = dict(state.replan_stability_metrics or {})
            replan_events = [dict(item) for item in list(state.replan_history or [])]
            effective_replan_events = (
                [
                    item
                    for item in replan_events
                    if not str(item.get("reason") or "").startswith("steering::")
                ]
                if has_interactive_scenarios
                else list(replan_events)
            )
            strong_replans = sum(1 for item in effective_replan_events if str(item.get("mode") or "") == "strong")
            total_replans = len(effective_replan_events)
            longform_250_summary = {
                "target_chapters": 250,
                "target_volume_count": target_volume_count,
                "completed_volume_count": completed_volume_count,
                "volume_boundary_survival": round(completed_volume_count / float(max(1, target_volume_count)), 3),
                "memory_recall_coverage": round(
                    len([item for item in list(state.volume_memory_snapshots or []) if (item.get("active_unresolved_promise_ids") or item.get("character_memory_refs"))])
                    / float(max(1, len(list(state.volume_memory_snapshots or [])) or 1)),
                    3,
                ) if list(state.volume_memory_snapshots or []) else 0.0,
                "replan_stability_score": round(
                    max(0.0, 1.0 - (strong_replans / float(max(1, total_replans or 1)))),
                    3,
                ) if total_replans else 1.0,
                "replan_stability_mode": "steering_adjusted" if has_interactive_scenarios else "static",
                "steering_replans_excluded": (
                    len(replan_events) - len(effective_replan_events)
                    if has_interactive_scenarios
                    else 0
                ),
                "volume_snapshot_integrity": round(
                    len(list(state.volume_memory_snapshots or [])) / float(max(1, completed_volume_count or 1)),
                    3,
                ) if completed_volume_count else 0.0,
                "mid_volume_pass_rate": float(pass_windows["mid_arc_pass_rate"]),
                "late_volume_pass_rate": float(pass_windows["late_arc_pass_rate"]),
            }
            simulation_report["longform_250_summary"] = longform_250_summary
            failed_checks = []
            if float(longform_250_summary["volume_boundary_survival"]) < 1.0:
                failed_checks.append("volume_boundary_survival")
            if float(longform_250_summary["memory_recall_coverage"]) < 0.5:
                failed_checks.append("memory_recall_coverage")
            if float(longform_250_summary["replan_stability_score"]) < 0.67:
                failed_checks.append("replan_stability_score")
            if float(longform_250_summary["volume_snapshot_integrity"]) < 1.0:
                failed_checks.append("volume_snapshot_integrity")
            simulation_report["longform_250_evidence"] = {
                "status": "ready" if not failed_checks else "watch",
                "failed_checks": failed_checks,
                "summary": dict(longform_250_summary),
            }
        if max_chapters >= 500:
            series_snapshots = [dict(item) for item in list(state.series_memory_snapshots or [])]
            target_volume_count = max(1, len(volume_plans))
            policy = dict(resolved_memory_compression_policy or {})
            every_n_volumes = max(1, int(policy.get("series_snapshot_every_n_volumes", 2) or 2))
            expected_series_snapshots = max(1, (target_volume_count + every_n_volumes - 1) // every_n_volumes)
            retained_series_snapshot_target = min(
                expected_series_snapshots,
                max(1, int(policy.get("series_snapshot_limit", expected_series_snapshots) or expected_series_snapshots)),
            )
            series_ending_checkpoint = dict(state.series_ending_checkpoint or {})
            longform_500_summary = {
                "target_chapters": 500,
                "target_volume_count": target_volume_count,
                "completed_volume_count": len({str(item.get('volume_id') or '') for item in list(state.volume_memory_snapshots or []) if str(item.get('volume_id') or '')}),
                "series_boundary_survival": round(
                    len({str(item.get('volume_id') or '') for item in list(state.volume_memory_snapshots or []) if str(item.get('volume_id') or '')})
                    / float(max(1, target_volume_count)),
                    3,
                ),
                "series_snapshot_count": len(series_snapshots),
                "expected_series_snapshots": expected_series_snapshots,
                "retained_series_snapshot_target": retained_series_snapshot_target,
                "series_memory_snapshot_integrity": round(
                    min(1.0, len(series_snapshots) / float(max(1, retained_series_snapshot_target))),
                    3,
                ),
                "memory_recall_coverage": round(
                    len([item for item in series_snapshots if (item.get("active_unresolved_promise_ids") or item.get("character_memory_refs"))])
                    / float(max(1, len(series_snapshots) or 1)),
                    3,
                ) if series_snapshots else 0.0,
                "replan_stability_score": round(float((simulation_report.get("longform_250_summary") or {}).get("replan_stability_score", 0.0) or 0.0), 3),
                "late_series_pass_rate": float(pass_windows["late_arc_pass_rate"]),
                "series_ending_control_score": 1.0 if bool(series_ending_checkpoint.get("terminal_ready")) else 0.0,
                "series_ending_status": str(series_ending_checkpoint.get("status") or "missing"),
            }
            simulation_report["longform_500_summary"] = longform_500_summary
            failed_checks = []
            if float(longform_500_summary["series_boundary_survival"]) < 1.0:
                failed_checks.append("series_boundary_survival")
            if float(longform_500_summary["series_memory_snapshot_integrity"]) < 1.0:
                failed_checks.append("series_memory_snapshot_integrity")
            if float(longform_500_summary["memory_recall_coverage"]) < 0.5:
                failed_checks.append("series_memory_recall_coverage")
            if float(longform_500_summary["replan_stability_score"]) < 0.67:
                failed_checks.append("replan_stability_score")
            if float(longform_500_summary["late_series_pass_rate"]) < 0.8:
                failed_checks.append("late_series_pass_rate")
            if float(longform_500_summary["series_ending_control_score"]) < 1.0:
                failed_checks.append("series_ending_control_score")
            simulation_report["longform_500_evidence"] = {
                "status": "ready" if not failed_checks else "watch",
                "failed_checks": failed_checks,
                "summary": dict(longform_500_summary),
            }
        if max_chapters >= 1000:
            policy = dict(resolved_memory_compression_policy or {})
            archive_limit = max(1, int(policy.get("archive_retention_limit", 160) or 160))
            timeline_limit = max(1, int(policy.get("timeline_retention_limit", 240) or 240))
            continuation_fact_limit = max(1, int(policy.get("continuation_fact_retention_limit", 120) or 120))
            continuation_visit_limit = max(1, int(policy.get("continuation_visit_retention_limit", 120) or 120))
            archive_count = len(list(state.archive_memory or []))
            timeline_count = len(list(state.timeline or []))
            continuation_fact_count = len([item for item in list(state.world_facts or []) if str(item).startswith("continuation::")])
            continuation_visit_count = len([item for item in list(state.visited_event_ids or []) if "__continuation__" in str(item)])
            late_stage_latencies = [
                float(item.get("runtime_latency_ms", 0.0) or 0.0)
                for item in chapter_trace
                if int(
                    item.get("simulation_chapter_index")
                    or dict(item.get("chapter_task_execution_summary") or {}).get("series_chapter_index")
                    or 0
                ) >= 750
                and item.get("runtime_latency_ms") is not None
            ]
            every_n_volumes = max(1, int(policy.get("series_snapshot_every_n_volumes", 2) or 2))
            target_volume_count = max(1, len(volume_plans))
            expected_series_snapshots = max(1, (target_volume_count + every_n_volumes - 1) // every_n_volumes)
            retained_series_snapshot_target = min(
                expected_series_snapshots,
                max(1, int(policy.get("series_snapshot_limit", expected_series_snapshots) or expected_series_snapshots)),
            )
            runtime_p95_ms = _percentile(late_stage_latencies, 0.95) if late_stage_latencies else 0.0
            runtime_max_ms = round(max(late_stage_latencies), 3) if late_stage_latencies else 0.0
            runtime_budget_score = 1.0 if runtime_p95_ms <= 2500 else round(max(0.0, 1.0 - ((runtime_p95_ms - 2500.0) / 7500.0)), 3)
            archive_retention_integrity = round(min(1.0, archive_limit / float(max(1, archive_count))), 3)
            timeline_retention_integrity = round(min(1.0, timeline_limit / float(max(1, timeline_count))), 3)
            continuation_state_retention_integrity = round(
                min(
                    1.0,
                    continuation_fact_limit / float(max(1, continuation_fact_count)),
                    continuation_visit_limit / float(max(1, continuation_visit_count)),
                ),
                3,
            )
            longform_1000_summary = {
                "target_chapters": 1000,
                "series_boundary_survival": round(float((simulation_report.get("longform_500_summary") or {}).get("series_boundary_survival", 0.0) or 0.0), 3),
                "series_memory_snapshot_integrity": round(float((simulation_report.get("longform_500_summary") or {}).get("series_memory_snapshot_integrity", 0.0) or 0.0), 3),
                "memory_recall_coverage": round(float((simulation_report.get("longform_500_summary") or {}).get("memory_recall_coverage", 0.0) or 0.0), 3),
                "replan_stability_score": round(float((simulation_report.get("longform_500_summary") or {}).get("replan_stability_score", 0.0) or 0.0), 3),
                "late_series_pass_rate": round(float((simulation_report.get("longform_500_summary") or {}).get("late_series_pass_rate", 0.0) or 0.0), 3),
                "series_ending_control_score": round(float((simulation_report.get("longform_500_summary") or {}).get("series_ending_control_score", 0.0) or 0.0), 3),
                "archive_retention_integrity": archive_retention_integrity,
                "timeline_retention_integrity": timeline_retention_integrity,
                "continuation_state_retention_integrity": continuation_state_retention_integrity,
                "late_stage_runtime_p95_ms": runtime_p95_ms,
                "late_stage_runtime_max_ms": runtime_max_ms,
                "late_stage_runtime_budget_score": runtime_budget_score,
                "series_snapshot_count": len(list(state.series_memory_snapshots or [])),
                "expected_series_snapshots": expected_series_snapshots,
                "retained_series_snapshot_target": retained_series_snapshot_target,
                "series_ending_status": str(dict(state.series_ending_checkpoint or {}).get("status") or "missing"),
            }
            simulation_report["longform_1000_summary"] = longform_1000_summary
            failed_checks = []
            if float(longform_1000_summary["series_boundary_survival"]) < 1.0:
                failed_checks.append("series_boundary_survival")
            if float(longform_1000_summary["series_memory_snapshot_integrity"]) < 1.0:
                failed_checks.append("series_memory_snapshot_integrity")
            if float(longform_1000_summary["archive_retention_integrity"]) < 1.0:
                failed_checks.append("archive_retention_integrity")
            if float(longform_1000_summary["timeline_retention_integrity"]) < 1.0:
                failed_checks.append("timeline_retention_integrity")
            if float(longform_1000_summary["continuation_state_retention_integrity"]) < 1.0:
                failed_checks.append("continuation_state_retention_integrity")
            if float(longform_1000_summary["late_stage_runtime_budget_score"]) < 0.67:
                failed_checks.append("late_stage_runtime_budget_score")
            if float(longform_1000_summary["series_ending_control_score"]) < 1.0:
                failed_checks.append("series_ending_control_score")
            simulation_report["longform_1000_evidence"] = {
                "status": "promising" if not failed_checks else "watch",
                "failed_checks": failed_checks,
                "summary": dict(longform_1000_summary),
            }
        simulation_report["simulation_drilldown"] = self._build_simulation_drilldown(simulation_report)
        simulation_report["longform_drilldown"] = self._build_longform_drilldown(simulation_report)
        simulation_report["creative_cockpit"] = self._build_creative_cockpit(version.worldpack_json, simulation_report)
        simulation_report["content_quality_contract_window_metrics"] = self._content_quality_window_metrics(
            version.worldpack_json,
            simulation_report,
        )
        simulation_report["content_quality_repair_workbench"] = self._build_content_quality_repair_workbench(
            version.worldpack_json,
            simulation_report,
        )
        simulation_report["latest_repair_loop_outcome"] = {}
        simulation_report["repair_loop_history"] = []
        simulation_report["latest_strategy_bundle_execution"] = {}
        simulation_report["strategy_bundle_execution_history"] = []
        if steering_checkpoints:
            scenario_results = []
            for checkpoint in steering_checkpoints:
                chapter_index = int(checkpoint.get("chapter_index", 0) or 0)
                post_short = [
                    item for item in chapter_trace
                    if chapter_index < int(dict(item.get("chapter_task_execution_summary") or {}).get("series_chapter_index", 0) or 0) <= chapter_index + 3
                ]
                post_long = [
                    item for item in chapter_trace
                    if chapter_index < int(dict(item.get("chapter_task_execution_summary") or {}).get("series_chapter_index", 0) or 0) <= chapter_index + 10
                ]
                short_reports = [item for item in simulation_report["chapter_evaluations"] if chapter_index < int(str(item.get("chapter_id", "")).rsplit("_", 1)[-1] or 0) <= chapter_index + 3]
                long_reports = [item for item in simulation_report["chapter_evaluations"] if chapter_index < int(str(item.get("chapter_id", "")).rsplit("_", 1)[-1] or 0) <= chapter_index + 10]
                q06_rate = round(
                    sum(1 for payload in long_reports if any(issue.get("issue_code") == "Q06" for issue in payload.get("issues", [])))
                    / float(max(1, len(long_reports) or 1)),
                    3,
                )
                q07_q09_rate = round(
                    sum(
                        1
                        for payload in long_reports
                        if any(issue.get("issue_code") in {"Q07", "Q09"} for issue in payload.get("issues", []))
                    )
                    / float(max(1, len(long_reports) or 1)),
                    3,
                )
                short_window = _issue_window_summary(short_reports, target_chapters=max_chapters)
                long_window = _issue_window_summary(long_reports, target_chapters=max_chapters)
                recovery = len(post_short) >= 3
                scenario_results.append(
                    {
                        **checkpoint,
                        "post_steer_short_window_chapters": len(post_short),
                        "post_steer_long_window_chapters": len(post_long),
                        "recovered": recovery,
                        "memory_consistency_score": round(1.0 - q06_rate, 3),
                        "promise_reconciliation_score": round(1.0 - q07_q09_rate, 3),
                        "replan_stability_score": 1.0 if recovery else 0.0,
                        "short_window": short_window,
                        "long_window": long_window,
                    }
                )
            simulation_report["interactive_summary"] = {
                "scenario_results": scenario_results,
                "scenario_count": len(scenario_results),
                "steering_recovery_rate": round(sum(1.0 for item in scenario_results if item.get("recovered")) / float(max(1, len(scenario_results))), 3),
                "post_steer_route_survival": round(sum(float(item.get("post_steer_long_window_chapters", 0)) for item in scenario_results) / float(max(1, len(scenario_results) * 10)), 3),
                "memory_consistency_after_steer": round(sum(float(item.get("memory_consistency_score", 0.0)) for item in scenario_results) / float(max(1, len(scenario_results))), 3),
                "promise_reconciliation_after_steer": round(sum(float(item.get("promise_reconciliation_score", 0.0)) for item in scenario_results) / float(max(1, len(scenario_results))), 3),
                "replan_stability_score": round(sum(float(item.get("replan_stability_score", 0.0)) for item in scenario_results) / float(max(1, len(scenario_results))), 3),
            }
            simulation_report["post_steer_issue_window_summary"] = [
                {
                    "scenario_id": item.get("scenario_id"),
                    "scenario_kind": item.get("scenario_kind"),
                    "chapter_index": item.get("chapter_index"),
                    "summary": item.get("summary"),
                    "short_window": dict(item.get("short_window") or {}),
                    "long_window": dict(item.get("long_window") or {}),
                }
                for item in scenario_results
            ]

        metadata = dict((version.worldpack_json or {}).get("metadata", {}))
        revision_history = list(metadata.get("revision_history", []))
        latest_repair_loop_outcome = self._build_repair_loop_outcome(
            revision_history,
            current_issue_groups=list((simulation_report.get("creative_cockpit") or {}).get("chapter_heatmap", {}).get("issue_priority_groups", [])),
            current_chapter_heatmap=list((simulation_report.get("creative_cockpit") or {}).get("chapter_heatmap", {}).get("chapters", [])),
        )
        if revision_history:
            revision_history[-1]["simulation_delta"] = {
                "pass_rate_delta": simulation_report.get("metric_deltas", {}).get("pass_rate_delta"),
                "rewrite_rate_delta": simulation_report.get("metric_deltas", {}).get("rewrite_rate_delta"),
                "block_rate_delta": simulation_report.get("metric_deltas", {}).get("block_rate_delta"),
                "metric_deltas": dict(simulation_report.get("metric_deltas", {})),
            }
            revision_history[-1]["simulation_snapshot"] = self._simulation_snapshot(simulation_report)
            if latest_repair_loop_outcome.get("repair_loop_revision_id"):
                for revision in revision_history:
                    if revision.get("revision_id") == latest_repair_loop_outcome["repair_loop_revision_id"]:
                        revision["repair_loop_outcome"] = copy.deepcopy(latest_repair_loop_outcome)
                        break
            metadata["revision_history"] = revision_history[-10:]
            version.worldpack_json["metadata"] = metadata
        simulation_report["latest_repair_loop_outcome"] = latest_repair_loop_outcome
        simulation_report["repair_loop_history"] = self._repair_loop_history(list(metadata.get("revision_history", [])))
        simulation_report["latest_strategy_bundle_execution"] = self._latest_strategy_bundle_execution(
            list(metadata.get("revision_history", []))
        )
        simulation_report["strategy_bundle_execution_history"] = self._strategy_bundle_execution_history(
            list(metadata.get("revision_history", []))
        )
        simulation_report["content_quality_repair_workbench"] = self._build_content_quality_repair_workbench(
            version.worldpack_json,
            simulation_report,
        )

        version.simulation_report_json = simulation_report
        self.repository.save_world_version(version, publish=False)
        return simulation_report

    def run_simulation(self, world_id: str) -> dict[str, Any]:
        return self.run_simulation_for_world_version(self._select_candidate_world_version_id(world_id))

    def submit_for_review(self, world_version_id: str) -> dict[str, Any]:
        version = self.repository.get_world_version(world_version_id)
        if not version.validation_report_json:
            version.validation_report_json = validate_worldpack_payload(version.worldpack_json)
            self.repository.save_world_version(version, publish=False)
        if not version.simulation_report_json:
            self.run_simulation_for_world_version(world_version_id)
            version = self.repository.get_world_version(world_version_id)
        version.status = "submitted"
        self.repository.save_world_version(version, publish=False)
        from .review import ReviewService

        review = ReviewService(self.repository).submit_world_version(world_version_id)
        return {
            "world_version_id": world_version_id,
            "status": "submitted",
            "review": review,
        }


def _slugify_world_id(title: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in title.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "custom_world"


def _genre_preset(preset_id: str) -> Dict[str, Any]:
    presets: Dict[str, Dict[str, Any]] = {
        "jade_court": {
            "title": "新门第试炼",
            "genres": ["duty", "love", "reputation"],
            "premise": "家门和情意互相牵扯，越想守住体面，越容易把真心逼到墙角。",
            "life_theme": "责任与真心能否同时被承担",
            "lead_name": "谢临",
            "counterpart_name": "沈霁",
            "supporting_name": "老夫人",
            "locations": ["花厅", "书房", "回廊"],
            "canon_rules": ["任何靠体面压下去的话，都会在更难看的时候回来。", "关系推进必须伴随代价。"],
            "forbidden_moves": ["无代价圆满", "一句话立刻化解所有误解"],
            "style_pack": {"mode": "novel_lush", "pov": "limited_third", "dialogue_density": "medium_high"},
            "tonal_lexicon": ["门第", "体面", "牵连", "旧账"],
            "thematic_axis_labels": {"duty": "责任与牵引", "love": "情意与靠近", "reputation": "名声与体面"},
            "hook_templates": ["这层体面先撑住了，可真正会追上来的，是那句被压回去的心里话。"],
            "dialogue_realism_policy": {"policy_id": "jade_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 3, "max_turns": 4, "turn_pattern": ["speaker", "reaction", "reply", "echo"], "minimum_exchanges": 2},
        },
        "urban_mystery": {
            "title": "旧巷回潮",
            "genres": ["urban_mystery", "truth", "suspense"],
            "premise": "一条旧巷里，越想压住的真相，越会换一种方式回来收债。",
            "life_theme": "真话是否值得承担失去",
            "lead_name": "江屹",
            "counterpart_name": "周岚",
            "supporting_name": "",
            "locations": ["旧巷", "便利店门口", "天桥下"],
            "canon_rules": ["任何隐瞒都会留下因果种子。", "关系推进必须伴随代价或误解。"],
            "forbidden_moves": ["神力直接解决问题", "无根由的完美和解"],
            "style_pack": {"mode": "novel_lush", "pov": "limited_third", "dialogue_density": "medium_high"},
            "tonal_lexicon": ["旧账", "巷口", "回声", "试探"],
            "thematic_axis_labels": {"urban_mystery": "真相与羞耻", "truth": "真相与揭露", "suspense": "悬疑与压迫"},
            "hook_templates": ["夜色先退了一步，可真正让人睡不着的，是下一次见面时还要不要继续问下去。"],
            "dialogue_realism_policy": {"policy_id": "urban_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 3, "max_turns": 4, "turn_pattern": ["speaker", "reaction", "reply", "echo"], "minimum_exchanges": 2},
        },
        "xianxia": {
            "title": "旧誓照骨",
            "genres": ["xianxia", "destiny", "truth"],
            "premise": "修行不是增添力量，而是看见自己到底愿意舍弃什么。",
            "life_theme": "旧誓与私心能否被同时承担",
            "lead_name": "沈照",
            "counterpart_name": "叶青烛",
            "supporting_name": "",
            "locations": ["偏殿", "石阶", "山门"],
            "canon_rules": ["每次逆天改命都会失去某种人间牵引。", "誓言可以护人也可以反噬。"],
            "forbidden_moves": ["主角毫无代价地逆天成功", "所有人都被一句话点悟"],
            "style_pack": {"mode": "manhua_drama", "pov": "limited_third", "dialogue_density": "medium"},
            "tonal_lexicon": ["旧誓", "反噬", "灵息", "山门"],
            "thematic_axis_labels": {"xianxia": "誓愿与天命", "destiny": "命运的去向", "truth": "真相与揭露"},
            "hook_templates": ["这一句先落在这里，可真正会逼人回头的，是下一次相见时还要不要认这层旧誓。"],
            "dialogue_realism_policy": {"policy_id": "xianxia_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 3, "max_turns": 4, "turn_pattern": ["speaker", "reaction", "reply", "echo"], "minimum_exchanges": 2},
        },
        "synthetic": {
            "title": "最小实验世界",
            "genres": ["synthetic", "truth", "selfhood"],
            "premise": "用于快速验证 narrative kernel 是否真的能承载不同的人和冲突。",
            "life_theme": "如何在压力里说真话",
            "lead_name": "甲",
            "counterpart_name": "乙",
            "supporting_name": "",
            "locations": ["中庭", "长廊", "窗边"],
            "canon_rules": ["所有能力都应依赖 contract 与 pack assets，而不是角色名。", "推进必须伴随明确选择。"],
            "forbidden_moves": ["依赖特定礼法与家门语汇", "无差异模板化对白"],
            "style_pack": {"mode": "novel_light", "pov": "limited_third", "dialogue_density": "medium"},
            "tonal_lexicon": ["试探", "回声", "选择", "停顿"],
            "thematic_axis_labels": {"synthetic": "试探与选择", "truth": "真相与揭露", "selfhood": "自我与抉择"},
            "hook_templates": ["这层平静先撑住了，可真正要追上来的，是那句被按回去的真话。"],
            "dialogue_realism_policy": {"policy_id": "synthetic_brief_dialogue", "require_turn_taking": True, "require_counter_reaction": True, "min_turns": 3, "max_turns": 4, "turn_pattern": ["speaker", "reaction", "reply", "echo"], "minimum_exchanges": 2},
        },
    }
    return dict(presets.get(preset_id, presets["urban_mystery"]))


def _chapter_task_repeat_rate(chapter_trace: List[Dict[str, Any]]) -> float:
    duties = [str((item.get("chapter_task") or {}).get("duty_type") or "") for item in chapter_trace if (item.get("chapter_task") or {}).get("duty_type")]
    if len(duties) < 2:
        return 0.0
    repeats = 0
    for index in range(1, len(duties)):
        if duties[index] == duties[index - 1]:
            repeats += 1
    return round(repeats / float(max(1, len(duties) - 1)), 3)


def _volume_climax_spacing_error(chapter_trace: List[Dict[str, Any]], volume_plans: List[Dict[str, Any]]) -> float:
    if not chapter_trace or not volume_plans:
        return 0.0
    actual_counts: Dict[str, int] = {}
    for item in chapter_trace:
        volume_id = str(item.get("volume_id") or "")
        if not volume_id:
            continue
        actual_counts[volume_id] = actual_counts.get(volume_id, 0) + 1
    deltas = []
    for volume in volume_plans:
        volume_id = str(volume.get("volume_id") or "")
        target = max(1, int(volume.get("target_chapters", 1)))
        actual = int(actual_counts.get(volume_id, 0))
        deltas.append(abs(actual - target) / float(target))
    return round(sum(deltas) / float(max(1, len(deltas))), 3)


def _longform_pass_windows(chapter_evaluations: List[Dict[str, Any]]) -> Dict[str, float]:
    if not chapter_evaluations:
        return {
            "mid_arc_pass_rate": 0.0,
            "late_arc_pass_rate": 0.0,
        }
    decisions = [str((item.get("decision") or {}).get("decision", "rewrite")) for item in chapter_evaluations]
    first_end = max(1, len(chapter_evaluations) // 3)
    mid_end = max(first_end + 1, (2 * len(chapter_evaluations)) // 3)
    middle_decisions = decisions[first_end:mid_end] or decisions[-1:]
    late_decisions = decisions[mid_end:] or decisions[-1:]
    return {
        "mid_arc_pass_rate": round(
            sum(1 for decision in middle_decisions if decision == "pass") / float(max(1, len(middle_decisions))),
            3,
        ),
        "late_arc_pass_rate": round(
            sum(1 for decision in late_decisions if decision == "pass") / float(max(1, len(late_decisions))),
            3,
        ),
    }


def _issue_window_summary(
    chapter_evaluations: List[Dict[str, Any]],
    *,
    target_chapters: int,
    issue_codes: tuple[str, ...] = INTERACTIVE_WINDOW_ISSUE_CODES,
) -> Dict[str, Any]:
    issue_counts = {
        issue_code: sum(
            1
            for payload in chapter_evaluations
            if (
                any(issue.get("issue_code") == issue_code for issue in payload.get("issues", []))
                or issue_code in diagnostic_issue_codes_for_chapter_payload(payload, target_chapters=target_chapters)
            )
        )
        for issue_code in issue_codes
    }
    chapter_count = len(chapter_evaluations)
    return {
        "chapter_count": chapter_count,
        "issue_counts": issue_counts,
        "issue_rates": {
            issue_code: round(issue_counts[issue_code] / float(max(1, chapter_count)), 3)
            for issue_code in issue_codes
        },
    }


def _build_memory_patch_summary(state: NarrativeState) -> Dict[str, Any]:
    runtime = dict(state.character_memory_runtime or {})
    pending_count = 0
    adopted_count = 0
    characters_with_pending: List[str] = []
    characters_with_adopted: List[str] = []
    for character_id, payload in runtime.items():
        entry = dict(payload or {})
        pending = [dict(item) for item in entry.get("pending_memory_patches", [])]
        adopted = [dict(item) for item in entry.get("adopted_memory_patches", [])]
        pending_count += len(pending)
        adopted_count += len(adopted)
        if pending:
            characters_with_pending.append(character_id)
        if adopted:
            characters_with_adopted.append(character_id)
    return {
        "pending_count": pending_count,
        "adopted_count": adopted_count,
        "characters_with_pending": characters_with_pending,
        "characters_with_adopted": characters_with_adopted,
    }


def _resolve_longform_theme(worldpack_payload: Dict[str, Any], runtime_world_title: str) -> str:
    metadata = dict(worldpack_payload.get("metadata") or {})
    brief = dict(metadata.get("author_brief") or {})
    if str(brief.get("life_theme") or "").strip():
        return str(brief.get("life_theme")).strip()
    manifest = dict(worldpack_payload.get("manifest") or {})
    genres = [str(item).strip() for item in manifest.get("genres", []) if str(item).strip()]
    if genres:
        return " / ".join(genres[:2])
    return runtime_world_title


def _resolve_longform_structure(
    *,
    worldpack_payload: Dict[str, Any],
    runtime_world_title: str,
    max_chapters: int,
) -> Dict[str, Any]:
    series_plan = dict(worldpack_payload.get("series_plan") or {})
    volume_plans = list(worldpack_payload.get("volume_plans") or [])
    arc_plans = list(worldpack_payload.get("arc_plans") or [])
    chapter_budget_policy = dict(worldpack_payload.get("chapter_budget_policy") or {})
    if series_plan and volume_plans and arc_plans:
        target_total_chapters = max(24, int(series_plan.get("total_chapter_target", max_chapters) or max_chapters))
        normalized_arc_plans = []
        for arc in arc_plans:
            arc_payload = dict(arc or {})
            arc_payload["chapter_tasks"] = [
                ensure_chapter_task_quality_contract(
                    dict(task or {}),
                    target_chapters=target_total_chapters,
                )
                for task in list(arc_payload.get("chapter_tasks") or [])
            ]
            normalized_arc_plans.append(arc_payload)
        return {
            "series_plan": series_plan,
            "volume_plans": volume_plans,
            "arc_plans": normalized_arc_plans,
            "chapter_budget_policy": chapter_budget_policy,
            "plan_source": "worldpack",
        }
    target_total_chapters = max(24, int(max_chapters))
    if target_total_chapters >= 1000:
        target_total_volumes = max(16, min(20, target_total_chapters // 60 or 16))
    elif target_total_chapters >= 500:
        target_total_volumes = max(8, min(10, target_total_chapters // 50 or 8))
    else:
        target_total_volumes = max(3, min(5, target_total_chapters // 20 or 3))
    fallback = _build_longform_structure(
        world_id=str(worldpack_payload.get("world_id") or _slugify_world_id(runtime_world_title)),
        world_title=str(worldpack_payload.get("title") or runtime_world_title),
        life_theme=_resolve_longform_theme(worldpack_payload, runtime_world_title),
        target_total_chapters=target_total_chapters,
        target_total_volumes=target_total_volumes,
        target_word_count=target_total_chapters * 2000,
    )
    fallback["plan_source"] = "runtime_fallback"
    return fallback


def _bootstrap_longform_structure_payload(
    *,
    worldpack_payload: Dict[str, Any],
    runtime_world_title: str,
) -> Dict[str, Any]:
    metadata = dict(worldpack_payload.get("metadata") or {})
    brief = dict(metadata.get("author_brief") or {})
    target_total_chapters = max(24, int(brief.get("target_total_chapters") or 100))
    target_total_volumes = max(1, int(brief.get("target_total_volumes") or 5))
    target_word_count = max(20000, int(brief.get("target_word_count") or (target_total_chapters * 2000)))
    return {
        **_build_longform_structure(
            world_id=str(worldpack_payload.get("world_id") or _slugify_world_id(runtime_world_title)),
            world_title=str(worldpack_payload.get("title") or runtime_world_title),
            life_theme=_resolve_longform_theme(worldpack_payload, runtime_world_title),
            target_total_chapters=target_total_chapters,
            target_total_volumes=target_total_volumes,
            target_word_count=target_word_count,
        ),
        "plan_source": "workbench_bootstrap",
    }


def _build_storyline_contract_from_brief(
    *,
    world_title: str,
    core_premise: str,
    life_theme: str,
    volume_plans: List[Dict[str, Any]],
) -> Dict[str, Any]:
    milestones = []
    cumulative = 0
    for volume in volume_plans:
        cumulative += max(1, int(volume.get("target_chapters", 1) or 1))
        milestones.append(
            {
                "milestone_id": str(volume.get("volume_id") or f"milestone_{len(milestones) + 1}"),
                "label": str(volume.get("title") or volume.get("goal") or "长篇阶段目标"),
                "target_chapter": cumulative,
                "status": "planned",
            }
        )
    protected_themes = [item for item in [life_theme, core_premise] if item]
    return {
        "core_storyline": core_premise or world_title,
        "storyline_summary": core_premise or world_title,
        "protected_themes": protected_themes,
        "no_early_ending": True,
        "milestones": milestones,
        "conflict_policy": "reconcile_and_carry_forward",
    }


def _build_character_memory_profiles_from_characters(characters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}
    for character in characters:
        character_id = str(character.get("character_id") or "")
        if not character_id:
            continue
        destiny = dict(character.get("destiny_contract") or {})
        vow_profile = dict(character.get("vow_profile") or {})
        wound = dict(character.get("wound_profile") or {})
        profiles[character_id] = {
            "structured_memory": {
                "relationship_history": [],
                "promises": list(vow_profile.get("vows", [])),
                "secrets": [],
                "scars": [str(wound.get("core_wound") or "")] if wound.get("core_wound") else [],
                "faction": "",
                "taboos": list(destiny.get("forbidden_escape", [])) if isinstance(destiny.get("forbidden_escape"), list) else ([str(destiny.get("forbidden_escape"))] if destiny.get("forbidden_escape") else []),
                "goals": [str(destiny.get("life_theme") or "")] if destiny.get("life_theme") else [],
            },
            "free_text_memory": [],
        }
    return profiles


def _ensure_character_memory_profile_coverage(worldpack_payload: Dict[str, Any]) -> None:
    characters = [dict(item) for item in list(worldpack_payload.get("characters") or [])]
    existing_profiles = {
        str(key): copy.deepcopy(dict(value or {}))
        for key, value in dict(worldpack_payload.get("character_memory_profiles") or {}).items()
        if str(key).strip()
    }
    generated_profiles = _build_character_memory_profiles_from_characters(characters)
    for character_id, generated in generated_profiles.items():
        current = existing_profiles.get(character_id, {})
        current_structured = dict(current.get("structured_memory") or {})
        generated_structured = dict(generated.get("structured_memory") or {})
        for key, value in generated_structured.items():
            current_structured.setdefault(key, copy.deepcopy(value))
        current["structured_memory"] = current_structured
        current.setdefault("free_text_memory", list(generated.get("free_text_memory") or []))
        existing_profiles[character_id] = current
    worldpack_payload["character_memory_profiles"] = existing_profiles


def _ensure_character_asset_coverage(
    worldpack_payload: Dict[str, Any],
    *,
    preset_id: Optional[str] = None,
) -> None:
    _ensure_character_memory_profile_coverage(worldpack_payload)


def _default_steering_guardrails() -> Dict[str, Any]:
    return {
        "replan_future_only": True,
        "no_past_rewrite": True,
        "conflict_policy": "reconcile_and_carry_forward",
        "no_early_ending": True,
    }


def _default_memory_compression_policy(total_volumes: int) -> Dict[str, Any]:
    volume_target = max(1, int(total_volumes or 1))
    if volume_target >= 16:
        return {
            "rolling_recap_limit": 4,
            "active_arc_memory_limit": 8,
            "archive_retrieval_limit": 8,
            "archive_retention_limit": 64,
            "series_archive_prune_margin_chapters": 20,
            "volume_snapshot_every_n_chapters": 1,
            "promote_memory_on_reference_count": 2,
            "volume_context_window": 1,
            "series_snapshot_every_n_volumes": 3,
            "series_snapshot_limit": 6,
            "series_ending_activation_window_chapters": 80,
            "series_terminal_min_completion_ratio": 0.985,
            "timeline_retention_limit": 64,
            "continuation_fact_retention_limit": 48,
            "continuation_visit_retention_limit": 48,
            "target_volume_count": volume_target,
        }
    return {
        "rolling_recap_limit": 6 if volume_target >= 8 else 8,
        "active_arc_memory_limit": 10 if volume_target >= 8 else 12,
        "archive_retrieval_limit": 10 if volume_target >= 8 else 12,
        "archive_retention_limit": 80 if volume_target >= 8 else 160,
        "series_archive_prune_margin_chapters": 30 if volume_target >= 8 else 40,
        "volume_snapshot_every_n_chapters": 1,
        "promote_memory_on_reference_count": 2,
        "volume_context_window": 1 if volume_target >= 8 else 2,
        "series_snapshot_every_n_volumes": 2,
        "series_snapshot_limit": 5 if volume_target >= 8 else 3,
        "series_ending_activation_window_chapters": 40 if volume_target >= 8 else 30,
        "series_terminal_min_completion_ratio": 0.97 if volume_target >= 8 else 0.96,
        "timeline_retention_limit": 80 if volume_target >= 8 else 240,
        "continuation_fact_retention_limit": 60 if volume_target >= 8 else 120,
        "continuation_visit_retention_limit": 60 if volume_target >= 8 else 120,
        "target_volume_count": volume_target,
    }


def _preset_name_components(preset_id: str) -> Dict[str, List[str]]:
    return dict(LONGFORM_EXTRA_NAME_COMPONENTS.get(preset_id) or LONGFORM_EXTRA_NAME_COMPONENTS["synthetic"])


def _generate_longform_name(preset_id: str, index: int) -> str:
    components = _preset_name_components(preset_id)
    surnames = list(components.get("surnames") or ["甲"])
    givens = list(components.get("givens") or ["一"])
    surname = surnames[index % len(surnames)]
    given = givens[(index * 3) % len(givens)]
    return f"{surname}{given}"


def _next_longform_character_blueprints(
    *,
    preset_id: str,
    life_theme: str,
    existing_character_ids: List[str],
    current_count: int,
    target_count: int,
) -> List[Dict[str, Any]]:
    generated: List[Dict[str, Any]] = []
    used_ids = set(existing_character_ids)
    next_index = current_count
    while len(existing_character_ids) + len(generated) < target_count:
        next_index += 1
        role = LONGFORM_EXTRA_ROLE_CYCLE[(next_index - 1) % len(LONGFORM_EXTRA_ROLE_CYCLE)]
        character_id = f"supporting_{next_index}"
        if character_id in used_ids:
            continue
        used_ids.add(character_id)
        name = _generate_longform_name(preset_id, next_index - 1)
        wound = LONGFORM_EXTRA_WOUND_POOL[(next_index - 1) % len(LONGFORM_EXTRA_WOUND_POOL)]
        public_self = LONGFORM_EXTRA_PUBLIC_SELF_POOL[(next_index - 1) % len(LONGFORM_EXTRA_PUBLIC_SELF_POOL)]
        shadow_desire = LONGFORM_EXTRA_SHADOW_DESIRE_POOL[(next_index - 1) % len(LONGFORM_EXTRA_SHADOW_DESIRE_POOL)]
        vow = LONGFORM_EXTRA_VOW_POOL[(next_index - 1) % len(LONGFORM_EXTRA_VOW_POOL)]
        generated.append(
            {
                "character_id": character_id,
                "display_name": name,
                "role": role,
                "destiny_contract": {"life_theme": life_theme or "把更长的代价和关系张力撑到下一卷。"},
                "poison_vector": {"greed": 0.18, "anger": 0.22, "delusion": 0.24, "pride": 0.38, "doubt": 0.36},
                "vow_profile": {"vows": [vow], "sacrifice_capacity": 0.46, "truth_tolerance": 0.58},
                "wound_profile": {
                    "core_wound": wound,
                    "public_self": public_self,
                    "shadow_desire": shadow_desire,
                    "defense_style": "先稳局面再认代价",
                },
                "awakening_profile": {
                    "clarity": 0.44,
                    "reflection_capacity": 0.56,
                    "repentance_threshold": 0.68,
                    "transformation_paths": ["承认", "补偿", "站队"],
                },
                "speech_traits": ["稳着说", "先收口"],
                "action_traits": ["观望", "压场", "追索"],
            }
        )
    return generated


def _next_longform_locations(*, preset_id: str, existing_locations: List[str], target_count: int) -> List[str]:
    normalized_existing = [str(item).strip() for item in existing_locations if str(item).strip()]
    if len(normalized_existing) >= target_count:
        return normalized_existing
    pool = list(LONGFORM_EXTRA_LOCATION_POOLS.get(preset_id) or LONGFORM_EXTRA_LOCATION_POOLS["synthetic"])
    for location in pool:
        if len(normalized_existing) >= target_count:
            break
        if location not in normalized_existing:
            normalized_existing.append(location)
    next_index = 1
    while len(normalized_existing) < target_count:
        candidate = f"{preset_id}_extended_location_{next_index}"
        if candidate not in normalized_existing:
            normalized_existing.append(candidate)
        next_index += 1
    return normalized_existing


def _next_longform_scene_blueprints(
    *,
    preset_id: str,
    existing_scenes: List[Dict[str, Any]],
    character_ids: List[str],
    target_count: int,
    desired_scene_family_count: int = 0,
    desired_role_pair_count: int = 0,
) -> List[Dict[str, Any]]:
    next_scenes = [ensure_scene_quality_contract(dict(item)) for item in existing_scenes]
    existing_ids = {str(item.get("scene_id") or "") for item in next_scenes}
    existing_functions = {
        str(item.get("scene_function") or "").strip()
        for item in next_scenes
        if str(item.get("scene_function") or "").strip()
    }
    existing_role_pairs = {
        " / ".join(sorted([str(role).strip() for role in list((item or {}).get("required_roles") or []) if str(role).strip()]))
        for item in next_scenes
        if len([str(role).strip() for role in list((item or {}).get("required_roles") or []) if str(role).strip()]) >= 2
    }
    required_roles_pool = list(character_ids or ["lead", "counterpart"])
    if len(required_roles_pool) == 1:
        required_roles_pool.append(required_roles_pool[0])

    def needs_more() -> bool:
        return (
            len(next_scenes) < target_count
            or len(existing_functions) < desired_scene_family_count
            or len(existing_role_pairs) < desired_role_pair_count
        )

    def select_role_pair(seed_index: int) -> List[str]:
        if len(required_roles_pool) < 2:
            return required_roles_pool[:1] or ["lead"]
        best_pair = None
        for offset in range(len(required_roles_pool)):
            role_start = (seed_index + offset) % len(required_roles_pool)
            candidate = [
                required_roles_pool[role_start],
                required_roles_pool[(role_start + 1) % len(required_roles_pool)],
            ]
            pair_key = " / ".join(sorted(candidate))
            if pair_key not in existing_role_pairs:
                best_pair = candidate
                break
            if best_pair is None:
                best_pair = candidate
        return best_pair or required_roles_pool[:2]

    def append_scene(scene_id: str, scene_function: str, beats: List[str], seed_index: int) -> None:
        role_pair = select_role_pair(seed_index)
        next_scenes.append(
            ensure_scene_quality_contract(
                {
                    "scene_id": scene_id,
                    "scene_function": scene_function,
                    "phase_support": ["setup", "early_rising", "midpoint", "late_turn"],
                    "required_roles": role_pair,
                    "beats_template": list(beats),
                }
            )
        )
        existing_ids.add(scene_id)
        existing_functions.add(scene_function)
        existing_role_pairs.add(" / ".join(sorted(role_pair)))

    prioritized_templates = sorted(
        LONGFORM_SCENE_TEMPLATE_CATALOG,
        key=lambda item: (
            0 if str(item[1]) not in existing_functions else 1,
            item[1],
            item[0],
        ),
    )
    for index, (scene_suffix, scene_function, beats) in enumerate(prioritized_templates, start=1):
        if not needs_more():
            break
        scene_id = f"{preset_id}_{scene_suffix}"
        if scene_id in existing_ids:
            continue
        if len(existing_functions) < desired_scene_family_count and scene_function in existing_functions:
            continue
        append_scene(scene_id, scene_function, beats, index - 1)
    fallback_scene_functions = [
        "setup",
        "trust_test",
        "discovery",
        "reversal",
        "temptation",
        "false_peace",
        "confession_window",
        "truth_trial",
        "debt_exchange",
        "karma_ripening",
        "misrecognition",
        "humiliation",
        "vow_payment",
        "mercy_vs_control",
    ]
    extra_index = 1
    while needs_more():
        scene_id = f"{preset_id}_extended_scene_{extra_index}"
        if scene_id not in existing_ids:
            missing_fallback = [item for item in fallback_scene_functions if item not in existing_functions]
            scene_function = missing_fallback[0] if missing_fallback else fallback_scene_functions[(extra_index - 1) % len(fallback_scene_functions)]
            append_scene(scene_id, scene_function, ["重回旧地", "细节露口", "关系偏转", "留下更大的追问"], extra_index - 1)
        extra_index += 1
    return next_scenes


def _series_promise_templates(*, series_id: str, world_title: str, life_theme: str) -> List[Dict[str, Any]]:
    return [
        {
            "promise_id": f"{series_id}::promise_core_truth",
            "label": f"{world_title} 的核心真相迟早要被真正认下",
            "holders": ["lead", "counterpart"],
            "stakes": "high",
            "due_by_chapter": 0,
            "source_level": "series",
            "description": f"围绕“{life_theme or world_title}”的核心真相，必须在长线中被真正承担。",
        },
        {
            "promise_id": f"{series_id}::promise_choice_cost",
            "label": "每一次选择都要先有代价落到关系里",
            "holders": ["lead", "counterpart"],
            "stakes": "high",
            "due_by_chapter": 0,
            "source_level": "series",
            "description": "长线里的重大推进必须伴随关系、局势或代价的重新分配。",
        },
        {
            "promise_id": f"{series_id}::promise_world_consequence",
            "label": "世界层后果不会自动消失",
            "holders": ["lead"],
            "stakes": "medium",
            "due_by_chapter": 0,
            "source_level": "series",
            "description": "外部异变、秩序反噬或系统代价必须持续回到主线中追账。",
        },
    ]


def _volume_promise_templates(*, volume_id: str, volume_index: int, volume_target: int) -> List[Dict[str, Any]]:
    midpoint_due = max(2, min(volume_target, max(2, volume_target // 2)))
    return [
        {
            "promise_id": f"{volume_id}::promise_main",
            "label": f"第{volume_index}卷主冲突必须在卷内转向一次",
            "holders": ["lead", "counterpart"],
            "stakes": "high",
            "due_by_chapter": midpoint_due,
            "source_level": "volume",
            "description": f"第{volume_index}卷里，主冲突必须显式转向，不能只靠解释拖住。",
        },
        {
            "promise_id": f"{volume_id}::promise_relationship",
            "label": f"第{volume_index}卷关系债要被重新分配",
            "holders": ["lead", "counterpart"],
            "stakes": "medium",
            "due_by_chapter": volume_target,
            "source_level": "volume",
            "description": f"第{volume_index}卷结束前，人物关系至少要被重新定义一次。",
        },
    ]


def _arc_promise_template(*, arc_id: str, volume_index: int, arc_offset: int, arc_size: int) -> Dict[str, Any]:
    return {
        "promise_id": f"{arc_id}::promise_turn",
        "label": f"第{volume_index}卷第{arc_offset}弧必须留下下一弧要追的账",
        "holders": ["lead", "counterpart"],
        "stakes": "medium",
        "due_by_chapter": max(1, arc_size),
        "source_level": "arc",
        "description": f"这条弧线结束时不能收死，必须把后续追问继续推出去。",
    }


def _chapter_task_promise_targets(
    *,
    duty_type: str,
    series_promises: List[Dict[str, Any]],
    volume_promises: List[Dict[str, Any]],
    arc_promise: Dict[str, Any],
) -> List[str]:
    series_ids = [str(item.get("promise_id") or "") for item in series_promises if str(item.get("promise_id") or "")]
    volume_ids = [str(item.get("promise_id") or "") for item in volume_promises if str(item.get("promise_id") or "")]
    arc_id = str(arc_promise.get("promise_id") or "")
    if duty_type == "advance_plot":
        return [value for value in [volume_ids[0] if volume_ids else "", series_ids[0] if series_ids else ""] if value]
    if duty_type == "advance_relationship":
        return [value for value in [arc_id, volume_ids[1] if len(volume_ids) > 1 else (volume_ids[0] if volume_ids else "")] if value]
    if duty_type == "expand_world":
        return [value for value in [series_ids[2] if len(series_ids) > 2 else (series_ids[0] if series_ids else ""), volume_ids[0] if volume_ids else ""] if value]
    if duty_type == "resolve_promise":
        return [value for value in [arc_id, volume_ids[0] if volume_ids else ""] if value]
    if duty_type == "deliver_climax":
        return [value for value in [arc_id, volume_ids[1] if len(volume_ids) > 1 else (volume_ids[0] if volume_ids else ""), series_ids[1] if len(series_ids) > 1 else ""] if value]
    if duty_type == "pace_breath":
        return [value for value in [arc_id] if value]
    return [value for value in [arc_id, volume_ids[0] if volume_ids else ""] if value]


def _chapter_task_promise_actions(*, duty_type: str, is_final_task_in_arc: bool, is_final_task_in_series: bool) -> tuple[List[str], bool]:
    if duty_type == "advance_plot":
        return ["maintain_continuity", "open_follow_on_promise"], False
    if duty_type == "advance_relationship":
        return ["maintain_continuity", "open_follow_on_promise"], False
    if duty_type == "expand_world":
        return ["maintain_continuity", "open_follow_on_promise"], False
    if duty_type == "resolve_promise":
        return ["advance_payoff", "maintain_continuity"], False
    if duty_type == "deliver_climax":
        return ["close_arc_loop", "advance_payoff", "maintain_continuity"], False
    if duty_type == "pace_breath":
        return (["maintain_continuity"], not is_final_task_in_arc and not is_final_task_in_series)
    return ["maintain_continuity"], False


def _build_longform_structure(
    *,
    world_id: str,
    world_title: str,
    life_theme: str,
    target_total_chapters: int,
    target_total_volumes: int,
    target_word_count: int,
) -> Dict[str, Any]:
    series_id = f"{world_id}::series"
    series_promises = _series_promise_templates(series_id=series_id, world_title=world_title, life_theme=life_theme)
    chapters_per_volume_base = max(1, target_total_chapters // target_total_volumes)
    volume_plans: List[Dict[str, Any]] = []
    arc_plans: List[Dict[str, Any]] = []
    remaining_chapters = target_total_chapters
    duty_cycle = (
        [
            "advance_plot",
            "advance_relationship",
            "expand_world",
            "resolve_promise",
            "pace_breath",
            "deliver_climax",
        ]
        if target_total_chapters >= 100
        else [
            "advance_plot",
            "advance_relationship",
            "expand_world",
            "resolve_promise",
        ]
    )
    for volume_index in range(1, target_total_volumes + 1):
        if volume_index == target_total_volumes:
            volume_target = remaining_chapters
        else:
            volume_target = chapters_per_volume_base
        remaining_chapters -= volume_target
        volume_id = f"{series_id}::volume_{volume_index}"
        volume_promises = _volume_promise_templates(volume_id=volume_id, volume_index=volume_index, volume_target=volume_target)
        volume_plans.append(
            {
                "volume_id": volume_id,
                "order": volume_index,
                "title": f"第{volume_index}卷",
                "goal": f"围绕“{life_theme or world_title}”推进第{volume_index}卷主线与关系变化。",
                "target_chapters": volume_target,
                "climax_definition": f"第{volume_index}卷高潮必须改变主角与世界的一项稳定关系。",
                "end_state": f"第{volume_index}卷结束时留下可推进下一卷的新债与新选择。",
                "volume_promises": volume_promises,
            }
        )
        first_arc = max(1, volume_target // 3)
        second_arc = max(1, volume_target // 3)
        third_arc = max(1, volume_target - first_arc - second_arc)
        arc_sizes = [first_arc, second_arc, third_arc]
        for arc_offset, arc_size in enumerate(arc_sizes, start=1):
            arc_id = f"{volume_id}::arc_{arc_offset}"
            arc_promise = _arc_promise_template(arc_id=arc_id, volume_index=volume_index, arc_offset=arc_offset, arc_size=arc_size)
            local_cycle = duty_cycle[arc_offset - 1 :] + duty_cycle[: arc_offset - 1]
            chapter_tasks = []
            for task_index in range(1, arc_size + 1):
                duty_type = local_cycle[(task_index - 1) % len(local_cycle)]
                if task_index == arc_size and volume_index == target_total_volumes and arc_offset == len(arc_sizes):
                    duty_type = "deliver_climax"
                elif task_index == arc_size:
                    duty_type = "resolve_promise"
                elif task_index == max(1, arc_size - 1):
                    duty_type = "expand_world" if duty_type == "resolve_promise" else duty_type
                promise_targets = _chapter_task_promise_targets(
                    duty_type=duty_type,
                    series_promises=series_promises,
                    volume_promises=volume_promises,
                    arc_promise=arc_promise,
                )
                promise_actions, bridge_only = _chapter_task_promise_actions(
                    duty_type=duty_type,
                    is_final_task_in_arc=task_index == arc_size,
                    is_final_task_in_series=task_index == arc_size and volume_index == target_total_volumes and arc_offset == len(arc_sizes),
                )
                chapter_tasks.append(
                    ensure_chapter_task_quality_contract(
                        {
                            "chapter_task_id": f"{arc_id}::task_{task_index}",
                            "objective": f"以 {duty_type} 为主职责推进当前弧线。",
                            "duty_type": duty_type,
                            "target_words": 2000,
                            "reveal_budget": 2 if duty_type in {"resolve_promise", "deliver_climax"} else 1,
                            "promise_actions": promise_actions,
                            "promise_targets": promise_targets,
                            "allow_terminal": duty_type == "deliver_climax" and volume_index == target_total_volumes and arc_offset == len(arc_sizes),
                            "bridge_only": bridge_only,
                            "notes": "auto_generated_longform_task",
                        },
                        target_chapters=target_total_chapters,
                    )
                )
            arc_plans.append(
                {
                    "arc_id": arc_id,
                    "volume_id": volume_id,
                    "order": arc_offset,
                    "title": f"第{volume_index}卷 · 第{arc_offset}弧",
                    "goal": f"完成第{volume_index}卷第{arc_offset}弧的核心推进。",
                    "conflict": f"让人物在第{volume_index}卷里承担新的关系与代价冲突。",
                    "reveal_budget": 2,
                    "payoff_targets": [f"{volume_id}::promise", f"{arc_id}::turn"],
                    "completion_conditions": ["main_conflict_shifted", "new_debt_or_promise_opened"],
                    "target_chapters": arc_size,
                    "arc_promises": [arc_promise],
                    "chapter_tasks": chapter_tasks,
                }
            )
    return {
        "series_plan": {
            "series_id": series_id,
            "title": world_title,
            "total_volume_target": target_total_volumes,
            "total_chapter_target": target_total_chapters,
            "target_word_count": target_word_count,
            "theme_statement": life_theme or world_title,
            "series_promises": series_promises,
        },
        "volume_plans": volume_plans,
        "arc_plans": arc_plans,
        "chapter_budget_policy": {
            "default_target_words": 2000,
            "min_target_words": 1800,
            "max_target_words": 2200,
            "default_reveal_budget": 1,
            "duty_cycle": duty_cycle,
        },
    }


def _build_characters_for_preset(
    *,
    preset_id: str,
    lead_name: str,
    counterpart_name: str,
    supporting_name: str,
    life_theme: str,
) -> List[Dict[str, Any]]:
    shared = {
        "jade_court": {
            "lead": {
                "core_wound": "总在体面和真心之间被迫二选一",
                "public_self": "我能撑住全局",
                "shadow_desire": "有人先替我认一次真心",
                "defense_style": "克制与硬撑",
                "vows": ["不再只替所有人考虑"],
                "poisons": {"greed": 0.2, "anger": 0.18, "delusion": 0.34, "pride": 0.62, "doubt": 0.42},
            },
            "counterpart": {
                "core_wound": "被体面和规矩替自己做决定",
                "public_self": "我不在乎",
                "shadow_desire": "被平等地选一次",
                "defense_style": "冷问",
                "vows": ["不再接收半真半假的温柔"],
                "poisons": {"greed": 0.12, "anger": 0.24, "delusion": 0.22, "pride": 0.48, "doubt": 0.5},
            },
        },
        "urban_mystery": {
            "lead": {
                "core_wound": "被误解与被抛下",
                "public_self": "我能把残局收干净",
                "shadow_desire": "有人先站在我这边一次",
                "defense_style": "嘴硬与拖延",
                "vows": ["不再让重要的人从别人那里知道真相"],
                "poisons": {"greed": 0.28, "anger": 0.22, "delusion": 0.46, "pride": 0.52, "doubt": 0.61},
            },
            "counterpart": {
                "core_wound": "被替自己决定命运",
                "public_self": "我不在乎",
                "shadow_desire": "被平等对待",
                "defense_style": "冷问与收口",
                "vows": ["不再被半真半假的温柔说服"],
                "poisons": {"greed": 0.12, "anger": 0.24, "delusion": 0.28, "pride": 0.48, "doubt": 0.54},
            },
        },
        "xianxia": {
            "lead": {
                "core_wound": "守不住最想守的人",
                "public_self": "我只讲大道",
                "shadow_desire": "哪怕一回，只为一人偏路",
                "defense_style": "克制与自罚",
                "vows": ["我当年既许众生，便不能只为一人"],
                "poisons": {"greed": 0.34, "anger": 0.18, "delusion": 0.36, "pride": 0.68, "doubt": 0.22},
            },
            "counterpart": {
                "core_wound": "被大道放弃在身后",
                "public_self": "我只是来问一句旧话",
                "shadow_desire": "他能为我偏一次路",
                "defense_style": "冷问与不肯退",
                "vows": ["若旧誓真要反噬，也该有人与你同担"],
                "poisons": {"greed": 0.16, "anger": 0.24, "delusion": 0.22, "pride": 0.44, "doubt": 0.48},
            },
        },
        "synthetic": {
            "lead": {
                "core_wound": "被替自己决定",
                "public_self": "我很稳",
                "shadow_desire": "被认真听见",
                "defense_style": "迟疑",
                "vows": ["不再退后"],
                "poisons": {"greed": 0.2, "anger": 0.2, "delusion": 0.4, "pride": 0.5, "doubt": 0.4},
            },
            "counterpart": {
                "core_wound": "被隐瞒",
                "public_self": "我不在乎",
                "shadow_desire": "被平等对待",
                "defense_style": "冷处理",
                "vows": ["不替别人圆谎"],
                "poisons": {"greed": 0.1, "anger": 0.3, "delusion": 0.3, "pride": 0.5, "doubt": 0.5},
            },
        },
    }[preset_id]

    def _character(character_id: str, display_name: str, role: str, template: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "character_id": character_id,
            "display_name": display_name,
            "role": role,
            "destiny_contract": {"life_theme": life_theme or "面对真正的代价时，是否还敢继续往前。"},
            "poison_vector": template["poisons"],
            "vow_profile": {
                "vows": list(template["vows"]),
                "sacrifice_capacity": 0.68 if role == "lead" else 0.52,
                "truth_tolerance": 0.48 if role == "lead" else 0.72,
            },
            "wound_profile": {
                "core_wound": template["core_wound"],
                "public_self": template["public_self"],
                "shadow_desire": template["shadow_desire"],
                "defense_style": template["defense_style"],
            },
            "awakening_profile": {
                "clarity": 0.34 if role == "lead" else 0.46,
                "reflection_capacity": 0.62 if role == "lead" else 0.66,
                "repentance_threshold": 0.76 if role == "lead" else 0.68,
                "transformation_paths": ["坦白", "承担", "改口"],
            },
            "speech_traits": [template["defense_style"]],
            "action_traits": ["试探", "逼问" if role == "counterpart" else "强撑"],
        }

    characters = [
        _character("lead", lead_name, "lead", shared["lead"]),
        _character("counterpart", counterpart_name, "counterpart", shared["counterpart"]),
    ]
    if supporting_name:
        characters.append(
            {
                "character_id": "supporting",
                "display_name": supporting_name,
                "role": "supporting",
                "destiny_contract": {"life_theme": "在局势逼近时守住自己的分寸"},
                "poison_vector": {"greed": 0.1, "anger": 0.15, "delusion": 0.2, "pride": 0.4, "doubt": 0.35},
                "vow_profile": {"vows": ["先稳住局势"], "sacrifice_capacity": 0.45, "truth_tolerance": 0.55},
                "wound_profile": {"core_wound": "总在残局里收拾他人后果", "public_self": "我只看局面", "shadow_desire": "有人也替我考虑一次", "defense_style": "稳住场面"},
                "awakening_profile": {"clarity": 0.42, "reflection_capacity": 0.58, "repentance_threshold": 0.7, "transformation_paths": ["松手", "转身"]},
                "speech_traits": ["稳着说"],
                "action_traits": ["压场"],
            }
        )
    return characters


def _build_scene_blueprints_for_preset(preset_id: str) -> List[Dict[str, Any]]:
    variants = {
        "jade_court": [
            ("family_pressure", "setup", ["lead", "counterpart"], ["当众应下", "目光试探", "师长压来", "留下钩子"]),
            ("truth_trial", "trust_test", ["lead", "counterpart"], ["追问", "回避", "局面升级", "沉默余波"]),
            ("mask_crack", "reversal", ["lead", "counterpart"], ["嘴硬", "旧伤碰响", "体面裂口", "各自收声"]),
            ("confession_window", "discovery", ["lead", "counterpart"], ["夜深相见", "一句真话", "不肯退让", "再留后患"]),
        ],
        "urban_mystery": [
            ("alley_meet", "setup", ["lead", "counterpart"], ["夜巷相遇", "试探", "藏而不说", "留下钩子"]),
            ("truth_request", "trust_test", ["lead", "counterpart"], ["追问", "回避", "情绪升级", "沉默余波"]),
            ("mask_crack", "reversal", ["lead", "counterpart"], ["嘴硬", "旧伤碰响", "假平静裂开", "各自退半步"]),
            ("confession_window", "discovery", ["lead", "counterpart"], ["夜深重提旧事", "有人松口", "代价浮上来", "留下更重的问题"]),
        ],
        "xianxia": [
            ("lamp_awakens", "setup", ["lead", "counterpart"], ["古灯异动", "旧誓回响", "心意压下", "不祥预兆"]),
            ("vow_trial", "temptation", ["lead", "counterpart"], ["旧人现身", "誓言动摇", "代价显形", "强行压下"]),
            ("mask_crack", "reversal", ["lead", "counterpart"], ["大道失守", "旧伤揭开", "私心露口", "不欢而散"]),
            ("confession_window", "discovery", ["lead", "counterpart"], ["偏殿对峙", "旧誓说破", "天命压下", "留下反噬"]),
        ],
        "synthetic": [
            ("synthetic_setup", "setup", ["lead", "counterpart"], ["入场", "试探", "沉默余波"]),
            ("synthetic_truth", "trust_test", ["lead", "counterpart"], ["追问", "回避", "硬着头皮开口"]),
            ("synthetic_mask", "reversal", ["lead", "counterpart"], ["嘴硬", "露怯", "裂口落地"]),
            ("synthetic_confession", "discovery", ["lead", "counterpart"], ["抓住窗口", "说半句真话", "留下更重后果"]),
        ],
    }
    return [
        ensure_scene_quality_contract(
            {
                "scene_id": scene_id,
                "scene_function": scene_function,
                "phase_support": ["setup", "early_rising", "midpoint"],
                "required_roles": required_roles,
                "beats_template": beats,
            }
        )
        for scene_id, scene_function, required_roles, beats in variants[preset_id]
    ]


def _build_voice_profiles_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    if preset_id == "xianxia":
        return {
            "lead": {
                "profile_id": "lead", "cadence": "measured", "directness": 0.54, "bluntness": 0.33, "restraint": 0.84, "social_rank_awareness": 0.72,
                "opening_style": ["旧誓若真要追上来，也该先由我自己接住。"],
                "pressure_style": ["你若非逼我开口，我也不愿让这层反噬先落到你身上。"],
                "pivot_style": ["大道我没有忘，只是这一次我也不能再把你留在身后。"],
                "aftermath_style": ["这一句先落在这里，后面的天罚我自己去领。"],
                "echo_style": ["等下一次再见时，我不会只带着一身沉默回来。"],
                "signature_replies": ["你先别替我断，我还想亲手把这句誓补完整。"],
            },
            "counterpart": {
                "profile_id": "counterpart", "cadence": "cool", "directness": 0.78, "bluntness": 0.61, "restraint": 0.46, "social_rank_awareness": 0.58,
                "opening_style": ["誓既然是你亲口许下的，就别总拿大道当成回避我的借口。"],
                "pressure_style": ["我来不是求你回头，是要你承认这道伤到底落在谁身上。"],
                "pivot_style": ["你若总想一个人把天命背完，那我偏要把这句话逼到明处。"],
                "aftermath_style": ["我先不替你收场，等你自己把这句旧誓认清。"],
                "echo_style": ["下次再见时，你最好带着真话，不是带着更圆的道理。"],
                "signature_replies": ["我不是来听你讲大道的，我是来问你到底还肯不肯看我。"],
            },
        }
    if preset_id == "jade_court":
        return {
            "lead": {
                "profile_id": "lead", "cadence": "measured", "directness": 0.62, "bluntness": 0.41, "restraint": 0.74, "social_rank_awareness": 0.82,
                "opening_style": ["我知道这一步迟早得走，只是没想到会压得这样快。"],
                "pressure_style": ["你若真要逼我回答，我也不能再把自己缩回去。"],
                "pivot_style": ["真正难的不是选路，而是承认自己早就被逼到了墙角。"],
                "aftermath_style": ["我先把话放在这里，后面该担的我自己担。"],
                "echo_style": ["等下一次再开口时，我不会再只带着体面过来。"],
                "signature_replies": ["我先把话放在这里，剩下的路我自己认。"],
            },
            "counterpart": {
                "profile_id": "counterpart", "cadence": "cool", "directness": 0.8, "bluntness": 0.58, "restraint": 0.52, "social_rank_awareness": 0.76,
                "opening_style": ["你总可以继续讲体面，但我更想听你到底肯不肯认心里那一句。"],
                "pressure_style": ["我不怕难听，只怕你又拿规矩替自己找台阶。"],
                "pivot_style": ["再绕半步，这件事只会在更坏的时候追上来。"],
                "aftermath_style": ["我先记着，等你想清楚了再来把后半句补上。"],
                "echo_style": ["下次见我时，别再只带着更圆的话。"],
                "signature_replies": ["你最好别再只给我半句真话。"],
            },
        }
    if preset_id == "synthetic":
        return {
            "lead": {
                "profile_id": "lead", "cadence": "measured", "directness": 0.56, "bluntness": 0.34, "restraint": 0.66, "social_rank_awareness": 0.18,
                "opening_style": ["我不是没想退，只是退到这里已经不算没选。"],
                "pressure_style": ["你要我认，我可以认，但别逼我装作从没动摇过。"],
                "pivot_style": ["既然已经看见这一层，我就不想再把它塞回去。"],
                "aftermath_style": ["这句话先落在这里，后面的代价我自己接。"],
                "echo_style": ["等下一次再说时，我不会再只带着沉默过来。"],
                "signature_replies": ["我先把这句认下，剩下的我不再推给局势。"],
            },
            "counterpart": {
                "profile_id": "counterpart", "cadence": "tight", "directness": 0.81, "bluntness": 0.63, "restraint": 0.44, "social_rank_awareness": 0.12,
                "opening_style": ["你要是不肯把话说明白，我就只能把它一路追到最里面。"],
                "pressure_style": ["我可以听难听的话，但不会再替你把裂口遮回去。"],
                "pivot_style": ["再绕半步，这件事只会换个地方继续裂。"],
                "aftermath_style": ["我先不替你收场，等你自己把后半句带回来。"],
                "echo_style": ["下次再来时，别只带着更圆的借口。"],
                "signature_replies": ["我可以先不走，但你别指望我继续替你圆这层假平静。"],
            },
        }
    return {
        "lead": {
            "profile_id": "lead", "cadence": "measured", "directness": 0.58, "bluntness": 0.37, "restraint": 0.71, "social_rank_awareness": 0.28,
            "opening_style": ["这条路我不是没想退过，只是退到这里已经来不及了。"],
            "pressure_style": ["你要我认，我可以认，可别逼我装作这一切从没发生。"],
            "pivot_style": ["我不是不怕失去，只是不想再靠沉默把人推远。"],
            "aftermath_style": ["话先落在这里，后面的亏欠我自己去补。"],
            "echo_style": ["等我下次再来，就不会只带着一句半真半假的话。"],
            "signature_replies": ["我先把这句认下，剩下的账我不会再赖给局势。"],
        },
        "counterpart": {
            "profile_id": "counterpart", "cadence": "cool", "directness": 0.82, "bluntness": 0.69, "restraint": 0.48, "social_rank_awareness": 0.22,
            "opening_style": ["你要是不肯把话说透，我就只能把它一层层逼出来。"],
            "pressure_style": ["我不怕难听，只怕你又拿沉默当成温柔。"],
            "pivot_style": ["再绕半步，这件事只会在更坏的时候反咬回来。"],
            "aftermath_style": ["我先记着，等你想清楚了再来把剩下那句说完。"],
            "echo_style": ["下次见我时，别再拿旧说辞来试探我的耐心。"],
            "signature_replies": ["我可以先不走，但你别指望我继续替你圆这层假平静。"],
        },
    }


def _build_response_profiles_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    if preset_id == "xianxia":
        return {
            "lead": {
                "cadence_id": "lead", "reaction_tempo": "measured",
                "reaction_lines": {"entry": ["他先垂了垂眼，像把翻起来的灵息又一点点按回骨血里。"], "pressure": ["袍袖下的手指轻轻一蜷，连呼吸都像先被他自己截断了一截。"], "pivot": ["他这才抬眼，眼底那点动摇没有散尽，语气却已经不肯再退。"], "aftermath": ["收声时他反倒更静，静得像把更重的代价先压回自己身上。"], "echo": ["他不再追着解释，可那层未尽之意仍在周身灵息里发紧。"]},
                "reply_lines": {"entry": ["你既然追到这里，我便不想再把这句话藏回去。"], "pressure": ["我不是不肯认，只是不想让反噬先顺着你落下来。"], "pivot": ["若连这一句我都不敢承，后面的天命我也担不起。"], "aftermath": ["这层代价先记在我身上，你不必替我接。"], "echo": ["等我再回来时，我会把那句欠你的话一并补完。"]},
            },
            "counterpart": {
                "cadence_id": "counterpart", "reaction_tempo": "tight",
                "reaction_lines": {"entry": ["她并未立刻近前，只把目光钉在他脸上，像先把旧伤一寸寸照亮。"], "pressure": ["她指尖搭在剑穗上，没真碰响，那点停顿反而更像逼问。"], "pivot": ["她这才开口，语气清冷，却把最不肯听的那句推到了面前。"], "aftermath": ["她先收住了势，可那点不肯退的锋芒还停在原处。"], "echo": ["她不再多说，可檐下那声铃响倒像替她把余话追了回来。"]},
                "reply_lines": {"entry": ["你若还肯认这层旧誓，就别再拿沉默替自己挡。"], "pressure": ["我不怕反噬，只怕你又把我留在你那套大道之外。"], "pivot": ["你若总往后退，我就只好把这句真话追到山门外。"], "aftermath": ["先把这句放下，回头你还是得自己来接。"], "echo": ["下一回再见，我要听的是你的真心，不是更漂亮的道理。"]},
            },
        }
    if preset_id == "jade_court":
        return {
            "lead": {
                "cadence_id": "lead", "reaction_tempo": "measured",
                "reaction_lines": {"entry": ["他没有立刻接话，只让那句意思先在心里过了一遍。"], "pressure": ["他手上的细小动作先停住了，像终于不打算再替谁留余地。"], "pivot": ["他这才抬起眼来，语气仍不见急，可越平，越像逼人。"], "aftermath": ["他临到收声时反而更轻了些，可那点轻偏偏更重。"], "echo": ["他没有再追，可沉默已经替下一次相见留了一道裂口。"]},
                "reply_lines": {"entry": ["这句话既然出口，就别再往回收。"], "pressure": ["你总得先替自己承认一次。"], "pivot": ["再退半步，也只是让伤口换个地方继续裂。"], "aftermath": ["这事不会就这样过去。"], "echo": ["等你再来，就别只带着半句真话。"]},
            },
            "counterpart": {
                "cadence_id": "counterpart", "reaction_tempo": "tight",
                "reaction_lines": {"entry": ["她没立刻接，只把那点迟疑先压在眼底。"], "pressure": ["她先收了动作，反倒把那层分寸逼得更紧。"], "pivot": ["她这才开口，语气不急，却把每个字都落得很实。"], "aftermath": ["她没有继续追问，可那层不肯退的意思还停在原地。"], "echo": ["她先收了声，留下来的却是更重的一道边界。"]},
                "reply_lines": {"entry": ["既然你肯开口，就别只给我半句。"], "pressure": ["你要真想护谁，就别总拿规矩来替自己找退路。"], "pivot": ["我可以听难听的话，但不会替你把代价咽回去。"], "aftermath": ["这句先放在这里，回头你还是得自己来认。"], "echo": ["下一次见我时，最好带着真话来。"]},
            },
        }
    if preset_id == "synthetic":
        return {
            "lead": {
                "cadence_id": "lead", "reaction_tempo": "measured",
                "reaction_lines": {"entry": ["没有立刻接，只把那点迟疑在心里又压了一遍。"], "pressure": ["呼吸很轻地顿了一下，像解释已经挤到喉间却又被他自己按住。"], "pivot": ["这才抬眼，明明还在犹豫，语气却已经不想再退。"], "aftermath": ["到收声时反而更慢，像是在替后面的代价先让出位置。"], "echo": ["没再追着补话，可那点未尽之意还挂在肩背上。"]},
                "reply_lines": {"entry": ["既然都走到这里了，我不想再把这句收回去。"], "pressure": ["我不是不肯认，只是不想再拿沉默糊弄过去。"], "pivot": ["再往后退，我也还是得自己把这句真话接住。"], "aftermath": ["这层后果先记在我这里。"], "echo": ["等下一次再说时，我会把后半句一起带来。"]},
            },
            "counterpart": {
                "cadence_id": "counterpart", "reaction_tempo": "tight",
                "reaction_lines": {"entry": ["没有立刻发作，只把那句没说透的话牢牢按在视线里。"], "pressure": ["指尖在桌沿轻轻一停，像先替那句真话占了个位置。"], "pivot": ["这才开口，字不多，却每个都卡在最难回避的地方。"], "aftermath": ["没有继续逼，可那种不肯圆谎的态度反而更重。"], "echo": ["先收了声，留下来的却是更明确的一层边界。"]},
                "reply_lines": {"entry": ["既然要说，就别只给我半句。"], "pressure": ["你要是真想往前走，就别总把退路藏在沉默后面。"], "pivot": ["我可以听真话，但不会再替你把代价吞回去。"], "aftermath": ["这句先放在这里，回头你还是得自己来认。"], "echo": ["下次见我时，最好带着真相来。"]},
            },
        }
    return {
        "lead": {
            "cadence_id": "lead", "reaction_tempo": "measured",
            "reaction_lines": {"entry": ["没有立刻接话，只先把手机扣回掌心，像在替自己压住那点慌。"], "pressure": ["喉结很轻地动了一下，像那些解释已经挤到了嘴边，却又被他硬压回去。"], "pivot": ["这才抬起眼来，眼底的迟疑没退干净，语气却已经不肯再软。"], "aftermath": ["到收声时，他反而把呼吸放慢了，像是在替后面的代价腾位置。"], "echo": ["他没再追着解释，可那点没说完的话还在肩背上绷着。"]},
            "reply_lines": {"entry": ["你先别急着定我，我至少得把这一层说完。"], "pressure": ["我不是不敢认，只是不想再把你拖进同一个坑里。"], "pivot": ["既然已经走到这里，我就不想再装作什么都没看见。"], "aftermath": ["这句先算在我头上，后面的我不会再躲。"], "echo": ["等我再来时，我会把那句真正该说的带过来。"]},
        },
        "counterpart": {
            "cadence_id": "counterpart", "reaction_tempo": "tight",
            "reaction_lines": {"entry": ["她没立刻接，只把视线钉在他脸上，像先看穿那层没说出口的退路。"], "pressure": ["指尖在杯盖上轻敲了两下，脆响短得很，却把场面一下子敲紧了。"], "pivot": ["她这才开口，语气不高，反而像把每个字都压到了最难回避的位置。"], "aftermath": ["她没有继续逼，可那种不肯替人圆谎的态度反而更重。"], "echo": ["她先收了声，留下来的却是更明确的一层边界。"]},
            "reply_lines": {"entry": ["既然你肯开口，就别只给我半句。"], "pressure": ["你要真想护谁，就别总拿沉默来替自己找台阶。"], "pivot": ["我可以听真话，但不会再替你把后果咽回去。"], "aftermath": ["这句先放在这，迟早还要回来算清。"], "echo": ["下次见我时，你最好带着真相，不是带着更圆的借口。"]},
        },
    }


def _build_pressure_styles_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    return {
        "lead": {
            "style_id": "lead",
            "under_pressure": "先压住动作，再把更难听的话轻一点说出来",
            "when_cornered": "沉默半拍后承认真正的裂口",
            "when_softening": "语气微松，但不立刻退让",
            "when_deflecting": "把心里最重的一句往旁边挪半寸",
        },
        "counterpart": {
            "style_id": "counterpart",
            "under_pressure": "先稳住目光，再把问题压到最难回避的位置",
            "when_cornered": "不替别人补台阶，只把真话逼到明处",
            "when_softening": "暂时收声，但不撤掉边界",
            "when_deflecting": "用更短的句子把退路堵回去",
        },
    }


def _build_action_policies_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    presets = {
        "jade_court": {
            "false_peace": {
                "entry": ["袖角拂过案沿，只一点轻响，厅里的分寸就全绷紧了。"],
                "pressure": ["茶盏还温着，谁也没先碰，倒像先把规矩摆到了人心上。"],
                "pivot": ["纸页一翘，连停顿都像在替谁把体面先挑开一线。"],
                "aftermath": ["人没立刻散，屋里的静却比刚才更沉。"],
                "echo": ["越到后面，灯火下那点没说完的话越像要回身索账。"],
                "repeat": ["动作不大，可谁都知道事情已经换了味道。"],
            },
            "truth_trial": {
                "entry": ["先动的不是声音，而是目光沿着席间一寸寸压过去。"],
                "pressure": ["灯影压在杯沿上，连换气都像先过了一道门槛。"],
                "pivot": ["最轻的一点改口，都像把场面推向了不得不认的那边。"],
                "aftermath": ["茶香渐淡，场里的气却更不肯散。"],
                "echo": ["等人散尽以后，空下来的位置还像留着刚才那句重话。"],
                "repeat": ["再往下走时，谁都回不到还能装作若无其事的一侧。"],
            },
            "mask_crack": {
                "entry": ["嘴上还稳着，真正先露出来的是指尖那一点不肯承认的迟疑。"],
                "pressure": ["对面的人不再追问，反而把那层遮掩衬得更薄。"],
                "pivot": ["一句话没能绕开，连站姿都跟着露了怯。"],
                "aftermath": ["表面上谁都没失态，可真正的裂口已经落在心里。"],
                "echo": ["等下一次再开口时，谁也回不到还能把体面讲圆的那边。"],
            },
            "confession_window": {
                "entry": ["回廊忽然静下来，像连风声都给这句真话让了一步。"],
                "pressure": ["那口气被人压了又压，最后还是没能把话咽回去。"],
                "pivot": ["对面的人没有补台阶，只把空白留成最逼人的催促。"],
                "aftermath": ["真话一落下来，连站在原地都更像一种表态。"],
                "echo": ["这一回先说到这里，可真正决定关系走向的，是谁会带着后半句回来。"],
            },
        },
        "urban_mystery": {},  # filled by current pack assets at runtime
        "xianxia": {},        # filled by current pack assets at runtime
        "synthetic": {},      # filled by current pack assets at runtime
    }
    action_map = presets.get(preset_id) or {
        "false_peace": {"entry": ["桌上的器物轻轻一碰，谁都知道这一步已经走出去，很难再收回来。"]},
        "truth_trial": {"entry": ["先动的不是声音，而是视线和手指那一点收紧。"]},
        "mask_crack": {"entry": ["嘴上还稳着，可真正先露出来的是那一点没藏住的停顿。"]},
        "confession_window": {"entry": ["屋里忽然安静下来，像所有杂音都先给这句真话让了地方。"]},
    }
    return {"default": {"policy_id": "%s_default_action" % preset_id, "action_map": action_map}}


def _build_sensory_policies_for_preset(preset_id: str, locations: List[str]) -> Dict[str, Dict[str, Any]]:
    if preset_id == "jade_court":
        slot_defaults = {
            "花厅": ("花厅里檀香还没散尽，窗外的天色却已经压低下来。", "杯沿上一点冷光轻轻一闪，把谁都不肯退的那层心思照了出来。", "灯火更低一寸，屋里的静反而比刚才更重。"),
            "书房": ("书房里纸香和墨气压得很稳，越稳，越显得谁都不肯先退。", "案角压着的纸页微微一翘，像替谁先揭开了遮掩。", "越到后面，纸页翻动的轻响越像把旧话重新翻出来。"),
            "回廊": ("回廊里的风比屋内更直，把灯影吹得一晃一晃。", "脚步踩过木板时，回声轻得像不肯认输的心跳。", "风声轻轻翻过去，连沉默都像被擦亮了一层。"),
        }
    elif preset_id == "xianxia":
        slot_defaults = {
            "偏殿": ("偏殿里灯焰不稳，薄薄一层金光把每个人心里的动摇都映得无处可藏。", "案上香灰斜斜坠下来，殿角风过时，铜铃只轻轻响了一声。", "越到后面，偏殿里那一点灯火越像把旧誓从灰里重新照了出来。"),
            "石阶": ("石阶上寒意贴着足底往上爬，连衣角擦过风声都显得格外冷。", "夜露落在阶边，月光从裂石里渗下来，把影子压得又细又长。", "风再过一遍石阶时，连沉默都像带了薄刃。"),
            "山门": ("山门外的风空得很，像专为那些说不出口的旧誓留出回响。", "远处云气压低，门前长阶只剩一点冷白，照得人连退路都看得太清。", "越靠近山门，越能听见那些没补完的誓言在风里一层层逼近。"),
        }
    elif preset_id == "synthetic":
        slot_defaults = {
            "中庭": ("中庭空得发亮，连人说话前那口气都像会先落在地上。", "风从廊檐底下穿过去，把纸页角和衣摆都掀起一点轻响。", "越到后面，中庭里那点回声越像把没说完的话一遍遍推回来。"),
            "长廊": ("长廊里脚步声拖得很长，像任何迟疑都会被放大。", "窗纸上挂着一点灰白的亮，连转身时衣料摩擦都显得分外清楚。", "长廊越静，那点不肯说透的心思就越像贴在身后。"),
            "窗边": ("窗边的光线斜斜落下来，把每个人脸上的犹豫都照得更薄。", "风碰着空杯边沿，发出一下极轻的响，倒像替谁先开了口。", "越靠近窗边，那点停不下来的回响越像逼人把话说完。"),
        }
    else:
        slot_defaults = {
            "旧巷": ("旧巷里潮气很重，墙面返出来的凉意像先替人把心口压窄了一圈。", "路灯把积水照出一层发灰的亮，连鞋底蹭过地面的声音都显得格外清。", "越到后面，巷子里的回声越像把那些没说完的话一遍遍弹回来。"),
            "便利店门口": ("便利店门口的白光太直，把每个人脸上的迟疑都照得无处可躲。", "冰柜的低鸣贴着耳边过去，塑料门帘轻轻一摆，带出一股凉得过分的甜味。", "门口那点白光不动声色，却把场面里的退路照得越来越窄。"),
            "天桥下": ("天桥下风声空荡，连一句压低的话都像会被钢梁重新弹回来。", "桥洞阴影压在肩头，远处车流从缝里掠过去，只留下短促的亮和噪音。", "越往后，桥下那种空空的回响越像把每个人心里的亏欠放大。"),
        }
    location_slots = {}
    for location in locations:
        atmosphere, detail, repeat_detail = slot_defaults.get(location, next(iter(slot_defaults.values())))
        location_slots[location] = {
            "atmosphere": [atmosphere],
            "detail": [detail],
            "repeat_detail": [repeat_detail],
        }
    generic = {
        "jade_court": {
            "atmosphere": ["屋里没有真正的安静，连空气都像在替谁压住一句没说完的话。"],
            "detail": ["最细小的灯影、纸页和杯沿冷光，都把场里的情绪衬得更清。"],
            "repeat_detail": ["等沉默拖长以后，最轻的一点响动反而更像回身索账。"],
        },
        "urban_mystery": {
            "atmosphere": ["这座城的夜里没有真正的安静，连空气都像替谁记着一笔旧账。"],
            "detail": ["最细小的光线和声响都在提醒人，这里没有一句话会白白落下去。"],
            "repeat_detail": ["等沉默拉长以后，城市里最轻的一点回声反而把情绪照得更明。"],
        },
        "xianxia": {
            "atmosphere": ["灵息与风声缠在一起，像谁都不肯先把那句真话放下。"],
            "detail": ["最轻的一点铃响和灯影，都把场里的取舍照得更锋利。"],
            "repeat_detail": ["等沉默拖长以后，连周身灵息都像替旧誓回了一次身。"],
        },
        "synthetic": {
            "atmosphere": ["屋里没有真正的安静，连空气都像在替人记着一句没说完的话。"],
            "detail": ["最轻的一点光线和声响，都把场里的试探照得更清。"],
            "repeat_detail": ["等沉默拖长以后，最小的动静反而成了最重的提醒。"],
        },
    }[preset_id]
    return {"default": {"policy_id": "%s_sensory" % preset_id, "location_slots": location_slots, "generic_slots": generic}}


def _build_scene_realization_for_preset(preset_id: str) -> Dict[str, Dict[str, Any]]:
    presets = {
        "jade_court": {
            "scene_openings": {
                "false_peace": ["家门与体面先压下来。屋里的静稳得过分，像每一句真话都得先过一道门槛。"],
                "truth_trial": ["真正开始逼近的不是答案，而是那句谁都不肯先认下来的真话。"],
                "mask_crack": ["表面还稳着，可真正先裂开的，往往是那一点不肯承认的迟疑。"],
                "confession_window": ["有些话只有在风声也退开的时候，才会自己浮到嘴边。"],
            },
            "scene_hooks": {
                "false_peace": ["这层平静撑不了太久，真正要追上来的，是那句被按回去的心里话。"],
                "truth_trial": ["话先停在这里，可下一次见面时还要不要继续问下去，才是更难的那一步。"],
                "mask_crack": ["等下一次再开口时，谁都回不到还能把体面讲圆的那一边。"],
                "confession_window": ["这一回先说到这里，可真正决定走向的，是谁会带着后半句回来。"],
            },
        },
        "urban_mystery": {
            "scene_openings": {
                "false_peace": ["表面平静下的暗潮。旧巷的凉意先贴上来，像把每个人真正不肯承认的心思都逼到了嘴边。"],
                "truth_trial": ["真相开始逼近的时候，场面反而先静了一下，像谁都知道下一句会更难听。"],
                "mask_crack": ["嘴上还稳着，可真正先裂开的往往不是语气，而是那一点藏不住的停顿。"],
                "confession_window": ["有些真话只有在最安静的时候才会自己浮上来，像谁也压不回去。"],
            },
            "scene_hooks": {
                "false_peace": ["这层表面上的平静撑不过太久，真正会追上来的，是旧巷里那句没说尽的话。"],
                "truth_trial": ["话先落在这里，可真正让人睡不着的，往往是下一次见面时还要不要继续问下去。"],
                "mask_crack": ["等下一次再开口时，谁也回不到刚才那副还能装作没事的样子。"],
                "confession_window": ["这一回先说到这里，可真正决定关系走向的，是谁会先带着真相回来。"],
            },
        },
        "xianxia": {
            "scene_openings": {
                "false_peace": ["誓愿与天命先压下来。偏殿里的灯火不稳，像连空气都在替这层旧誓发颤。"],
                "temptation": ["真正先动摇的不是人，而是那一点被旧誓照亮以后再也压不住的执念。"],
                "mask_crack": ["大道还挂在嘴边，可真正先裂开的，是那一点再也讲不圆的私心。"],
                "confession_window": ["有些真话只有在灵息都静下来的时候才会自己浮上来，像谁也按不回去。"],
            },
            "scene_hooks": {
                "false_peace": ["这一层表面上的平静撑不过太久，真正要追上来的，是照骨灯里那句没人敢补完的旧誓。"],
                "temptation": ["话先停在这里，可真正难的，是下一次见面时谁还肯先认这层执念。"],
                "mask_crack": ["等下一次再开口时，谁都回不到还能把大道说得毫无裂缝的那边。"],
                "confession_window": ["这一回先说到这里，可真正决定命数的，是谁会带着那句真话回来。"],
            },
        },
        "synthetic": {
            "scene_openings": {
                "false_peace": ["表面平静下的暗潮。中庭里空得过分，像连空气都在等谁先把真话放下来。"],
                "truth_trial": ["真正开始逼近的不是答案，而是那句谁都不肯先认下来的真话。"],
                "mask_crack": ["表面还稳着，可真正先裂开的，往往是那一点不肯承认的迟疑。"],
                "confession_window": ["有些话只有在所有杂音都退开以后，才会自己浮到嘴边。"],
            },
            "scene_hooks": {
                "false_peace": ["这层平静撑不了太久，真正要追上来的，是那句被按回去的真话。"],
                "truth_trial": ["话先停在这里，可真正让人退不回去的，是下一次见面时还要不要继续问下去。"],
                "mask_crack": ["等下一次再开口时，谁都回不到刚才还能装稳的那一侧。"],
                "confession_window": ["这一回先说到这里，可真正决定走向的，是谁会带着后半句回来。"],
            },
        },
    }
    return {"default": {"contract_id": "%s_scene_realization" % preset_id, **presets[preset_id]}}
