from src.narrativeos.eval.learned_data_ops import build_learned_data_ops_summary
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.training_signal import TrainingSignalService
from tests.test_learned_reranker_baseline import _seed_reranker_world


def _seed_ops_data(repository: SQLAlchemyRepository) -> str:
    world_version_id = _seed_reranker_world(repository, world_id="jade_court_romance")
    version = repository.get_world_version(world_version_id)
    version.simulation_report_json = {
        "ok": False,
        "world_version_id": world_version_id,
        "world_id": version.world_id,
        "evaluation_summary": {"pass_rate": 0.0, "rewrite_rate": 1.0, "block_rate": 0.0},
        "cross_pack_summary": {"cross_pack_pass_rate": 0.4},
        "chapter_evaluations": [
            {
                "chapter_id": "chapter_ops_data_1",
                "world_version_id": world_version_id,
                "session_id": "session_ops_data",
                "decision": {"decision": "rewrite", "reason": "rewrite_needed"},
                "issues": [{"issue_code": "Q04", "severity": "medium", "summary": "解释句偏多", "owning_module": "writer", "evidence": []}],
                "scores": {
                    "readability": 0.7,
                    "scene_density": 0.4,
                    "character_fidelity": 0.6,
                    "causal_continuity": 0.8,
                    "pacing": 0.5,
                    "choice_distinctness": 0.7,
                    "hook_quality": 0.5,
                    "monetize_ready": 0.5,
                    "overall_score": 0.58,
                },
                "hard_validator_results": {},
                "summary": "Q04 解释句偏多",
                "created_at": "2026-04-01T00:00:00+00:00",
            }
        ],
    }
    repository.save_world_version(version, publish=False)
    return world_version_id


def test_issue_fix_pair_backlog_identifies_low_coverage_world_issue_pairs(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_data_ops_pairs.db"))
    world_version_id = _seed_ops_data(repository)
    backlog = TrainingSignalService(repository).issue_fix_pair_backlog(world_version_id=world_version_id)
    assert backlog
    assert backlog[0]["world_version_id"] == world_version_id
    assert "coverage_count" in backlog[0]
    assert "recent_revision_ids" in backlog[0]
    assert "changed_sections" in backlog[0]
    assert backlog[0]["recommended_action"] in {"request_more_revisions", "expand_issue_fix_pairs"}


def test_learned_data_ops_summary_aggregates_review_and_pair_backlogs(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "learned_data_ops_summary.db"))
    _seed_ops_data(repository)
    summary = build_learned_data_ops_summary(repository=repository, world_id="jade_court_romance")
    assert summary["preferred_shadow_candidate"] in {"evaluator", "reranker", "neither"}
    assert summary["recommended_next_action"]
    assert summary["review_sample_backlog"]
    assert summary["pair_coverage_backlog"]
    assert summary["action_queue"]
    assert summary["coverage_gaps"]["review_sample_backlog_count"] >= 1
    assert summary["coverage_gaps"]["pair_coverage_backlog_count"] >= 1
