from pathlib import Path

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.eval.learned_baseline import train_learned_evaluator_baseline
from src.narrativeos.eval.learned_inference import LearnedInferenceService
from src.narrativeos.eval.learned_shadow import LearnedShadowService
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def test_reader_author_ops_endpoints_and_shell(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_api.db")))
    client = TestClient(app)
    registry = FileSystemWorldRegistry()

    shell = client.get("/app")
    assert shell.status_code == 200
    assert "Reader" in shell.text
    assert "Author" in shell.text
    assert "Ops" in shell.text
    assert "统一导航 / 升级路径" in shell.text
    assert "Sync Context" in shell.text
    assert "Follow Recommendation" in shell.text
    assert "发布 / Checklist / 回滚统一处置页" in shell.text
    assert "Refresh Release Workspace" in shell.text
    assert "根据 Brief 生成 Draft" in shell.text
    assert "当前草稿详情" in shell.text
    assert "Asset Diff" in shell.text
    assert "Version History" in shell.text
    assert "角色卡编辑" in shell.text
    assert "场景蓝图编辑" in shell.text
    assert "Membership & Wallet" in shell.text
    assert "Story Credits" in shell.text
    assert "开始 Web Checkout" in shell.text
    assert "Retry Payment" in shell.text
    assert "Renew Subscription" in shell.text
    assert "Cancel At Period End" in shell.text
    assert "当前世界" in shell.text
    assert "Learned Dashboard" in shell.text
    assert "Learned Impact" in shell.text
    assert "Learned Cadence" in shell.text
    assert "Assisted Gate Experiment" in shell.text
    assert "Assisted Rerank Experiment" in shell.text
    assert "Shadow Candidate Compare" in shell.text
    assert "Preference Capture" in shell.text
    assert "Ranking Capture" in shell.text
    assert "Evaluator Promotion Gate" in shell.text
    assert "Reranker Promotion Gate" in shell.text
    assert "会员 / 钱包 / 订阅审计" in shell.text
    assert "Billing Event ID" in shell.text
    assert "Reconcile Subscription" in shell.text
    assert "Retry Subscription" in shell.text
    assert "Replay Billing Event" in shell.text
    assert "账户详情 / 权益 / 订阅 / 钱包统一排查页" in shell.text
    assert "operator workspace summary" in shell.text
    assert "quick actions" in shell.text
    assert "Approve Evaluator" in shell.text
    assert "Revoke Evaluator" in shell.text
    assert "Approve Reranker" in shell.text
    assert "Revoke Reranker" in shell.text
    assert "Learned Data Ops" in shell.text
    assert "Human Review Coverage" in shell.text
    assert "Review Backlog" in shell.text
    assert "Pair Coverage Backlog" in shell.text
    assert "Quick Capture Review" in shell.text
    assert "Last Action Impact" in shell.text
    assert "Weak Worlds" in shell.text
    assert "Weak Issues" in shell.text
    assert "Brief Access" in shell.text
    assert "Simulate Access" in shell.text
    assert "主路径引导" in shell.text
    assert "Revision / Chapter Compare" in shell.text
    assert "评论 / 审批" in shell.text
    assert "Reviewer Inbox" in shell.text
    assert "Auth Session" in shell.text
    assert "作者登录 / Token 会话" in shell.text
    assert "Register" in shell.text
    assert "Login" in shell.text
    assert "Logout" in shell.text
    assert "Inbox Status Filter" in shell.text
    assert "Inbox Search" in shell.text
    assert "Search Inbox" in shell.text
    assert "Load More" in shell.text
    assert "Mark Visible Read" in shell.text
    assert "Archive Visible" in shell.text
    assert "Draft Watcher ID" in shell.text
    assert "Notification Preference" in shell.text
    assert "External Channel" in shell.text
    assert "账户详情" in shell.text
    assert "客服问题定位" in shell.text
    assert "Alert Center" in shell.text
    assert "主动告警与标准处置" in shell.text
    assert "Refresh Alerts" in shell.text
    assert "Acknowledge Alert" in shell.text
    assert "Resolve Alert" in shell.text
    assert "治理 Case 流" in shell.text
    assert "Owner ID" in shell.text
    assert "Due At" in shell.text
    assert "Policy Labels" in shell.text
    assert "Evidence Title" in shell.text
    assert "Evidence Preview" in shell.text
    assert "Assign Case" in shell.text
    assert "Add Evidence" in shell.text
    assert "Unified Investigation" in shell.text
    assert "施加 Restriction" in shell.text
    assert "刷新治理导出" in shell.text
    assert "选中 governance case 的 drill-down" in shell.text
    assert "Run Evaluator" in shell.text
    assert "Run Both" in shell.text
    assert "Safe Rollout" in shell.text
    assert "Schema Lifecycle" in shell.text
    assert "Data Integrity / Repair" in shell.text
    assert "Run Integrity Dry-run" in shell.text
    assert "Apply Safe Repair" in shell.text
    assert "Run Recovery Drill" in shell.text
    assert "Request Restore" in shell.text
    assert "Approve Restore" in shell.text
    assert "Revoke Restore" in shell.text
    assert "Execute Approved Restore" in shell.text
    assert "Runtime Receipts / Incident Snapshot" in shell.text
    assert "Provider Routing Policy" in shell.text
    assert "Candidate Canary" in shell.text
    assert "Renderer Canary" in shell.text
    assert "Deployment / Backup / Incident" in shell.text
    assert "Deployment Health Gate" in shell.text
    assert "Async Jobs" in shell.text
    assert "Long-running workflow queue" in shell.text
    assert "boot-time async reconciler" in shell.text
    assert "artifact retention" in shell.text
    assert "operator run history" in shell.text
    assert "Async Job Note" in shell.text
    assert "Export Handoff Bundle" in shell.text
    assert "Acknowledge Job" in shell.text
    assert "Ship Remote Artifacts" in shell.text
    assert "Escalate Handoff SLA" in shell.text
    assert "adapter config validation" in shell.text
    assert "adapter health probe" in shell.text
    assert "notification delivery receipts" in shell.text
    assert "Notification Receipt / Retry ID" in shell.text
    assert "Queue Notification Retry" in shell.text
    assert "Process Notification Retry" in shell.text
    assert "Notification Dead-letter Queue" in shell.text
    assert "Retry Outcome Dashboard" in shell.text
    assert "Retry Failed Job" in shell.text
    assert "Resume Job" in shell.text
    assert "Recover Stale Jobs" in shell.text
    assert "Enforce Retention" in shell.text
    assert "Run Cold-start Drill" in shell.text
    assert "Provider Runtime Metrics" in shell.text
    assert "完整审计轨迹" in shell.text

    worlds = client.get("/v1/library/worlds")
    assert worlds.status_code == 200
    payload = worlds.json()
    assert len(payload["worlds"]) >= 3

    reader_session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam"})
    assert reader_session.status_code == 200
    session_payload = reader_session.json()
    assert session_payload["world_version_id"]

    chapter = client.post(
        "/v1/reader/continue",
        json={"session_id": session_payload["session_id"], "freeform_intent": "我先看看这条路会怎么变。"},
    )
    assert chapter.status_code == 200
    chapter_payload = chapter.json()
    assert chapter_payload["status"] in {"ok", "payment_required"}
    if chapter_payload["status"] == "payment_required":
      assert "required_display_name" in chapter_payload["paywall"]
      assert "required_capability" in chapter_payload["paywall"]
      assert "suggested_checkout_tier" in chapter_payload["paywall"]
    prefill = client.get(f"/v1/reader/sessions/{session_payload['session_id']}/prefill")
    assert prefill.status_code == 200
    assert prefill.json()["suggested_prefill"]

    grant = client.post(
        "/v1/reader/entitlements/grant",
        json={
            "reader_id": "reader_api",
            "entitlement_type": "credits",
            "world_id": "jade_court_exam",
            "balance": 3,
        },
    )
    assert grant.status_code == 200
    entitlements = client.get("/v1/reader/entitlements", params={"reader_id": "reader_api", "world_id": "jade_court_exam"})
    assert entitlements.status_code == 200
    assert entitlements.json()["entitlements"]
    assert "status" in entitlements.json()["entitlements"][0]
    assert "reason" in entitlements.json()["entitlements"][0]
    subscription = client.get("/v1/reader/subscription", params={"account_id": "reader_api"})
    assert subscription.status_code == 200
    assert "tiers" in subscription.json()
    assert "config_version" in subscription.json()
    if subscription.json()["subscription"]:
        assert "next_action" in subscription.json()["subscription"]
    tier_ids = [item["tier_id"] for item in subscription.json()["tiers"]]
    assert tier_ids == ["play_pass", "creator_pass", "studio_pass"]
    checkout = client.post(
        "/v1/reader/checkout/start",
        json={"account_id": "reader_api", "tier_id": "play_pass", "provider": "web_stub"},
    )
    assert checkout.status_code == 200
    assert checkout.json()["checkout"]["provider"] == "web_stub"

    brief_template = client.get("/v1/author/brief-template")
    assert brief_template.status_code == 200
    assert brief_template.json()["genre_presets"]
    author_access = client.get("/v1/author/access", params={"account_id": "web_author"})
    assert author_access.status_code == 200
    assert author_access.json()["config_version"] == "entitlement_matrix_v1"
    assert "draft_from_brief" in author_access.json()["actions"]
    assert "simulate" in author_access.json()["actions"]
    assert "required_display_name" in author_access.json()["actions"]["draft_from_brief"]
    assert "suggested_checkout_tier" in author_access.json()["actions"]["simulate"]

    creator_grant = client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "web_author",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    assert creator_grant.status_code == 200

    scaffolded = client.post(
        "/v1/author/drafts/from-brief",
        json={
            "brief": {
                "genre_preset": "urban_mystery",
                "world_title": "深巷回声",
                "lead_name": "江屹",
                "counterpart_name": "周岚",
                "core_premise": "一条旧巷里，越想压住的真相越会换一种方式回来收债。",
                "life_theme": "真话是否值得承担失去",
                "locations": "旧巷\n便利店门口\n天桥下",
            }
        },
    )
    assert scaffolded.status_code == 200
    assert scaffolded.json()["world_version_id"]

    worldpack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    worldpack["version"] = "0.3.0"
    worldpack["manifest"]["author_id"] = "api_author"

    api_author_grant = client.post(
        "/v1/ops/subscriptions/grant",
        json={
            "account_id": "api_author",
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        },
    )
    assert api_author_grant.status_code == 200

    draft = client.post("/v1/author/drafts", json={"worldpack": worldpack})
    assert draft.status_code == 200
    draft_payload = draft.json()
    assert draft_payload["world_version_id"]
    draft_detail = client.get(f"/v1/author/drafts/{draft_payload['world_version_id']}")
    assert draft_detail.status_code == 200
    assert "revision_history" in draft_detail.json()
    assert "latest_diff_summary" in draft_detail.json()
    assert "diff_drilldown" in draft_detail.json()
    assert "validation_drilldown" in draft_detail.json()
    workflow = client.get(f"/v1/author/workflow?account_id=api_author&world_version_id={draft_payload['world_version_id']}")
    assert workflow.status_code == 200
    assert "stage" in workflow.json()
    assert "recommended_action" in workflow.json()
    assert "cta_actions" in workflow.json()

    simulate = client.post(f"/v1/author/drafts/{draft_payload['world_version_id']}/simulate")
    assert simulate.status_code == 200
    assert "completed_chapters" in simulate.json()
    assert "evaluation_summary" in simulate.json()
    assert "cross_pack_summary" in simulate.json()
    assert "metric_deltas" in simulate.json()
    assert "learned_evaluation_summary" in simulate.json()
    assert "learned_shadow_summary" in simulate.json()
    assert "chapter_trace" in simulate.json()
    assert "simulation_drilldown" in simulate.json()
    assert simulate.json()["simulation_drilldown"]["chapter_breakdown"]
    assert simulate.json()["simulation_drilldown"]["issue_histogram"] is not None
    assert "issue_focus_queue" in simulate.json()["simulation_drilldown"]

    updated_pack = draft_detail.json()["worldpack"]
    updated_pack["characters"][0]["display_name"] = "试改角色"
    updated = client.put(
        f"/v1/author/drafts/{draft_payload['world_version_id']}",
        json={
            "worldpack": updated_pack,
            "change_context": {"source": "character_editor", "label": "保存角色卡"},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["revision_history"][-1]["source"] == "character_editor"
    assert updated.json()["diff_drilldown"]["revisions"]
    assert updated.json()["diff_drilldown"]["recommended_next_actions"]

    updated_pack = updated.json()["worldpack"]
    style_pack = updated_pack["narrative_style_pack"]
    style_pack["tonal_lexicon"] = ["门第", "体面", "牵连"]
    style_pack["hook_templates"] = ["这层体面先撑住了，可真正会追上来的，是那句被压回去的心里话。"]
    updated_pack["dialogue_realism_policy"]["min_turns"] = 3
    updated_pack["dialogue_realism_policy"]["max_turns"] = 4
    updated_pack["dialogue_realism_policy"]["turn_pattern"] = ["speaker", "reaction", "reply", "echo"]
    default_contract_key = next(iter(updated_pack["scene_realization_contracts"]))
    updated_pack["scene_realization_contracts"][default_contract_key]["scene_hooks"] = {
        "truth_trial": ["等这场话停下来时，真正追上来的，往往是那句没说尽的话。"]
    }
    updated_style = client.put(
        f"/v1/author/drafts/{draft_payload['world_version_id']}",
        json={
            "worldpack": updated_pack,
            "change_context": {"source": "capability_editor", "label": "保存风格 / 节奏 / Hook"},
        },
    )
    assert updated_style.status_code == 200
    assert updated_style.json()["worldpack"]["dialogue_realism_policy"]["min_turns"] == 3
    assert updated_style.json()["worldpack"]["narrative_style_pack"]["hook_templates"][0].startswith("这层体面先撑住了")

    submit = client.post(f"/v1/author/drafts/{draft_payload['world_version_id']}/submit")
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"
    waiting = client.get(f"/v1/author/workflow?account_id=api_author&world_version_id={draft_payload['world_version_id']}")
    assert waiting.status_code == 200
    assert waiting.json()["stage"] == "submitted"

    validation = client.post(
        "/v1/author/drafts/validate",
        json={"worldpack": updated_style.json()["worldpack"], "account_id": "api_author"},
    )
    assert validation.status_code == 200
    assert "validation_drilldown" in validation.json()

    version = app.state.repository.get_world_version(draft_payload["world_version_id"])
    version.simulation_report_json = {
      "ok": True,
      "latest_decision": "pass",
      "evaluation_summary": {"pass_rate": 1.0, "rewrite_rate": 0.0, "block_rate": 0.0},
      "cross_pack_summary": {
        "cross_pack_pass_rate": 0.5,
        "top_failing_packs": [],
        "delta_summary": {"cross_pack_pass_rate_delta": 0.0, "regressions": [], "world_deltas": {}},
        "worlds": [],
      },
    }
    app.state.repository.save_world_version(version, publish=False)

    queue = client.get("/v1/ops/review-queue")
    assert queue.status_code == 200
    assert any(item["asset_id"] == draft_payload["world_version_id"] for item in queue.json()["reviews"])

    publish = client.post(
        f"/v1/ops/world-versions/{draft_payload['world_version_id']}/publish",
        json={"reviewer_id": "ops_tester"},
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"

    status = client.get("/v1/ops/worlds/urban_mystery_lotus_lane/status")
    assert status.status_code == 200
    assert status.json()["versions"]
    assert status.json()["recent_reviews"] is not None
    assert status.json()["publish_checklist"][0]["reason"]
    assert "owner" in status.json()["publish_checklist"][0]
    assert "evidence" in status.json()["publish_checklist"][0]
    assert "publish_checklist_summary" in status.json()
    assert "recent_reviews_drilldown" in status.json()
    assert "risk_summary" in status.json()
    assert "recent_entitlement_events" in status.json()
    assert "learned_shadow_summary" in status.json()
    history = client.get("/v1/ops/worlds/urban_mystery_lotus_lane/history")
    assert history.status_code == 200
    assert "review_history" in history.json()
    assert "rollback_history" in history.json()
    assert "rollback_drilldown" in history.json()
    assert "rollback_summary" in history.json()
    assert "review_timeline" in history.json()
    assert "review_summary" in history.json()
    assert "quality_trend" in history.json()
    assert "quality_trend_summary" in history.json()
    if history.json()["quality_trend"]:
        assert "delta_vs_previous" in history.json()["quality_trend"][0]
    release_workspace = client.get("/v1/ops/worlds/urban_mystery_lotus_lane/release-workspace")
    assert release_workspace.status_code == 200
    assert "release_summary" in release_workspace.json()
    assert "publish_blockers" in release_workspace.json()
    assert "rollback_workspace" in release_workspace.json()
    assert "action_pack" in release_workspace.json()
    assert "operator_timeline" in release_workspace.json()
    metrics = client.get("/v1/ops/eval-metrics")
    assert metrics.status_code == 200
    assert "pass_rate" in metrics.json()
    assert "top_issue_categories" in metrics.json()
    assert "continuation_signal_summary" in metrics.json()
    assert "quality_signal_correlations" in metrics.json()
    assert "learned_eval_available" in metrics.json()
    assert "learned_rule_agreement_rate" in metrics.json()
    assert "learned_shadow_summary" in metrics.json()
    cross_pack = client.get("/v1/ops/cross-pack-quality")
    assert cross_pack.status_code == 200
    assert "cross_pack_pass_rate" in cross_pack.json()
    assert "top_failing_packs" in cross_pack.json()
    assert "strongest_packs" in cross_pack.json()
    assert "weakest_packs" in cross_pack.json()
    assert "weakest_pack_diagnostics" in cross_pack.json()
    assert "top_issue_categories" in cross_pack.json()["worlds"][0]
    assert "dimension_scores" in cross_pack.json()["worlds"][0]
    assert "issue_summary" in cross_pack.json()["worlds"][0]
    assert "issue_mix" in cross_pack.json()["worlds"][0]
    assert "long_route_quality" in cross_pack.json()["worlds"][0]
    assert "mid_arc_drop" in cross_pack.json()["worlds"][0]
    assert "dialogue_distinctness" in cross_pack.json()["worlds"][0]
    assert "completion_ratio" in cross_pack.json()["worlds"][0]
    assert "stop_reason" in cross_pack.json()["worlds"][0]
    assert "diagnostic_score" in cross_pack.json()["worlds"][0]
    assert "diagnostic_rank" in cross_pack.json()["worlds"][0]
    assert "weakest_dimensions" in cross_pack.json()["top_failing_packs"][0]
    assert "worst_chapters" in cross_pack.json()["weakest_pack_diagnostics"][0]
    assert "attribution_map" in cross_pack.json()["weakest_pack_diagnostics"][0]
    assert "next_fix_candidates" in cross_pack.json()["weakest_pack_diagnostics"][0]
    assert "ranking_changes" in cross_pack.json()["delta_summary"]
    learned_dashboard = client.get("/v1/ops/learned-dashboard")
    assert learned_dashboard.status_code == 200
    assert "artifact_status" in learned_dashboard.json()
    assert "recommended_next_focus" in learned_dashboard.json()
    assert "published_at" in learned_dashboard.json()["artifact_status"]["evaluator"]
    assert "world_details" in learned_dashboard.json()
    assert "issue_details" in learned_dashboard.json()
    learned_compare = client.get("/v1/ops/learned-compare")
    assert learned_compare.status_code == 200
    assert learned_compare.json()["preferred_shadow_candidate"] in {"evaluator", "reranker", "neither"}
    assert "recommended_next_action" in learned_compare.json()
    assert "disagreement_worlds" in learned_compare.json()
    assert "disagreement_issue_codes" in learned_compare.json()
    learned_data_ops = client.get("/v1/ops/learned-data-ops")
    assert learned_data_ops.status_code == 200
    assert "review_sample_backlog" in learned_data_ops.json()
    assert "pair_coverage_backlog" in learned_data_ops.json()
    assert "action_queue" in learned_data_ops.json()
    learned_review_quality = client.get("/v1/ops/learned-review-quality")
    assert learned_review_quality.status_code == 200
    assert "coverage_summary" in learned_review_quality.json()
    assert "quality_summary" in learned_review_quality.json()
    assert "replenishment_backlog" in learned_review_quality.json()
    learned_cadence = client.get("/v1/ops/learned-cadence")
    assert learned_cadence.status_code == 200
    assert "cadence_summary" in learned_cadence.json()
    assert {item["track"] for item in learned_cadence.json()["track_summaries"]} == {"evaluator", "reranker"}
    learned_impact = client.get("/v1/ops/learned-impact")
    assert learned_impact.status_code == 200
    assert "retention_proxies" in learned_impact.json()
    assert "monetization_proxies" in learned_impact.json()
    assert "experiment_summaries" in learned_impact.json()
    assert "assisted_gate" in learned_impact.json()["experiment_summaries"]
    evaluator_cadence = client.get("/v1/ops/learned-cadence/evaluator")
    assert evaluator_cadence.status_code == 200
    assert evaluator_cadence.json()["track"] == "evaluator"
    assert "track_summary" in evaluator_cadence.json()
    assisted_gate = client.get("/v1/ops/learned-assisted-gate")
    assert assisted_gate.status_code == 200
    assert "guardrails" in assisted_gate.json()
    assert "rollback_conditions" in assisted_gate.json()
    assisted_rerank = client.get("/v1/ops/learned-assisted-rerank")
    assert assisted_rerank.status_code == 200
    assert "guardrails" in assisted_rerank.json()
    assert "rollback_conditions" in assisted_rerank.json()
    ops_subscriptions = client.get("/v1/ops/subscriptions", params={"account_id": "web_author"})
    assert ops_subscriptions.status_code == 200
    if ops_subscriptions.json()["subscriptions"]:
        assert "next_action" in ops_subscriptions.json()["subscriptions"][0]
    schema_lifecycle = client.get("/v1/ops/schema-lifecycle")
    assert schema_lifecycle.status_code == 200
    assert "status" in schema_lifecycle.json()
    assert "pending_versions" in schema_lifecycle.json()
    assert "schema_matches_migrations" in schema_lifecycle.json()
    assert "alembic" in schema_lifecycle.json()
    assert "head_revision" in schema_lifecycle.json()["alembic"]
    data_integrity = client.get("/v1/ops/data-integrity")
    assert data_integrity.status_code == 200
    assert "hotspot_index_summary" in data_integrity.json()
    assert "repair_actions" in data_integrity.json()
    data_integrity_dry_run = client.post(
        "/v1/ops/data-integrity/repair",
        json={"apply": False, "actions": ["reconcile_session_chapter_pointers"], "limit": 5},
    )
    assert data_integrity_dry_run.status_code == 200
    assert "action_results" in data_integrity_dry_run.json()
    runtime_receipts = client.get("/v1/ops/runtime-receipts", params={"account_id": "web_author"})
    assert runtime_receipts.status_code == 200
    assert "runtime_receipts" in runtime_receipts.json()
    if runtime_receipts.json()["runtime_receipts"]:
        assert "runtime_latency_ms" in runtime_receipts.json()["runtime_receipts"][0]
        assert "candidate_attempt_count" in runtime_receipts.json()["runtime_receipts"][0]
    runtime_snapshot = client.get("/v1/ops/runtime-incident-snapshot", params={"account_id": "web_author"})
    assert runtime_snapshot.status_code == 200
    assert "incident_count" in runtime_snapshot.json()
    assert "schema_lifecycle_status" in runtime_snapshot.json()
    assert "latency_summary" in runtime_snapshot.json()
    provider_routing = client.get("/v1/ops/provider-routing")
    assert provider_routing.status_code == 200
    assert "candidate" in provider_routing.json()
    assert "renderer" in provider_routing.json()
    provider_rollout = client.get("/v1/ops/provider-rollout")
    assert provider_rollout.status_code == 200
    assert "tracks" in provider_rollout.json()
    provider_metrics = client.get("/v1/ops/provider-runtime-metrics", params={"account_id": "web_author"})
    assert provider_metrics.status_code == 200
    assert "provider_summary" in provider_metrics.json()
    assert "cost_trend" in provider_metrics.json()
    assert "latency_summary" in provider_metrics.json()
    assert "latency_trend" in provider_metrics.json()
    assert "rollout_stage_summary" in provider_metrics.json()
    deployment_runbook = client.get("/v1/ops/deployment-runbook")
    assert deployment_runbook.status_code == 200
    assert "deploy_steps" in deployment_runbook.json()
    deployment_gate = client.get("/v1/ops/deployment-health-gate", params={"account_id": "web_author"})
    assert deployment_gate.status_code == 200
    assert "checks" in deployment_gate.json()
    preflight_bundle = client.get("/v1/ops/preflight-verification-bundle", params={"account_id": "web_author"})
    assert preflight_bundle.status_code == 200
    assert "verification_summary" in preflight_bundle.json()
    assert "restore_verification_steps" in preflight_bundle.json()
    incident_playbook = client.get("/v1/ops/incident-playbook", params={"account_id": "web_author"})
    assert incident_playbook.status_code == 200
    assert "triage_steps" in incident_playbook.json()
    recovery_drills = client.get("/v1/ops/recovery-drills")
    assert recovery_drills.status_code == 200
    assert "recovery_drills" in recovery_drills.json()
    restore_requests = client.get("/v1/ops/runtime-restore-requests")
    assert restore_requests.status_code == 200
    assert "restore_requests" in restore_requests.json()
    ops_entitlements = client.get("/v1/ops/entitlements", params={"account_id": "web_author"})
    assert ops_entitlements.status_code == 200
    assert "audit_summary" in ops_entitlements.json()
    assert "audit_timeline" in ops_entitlements.json()
    assert "audit_trail" in ops_entitlements.json()
    assert "audit_breakdown" in ops_entitlements.json()
    if ops_entitlements.json()["revoke_candidates"]:
        entitlement_id = ops_entitlements.json()["revoke_candidates"][0]["entitlement_id"]
        revoke = client.post(
            "/v1/ops/entitlements/revoke",
            json={"entitlement_id": entitlement_id, "reason": "manual_entitlement_revoke"},
        )
        assert revoke.status_code == 200
        assert revoke.json()["entitlement"]["status"] == "revoked"
    ops_account_detail = client.get("/v1/ops/accounts/web_author")
    assert ops_account_detail.status_code == 200
    assert "activity_summary" in ops_account_detail.json()
    assert "recent_meters" in ops_account_detail.json()
    assert "author_access" in ops_account_detail.json()
    assert "recent_sessions" in ops_account_detail.json()
    assert "recent_drafts" in ops_account_detail.json()
    assert "audit_trail" in ops_account_detail.json()
    assert "audit_breakdown" in ops_account_detail.json()
    assert "timeline_cursor" in ops_account_detail.json()
    assert "support_summary" in ops_account_detail.json()
    assert "support_issues" in ops_account_detail.json()
    assert "support_tooling" in ops_account_detail.json()
    ops_account_workspace = client.get("/v1/ops/accounts/web_author/workspace")
    assert ops_account_workspace.status_code == 200
    assert "workspace_summary" in ops_account_workspace.json()
    assert "action_pack" in ops_account_workspace.json()
    assert "operator_timeline" in ops_account_workspace.json()
    ops_account_issues = client.get("/v1/ops/accounts/web_author/issues")
    assert ops_account_issues.status_code == 200
    assert "support_summary" in ops_account_issues.json()
    assert "support_issues" in ops_account_issues.json()
    assert "support_tooling" in ops_account_issues.json()
    ops_alerts = client.get("/v1/ops/alerts", params={"account_id": "web_author", "limit": 20})
    assert ops_alerts.status_code == 200
    assert "summary" in ops_alerts.json()
    assert "alerts" in ops_alerts.json()
    ops_navigation = client.get("/v1/ops/navigation-model", params={"account_id": "web_author"})
    assert ops_navigation.status_code == 200
    assert "active_context" in ops_navigation.json()
    assert "escalation_summary" in ops_navigation.json()
    assert "navigation_targets" in ops_navigation.json()
    assert "follow_up_actions" in ops_navigation.json()
    ops_account_governance = client.get("/v1/ops/accounts/web_author/governance")
    assert ops_account_governance.status_code == 200
    assert "governance_summary" in ops_account_governance.json()
    assert "governance_cases" in ops_account_governance.json()
    assert "recommended_case_prefills" in ops_account_governance.json()
    governance_case = client.post(
        "/v1/ops/governance/cases",
        json={
            "case_type": "rights",
            "target_type": "account",
            "target_id": "web_author",
            "account_id": "web_author",
            "severity": "medium",
            "summary": "账号访问问题需要 rights 跟进",
            "description": "先建一个 rights skeleton case。",
            "reviewer_id": "ops_web",
        },
    )
    assert governance_case.status_code == 200
    case_id = governance_case.json()["case"]["case_id"]
    governance_status = client.post(
        f"/v1/ops/governance/cases/{case_id}/status",
        json={"status": "in_review", "reviewer_id": "ops_web", "resolution_notes": "开始排查。"},
    )
    assert governance_status.status_code == 200
    assert governance_status.json()["case"]["status"] == "in_review"
    governance_restriction = client.post(
        "/v1/ops/governance/restrictions",
        json={
            "restriction_type": "author_access_block",
            "account_id": "web_author",
            "case_type": "abuse",
            "severity": "high",
            "summary": "暂时冻结 author access",
            "reviewer_id": "ops_web",
        },
    )
    assert governance_restriction.status_code == 200
    restriction_id = governance_restriction.json()["case"]["restriction"]["restriction_id"]
    author_access_after_restriction = client.get("/v1/author/access", params={"account_id": "web_author"})
    assert author_access_after_restriction.status_code == 200
    assert author_access_after_restriction.json()["actions"]["simulate"]["reason"] == "manual_restriction_active"
    restriction_listing = client.get("/v1/ops/governance/restrictions", params={"account_id": "web_author"})
    assert restriction_listing.status_code == 200
    assert restriction_listing.json()["restrictions"]
    restriction_release = client.post(
        f"/v1/ops/governance/restrictions/{restriction_id}/release",
        json={"reviewer_id": "ops_web", "release_reason": "解除限制"},
    )
    assert restriction_release.status_code == 200
    assert restriction_release.json()["case"]["restriction"]["status"] == "released"
    governance_cases = client.get("/v1/ops/governance/cases", params={"account_id": "web_author"})
    assert governance_cases.status_code == 200
    assert governance_cases.json()["cases"]
    governance_case_detail = client.get(f"/v1/ops/governance/cases/{case_id}")
    assert governance_case_detail.status_code == 200
    assert "detail_summary" in governance_case_detail.json()
    assert "recommended_next_actions" in governance_case_detail.json()
    assert "workflow_summary" in governance_case_detail.json()
    governance_assign = client.post(
        f"/v1/ops/governance/cases/{case_id}/assign",
        json={"owner_id": "ops_owner", "reviewer_id": "ops_web", "note": "beta api assign"},
    )
    assert governance_assign.status_code == 200
    assert governance_assign.json()["case"]["owner_id"] == "ops_owner"
    governance_evidence = client.post(
        f"/v1/ops/governance/cases/{case_id}/evidence",
        json={"reviewer_id": "ops_owner", "title": "audit note", "preview": "collected trace evidence", "ref_id": "audit_1"},
    )
    assert governance_evidence.status_code == 200
    assert governance_evidence.json()["case"]["evidence_refs"]
    governance_export = client.get("/v1/ops/export/governance-audit", params={"account_id": "web_author"})
    assert governance_export.status_code == 200
    assert "cases" in governance_export.json()
    assert "restrictions" in governance_export.json()
    investigation = client.get("/v1/ops/investigations/accounts/web_author", params={"limit": 40})
    assert investigation.status_code == 200
    assert "investigation_summary" in investigation.json()
    assert "trace_timeline" in investigation.json()
    assert "evidence_index" in investigation.json()
    assert "recommended_paths" in investigation.json()
    case_investigation = client.get(f"/v1/ops/investigations/cases/{case_id}", params={"limit": 40})
    assert case_investigation.status_code == 200
    assert case_investigation.json()["filters"]["case_id"] == case_id
    world_investigation = client.get(
        f"/v1/ops/investigations/world-versions/{scaffolded.json()['world_version_id']}",
        params={"limit": 40},
    )
    assert world_investigation.status_code == 200
    assert world_investigation.json()["filters"]["world_version_id"] == scaffolded.json()["world_version_id"]
    investigation_export = client.get(
        "/v1/ops/export/investigation-trace",
        params={"account_id": "web_author", "case_id": case_id, "limit": 40},
    )
    assert investigation_export.status_code == 200
    assert investigation_export.json()["generated_at"]
    governance_alerts = client.get("/v1/ops/alerts", params={"account_id": "web_author", "limit": 40})
    assert governance_alerts.status_code == 200
    if governance_alerts.json()["alerts"]:
        alert_id = governance_alerts.json()["alerts"][0]["alert_id"]
        alert_detail = client.get(f"/v1/ops/alerts/{alert_id}", params={"account_id": "web_author"})
        assert alert_detail.status_code == 200
        assert "alert" in alert_detail.json()
        updated_alert = client.post(
            f"/v1/ops/alerts/{alert_id}/status",
            json={"account_id": "web_author", "status": "acknowledged", "reviewer_id": "ops_web", "note": "beta api test"},
        )
        assert updated_alert.status_code == 200
        assert updated_alert.json()["alert"]["status"] == "acknowledged"
    ops_account_detail_after_case = client.get("/v1/ops/accounts/web_author")
    assert any(
        item["action"] in {"governance_case_created", "governance_case_status_changed", "governance_restriction_applied", "governance_restriction_released"}
        for item in ops_account_detail_after_case.json()["audit_trail"]
    )
    ops_events = client.get("/v1/ops/monetization-events", params={"account_id": "web_author"})
    assert ops_events.status_code == 200
    assert "events" in ops_events.json()

    support_session = client.post("/v1/reader/sessions", json={"world_id": "jade_court_exam", "account_id": "acct_support_escalate"}).json()
    with app.state.repository.SessionLocal() as db:
        row = db.get(SessionRow, support_session["session_id"])
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()
    support_blocked = client.post(
        "/v1/reader/continue",
        json={"session_id": support_session["session_id"], "account_id": "acct_support_escalate", "freeform_intent": "继续往前。"},
    )
    assert support_blocked.status_code == 200
    support_issues = client.get("/v1/ops/accounts/acct_support_escalate/issues")
    assert support_issues.status_code == 200
    issue_id = support_issues.json()["support_issues"][0]["issue_id"]
    escalated = client.post(
        "/v1/ops/accounts/acct_support_escalate/governance/escalate-support",
        json={"issue_id": issue_id, "reviewer_id": "ops_escalate"},
    )
    assert escalated.status_code == 200
    assert escalated.json()["case"]["linked_support_issues"][0]["issue_id"] == issue_id
    learned_promotion = client.get("/v1/ops/learned-promotion")
    assert learned_promotion.status_code == 200
    assert learned_promotion.json()["track"] == "evaluator"
    assert learned_promotion.json()["mode"] == "manual_approval"
    assert learned_promotion.json()["recommendation_status"] in {"eligible", "watching", "blocked"}
    assert learned_promotion.json()["approval_status"] in {"unapproved", "approved", "stale", "revoked"}
    assert "checklist" in learned_promotion.json()
    assert "evidence" in learned_promotion.json()
    learned_reranker_promotion = client.get("/v1/ops/learned-reranker-promotion")
    assert learned_reranker_promotion.status_code == 200
    assert learned_reranker_promotion.json()["track"] == "reranker"
    assert learned_reranker_promotion.json()["scope"] == "global"
    assert learned_reranker_promotion.json()["mode"] == "manual_approval"
    assert learned_reranker_promotion.json()["recommendation_status"] in {"eligible", "watching", "blocked"}
    assert learned_reranker_promotion.json()["approval_status"] in {"unapproved", "approved", "stale", "revoked"}
    assert "checklist" in learned_reranker_promotion.json()
    assert "evidence" in learned_reranker_promotion.json()
    approve_reranker = client.post(
        "/v1/ops/learned-reranker-promotion/approve",
        json={"reviewer_id": "ops_promoter", "reason": "先批准 reranker promotion。"},
    )
    assert approve_reranker.status_code == 200
    assert approve_reranker.json()["approval_status"] in {"approved", "stale"}
    revoke_reranker = client.post(
        "/v1/ops/learned-reranker-promotion/revoke",
        json={"reviewer_id": "ops_promoter", "reason": "暂时撤销 reranker promotion。"},
    )
    assert revoke_reranker.status_code == 200
    assert revoke_reranker.json()["approval_status"] == "revoked"
    approve = client.post(
        "/v1/ops/learned-promotion/approve",
        json={"reviewer_id": "ops_promoter", "reason": "先批准 evaluator promotion。"},
    )
    assert approve.status_code == 200
    assert approve.json()["approval_status"] in {"approved", "stale"}
    revoke = client.post(
        "/v1/ops/learned-promotion/revoke",
        json={"reviewer_id": "ops_promoter", "reason": "暂时撤销 evaluator promotion。"},
    )
    assert revoke.status_code == 200
    assert revoke.json()["approval_status"] == "revoked"

    impact_create = client.post(
        "/v1/ops/review-samples",
        json={
            "chapter_id": "chapter_api_impact",
            "world_id": "jade_court_exam",
            "world_version_id": "jade_court_exam@0.1.0",
            "reviewer_id": "ops_impact",
            "score_overall": 0.66,
            "issue_codes": ["Q04"],
            "freeform_notes": "用于验证 impact receipt。",
            "would_continue": True,
            "would_pay": False,
        },
    )
    assert impact_create.status_code == 200
    assert "impact_receipt" in impact_create.json()
    assert impact_create.json()["impact_receipt"]["chapter_id"] == "chapter_api_impact"


def test_legacy_session_step_consumes_credits_and_returns_access_state(tmp_path: Path):
    app = create_app(repository=SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_api_credits.db")))
    client = TestClient(app)

    world_payload = client.get("/v1/examples/demo").json()
    client.post(
        "/v1/worlds",
        json={
            "world_bible": world_payload["world_bible"],
            "event_atoms": world_payload["event_atoms"],
            "metadata": {"source": "test"},
        },
    )
    session = client.post(
        "/v1/sessions",
        json={
            "world_id": world_payload["world_bible"]["world_id"],
            "initial_state": world_payload["initial_state"],
            "player_profile": {"reader_id": "reader_legacy", "surface": "test"},
            "metadata": {"reader_id": "reader_legacy"},
        },
    ).json()

    client.post(
        "/v1/reader/entitlements/grant",
        json={
            "reader_id": "reader_legacy",
            "world_id": world_payload["world_bible"]["world_id"],
            "entitlement_type": "credits",
            "balance": 3,
        },
    )

    from src.narrativeos.persistence.db import SessionRow

    with app.state.repository.SessionLocal() as db:
        row = db.get(SessionRow, session["session_id"])
        state = dict(row.narrative_state_json)
        state["chapter_index"] = 3
        row.chapter_index = 3
        row.narrative_state_json = state
        db.commit()

    result = client.post(
        f"/v1/sessions/{session['session_id']}/step?debug=true",
        json={
            "player_input": "我继续往前走。",
            "metadata": {"reader_id": "reader_legacy"},
        },
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "ok"
    assert payload["paywall"]["reason"] == "credits_consumed"
    assert payload["paywall"]["balance"] == 2.0
    assert payload["paywall"]["status"] in {"active", "exhausted"}

    entitlements = client.get(
        "/v1/reader/entitlements",
        params={"reader_id": "reader_legacy", "world_id": world_payload["world_bible"]["world_id"]},
    )
    assert entitlements.status_code == 200
    assert entitlements.json()["entitlements"][0]["reason"] in {"credits_balance", "credits_exhausted"}


def test_ops_eval_metrics_can_report_learned_shadow_summary(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "beta_api_learned_eval.db"))
    artifact_dir = tmp_path / "artifacts"
    app = create_app(repository=repository)
    client = TestClient(app)
    registry = FileSystemWorldRegistry()

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.0"
    pack["manifest"]["author_id"] = "api_learned_eval"
    draft = app.state.authoring_service.save_draft(pack)
    app.state.authoring_service.run_simulation_for_world_version(draft["world_version_id"])
    train_learned_evaluator_baseline(
        repository=repository,
        output_dir=artifact_dir,
        dataset_view="evaluator",
        world_id="urban_mystery_lotus_lane",
    )
    app.state.learned_inference_service = LearnedInferenceService(artifact_dir)
    app.state.learned_shadow_service = LearnedShadowService(
        artifact_dir,
        learned_inference_service=app.state.learned_inference_service,
    )
    app.state.authoring_service.learned_inference = app.state.learned_inference_service
    app.state.authoring_service.learned_shadow = app.state.learned_shadow_service

    metrics = client.get("/v1/ops/eval-metrics", params={"world_version_id": draft["world_version_id"]})
    assert metrics.status_code == 200
    assert "continuation_signal_summary" in metrics.json()
    assert "quality_signal_correlations" in metrics.json()
    assert metrics.json()["learned_eval_available"] is True
    assert "top_mismatch_worlds" in metrics.json()
    assert "top_mismatch_issue_codes" in metrics.json()
    assert metrics.json()["learned_shadow_summary"]["status"] in {"warming_up", "candidate", "not_ready"}
    assert "learned_reranker_shadow_summary" in metrics.json()
    assert metrics.json()["learned_reranker_shadow_summary"]["status"] in {"unavailable", "warming_up", "candidate", "not_ready"}
    dashboard = client.get("/v1/ops/learned-dashboard", params={"world_version_id": draft["world_version_id"]})
    assert dashboard.status_code == 200
    assert "artifact_status" in dashboard.json()
    assert "coverage_summary" in dashboard.json()
    assert "source_output_dir" in dashboard.json()["artifact_status"]["evaluator"]
    compare = client.get("/v1/ops/learned-compare", params={"world_version_id": draft["world_version_id"]})
    assert compare.status_code == 200
    assert "evaluator_scorecard" in compare.json()
    assert "reranker_scorecard" in compare.json()
    if dashboard.json()["world_details"]:
        world_id = dashboard.json()["world_details"][0]["world_id"]
        world_detail = client.get(f"/v1/ops/learned-dashboard/worlds/{world_id}")
        assert world_detail.status_code == 200
        assert "recommended_action" in world_detail.json()
    if dashboard.json()["issue_details"]:
        issue_code = dashboard.json()["issue_details"][0]["issue_code"]
        issue_detail = client.get(f"/v1/ops/learned-dashboard/issues/{issue_code}")
        assert issue_detail.status_code == 200
        assert "affected_worlds" in issue_detail.json()
