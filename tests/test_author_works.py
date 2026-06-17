import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.core.linter import story_text_unit_count
from src.narrativeos.eval.service import evaluate_persisted_chapter
from src.narrativeos.models import NarrativeState
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def _auth_headers(client: TestClient, *, actor_id: str, actor_role: str, password: str) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={
            "actor_id": actor_id,
            "actor_role": actor_role,
            "password": password,
            "account_id": actor_id,
        },
    )
    login = client.post("/v1/auth/login", json={"actor_id": actor_id, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']['access_token']}"}


def _simple_state(chapter_index: int = 1) -> NarrativeState:
    return NarrativeState.from_dict(
        {
            "state_id": f"test_state_{chapter_index}",
            "world_id": "test_world",
            "turn_index": chapter_index,
            "story_phase": "setup",
            "chapter_index": chapter_index,
            "min_end_turn": 8,
            "fate_pressure": 0.0,
            "karmic_weather": {},
            "unresolved_debts": [],
            "world_facts": [],
            "timeline": [],
            "characters": {},
            "relationship_graph": [],
            "open_promises": [],
            "tension": 0.3,
            "themes": {},
            "player_intent": {},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13",
        }
    )


def _seed_tide_archive_strategy_bundle_draft(
    authoring: AuthoringService,
    repository: SQLAlchemyRepository,
    *,
    author_id: str = "",
) -> dict[str, object]:
    pack = copy.deepcopy(authoring.registry.get_published_world("tide_archive_memory_debt")["worldpack"])
    if author_id:
        pack["manifest"]["author_id"] = author_id
        pack["metadata"] = {**dict(pack.get("metadata") or {}), "author_brief": {"author_id": author_id}}
    draft = authoring.save_draft(pack)
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    early_scene = worldpack["scene_blueprints"][0]
    mid_scene = next(item for item in worldpack["scene_blueprints"] if item["scene_id"] == "submerged_return")
    late_arc = worldpack["arc_plans"][-1]
    late_task = late_arc["chapter_tasks"][0]
    chapter_heatmap = [
        {
            "chapter_index": 2,
            "chapter_title": "第2章",
            "decision": "rewrite",
            "severity": "watch",
            "overall_score": 0.79,
            "issue_count": 2,
            "issue_codes": ["Q03", "Q04"],
            "scene_function": early_scene["scene_function"],
            "scene_id": early_scene["scene_id"],
            "chapter_task_id": worldpack["arc_plans"][0]["chapter_tasks"][0]["chapter_task_id"],
            "arc_id": worldpack["arc_plans"][0]["arc_id"],
            "volume_id": worldpack["arc_plans"][0]["volume_id"],
            "related_character_ids": list(early_scene["required_roles"]),
            "related_characters": list(early_scene["required_roles"]),
        },
        {
            "chapter_index": 35,
            "chapter_title": "第35章",
            "decision": "rewrite",
            "severity": "watch",
            "overall_score": 0.76,
            "issue_count": 2,
            "issue_codes": ["Q03", "Q04"],
            "scene_function": mid_scene["scene_function"],
            "scene_id": mid_scene["scene_id"],
            "chapter_task_id": worldpack["arc_plans"][5]["chapter_tasks"][0]["chapter_task_id"],
            "arc_id": worldpack["arc_plans"][5]["arc_id"],
            "volume_id": worldpack["arc_plans"][5]["volume_id"],
            "related_character_ids": list(mid_scene["required_roles"]),
            "related_characters": list(mid_scene["required_roles"]),
        },
        {
            "chapter_index": 85,
            "chapter_title": "第85章",
            "decision": "rewrite",
            "severity": "watch",
            "overall_score": 0.74,
            "issue_count": 1,
            "issue_codes": ["Q09"],
            "scene_function": "truth_trial",
            "scene_id": "",
            "chapter_task_id": late_task["chapter_task_id"],
            "arc_id": late_arc["arc_id"],
            "volume_id": late_arc["volume_id"],
            "related_character_ids": ["wen_xi", "gu_chenzhou"],
            "related_characters": ["闻汐", "顾沉舟"],
        },
    ]
    baseline_report = {
        "chapter_budget": 100,
        "longform_plan_snapshot": {
            "series_plan": worldpack["series_plan"],
            "volume_plans": worldpack["volume_plans"],
            "arc_plans": worldpack["arc_plans"],
            "chapter_budget_policy": worldpack["chapter_budget_policy"],
        },
        "evaluation_summary": {
            "pass_rate": 0.52,
            "rewrite_rate": 0.48,
            "block_rate": 0.0,
            "dialogue_ratio": 0.395,
            "avg_repetition_score": 0.289,
            "avg_exposition_ratio": 0.694,
        },
        "longform_summary": {
            "mid_arc_pass_rate": 0.758,
            "late_arc_pass_rate": 0.441,
            "q09_incidence_rate": 0.18,
        },
        "content_quality_contract_window_metrics": {
            "enabled": True,
            "early_window_q03_q04_share": 0.8,
            "mid_window_repeat_breach_rate": 0.7,
            "mid_window_exposition_breach_rate": 0.66,
            "late_window_q09_breach_rate": 0.4,
            "thresholds": {
                "early_window_q03_q04_share_max": 0.45,
                "mid_window_repeat_breach_rate_max": 0.30,
                "mid_window_exposition_breach_rate_max": 0.30,
                "late_window_q09_breach_rate_max": 0.08,
            },
            "contract_failed_chapters": [
                {"chapter_id": "chapter_2", "chapter_index": 2, "failed_checks": ["repetition_score_cap", "exposition_ratio_cap"], "decision": "rewrite"},
                {"chapter_id": "chapter_35", "chapter_index": 35, "failed_checks": ["repetition_score_cap", "exposition_ratio_cap"], "decision": "rewrite"},
                {"chapter_id": "chapter_85", "chapter_index": 85, "failed_checks": ["q09_pre_end", "continuation_pressure_floor"], "decision": "rewrite"},
            ],
        },
        "creative_cockpit": {
            "chapter_heatmap": {
                "chapters": chapter_heatmap,
                "issue_priority_groups": authoring._build_issue_priority_groups(chapter_heatmap),
            }
        },
        "chapter_evaluations": [],
        "latest_repair_loop_outcome": {},
        "repair_loop_history": [],
        "latest_strategy_bundle_execution": {},
        "strategy_bundle_execution_history": [],
    }
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = copy.deepcopy(baseline_report)
    repository.save_world_version(version, publish=False)
    return {
        "draft": draft,
        "worldpack": worldpack,
        "baseline_report": baseline_report,
        "early_scene": early_scene,
        "mid_scene": mid_scene,
        "late_arc": late_arc,
        "late_task": late_task,
    }


def test_shared_chapter_quality_gate_enforces_budget_and_pass_decision():
    good_body = "\n\n".join(
        [
            "旧站台的铁锈味被潮风一点点顶起来，沈砚把录音带从口袋里摸出来时，塑料外壳碰到栏杆，发出很轻的一响。林潮没有马上接，只把雨伞靠在售票窗边，低声问：“你到底还打不打算把那晚缺掉的话说完？”",
            "他沿着站台边缘向前走了两步，鞋底压过碎石，像把迟疑一粒粒踩碎。远处列车灯掠过黑水，映得她袖口那道旧折痕更明显。沈砚抬眼看她：“我不是怕真相，我是怕你听完以后连回头都不会。”",
            "林潮把湿掉的票根摊平在掌心，纸边卷起，像一条一直没能压好的时间线。她没有替自己辩解，只把票根递到他手边：“三年前你转身的时候，我就知道以后每一次重逢都得从这里重新开始。”",
            "站台顶棚被风吹得轻晃，灯影一格一格落下来，刚好把两个人隔在明暗交界处。沈砚没再躲，伸手接过票根时指腹被纸边割得发麻，却还是把那句压了太久的话送了出去：“我那时不是不信你，我是不敢让自己信。”",
            "话落下去以后，最先响起来的是远处铁轨深处的一阵空鸣。林潮慢慢把手收回衣袋，肩线却没有再绷得那么硬。她看着他：“那你现在最好想清楚，这句认下来以后，不只是你一个人要付代价。”",
            "沈砚靠在褪色的站牌上，没有像从前那样替任何人做决定。他把录音带放到两人中间的长椅上，像把证据和选择一起摊开：“这次我不替你选，也不替自己留后门。你要走，我认；你要继续查，我陪。”",
            "风从废弃检票口灌进来，带得玻璃窗轻轻发颤。林潮低头看着那卷录音带，忽然笑了一下，笑意却很淡：“你总算学会先问一句我愿不愿意。”她弯腰把磁带收进包里，动作稳得像把下一步也一并定了下来。",
            "两个人并肩离开站台时，脚边积水映着路灯，一路晃出细碎的光。谁都没有说和好，也没有给未来下定义，可那卷终于被共同带走的录音带，已经把下一章要面对的真相和关系一起推到了眼前。"
        ]
    )
    good = evaluate_persisted_chapter(
        chapter_id="chapter_good",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        choices=["继续追问", "先忍住不说"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert good["quality_gate"]["ok"] is True

    short_body = "他看了她一眼。\\n\\n“走吧。”"
    short = evaluate_persisted_chapter(
        chapter_id="chapter_short",
        world_version_id="world_v1",
        session_id="session_1",
        body=short_body,
        paragraphs=short_body.split("\n\n"),
        dialogue_count=1,
        action_count=0,
        detail_count=0,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        choices=["继续", "离开"],
        paywall_required=False,
        target_words=2000,
        min_target_words=1800,
    )
    assert short["quality_gate"]["ok"] is False
    assert "text_unit_floor_not_met" in short["quality_gate"]["failed_checks"]
    assert short["quality_gate"]["decision"] in {"rewrite", "block"}


def test_shared_chapter_quality_gate_blocks_disallowed_latin_tokens_in_visible_story_text():
    good_body = "\n\n".join(
        [
            "旧站台的铁锈味被潮风一点点顶起来，沈砚把录音带从口袋里摸出来时，塑料外壳碰到栏杆，发出很轻的一响。林潮没有马上接，只把雨伞靠在售票窗边，低声问：“你到底还打不打算把那晚缺掉的话说完？”",
            "他沿着站台边缘向前走了两步，鞋底压过碎石，像把迟疑一粒粒踩碎。远处列车灯掠过黑水，映得她袖口那道旧折痕更明显。沈砚抬眼看她：“我不是怕真相，我是怕你听完以后连回头都不会。”",
            "林潮把湿掉的票根摊平在掌心，纸边卷起，像一条一直没能压好的时间线。她没有替自己辩解，只把票根递到他手边：“三年前你转身的时候，我就知道以后每一次重逢都得从这里重新开始。”",
            "站台顶棚被风吹得轻晃，灯影一格一格落下来，刚好把两个人隔在明暗交界处。沈砚没再躲，伸手接过票根时指腹被纸边割得发麻，却还是把那句压了太久的话送了出去：“我那时不是不信你，我是不敢让自己信。”",
            "话落下去以后，最先响起来的是远处铁轨深处的一阵空鸣。林潮慢慢把手收回衣袋，肩线却没有再绷得那么硬。她看着他：“那你现在最好想清楚，这句认下来以后，不只是你一个人要付代价。”",
            "沈砚靠在褪色的站牌上，没有像从前那样替任何人做决定。他把录音带放到两人中间的长椅上，像把证据和选择一起摊开：“这次我不替你选，也不替自己留后门。你要走，我认；你要继续查，我陪。”",
            "风从废弃检票口灌进来，带得玻璃窗轻轻发颤。林潮低头看着那卷录音带，忽然笑了一下，笑意却很淡：“你总算学会先问一句我愿不愿意。”她弯腰把磁带收进包里，动作稳得像把下一步也一并定了下来。",
            "两个人并肩离开站台时，脚边积水映着路灯，一路晃出细碎的光。谁都没有说和好，也没有给未来下定义，可那卷终于被共同带走的录音带，已经把下一章要面对的真相和关系一起推到了眼前。",
        ]
    )

    allowed = evaluate_persisted_chapter(
        chapter_id="chapter_allowed_uppercase",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        chapter_title="第 1 章 · AI 回响",
        recap="前情提要：AI 留下的痕迹还没有散。",
        relationship_hints=["甲对乙多了一点信任。", "URL 只是缩写，不算正文英文。"],
        choices=["继续查看 API 留下的痕迹", "先不追问"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert allowed["quality_gate"]["ok"] is True
    assert allowed["quality_gate"]["disallowed_latin_token_hits"] == []

    blocked_body = evaluate_persisted_chapter(
        chapter_id="chapter_bad_body_token",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body + "\n\n她把 temptation 压回喉间，却还是没能把那句话彻底收住。",
        paragraphs=(good_body + "\n\n她把 temptation 压回喉间，却还是没能把那句话彻底收住。").split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        chapter_title="第 1 章 · 表面平静下的暗潮",
        recap="前情提要：他们把 temptation 压回了沉默里。",
        relationship_hints=["甲对乙多了一点信任。"],
        choices=["继续追问", "先忍住不说"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert blocked_body["quality_gate"]["ok"] is False
    assert "disallowed_latin_token_detected" in blocked_body["quality_gate"]["failed_checks"]
    assert "body" in blocked_body["quality_gate"]["latin_token_fields"]
    assert "temptation" in blocked_body["quality_gate"]["latin_token_tokens"]

    blocked_title = evaluate_persisted_chapter(
        chapter_id="chapter_bad_title_token",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        chapter_title="第 1 章 · temptation 回潮",
        recap="前情提要：风声还压在窗边。",
        relationship_hints=["甲对乙多了一点信任。"],
        choices=["继续追问", "先忍住不说"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert blocked_title["quality_gate"]["ok"] is False
    assert blocked_title["quality_gate"]["latin_token_fields"] == ["chapter_title"]

    blocked_choice = evaluate_persisted_chapter(
        chapter_id="chapter_bad_choice_token",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        chapter_title="第 1 章 · 表面平静下的暗潮",
        recap="前情提要：风声还压在窗边。",
        relationship_hints=["甲对乙多了一点信任。"],
        choices=["先压下 temptation", "继续追问"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert blocked_choice["quality_gate"]["ok"] is False
    assert blocked_choice["quality_gate"]["latin_token_fields"] == ["choice_1"]

    blocked_recap = evaluate_persisted_chapter(
        chapter_id="chapter_bad_recap_token",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        chapter_title="第 1 章 · 表面平静下的暗潮",
        recap="前情提要：她把 temptation 压回了沉默里。",
        relationship_hints=["甲对乙多了一点信任。"],
        choices=["继续追问", "先忍住不说"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert blocked_recap["quality_gate"]["ok"] is False
    assert blocked_recap["quality_gate"]["latin_token_fields"] == ["recap"]

    blocked_hint = evaluate_persisted_chapter(
        chapter_id="chapter_bad_relationship_hint_token",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=4,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.9,
        state_after=_simple_state(),
        ending_ready=False,
        chapter_title="第 1 章 · 表面平静下的暗潮",
        recap="前情提要：风声还压在窗边。",
        relationship_hints=["甲对乙多了一点 temptation。"],
        choices=["继续追问", "先忍住不说"],
        paywall_required=False,
        target_words=700,
        min_target_words=600,
    )
    assert blocked_hint["quality_gate"]["ok"] is False
    assert blocked_hint["quality_gate"]["latin_token_fields"] == ["relationship_hint_1"]


def test_content_quality_contract_gate_blocks_rolling_q03_breach_in_100_band():
    repeated_paragraph = (
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里，"
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。"
    )
    body = "\n\n".join([repeated_paragraph for _ in range(9)])
    result = evaluate_persisted_chapter(
        chapter_id="chapter_contract_q03",
        world_version_id="world_v1",
        session_id="session_1",
        body=body,
        paragraphs=body.split("\n\n"),
        dialogue_count=0,
        action_count=1,
        detail_count=1,
        character_fidelity_score=0.8,
        state_after=_simple_state(35),
        ending_ready=False,
        choices=["继续追问", "先忍住不说"],
        paywall_required=False,
        target_words=2000,
        min_target_words=1800,
        chapter_index=35,
        target_chapters=100,
        rolling_quality_window=[
            {
                "chapter_index": 34,
                "decision": "rewrite",
                "issue_codes": ["Q03"],
                "repetition_score": 0.24,
                "exposition_ratio": 0.3,
                "concrete_detail_density": 0.05,
                "dialogue_plus_action_ratio": 0.45,
                "hook_quality": 0.9,
                "scene_function": "truth_trial",
                "chapter_task_id": "task_prev",
            }
        ],
        enforcement_scope="author_work_generation",
    )
    gate = result["quality_gate"]
    assert gate["ok"] is False
    assert "repetition_score_cap" in gate["failed_checks"]
    assert "rolling_window_repeat_breach" in gate["failed_checks"]
    assert gate["enforced_decision"] == "block"
    assert gate["primary_asset_target"]["asset_type"] == "scene_blueprint"
    assert gate["window_breach_kind"] in {"repetition_score_cap", "rolling_window_repeat_breach"}
    assert gate["enforcement_scope"] == "author_work_generation"


def test_content_quality_contract_gate_blocks_q09_before_late_window_ending():
    good_body = "\n\n".join(
        [
            "旧站台的风把灯影吹得一格格晃开，沈砚没有立刻接话，只把录音带更稳地压在掌心里。",
            "她站在检票口边，没有替他退路，只问了一句更难回答的话，让场面一下子更紧。",
            "远处列车灯掠过积水，细小回声从铁轨深处顶回来，像把后面的代价也提前带到了眼前。",
            "沈砚知道这一次再装作没发生，下一次会被追上的不只是旧案，还有他们两个人没认下的话。",
            "他抬眼看她，终于把那句最难听的部分送出来，可真正重的，是这句说完以后还要不要继续往前。",
            "她没有说原谅，只把那卷录音带推回他手边，让选择和真相都一起停在两个人中间。",
            "风声、铁锈和脚步声没有停，反而把下一步该承担的那层压力照得更清。",
            "这一章没有给出结局，只把更大的追问推到了下一次开口之前。"
        ]
    )
    result = evaluate_persisted_chapter(
        chapter_id="chapter_contract_q09",
        world_version_id="world_v1",
        session_id="session_1",
        body=good_body,
        paragraphs=good_body.split("\n\n"),
        dialogue_count=3,
        action_count=6,
        detail_count=6,
        character_fidelity_score=0.85,
        state_after=_simple_state(40),
        ending_ready=True,
        choices=["继续追问", "先保住她"],
        paywall_required=False,
        target_words=2000,
        min_target_words=1800,
        chapter_index=40,
        target_chapters=100,
        enforcement_scope="reader_session_generation",
    )
    gate = result["quality_gate"]
    assert gate["ok"] is False
    assert "premature_terminal_forbidden" in gate["failed_checks"]
    assert gate["primary_issue_group"] == "Q09"
    assert gate["enforced_decision"] == "block"
    assert gate["primary_asset_target"]["asset_type"] == "chapter_task"


def test_draft_detail_builds_content_quality_repair_workbench_for_tide_archive_windows(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "tide_archive_repair_workbench.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)

    pack = registry.get_published_world("tide_archive_memory_debt")["worldpack"]
    draft = authoring.save_draft(pack)
    detail = authoring.get_draft(draft["world_version_id"])
    worldpack = detail["worldpack"]
    early_scene = worldpack["scene_blueprints"][0]
    mid_scene = next(item for item in worldpack["scene_blueprints"] if item["scene_id"] == "submerged_return")
    late_arc = worldpack["arc_plans"][-1]
    late_task = late_arc["chapter_tasks"][0]
    late_volume_id = late_arc["volume_id"]

    chapter_heatmap = [
        {
            "chapter_index": 2,
            "chapter_title": "第2章",
            "decision": "rewrite",
            "severity": "watch",
            "overall_score": 0.79,
            "issue_count": 2,
            "issue_codes": ["Q03", "Q04"],
            "scene_function": early_scene["scene_function"],
            "scene_id": early_scene["scene_id"],
            "chapter_task_id": worldpack["arc_plans"][0]["chapter_tasks"][0]["chapter_task_id"],
            "arc_id": worldpack["arc_plans"][0]["arc_id"],
            "volume_id": worldpack["arc_plans"][0]["volume_id"],
            "related_character_ids": list(early_scene["required_roles"]),
            "related_characters": list(early_scene["required_roles"]),
        },
        {
            "chapter_index": 35,
            "chapter_title": "第35章",
            "decision": "rewrite",
            "severity": "watch",
            "overall_score": 0.76,
            "issue_count": 2,
            "issue_codes": ["Q03", "Q04"],
            "scene_function": mid_scene["scene_function"],
            "scene_id": mid_scene["scene_id"],
            "chapter_task_id": worldpack["arc_plans"][5]["chapter_tasks"][0]["chapter_task_id"],
            "arc_id": worldpack["arc_plans"][5]["arc_id"],
            "volume_id": worldpack["arc_plans"][5]["volume_id"],
            "related_character_ids": list(mid_scene["required_roles"]),
            "related_characters": list(mid_scene["required_roles"]),
        },
        {
            "chapter_index": 85,
            "chapter_title": "第85章",
            "decision": "rewrite",
            "severity": "watch",
            "overall_score": 0.74,
            "issue_count": 1,
            "issue_codes": ["Q09"],
            "scene_function": "truth_trial",
            "scene_id": "",
            "chapter_task_id": late_task["chapter_task_id"],
            "arc_id": late_arc["arc_id"],
            "volume_id": late_volume_id,
            "related_character_ids": ["wen_xi", "gu_chenzhou"],
            "related_characters": ["闻汐", "顾沉舟"],
        },
    ]
    version = repository.get_world_version(draft["world_version_id"])
    version.simulation_report_json = {
        "chapter_budget": 100,
        "longform_plan_snapshot": {
            "series_plan": worldpack["series_plan"],
            "volume_plans": worldpack["volume_plans"],
            "arc_plans": worldpack["arc_plans"],
            "chapter_budget_policy": worldpack["chapter_budget_policy"],
        },
        "content_quality_contract_window_metrics": {
            "enabled": True,
            "early_window_q03_q04_share": 0.8,
            "mid_window_repeat_breach_rate": 0.7,
            "mid_window_exposition_breach_rate": 0.66,
            "late_window_q09_breach_rate": 0.4,
            "thresholds": {
                "early_window_q03_q04_share_max": 0.45,
                "mid_window_repeat_breach_rate_max": 0.30,
                "mid_window_exposition_breach_rate_max": 0.30,
                "late_window_q09_breach_rate_max": 0.08,
            },
            "contract_failed_chapters": [
                {"chapter_id": "chapter_2", "chapter_index": 2, "failed_checks": ["repetition_score_cap", "exposition_ratio_cap"], "decision": "rewrite"},
                {"chapter_id": "chapter_35", "chapter_index": 35, "failed_checks": ["repetition_score_cap", "exposition_ratio_cap"], "decision": "rewrite"},
                {"chapter_id": "chapter_85", "chapter_index": 85, "failed_checks": ["q09_pre_end", "continuation_pressure_floor"], "decision": "rewrite"},
            ],
        },
        "creative_cockpit": {
            "chapter_heatmap": {
                "chapters": chapter_heatmap,
                "issue_priority_groups": authoring._build_issue_priority_groups(chapter_heatmap),
            }
        },
        "chapter_evaluations": [],
    }
    repository.save_world_version(version, publish=False)

    refreshed = authoring.get_draft(draft["world_version_id"])
    workbench = refreshed["content_quality_repair_workbench"]
    campaigns = {(item["window_label"], item["issue_code"]): item for item in workbench["campaigns"]}

    assert workbench["available"] is True
    assert refreshed["hard_constraint_status"] == "blocked"
    assert refreshed["blocking_dimension"] == "Q09"
    assert refreshed["window_breach_kind"] == "late_window_q09_breach_rate"
    assert refreshed["ready_for_validation"] is False
    assert workbench["default_campaign"]["window_label"] == "late"
    assert workbench["default_campaign"]["issue_code"] == "Q09"
    assert workbench["default_campaign"]["primary_asset_type"] == "chapter_task"
    assert ("early", "Q03") in campaigns
    assert ("early", "Q04") in campaigns
    assert ("mid", "Q03") in campaigns
    assert ("mid", "Q04") in campaigns
    assert ("late", "Q09") in campaigns
    assert [item["asset_type"] for item in campaigns[("early", "Q03")]["secondary_asset_targets"]] == [
        "scene_realization_contracts",
        "emotion_action_policies",
    ]
    assert [item["asset_type"] for item in campaigns[("early", "Q04")]["secondary_asset_targets"]] == [
        "scene_realization_contracts",
        "emotion_action_policies",
    ]
    assert campaigns[("mid", "Q03")]["secondary_asset_targets"][0]["target_label"] == "default::karma_ripening"
    early_q03_paths = [item["path"] for item in campaigns[("early", "Q03")]["suggested_field_edits"]]
    early_q04_paths = [item["path"] for item in campaigns[("early", "Q04")]["suggested_field_edits"]]
    mid_q03_paths = [item["path"] for item in campaigns[("mid", "Q03")]["suggested_field_edits"]]
    assert any(path.startswith('scene_realization_contracts["default"]') for path in early_q03_paths)
    assert any(path.startswith('emotion_action_policies["default"]') for path in early_q03_paths)
    assert any(path.startswith('scene_realization_contracts["default"]') for path in early_q04_paths)
    assert any(path.startswith('emotion_action_policies["default"]') for path in early_q04_paths)
    assert any(path.startswith('scene_realization_contracts["default"]') for path in mid_q03_paths)
    assert campaigns[("early", "Q03")]["strategy_bundle_id"] == "q03_q04_scene_dialogue_cadence_task_coupling"
    assert campaigns[("mid", "Q04")]["strategy_bundle"]["strategy_bundle_label"] == "Scene + Dialogue + Cadence + Task Coupling"
    assert campaigns[("early", "Q03")]["strategy_bundle"]["execution_protocol_enabled"] is True
    assert campaigns[("early", "Q03")]["strategy_bundle"]["bundle_step_planning"][0]["apply_order"] == 1
    assert campaigns[("early", "Q03")]["strategy_bundle"]["rerun_attribution"]["rerun_scope"] == "full_100_rerun"
    assert campaigns[("early", "Q03")]["strategy_bundle"]["stop_condition"]["rule_id"] == "upgrade_to_planner_or_pack_contract_if_two_reruns_flat"
    assert campaigns[("late", "Q09")]["primary_asset_target"]["chapter_task_id"] == late_task["chapter_task_id"]
    assert campaigns[("late", "Q09")]["repair_loop_context"]["window_label"] == "late"
    assert any(
        edit["path"].endswith(".quality_contract.continuation_pressure_required")
        for edit in campaigns[("late", "Q09")]["suggested_field_edits"]
    )


def test_repair_workbench_creates_preventive_q03_campaign_from_quality_pass_burden(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "preventive_q03_workbench.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)

    worldpack = copy.deepcopy(registry.get_published_world("tide_archive_memory_debt")["worldpack"])
    simulation_report = {
        "chapter_budget": 6,
        "completed_chapters": 6,
        "latest_decision": "pass",
        "evaluation_summary": {"pass_rate": 1.0, "rewrite_rate": 0.0, "block_rate": 0.0},
        "content_quality_contract_window_metrics": {
            "enabled": True,
            "thresholds": {},
            "contract_failed_chapters": [],
        },
        "longform_plan_snapshot": {"series_plan": {"total_chapter_target": 100}},
        "chapter_trace": [
            {
                "chapter_id": "chapter_1",
                "chapter_title": "第1章",
                "scene_function": "false_peace",
                "quality_pass_applied": True,
                "quality_pass_actions": ["q03_final_repetition_replace:4", "q03_bundle_target_replace:6"],
            }
        ],
        "chapter_evaluations": [
            {
                "chapter_id": "chapter_1",
                "decision": {"decision": "pass"},
                "scores": {"overall_score": 0.86, "pacing": 0.8, "hook_quality": 0.8, "scene_density": 0.8},
                "issues": [],
                "hard_validator_results": {
                    "lint_metrics": {
                        "repetition_score": 0.15,
                        "exposition_ratio": 0.2,
                        "dialogue_plus_action_ratio": 0.62,
                        "concrete_detail_density": 0.5,
                    }
                },
            }
        ],
    }

    workbench = authoring._build_content_quality_repair_workbench(worldpack, simulation_report)

    assert workbench["available"] is True
    campaign = workbench["default_campaign"]
    assert campaign["issue_code"] == "Q03"
    assert campaign["breach_kind"] == "quality_pass_q03_repair_burden"
    assert campaign["strategy_bundle"]["execution_protocol_enabled"] is True
    assert campaign["repair_loop_context"]["preventive_quality_pass_campaign"] is True
    assert campaign["repair_loop_context"]["baseline_quality_pass_q03_action_count"] == 2


def test_strategy_bundle_executor_records_step_receipt_and_result_attribution(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "strategy_bundle_executor.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    seeded = _seed_tide_archive_strategy_bundle_draft(authoring, repository)
    world_version_id = seeded["draft"]["world_version_id"]
    baseline_report = copy.deepcopy(seeded["baseline_report"])

    def fake_rerun(world_version_id_arg: str, **_: object) -> dict[str, object]:
        assert world_version_id_arg == world_version_id
        rerun_report = copy.deepcopy(baseline_report)
        rerun_report["evaluation_summary"]["avg_repetition_score"] = 0.211
        rerun_report["evaluation_summary"]["dialogue_ratio"] = 0.43
        rerun_report["content_quality_contract_window_metrics"]["early_window_q03_q04_share"] = 0.42
        rerun_report["content_quality_contract_window_metrics"]["mid_window_repeat_breach_rate"] = 0.28
        rerun_report["content_quality_contract_window_metrics"]["mid_window_exposition_breach_rate"] = 0.31
        rerun_report["latest_repair_loop_outcome"] = {
            "issue_code": "Q03",
            "window_label": "early",
            "window_breach_kind": "early_window_q03_q04_share",
            "baseline_window_issue_count": 1,
            "current_window_issue_count": 0,
            "severity_trend": "improved",
            "ready_for_validation": True,
        }
        version = repository.get_world_version(world_version_id_arg)
        version.simulation_report_json = copy.deepcopy(rerun_report)
        repository.save_world_version(version, publish=False)
        return rerun_report

    authoring.run_simulation_for_world_version = fake_rerun  # type: ignore[method-assign]

    updated = authoring.execute_content_quality_strategy_bundle(
        world_version_id,
        campaign_id="content_quality::early::Q03",
    )

    latest_execution = updated["latest_strategy_bundle_execution"]
    assert latest_execution["strategy_bundle_id"] == "q03_q04_scene_dialogue_cadence_task_coupling"
    assert latest_execution["step_level_apply_receipt"]
    assert latest_execution["step_level_apply_receipt"][0]["apply_order"] == 1
    assert latest_execution["step_level_apply_receipt"][0]["asset_type"] == "scene_blueprint"
    assert latest_execution["step_level_apply_receipt"][0]["status"] == "applied"
    assert latest_execution["applied_edit_count"] > 0
    assert latest_execution["result_attribution"]["overall_status"] == "improved"
    assert "early_window_q03_q04_share" in latest_execution["result_attribution"]["improved_metrics"]
    assert latest_execution["stop_decision"]["decision"] == "stop"
    assert updated["strategy_bundle_execution_history"]
    assert updated["worldpack"]["scene_blueprints"][0]["quality_contract"]["variation_axes"] == [
        "voice",
        "movement",
        "object_state",
        "information_reveal",
        "consequence",
    ]


def test_strategy_bundle_executor_escalates_after_second_flat_rerun(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "strategy_bundle_executor_escalate.db"))
    registry = FileSystemWorldRegistry()
    authoring = AuthoringService(repository, registry=registry)
    seeded = _seed_tide_archive_strategy_bundle_draft(authoring, repository)
    world_version_id = seeded["draft"]["world_version_id"]
    baseline_report = copy.deepcopy(seeded["baseline_report"])

    def flat_rerun(world_version_id_arg: str, **_: object) -> dict[str, object]:
        assert world_version_id_arg == world_version_id
        rerun_report = copy.deepcopy(baseline_report)
        rerun_report["latest_repair_loop_outcome"] = {
            "issue_code": "Q03",
            "window_label": "early",
            "window_breach_kind": "early_window_q03_q04_share",
            "baseline_window_issue_count": 1,
            "current_window_issue_count": 1,
            "severity_trend": "flat",
            "ready_for_validation": False,
        }
        version = repository.get_world_version(world_version_id_arg)
        version.simulation_report_json = copy.deepcopy(rerun_report)
        repository.save_world_version(version, publish=False)
        return rerun_report

    authoring.run_simulation_for_world_version = flat_rerun  # type: ignore[method-assign]

    first = authoring.execute_content_quality_strategy_bundle(
        world_version_id,
        campaign_id="content_quality::early::Q03",
    )
    assert first["latest_strategy_bundle_execution"]["stop_decision"]["decision"] == "continue"

    second = authoring.execute_content_quality_strategy_bundle(
        world_version_id,
        campaign_id="content_quality::early::Q03",
    )
    assert second["latest_strategy_bundle_execution"]["stop_decision"]["decision"] == "escalate"
    assert second["latest_strategy_bundle_execution"]["stop_decision"]["escalation_target"] == "planner_or_pack_contract"


def test_author_api_can_execute_strategy_bundle_and_return_receipt(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_strategy_bundle_api.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_strategy", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_strategy", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_strategy", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_strategy", "wallet_type": "studio_credits", "amount": 10},
    )

    seeded = _seed_tide_archive_strategy_bundle_draft(
        app.state.authoring_service,
        app.state.repository,
        author_id="acct_author_strategy",
    )
    world_version_id = seeded["draft"]["world_version_id"]
    baseline_report = copy.deepcopy(seeded["baseline_report"])
    starting_entitlements = client.get(
        "/v1/reader/entitlements",
        headers=author_headers,
        params={"account_id": "acct_author_strategy"},
    )
    assert starting_entitlements.status_code == 200
    starting_balance = starting_entitlements.json()["wallets"]["studio_credits"]["balance"]

    def fake_rerun(world_version_id_arg: str, **_: object) -> dict[str, object]:
        rerun_report = copy.deepcopy(baseline_report)
        rerun_report["evaluation_summary"]["avg_repetition_score"] = 0.23
        rerun_report["evaluation_summary"]["dialogue_ratio"] = 0.41
        rerun_report["content_quality_contract_window_metrics"]["early_window_q03_q04_share"] = 0.44
        rerun_report["latest_repair_loop_outcome"] = {
            "issue_code": "Q03",
            "window_label": "early",
            "window_breach_kind": "early_window_q03_q04_share",
            "baseline_window_issue_count": 1,
            "current_window_issue_count": 0,
            "severity_trend": "improved",
            "ready_for_validation": True,
        }
        version = app.state.repository.get_world_version(world_version_id_arg)
        version.simulation_report_json = copy.deepcopy(rerun_report)
        app.state.repository.save_world_version(version, publish=False)
        return rerun_report

    app.state.authoring_service.run_simulation_for_world_version = fake_rerun  # type: ignore[method-assign]

    response = client.post(
        f"/v1/author/drafts/{world_version_id}/strategy-bundles/execute",
        headers=author_headers,
        json={"campaign_id": "content_quality::early::Q03", "account_id": "acct_author_strategy"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_strategy_bundle_execution"]["campaign_id"] == "content_quality::early::Q03"
    assert payload["latest_strategy_bundle_execution"]["step_level_apply_receipt"]
    assert payload["latest_strategy_bundle_execution"]["result_attribution"]["overall_status"] == "improved"
    assert payload["strategy_bundle_execution_history"]

    entitlements = client.get(
        "/v1/reader/entitlements",
        headers=author_headers,
        params={"account_id": "acct_author_strategy"},
    )
    assert entitlements.status_code == 200
    assert entitlements.json()["wallets"]["studio_credits"]["balance"] == starting_balance - 1


def test_author_work_flow_supports_generate_edit_diagnostics_and_submit(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_flow.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_work", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_work", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_work", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_work", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
                "brief": {
                    "genre_preset": "urban_mystery",
                    "world_title": "质量长章测试",
                    "lead_name": "沈砚",
                    "counterpart_name": "林潮",
                    "core_premise": "一个在临港旧区整理遗物的年轻档案修复师，意外收到一卷属于失踪旧案的录音带。他必须在潮水、旧街改造和关系背叛之间，查清多年前被掩埋的真相。",
                    "life_theme": "真相是否值得付出关系的代价",
                    "locations": "临港旧区\n潮渠边档案仓\n停运渡口\n废弃录音棚",
                    "author_id": "acct_author_work",
                    "target_total_chapters": 24,
                    "target_total_volumes": 3,
                    "target_word_count": 48000,
                },
            "account_id": "acct_author_work",
        },
    )
    assert draft.status_code == 200
    world_version_id = draft.json()["world_version_id"]

    created_work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_work"},
    )
    assert created_work.status_code == 200
    work_id = created_work.json()["work_id"]

    generated_first = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_work"},
    )
    assert generated_first.status_code == 200
    assert generated_first.json()["chapter_count"] >= 1
    assert 1800 <= story_text_unit_count(generated_first.json()["chapters"][0]["body"]) <= 2200

    generated_next = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "next", "account_id": "acct_author_work"},
    )
    assert generated_next.status_code == 200
    assert generated_next.json()["chapter_count"] >= 2
    assert 1800 <= story_text_unit_count(generated_next.json()["chapters"][-1]["body"]) <= 2200

    chapter = client.get(
        f"/v1/author/works/{work_id}/chapters/1",
        headers=author_headers,
    )
    assert chapter.status_code == 200
    assert chapter.json()["chapter"]["body"]
    assert "chapter_task" in chapter.json()["chapter"]
    assert "latest_diagnostic_summary" in chapter.json()["chapter"]

    edited = client.post(
        f"/v1/author/works/{work_id}/chapters/1/edit",
        headers=author_headers,
        json={
            "chapter_title": "第 1 章 · 作者手改版",
            "body": chapter.json()["chapter"]["body"] + "\n\n这一次，他先确认的不只是长度，而是每一段是否真的推进了关系与真相。",
            "summary": "作者手工修订了开场，并补强了继续阅读压力。",
            "account_id": "acct_author_work",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["chapter"]["source_type"] == "manual_edit"

    diagnostics = client.post(
        f"/v1/author/works/{work_id}/diagnostics/run",
        headers=author_headers,
        json={"account_id": "acct_author_work"},
    )
    assert diagnostics.status_code == 200
    assert "evaluation_summary" in diagnostics.json()
    assert diagnostics.json()["work"]["diagnostics_summary"]["evaluation_summary"]["block_rate"] >= 0.0
    assert diagnostics.json()["work"]["diagnostics_summary"]["latest_decision"] == "pass"
    assert diagnostics.json()["work"]["status"] == "review_ready"
    chapter_lengths = [
        story_text_unit_count(item["body"])
        for item in diagnostics.json()["work"]["chapters"]
    ]
    assert all(1800 <= length <= 2200 for length in chapter_lengths)
    assert diagnostics.json()["work"]["diagnostics_summary"]["evaluation_summary"]["rewrite_rate"] == 0.0
    for chapter_payload in diagnostics.json()["work"]["chapters"]:
        issue_codes = set(chapter_payload["latest_diagnostic_summary"]["issue_codes"])
        assert "Q03" not in issue_codes
        assert "Q09" not in issue_codes

    submitted = client.post(
        f"/v1/author/works/{work_id}/submit",
        headers=author_headers,
        json={"account_id": "acct_author_work"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"


def test_author_work_can_create_parallel_universe_branch_without_overwriting_mainline(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_branching.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_branch", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_branch", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_branch", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_branch", "wallet_type": "studio_credits", "amount": 20},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "xianxia",
                "world_title": "平行宇宙分支测试",
                "lead_name": "沈照",
                "counterpart_name": "叶青烛",
                "core_premise": "验证作者作品分支能力。",
                "life_theme": "命运线分叉",
                "author_id": "acct_author_branch",
                "target_total_chapters": 12,
                "target_total_volumes": 2,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_branch",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_branch"},
    )
    work_id = work.json()["work_id"]

    first = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_branch"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "next", "account_id": "acct_author_branch"},
    )
    assert second.status_code == 200

    mainline_before = client.get(f"/v1/author/works/{work_id}", headers=author_headers).json()
    mainline_revision_before = mainline_before["current_revision"]
    chapter_one_before = client.get(
        f"/v1/author/works/{work_id}/chapters/1",
        headers=author_headers,
    ).json()["chapter"]["body"]

    branched = client.post(
        f"/v1/author/works/{work_id}/branches",
        headers=author_headers,
        json={
            "source_chapter_index": 1,
            "steering_directive": {
                "current_user_intent": "让主角从这一章之后走向另一种代价。",
                "summary": "让主角从这一章之后走向另一种代价。",
                "impacted_character_ids": ["lead", "counterpart"],
            },
            "choice_source": "先顺着诱惑往前探一步，看代价会先落到谁身上。",
            "account_id": "acct_author_branch",
        },
    )
    assert branched.status_code == 200
    branch_payload = branched.json()
    assert branch_payload["branch_kind"] == "parallel_universe"
    assert branch_payload["parent_work_id"] == work_id
    assert branch_payload["root_work_id"] == work_id
    assert branch_payload["fork_after_chapter_index"] == 1
    assert branch_payload["chapter_count"] == 1
    assert branch_payload["branch_origin_label"] == "先顺着诱惑往前探一步，看代价会先落到谁身上。"
    assert branch_payload["is_active_line"] is True
    assert any(item["branch_kind"] == "mainline" and item["is_active_line"] is False for item in branch_payload["branch_family"])
    assert any(item["work_id"] == branch_payload["work_id"] and item["is_active_line"] is True for item in branch_payload["branch_family"])

    branch_chapter_one = client.get(
        f"/v1/author/works/{branch_payload['work_id']}/chapters/1",
        headers=author_headers,
    )
    assert branch_chapter_one.status_code == 200
    assert branch_chapter_one.json()["chapter"]["body"] == chapter_one_before

    family = client.get(
        f"/v1/author/works/{branch_payload['work_id']}/branches",
        headers=author_headers,
    )
    assert family.status_code == 200
    assert len(family.json()["branch_family"]) >= 2
    assert any(item["branch_kind"] == "mainline" for item in family.json()["branch_family"])
    assert any(item["branch_kind"] == "parallel_universe" for item in family.json()["branch_family"])

    branch_next = client.post(
        f"/v1/author/works/{branch_payload['work_id']}/chapters/generate",
        headers=author_headers,
        json={"mode": "next", "account_id": "acct_author_branch"},
    )
    assert branch_next.status_code == 200
    assert branch_next.json()["chapter_count"] == 2

    activated_mainline = client.post(
        f"/v1/author/works/{work_id}/activate-line",
        headers=author_headers,
        json={"account_id": "acct_author_branch"},
    )
    assert activated_mainline.status_code == 200
    assert activated_mainline.json()["is_active_line"] is True
    assert any(item["work_id"] == work_id and item["is_active_line"] is True for item in activated_mainline.json()["branch_family"])
    assert any(item["work_id"] == branch_payload["work_id"] and item["is_active_line"] is False for item in activated_mainline.json()["branch_family"])

    mainline_after = client.get(f"/v1/author/works/{work_id}", headers=author_headers).json()
    assert mainline_after["chapter_count"] == 2
    assert mainline_after["current_revision"] == mainline_revision_before


def test_author_work_branch_discards_mainline_future_chapters_after_selected_fork_point(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_branch_future_cut.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_future", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_future", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_future", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_future", "wallet_type": "studio_credits", "amount": 40},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "xianxia",
                "world_title": "未来章节裁剪测试",
                "lead_name": "沈照",
                "counterpart_name": "叶青烛",
                "core_premise": "验证 steering 只影响未来章节。",
                "life_theme": "命运线分叉",
                "author_id": "acct_author_future",
                "target_total_chapters": 30,
                "target_total_volumes": 3,
                "target_word_count": 60000,
            },
            "account_id": "acct_author_future",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_future"},
    )
    work_id = work.json()["work_id"]

    repository = app.state.repository
    for chapter_index in range(1, 31):
        repository.save_author_work_chapter(
            {
                "work_id": work_id,
                "chapter_index": chapter_index,
                "chapter_title": f"第 {chapter_index} 章",
                "body": f"第 {chapter_index} 章正文，保持中文内容。",
                "status": "generated",
                "source_type": "generated",
                "summary": f"第 {chapter_index} 章摘要",
                "choices_json": ["继续", "停下"],
                "state_snapshot_json": _simple_state(chapter_index).to_dict(),
            }
        )
    seeded_work = repository.get_author_work(work_id)
    repository.save_author_work(
        {
            **seeded_work,
            "chapter_count": 30,
            "narrative_state_json": _simple_state(30).to_dict(),
        }
    )

    branched = client.post(
        f"/v1/author/works/{work_id}/branches",
        headers=author_headers,
        json={
            "source_chapter_index": 7,
            "steering_directive": {
                "current_user_intent": "从第七章之后让命运转向另一条路。",
                "summary": "从第七章之后让命运转向另一条路。",
                "impacted_character_ids": ["lead", "counterpart"],
            },
            "choice_source": "先看清这一剑往谁身上落。",
            "account_id": "acct_author_future",
        },
    )
    assert branched.status_code == 200
    branch_payload = branched.json()
    assert branch_payload["fork_after_chapter_index"] == 7
    assert branch_payload["chapter_count"] == 7
    assert len(branch_payload["chapters"]) == 7
    assert branch_payload["chapters"][-1]["chapter_index"] == 7

    mainline = client.get(f"/v1/author/works/{work_id}", headers=author_headers)
    assert mainline.status_code == 200
    assert mainline.json()["chapter_count"] == 30


def test_author_work_delete_removes_entire_work_family_for_owner_only(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_delete_family.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_delete", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_delete", actor_role="author", password="secret123")
    other_author_headers = _auth_headers(client, actor_id="acct_author_other", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_delete", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_delete", "wallet_type": "studio_credits", "amount": 20},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "xianxia",
                "world_title": "删除作品测试",
                "lead_name": "沈照",
                "counterpart_name": "叶青烛",
                "core_premise": "验证作者可以删除自己的作品族。",
                "life_theme": "删除后不留残影",
                "author_id": "acct_author_delete",
                "target_total_chapters": 12,
                "target_total_volumes": 2,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_delete",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_delete"},
    )
    work_id = work.json()["work_id"]

    first = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_delete"},
    )
    assert first.status_code == 200

    branch = client.post(
        f"/v1/author/works/{work_id}/branches",
        headers=author_headers,
        json={
            "source_chapter_index": 1,
            "steering_directive": {
                "current_user_intent": "从这一章后改写命运。",
                "summary": "从这一章后改写命运。",
                "impacted_character_ids": ["lead", "counterpart"],
            },
            "choice_source": "先把真相压后一步。",
            "account_id": "acct_author_delete",
        },
    )
    assert branch.status_code == 200
    branch_work_id = branch.json()["work_id"]

    forbidden = client.delete(
        f"/v1/author/works/{work_id}",
        headers=other_author_headers,
    )
    assert forbidden.status_code == 403

    deleted = client.delete(
        f"/v1/author/works/{work_id}",
        headers=author_headers,
    )
    assert deleted.status_code == 200
    deleted_payload = deleted.json()
    assert deleted_payload["deleted_root_work_id"] == work_id
    assert deleted_payload["deleted_work_count"] == 2
    assert set(deleted_payload["deleted_work_ids"]) == {work_id, branch_work_id}
    assert deleted_payload["deleted_chapter_count"] >= 2
    assert deleted_payload["deleted_revision_count"] >= 2

    works_after = client.get(
        "/v1/author/works?account_id=acct_author_delete",
        headers=author_headers,
    )
    assert works_after.status_code == 200
    assert works_after.json()["works"] == []

    repository = app.state.repository
    for deleted_work_id in deleted_payload["deleted_work_ids"]:
        try:
            repository.get_author_work(deleted_work_id)
            assert False, f"expected deleted work to be gone: {deleted_work_id}"
        except KeyError:
            pass
        assert repository.list_author_work_chapters(work_id=deleted_work_id) == []
        assert repository.list_author_work_revisions(work_id=deleted_work_id) == []


def test_author_work_quality_gate_blocks_short_generation_and_manual_edit(tmp_path: Path, monkeypatch):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_quality_gate.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_guard", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_guard", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_guard", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_guard", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "章节硬约束测试",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "短章不能入库。",
                "life_theme": "质量先于入库",
                "author_id": "acct_author_guard",
                "target_total_chapters": 12,
                "target_total_volumes": 2,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_guard",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_guard"},
    )
    work_id = work.json()["work_id"]

    import src.narrativeos.services.author_work as author_work_module

    original_plan_next_turn = author_work_module.plan_next_turn

    def short_plan_next_turn(*args, **kwargs):
        result = original_plan_next_turn(*args, **kwargs)
        result["reader_view"]["body"] = "他停了一下。\\n\\n“先别说。”"
        result["reader_view"]["chapter_title"] = "第 1 章 · 过短短章"
        return result

    monkeypatch.setattr(author_work_module, "plan_next_turn", short_plan_next_turn)
    blocked_generate = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_guard"},
    )
    assert blocked_generate.status_code == 400
    assert blocked_generate.json()["detail"]["code"] == "chapter_quality_guard_failed"
    assert blocked_generate.json()["detail"]["quality_gate"]["required_text_units"] >= 1800

    work_detail = client.get(f"/v1/author/works/{work_id}", headers=author_headers)
    assert work_detail.status_code == 200
    assert work_detail.json()["chapter_count"] == 0
    assert "content_quality_repair_workbench" in work_detail.json()
    assert all(rev["revision_type"] != "generation" for rev in work_detail.json()["revisions"][:1])
    assert any(rev["revision_type"] == "quality_guard_blocked" for rev in work_detail.json()["revisions"])

    monkeypatch.setattr(author_work_module, "plan_next_turn", original_plan_next_turn)
    generated = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_guard"},
    )
    assert generated.status_code == 200

    chapter_before = client.get(
        f"/v1/author/works/{work_id}/chapters/1",
        headers=author_headers,
    ).json()["chapter"]["body"]
    work_before_edit = client.get(f"/v1/author/works/{work_id}", headers=author_headers).json()["current_revision"]

    blocked_edit = client.post(
        f"/v1/author/works/{work_id}/chapters/1/edit",
        headers=author_headers,
        json={
            "chapter_title": "第 1 章 · 过短手工稿",
            "body": "他看着她。\\n\\n“算了。”",
            "summary": "太短了。",
            "account_id": "acct_author_guard",
        },
    )
    assert blocked_edit.status_code == 400
    assert blocked_edit.json()["detail"]["code"] == "chapter_quality_guard_failed"

    chapter_after = client.get(
        f"/v1/author/works/{work_id}/chapters/1",
        headers=author_headers,
    ).json()["chapter"]["body"]
    work_after = client.get(f"/v1/author/works/{work_id}", headers=author_headers).json()
    assert chapter_after == chapter_before
    assert work_after["current_revision"] == work_before_edit
    assert any(rev["revision_type"] == "quality_guard_blocked" for rev in work_after["revisions"])


def test_author_work_quality_gate_blocks_disallowed_latin_tokens_in_generation_and_manual_edit(tmp_path: Path, monkeypatch):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_latin_guard.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_latin", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_latin", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_latin", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_latin", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "英文硬约束测试",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "reader 可见文本不允许出现普通英文。",
                "life_theme": "中文可见面必须稳定",
                "author_id": "acct_author_latin",
                "target_total_chapters": 12,
                "target_total_volumes": 2,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_latin",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_latin"},
    )
    work_id = work.json()["work_id"]

    import src.narrativeos.services.author_work as author_work_module

    original_plan_next_turn = author_work_module.plan_next_turn

    def latin_plan_next_turn(*args, **kwargs):
        result = original_plan_next_turn(*args, **kwargs)
        result["reader_view"]["body"] = f"{result['reader_view']['body']}\n\n她把 obedience 压回沉默里，却没法把这一步重新说轻。"
        result["reader_view"]["recap"] = "前情提要：她把 temptation 压回了沉默里。"
        result["reader_view"]["relationship_hints"] = ["甲对乙多了一点 temptation。"]
        return result

    monkeypatch.setattr(author_work_module, "plan_next_turn", latin_plan_next_turn)
    generated_with_sanitization = client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_latin"},
    )
    assert generated_with_sanitization.status_code == 200
    chapter_generated = app.state.repository.get_author_work_chapter(work_id=work_id, chapter_index=1)
    assert "obedience" not in chapter_generated["body"]

    monkeypatch.setattr(author_work_module, "plan_next_turn", original_plan_next_turn)
    chapter_before = client.get(
        f"/v1/author/works/{work_id}/chapters/1",
        headers=author_headers,
    ).json()["chapter"]["body"]

    blocked_edit = client.post(
        f"/v1/author/works/{work_id}/chapters/1/edit",
        headers=author_headers,
        json={
            "chapter_title": "第 1 章 · temptation 手工稿",
            "body": chapter_before,
            "summary": "标题里不应再混入英文。",
            "account_id": "acct_author_latin",
        },
    )
    assert blocked_edit.status_code == 400
    assert blocked_edit.json()["detail"]["code"] == "chapter_quality_guard_failed"
    assert blocked_edit.json()["detail"]["quality_gate"]["latin_token_fields"] == ["chapter_title"]


def test_draft_from_brief_preserves_explicit_user_values(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_brief_values.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_brief", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_brief", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_brief", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_brief", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "雾港回潮测试",
                "lead_name": "沈砚",
                "counterpart_name": "林潮",
                "supporting_name": "许织",
                "core_premise": "作者输入的 brief 必须保留下来，不能被 preset 覆盖。",
                "life_theme": "真相是否值得付出关系的代价",
                "locations": "临港旧区\n潮渠边档案仓\n停运渡口",
                "author_id": "acct_author_brief",
                "account_id": "acct_author_brief",
            },
        },
    )
    assert draft.status_code == 200
    world_version_id = draft.json()["world_version_id"]
    detail = client.get(f"/v1/author/drafts/{world_version_id}", headers=author_headers)
    assert detail.status_code == 200
    worldpack = detail.json()["worldpack"]
    lead = next(item for item in worldpack["characters"] if item["character_id"] == "lead")
    counterpart = next(item for item in worldpack["characters"] if item["character_id"] == "counterpart")

    assert worldpack["title"] == "雾港回潮测试"
    assert worldpack["world_bible"]["premise"] == "作者输入的 brief 必须保留下来，不能被 preset 覆盖。"
    assert lead["display_name"] == "沈砚"
    assert counterpart["display_name"] == "林潮"
    assert lead["destiny_contract"]["life_theme"] == "真相是否值得付出关系的代价"
    assert worldpack["metadata"]["author_brief"]["world_title"] == "雾港回潮测试"


def test_author_simulate_accepts_optional_steering_payload_and_exposes_creative_cockpit(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_simulate_steering.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_steering", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_steering", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_steering", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_steering", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "synthetic",
                "world_title": "作者 Steering 驾驶舱测试",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "验证 author simulate 可接受 steering payload。",
                "life_theme": "作者可以直接扭转下一轮剧情方向",
                "author_id": "acct_author_steering",
                "target_total_chapters": 12,
                "target_total_volumes": 3,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_steering",
        },
    )
    assert draft.status_code == 200
    world_version_id = draft.json()["world_version_id"]
    entitlements_before = client.get(
        "/v1/reader/entitlements",
        headers=author_headers,
        params={"account_id": "acct_author_steering"},
    )
    assert entitlements_before.status_code == 200
    starting_balance = entitlements_before.json()["wallets"]["studio_credits"]["balance"]

    legacy = client.post(
        f"/v1/author/drafts/{world_version_id}/simulate",
        headers=author_headers,
    )
    assert legacy.status_code == 200
    assert "creative_cockpit" in legacy.json()

    steered = client.post(
        f"/v1/author/drafts/{world_version_id}/simulate",
        headers=author_headers,
        json={
            "account_id": "acct_author_steering",
            "interactive_scenarios": [
                {
                    "scenario_kind": "memory_steer",
                    "label": "旧誓突然回潮",
                    "steering_directive": {
                        "current_user_intent": "让主角在下一章因为旧誓而收住真话。",
                        "summary": "让主角在下一章因为旧誓而收住真话。",
                        "memory_patch_note": "主角突然想起旧誓的细节，因而不敢一次说尽。",
                        "impacted_character_ids": ["lead"],
                    },
                }
            ],
        },
    )
    assert steered.status_code == 200
    steered_payload = steered.json()
    assert steered_payload["steering_checkpoints"]
    assert steered_payload["creative_cockpit"]["available"] is True
    assert steered_payload["creative_cockpit"]["steering_timeline"]["checkpoint_count"] == 1
    assert "relationship_network" in steered_payload["creative_cockpit"]
    assert "scene_id" in steered_payload["creative_cockpit"]["chapter_heatmap"]["chapters"][0]
    assert "chapter_task_id" in steered_payload["creative_cockpit"]["chapter_heatmap"]["chapters"][0]
    assert "issue_priority_groups" in steered_payload["creative_cockpit"]["chapter_heatmap"]

    detail = client.get(f"/v1/author/drafts/{world_version_id}", headers=author_headers)
    assert detail.status_code == 200
    assert detail.json()["creative_cockpit"]["steering_timeline"]["checkpoint_count"] == 1

    repair_detail = client.get(f"/v1/author/drafts/{world_version_id}", headers=author_headers)
    assert repair_detail.status_code == 200
    worldpack = repair_detail.json()["worldpack"]
    worldpack["scene_blueprints"][0]["beats_template"].append("让环境细节承担更多压迫感。")
    saved = client.put(
        f"/v1/author/drafts/{world_version_id}",
        headers=author_headers,
        json={
            "worldpack": worldpack,
            "account_id": "acct_author_steering",
            "change_context": {
                "source": "scene_editor",
                "label": "保存场景蓝图",
                "repair_loop_context": {
                    "issue_code": "Q05",
                    "issue_label": "lack of scene detail",
                    "asset_type": "scene_blueprint",
                    "asset_label": "场景蓝图",
                    "target_label": worldpack["scene_blueprints"][0]["scene_id"],
                    "validation_panel": "compare",
                    "validation_panel_label": "Compare",
                    "validation_reason": "改完 scene 后回 Compare 看前后章节差异。",
                    "scene_id": worldpack["scene_blueprints"][0]["scene_id"],
                    "scene_function": worldpack["scene_blueprints"][0]["scene_function"],
                    "chapter_index": 1,
                    "chapter_title": "第1章",
                    "targeted_chapters": [{"chapter_index": 1, "chapter_title": "第1章"}],
                },
            },
        },
    )
    assert saved.status_code == 200
    assert saved.json()["revision_history"][-1]["repair_loop_context"]["issue_code"] == "Q05"

    rerun = client.post(
        f"/v1/author/drafts/{world_version_id}/simulate",
        headers=author_headers,
    )
    assert rerun.status_code == 200
    assert "latest_repair_loop_outcome" in rerun.json()

    repaired_detail = client.get(f"/v1/author/drafts/{world_version_id}", headers=author_headers)
    assert repaired_detail.status_code == 200
    assert "latest_repair_loop_outcome" in repaired_detail.json()
    assert repaired_detail.json()["repair_loop_history"]

    entitlements = client.get(
        "/v1/reader/entitlements",
        headers=author_headers,
        params={"account_id": "acct_author_steering"},
    )
    assert entitlements.status_code == 200
    assert entitlements.json()["wallets"]["studio_credits"]["balance"] == starting_balance - 3


def test_author_simulate_summary_only_returns_lightweight_remote_payload(tmp_path: Path, monkeypatch):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_simulate_summary.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_summary", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_summary", actor_role="author", password="secret123")
    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_summary", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_summary", "wallet_type": "studio_credits", "amount": 10},
    )
    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "synthetic",
                "world_title": "作者远端轻量模拟测试",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "验证远端 smoke 可使用轻量响应。",
                "life_theme": "轻量响应",
                "author_id": "acct_author_summary",
                "target_total_chapters": 12,
                "target_total_volumes": 3,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_summary",
        },
    )
    assert draft.status_code == 200
    world_version_id = draft.json()["world_version_id"]

    simulation_called = {"called": False}

    def _fail_if_full_simulation_runs(*_args, **_kwargs):
        simulation_called["called"] = True
        raise AssertionError("summary_only must not run full Author simulation")

    monkeypatch.setattr(app.state.authoring_service, "run_simulation_for_world_version", _fail_if_full_simulation_runs)
    summary_only = client.post(
        f"/v1/author/drafts/{world_version_id}/simulate?summary_only=true",
        headers=author_headers,
    )
    assert summary_only.status_code == 200
    payload = summary_only.json()
    assert payload["summary_only"] is True
    assert payload["simulation_executed"] is False
    assert payload["serverless_safe"] is True
    assert payload["status"] == "simulated"
    assert payload["world_version_id"] == world_version_id
    assert payload["issue_count"] == 0
    assert payload["access"]["allowed"] is True
    assert payload["simulation_summary"]["available"] is False
    assert "creative_cockpit" not in payload
    assert simulation_called["called"] is False


def test_reviewer_can_open_author_work_from_review_hub(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_review_hub.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_work", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_work", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_work", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_work", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "审阅对象测试",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "作品稿审阅对象测试。",
                "life_theme": "审阅对象应为正文",
                "author_id": "acct_author_work",
                "target_total_chapters": 24,
                "target_total_volumes": 3,
                "target_word_count": 48000,
            },
            "account_id": "acct_author_work",
        },
    )
    world_version_id = draft.json()["world_version_id"]

    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_work"},
    )
    work_id = work.json()["work_id"]
    client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_work"},
    )
    client.post(
        f"/v1/author/works/{work_id}/diagnostics/run",
        headers=author_headers,
        json={"account_id": "acct_author_work"},
    )
    client.post(
        f"/v1/author/works/{work_id}/submit",
        headers=author_headers,
        json={"account_id": "acct_author_work"},
    )

    hub = client.get("/v1/ops/review-hub?queue=content_release", headers=reviewer_headers)
    assert hub.status_code == 200
    assert not any(
        entry["source_type"] == "world_version_review" and entry["world_version_id"] == world_version_id
        for entry in hub.json()["items"]
    )
    item = next(entry for entry in hub.json()["items"] if entry["source_type"] == "author_work")
    work_detail = client.get(f"/v1/ops/review-items/{item['review_item_id']}/work", headers=reviewer_headers)
    assert work_detail.status_code == 200
    assert work_detail.json()["work"]["work_id"] == work_id
    assert work_detail.json()["work"]["chapters"]
    assert work_detail.json()["work"]["diagnostics_summary_json"]["evaluation_summary"]["block_rate"] >= 0.0


def test_author_draft_list_is_scoped_to_authenticated_account(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_draft_scope.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_scope", actor_role="reviewer", password="secret123")
    first_author_headers = _auth_headers(client, actor_id="acct_author_scope_one", actor_role="author", password="secret123")
    second_author_headers = _auth_headers(client, actor_id="acct_author_scope_two", actor_role="author", password="secret123")

    for account_id in ("acct_author_scope_one", "acct_author_scope_two"):
        client.post(
            "/v1/ops/subscriptions/grant",
            headers=reviewer_headers,
            json={"account_id": account_id, "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
        )
        client.post(
            "/v1/ops/wallets/grant",
            headers=reviewer_headers,
            json={"account_id": account_id, "wallet_type": "studio_credits", "amount": 10},
        )

    first_draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=first_author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "scope_one_world",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "账号一的草稿。",
                "life_theme": "scope one",
                "author_id": "acct_author_scope_one",
                "target_total_chapters": 24,
                "target_total_volumes": 3,
                "target_word_count": 48000,
            },
            "account_id": "acct_author_scope_one",
        },
    )
    second_draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=second_author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "scope_two_world",
                "lead_name": "丙",
                "counterpart_name": "丁",
                "core_premise": "账号二的草稿。",
                "life_theme": "scope two",
                "author_id": "acct_author_scope_two",
                "target_total_chapters": 24,
                "target_total_volumes": 3,
                "target_word_count": 48000,
            },
            "account_id": "acct_author_scope_two",
        },
    )
    assert first_draft.status_code == 200
    assert second_draft.status_code == 200

    first_list = client.get("/v1/author/drafts", headers=first_author_headers)
    second_list = client.get("/v1/author/drafts", headers=second_author_headers)

    assert first_list.status_code == 200
    assert second_list.status_code == 200
    assert [item["author_id"] for item in first_list.json()["drafts"]] == ["acct_author_scope_one"]
    assert [item["author_id"] for item in second_list.json()["drafts"]] == ["acct_author_scope_two"]


def test_author_work_requires_identity_match_for_read_and_write(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_authz.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_work", actor_role="reviewer", password="secret123")
    owner_headers = _auth_headers(client, actor_id="acct_author_owner", actor_role="author", password="secret123")
    intruder_headers = _auth_headers(client, actor_id="acct_author_intruder", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_owner", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_owner", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=owner_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "权限隔离作品",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "只有本人可读写作品稿。",
                "life_theme": "权限隔离",
                "author_id": "acct_author_owner",
                "target_total_chapters": 12,
                "target_total_volumes": 2,
                "target_word_count": 24000,
            },
            "account_id": "acct_author_owner",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=owner_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_owner"},
    )
    work_id = work.json()["work_id"]
    client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=owner_headers,
        json={"mode": "first", "account_id": "acct_author_owner"},
    )

    intruder_read = client.get(f"/v1/author/works/{work_id}", headers=intruder_headers)
    assert intruder_read.status_code == 403
    assert intruder_read.json()["detail"]["reason"] == "author_work_account_mismatch"

    intruder_edit = client.post(
        f"/v1/author/works/{work_id}/chapters/1/edit",
        headers=intruder_headers,
        json={"chapter_title": "越权", "body": "越权正文", "account_id": "acct_author_intruder"},
    )
    assert intruder_edit.status_code == 403
    assert intruder_edit.json()["detail"]["reason"] == "author_work_account_mismatch"


def test_author_work_diagnostics_keep_decision_and_status_in_sync(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_work_decision_sync.db")))
    client = TestClient(app)

    reviewer_headers = _auth_headers(client, actor_id="ops_reviewer_sync", actor_role="reviewer", password="secret123")
    author_headers = _auth_headers(client, actor_id="acct_author_sync", actor_role="author", password="secret123")

    client.post(
        "/v1/ops/subscriptions/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_sync", "tier_id": "creator_pass", "provider": "ops_manual", "status": "active"},
    )
    client.post(
        "/v1/ops/wallets/grant",
        headers=reviewer_headers,
        json={"account_id": "acct_author_sync", "wallet_type": "studio_credits", "amount": 10},
    )

    draft = client.post(
        "/v1/author/drafts/from-brief",
        headers=author_headers,
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "语义同步作品",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "诊断语义必须一致。",
                "life_theme": "语义一致",
                "author_id": "acct_author_sync",
                "target_total_chapters": 24,
                "target_total_volumes": 3,
                "target_word_count": 48000,
            },
            "account_id": "acct_author_sync",
        },
    )
    world_version_id = draft.json()["world_version_id"]
    work = client.post(
        "/v1/author/works",
        headers=author_headers,
        json={"world_version_id": world_version_id, "account_id": "acct_author_sync"},
    )
    work_id = work.json()["work_id"]
    client.post(
        f"/v1/author/works/{work_id}/chapters/generate",
        headers=author_headers,
        json={"mode": "first", "account_id": "acct_author_sync"},
    )
    client.post(
        f"/v1/author/works/{work_id}/chapters/1/edit",
        headers=author_headers,
        json={
            "chapter_title": "第 1 章 · 短章重写",
            "body": "短。短。短。",
            "summary": "故意制造需要重写的正文。",
            "account_id": "acct_author_sync",
        },
    )
    diagnostics = client.post(
        f"/v1/author/works/{work_id}/diagnostics/run",
        headers=author_headers,
        json={"account_id": "acct_author_sync"},
    )
    assert diagnostics.status_code == 200
    assert diagnostics.json()["work"]["diagnostics_summary"]["latest_decision"] == "rewrite"
    assert diagnostics.json()["work"]["status"] == "needs_changes"
