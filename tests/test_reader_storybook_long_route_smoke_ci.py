from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_reader_storybook_long_route_smoke_scripts_exist_and_are_parseable():
    run_script = ROOT / "scripts" / "run_reader_storybook_long_route_smoke.sh"
    seed_script = ROOT / "scripts" / "seed_reader_storybook_long_route_smoke.py"
    verify_script = ROOT / "scripts" / "verify_reader_storybook_long_route_smoke.js"

    assert run_script.exists()
    assert seed_script.exists()
    assert verify_script.exists()

    run_text = run_script.read_text(encoding="utf-8")
    seed_text = seed_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")

    assert "CI_HEADLESS" in run_text
    assert "CHROME_BIN" in run_text
    assert "reader_storybook_long_route_smoke_seed.json" in run_text
    assert "reader_storybook_long_route_smoke_result.json" in run_text
    assert "reader_storybook_long_route_smoke_history.json" in run_text
    assert "reader_storybook_long_route_smoke_failure_snapshot.json" in run_text
    assert "reader_storybook_long_route_smoke_failure.png" in run_text
    assert "reader_storybook_long_route_smoke_storybook.png" in run_text
    assert "seed_reader_storybook_long_route_smoke.py" in run_text
    assert "verify_reader_storybook_long_route_smoke.js" in run_text
    assert "WORLD_IDS=\"${WORLD_IDS:-jade_court_exam,jade_court_romance,urban_mystery_lotus_lane}\"" in run_text
    assert "TARGET_CHAPTERS=\"${TARGET_CHAPTERS:-30}\"" in run_text
    assert "--min-target-chapters" in run_text

    assert "DEFAULT_WORLD_IDS = (\"jade_court_exam\", \"jade_court_romance\", \"urban_mystery_lotus_lane\")" in seed_text
    assert "DEFAULT_READER_PASSWORD = \"reader-smoke-pass-123\"" in seed_text
    assert "DEFAULT_TARGET_CHAPTERS = 30" in seed_text
    assert "DEFAULT_MIN_TARGET_CHAPTERS = 30" in seed_text
    assert "register_identity" in seed_text
    assert "grant_entitlement" in seed_text
    assert "quality_guard_failed" in seed_text
    assert "world_summaries" in seed_text
    assert "beats_coverage_rate" in seed_text
    assert "visible_trajectory_sample_indexes" in seed_text

    assert "Reader Storybook Long-Route Smoke" in verify_text
    assert "reader_storybook_quote_unstable" in verify_text
    assert "reader_storybook_beats_missing" in verify_text
    assert "reader_storybook_trajectory_too_short" in verify_text
    assert "reader_storybook_cross_pack_distinctness_failed" in verify_text
    assert "title_homogenization_non_blocking" in verify_text
    assert "login_reader_identity" in verify_text
    assert "#shell-auth-actor-id" in verify_text
    assert "#shell-auth-password" in verify_text
    assert "restore_seeded_session:jade_court_exam" not in verify_text
    assert "ReaderRuntime.restoreSession" in verify_text
    assert "reader_storybook_world_summaries" in verify_text
    assert "reader_storybook_cross_pack_distinctness" in verify_text
    assert "reader_storybook_title_homogenization_warnings" in verify_text
    assert "reader_storybook_title_homogenization_warning_count" in verify_text
    assert "reader_storybook_title_homogenization_history_summary" in verify_text
    assert "reader_storybook_title_homogenization_trend" in verify_text
    assert "reader_storybook_title_homogenization_promoted_pairs" in verify_text
    assert "title_similarity" in verify_text
    assert "quote_similarity" in verify_text
    assert "#reader-v2-storybook-quote" in verify_text
    assert "#reader-v2-storybook-beats" in verify_text
    assert "#reader-v2-storybook-sequence" in verify_text
    assert "Page.captureScreenshot" in verify_text
    assert "reader_storybook_screenshot_file" in verify_text


def test_reader_storybook_500_verification_uses_quantum_frontend_and_human_review_samples():
    run_script = ROOT / "scripts" / "run_reader_storybook_500_verification.sh"
    seed_script = ROOT / "scripts" / "seed_reader_storybook_long_route_smoke.py"
    verify_script = ROOT / "scripts" / "verify_reader_storybook_500_quantum.js"
    audit_script = ROOT / "scripts" / "audit_reader_storybook_500_redundancy.py"
    story_page = ROOT / "Kimi_Agent_设计系统加载" / "app" / "src" / "pages" / "Story.tsx"
    showcase_page = ROOT / "Kimi_Agent_设计系统加载" / "app" / "src" / "pages" / "Showcase.tsx"
    frontend_types = ROOT / "Kimi_Agent_设计系统加载" / "app" / "src" / "types" / "index.ts"

    assert run_script.exists()
    assert seed_script.exists()
    assert verify_script.exists()
    assert audit_script.exists()
    assert story_page.exists()
    assert showcase_page.exists()
    assert frontend_types.exists()

    run_text = run_script.read_text(encoding="utf-8")
    seed_text = seed_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")
    audit_text = audit_script.read_text(encoding="utf-8")
    story_text = story_page.read_text(encoding="utf-8")
    showcase_text = showcase_page.read_text(encoding="utf-8")
    frontend_types_text = frontend_types.read_text(encoding="utf-8")
    story_api = (ROOT / "Kimi_Agent_设计系统加载" / "app" / "src" / "api" / "story.ts").read_text(encoding="utf-8")
    story_hook = (ROOT / "Kimi_Agent_设计系统加载" / "app" / "src" / "hooks" / "useStory.ts").read_text(encoding="utf-8")

    assert 'PYTHON_BIN="${NARRATIVEOS_PYTHON:-}"' in run_text
    assert '.venv311/bin/python' in run_text
    assert 'BACKEND_PORT="${BACKEND_PORT:-8000}"' in run_text
    assert 'FRONTEND_PORT="${FRONTEND_PORT:-3000}"' in run_text
    assert 'REUSE_SEEDED_DB="${REUSE_SEEDED_DB:-1}"' in run_text
    assert "Reusing seeded 500-chapter Reader Storybook replay data" in run_text
    assert 'FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:${FRONTEND_PORT}}"' in run_text
    assert "Kimi_Agent_设计系统加载/app" in run_text
    assert "verify_reader_storybook_500_quantum.js" in run_text
    assert "audit_reader_storybook_500_redundancy.py" in run_text
    assert "--world-ids all" in run_text
    assert "--target-chapters" in run_text
    assert "--min-target-chapters" in run_text

    assert "DEFAULT_REVIEW_TARGET_CHAPTERS = (1, 21, 220, 260, 460, 480)" in seed_text
    assert "FileSystemWorldRegistry" in seed_text
    assert 'item.lower() == "all"' in seed_text
    assert '"world_version_id": world_version_id' in seed_text
    assert '"review_target_chapters": review_targets' in seed_text

    assert "reader_storybook_500_quantum_result/v1" in verify_text
    assert 'http://127.0.0.1:3000' in verify_text
    assert "data-reader-storybook-window" in verify_text
    assert "#reader-v2-storybook-title" in verify_text
    assert "#reader-v2-storybook-prose" in verify_text
    assert "#reader-v2-storybook-quote" in verify_text
    assert "#reader-v2-storybook-beats" in verify_text
    assert "#reader-v2-storybook-sequence" in verify_text
    assert "Chapter ${Number(chapterIndex)}" in verify_text

    assert "ops_longform500_reader_q03_recovery_20260425" in audit_text
    assert "reader_q03_recovery_ready" in audit_text
    assert "MAX_MEDIUM_RISK = 6" in audit_text
    assert "MAX_HIGH_RISK = 0" in audit_text
    assert '"source": "human_review"' in audit_text
    assert '"kind": "manual_entry"' in audit_text
    assert "chapter_function_novelty" in audit_text
    assert "scene_object_novelty" in audit_text
    assert "emotional_pressure_novelty" in audit_text
    assert "dialogue_novelty" in audit_text
    assert "continuation_pull" in audit_text
    assert "redundancy_risk" in audit_text

    assert "reader-v2-storybook-window-tabs" in story_text
    assert "STORYBOOK_WINDOWS" in story_text
    assert "label: '早段'" in story_text
    assert "label: '中段'" in story_text
    assert "label: '末段'" in story_text
    assert "label: '最近'" in story_text
    assert "startChapter" in story_api
    assert "loadProjectedNodes" in story_hook
    assert "nodeCount < 120" in story_hook
    assert "startChapter: 460" in story_hook
    assert "productReadyBand === '500'" in story_text
    assert "longform500ProductReady" in story_text
    assert "claimSafeBand === '500'" not in story_text
    assert "productReadyBand === '500'" in showcase_text
    assert "longform500ProductReady" in showcase_text
    assert "claimSafeBand === '500'" not in showcase_text
    assert "claimSafeBand?: string | null" in frontend_types_text
    assert "productReadyBand?: string | null" in frontend_types_text
    assert "longform500ProductReady?: boolean" in frontend_types_text


def test_reader_storybook_long_route_smoke_workflow_restores_and_reuploads_history():
    workflow_path = ROOT / ".github" / "workflows" / "reader-storybook-long-route-smoke.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert payload["name"] == "reader-storybook-long-route-smoke"
    smoke_job = payload["jobs"]["smoke"]
    steps = smoke_job["steps"]

    assert smoke_job["permissions"]["actions"] == "read"
    assert smoke_job["permissions"]["contents"] == "read"

    setup_node_step = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node_step["with"]["node-version"] == "22"

    resolve_step = next(step for step in steps if step.get("id") == "history")
    assert resolve_step["uses"] == "actions/github-script@v7"
    assert "reader-storybook-long-route-smoke-history" in resolve_step["with"]["script"]
    assert "listArtifactsForRepo" in resolve_step["with"]["script"]
    assert "workflow_run.head_branch" in resolve_step["with"]["script"]

    restore_step = next(step for step in steps if step.get("name") == "Restore reader storybook history artifact")
    assert restore_step["if"] == "steps.history.outputs.run-id != ''"
    assert restore_step["uses"].startswith("actions/download-artifact@")
    assert restore_step["with"]["name"] == "${{ steps.history.outputs.artifact-name }}"
    assert restore_step["with"]["path"] == "artifacts"
    assert restore_step["with"]["repository"] == "${{ github.repository }}"
    assert restore_step["with"]["github-token"] == "${{ github.token }}"

    run_step = next(step for step in steps if step.get("name") == "Run reader storybook long-route smoke")
    run_script = run_step["run"]
    assert "CI_HEADLESS=1" in run_script
    assert "CHROME_BIN=" in run_script
    assert "bash scripts/run_reader_storybook_long_route_smoke.sh" in run_script

    summary_step = next(step for step in steps if step.get("name") == "Publish reader storybook long-route smoke summary")
    assert summary_step["if"] == "always()"
    assert "write_reader_storybook_long_route_smoke_step_summary.py" in summary_step["run"]
    assert "reader_storybook_long_route_smoke_result.json" in summary_step["run"]
    assert "reader_storybook_long_route_smoke_failure_snapshot.json" in summary_step["run"]

    artifact_step = next(step for step in steps if step.get("name") == "Upload reader storybook long-route smoke artifacts")
    assert artifact_step["if"] == "always()"
    assert artifact_step["uses"].startswith("actions/upload-artifact@")
    artifact_path = artifact_step["with"]["path"]
    assert "artifacts/reader_storybook_long_route_smoke_seed.json" in artifact_path
    assert "artifacts/reader_storybook_long_route_smoke_result.json" in artifact_path
    assert "artifacts/reader_storybook_long_route_smoke_history.json" in artifact_path
    assert "artifacts/reader_storybook_long_route_smoke_storybook.png" in artifact_path

    history_upload_step = next(step for step in steps if step.get("name") == "Upload reader storybook history artifact")
    assert history_upload_step["if"] == "always()"
    assert history_upload_step["uses"].startswith("actions/upload-artifact@")
    assert history_upload_step["with"]["name"] == "reader-storybook-long-route-smoke-history"
    assert history_upload_step["with"]["path"] == "artifacts/reader_storybook_long_route_smoke_history.json"


def test_reader_storybook_long_route_smoke_workflow_restores_history_before_run_and_uploads_both_artifact_shapes():
    workflow_path = ROOT / ".github" / "workflows" / "reader-storybook-long-route-smoke.yml"
    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    steps = payload["jobs"]["smoke"]["steps"]
    step_names = [step.get("name", "") for step in steps]

    restore_index = step_names.index("Restore reader storybook history artifact")
    run_index = step_names.index("Run reader storybook long-route smoke")
    bundle_upload_index = step_names.index("Upload reader storybook long-route smoke artifacts")
    history_upload_index = step_names.index("Upload reader storybook history artifact")

    assert restore_index < run_index < bundle_upload_index < history_upload_index

    bundle_upload_step = steps[bundle_upload_index]
    history_upload_step = steps[history_upload_index]

    bundle_path = bundle_upload_step["with"]["path"]
    assert "artifacts/reader_storybook_long_route_smoke_result.json" in bundle_path
    assert "artifacts/reader_storybook_long_route_smoke_history.json" in bundle_path
    assert "artifacts/reader_storybook_long_route_smoke_storybook.png" in bundle_path

    assert history_upload_step["with"]["name"] == "reader-storybook-long-route-smoke-history"
    assert history_upload_step["with"]["path"] == "artifacts/reader_storybook_long_route_smoke_history.json"
