from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.billing import BillingService
from src.narrativeos.services.governance import GovernanceService


def test_governance_case_workflow_tracks_owner_due_evidence_and_transition_rules(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "governance_workflow.db"))
    billing = BillingService(repository)
    governance = GovernanceService(repository, billing_service=billing)

    case = governance.create_case(
        {
            "case_type": "rights",
            "target_type": "account",
            "target_id": "acct_workflow",
            "account_id": "acct_workflow",
            "severity": "high",
            "summary": "治理 workflow 完整流",
            "reviewer_id": "ops_triage",
            "owner_id": "ops_triage",
            "policy_labels": ["billing_rights"],
        }
    )
    assert case["workflow_summary"]["owner_id"] == "ops_triage"
    assert case["workflow_summary"]["transition_options"] == ["dismissed", "escalated", "in_review"]
    assert case["workflow_summary"]["pending_checklist_count"] >= 1

    assigned = governance.assign_case(
        case["case_id"],
        owner_id="ops_owner",
        reviewer_id="ops_triage",
        note="handoff to owner",
    )
    assert assigned["owner_id"] == "ops_owner"

    evidenced = governance.append_case_evidence(
        case["case_id"],
        reviewer_id="ops_owner",
        title="support transcript",
        preview="customer requests subscription fix",
        ref_id="ticket_123",
    )
    assert len(evidenced["evidence_refs"]) == 1
    assert evidenced["evidence_refs"][0]["title"] == "support transcript"

    in_review = governance.update_case_status(
        case["case_id"],
        status="in_review",
        reviewer_id="ops_owner",
    )
    assert in_review["status"] == "in_review"

    with pytest.raises(PermissionError):
        governance.update_case_status(
            case["case_id"],
            status="resolved",
            reviewer_id="ops_other",
            resolution_notes="not owner",
            disposition="customer_remedy_applied",
        )

    resolved = governance.update_case_status(
        case["case_id"],
        status="resolved",
        reviewer_id="ops_owner",
        resolution_notes="customer remedy completed",
        disposition="customer_remedy_applied",
    )
    assert resolved["status"] == "resolved"
    assert resolved["disposition"] == "customer_remedy_applied"
    detail = governance.case_detail(case["case_id"], actor_id="ops_owner", actor_role="reviewer")
    assert detail["workflow_summary"]["completed_checklist_count"] >= 1
    assert detail["permission_summary"]["can_transition"] is True

    with pytest.raises(ValueError):
        governance.update_case_status(
            case["case_id"],
            status="in_review",
            reviewer_id="ops_owner",
        )


def test_governance_api_enforces_reviewer_identity_for_mutations(tmp_path: Path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "governance_api_identity.db"))
    app = create_app(repository=repository)
    client = TestClient(app)

    reviewer_auth = client.post(
        "/v1/auth/register",
        json={"actor_id": "ops_reviewer", "actor_role": "reviewer", "password": "secret123"},
    )
    assert reviewer_auth.status_code == 200
    author_auth = client.post(
        "/v1/auth/register",
        json={"actor_id": "plain_author", "actor_role": "author", "password": "secret123"},
    )
    assert author_auth.status_code == 200
    reviewer_login = client.post("/v1/auth/login", json={"actor_id": "ops_reviewer", "password": "secret123"})
    assert reviewer_login.status_code == 200
    author_login = client.post("/v1/auth/login", json={"actor_id": "plain_author", "password": "secret123"})
    assert author_login.status_code == 200
    reviewer_headers = {"Authorization": f"Bearer {reviewer_login.json()['token']['access_token']}"}
    author_headers = {"Authorization": f"Bearer {author_login.json()['token']['access_token']}"}

    created = client.post(
        "/v1/ops/governance/cases",
        headers=reviewer_headers,
        json={
            "case_type": "moderation",
            "target_type": "account",
            "target_id": "acct_api_identity",
            "account_id": "acct_api_identity",
            "severity": "medium",
            "summary": "reviewer-owned governance case",
            "reviewer_id": "ignored_by_bearer",
            "owner_id": "ops_reviewer",
        },
    )
    assert created.status_code == 200
    case_id = created.json()["case"]["case_id"]
    assert created.json()["case"]["reviewer_id"] == "ops_reviewer"

    evidence = client.post(
        f"/v1/ops/governance/cases/{case_id}/evidence",
        headers=reviewer_headers,
        json={"title": "operator note", "preview": "captured evidence", "ref_id": "receipt_1"},
    )
    assert evidence.status_code == 200
    assert evidence.json()["case"]["evidence_refs"]

    forbidden = client.post(
        f"/v1/ops/governance/cases/{case_id}/status",
        headers=author_headers,
        json={"status": "in_review", "reviewer_id": "author_should_fail"},
    )
    assert forbidden.status_code == 403

    moved = client.post(
        f"/v1/ops/governance/cases/{case_id}/status",
        headers=reviewer_headers,
        json={"status": "in_review"},
    )
    assert moved.status_code == 200
    detail = client.get(f"/v1/ops/governance/cases/{case_id}", headers=reviewer_headers)
    assert detail.status_code == 200
    assert detail.json()["permission_summary"]["can_assign"] is True
    assert detail.json()["workflow_summary"]["owner_id"] == "ops_reviewer"
