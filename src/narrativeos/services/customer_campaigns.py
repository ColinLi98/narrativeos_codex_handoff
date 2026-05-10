from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..quality.models import ReviewCase
from ..persistence.repositories import SQLAlchemyPlatformRepository
from .commercial_audit import CommercialAuditService
from .customer_accounts import CustomerAccountService


CAMPAIGN_ACTIVATION_STATUSES = {"draft", "in_review", "approved", "active", "paused", "blocked"}
CAMPAIGN_REVIEW_STATUSES = {"submitted", "in_review", "approved", "needs_changes", "blocked", "activated", "paused"}


class CustomerCampaignService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        customer_account_service: CustomerAccountService,
        audit_service: CommercialAuditService,
    ) -> None:
        self.repository = repository
        self.customer_accounts = customer_account_service
        self.audit = audit_service

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_status(self, status: str) -> str:
        normalized = str(status or "").strip()
        if normalized not in CAMPAIGN_ACTIVATION_STATUSES:
            raise ValueError("campaign_activation_status_invalid:%s" % normalized)
        return normalized

    def _validate_review_status(self, status: str) -> str:
        normalized = str(status or "").strip()
        if normalized not in CAMPAIGN_REVIEW_STATUSES:
            raise ValueError("campaign_review_status_invalid:%s" % normalized)
        return normalized

    def _campaign_counts(self, *, customer_account_id: str) -> int:
        return len(self.repository.list_campaigns(customer_account_id=customer_account_id, limit=500))

    def _sync_customer_campaign_count(self, *, customer_account_id: str) -> None:
        customer = self.repository.get_customer_account(customer_account_id)
        count = self._campaign_counts(customer_account_id=customer_account_id)
        self.repository.save_customer_account({**customer, "campaign_count": count})

    def _campaign_bundle(self, campaign_id: str) -> Dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        proof_bundles = self.repository.list_campaign_proof_bundles(campaign_id=campaign_id)
        channel_targets = self.repository.list_campaign_channel_targets(campaign_id=campaign_id)
        submissions = self.repository.list_campaign_review_submissions(campaign_id=campaign_id, limit=20)
        review_case = None
        if campaign.get("primary_review_case_id"):
            try:
                review_case = self.repository.get_review_case(campaign["primary_review_case_id"])
            except KeyError:
                review_case = None
        return {
            "campaign": campaign,
            "proof_bundles": proof_bundles,
            "channel_targets": channel_targets,
            "review_submissions": submissions,
            "review_case": review_case,
        }

    def create_or_update_campaign(
        self,
        *,
        account_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        customer_detail = self.customer_accounts.customer_account_detail(account_id=account_id)
        customer = dict(customer_detail.get("customer_account") or {})
        existing = None
        campaign_id = str(payload.get("campaign_id") or "").strip() or None
        if campaign_id:
            existing = self.repository.get_campaign(campaign_id)
            if str(existing.get("account_id") or "") != account_id:
                raise PermissionError("campaign_account_ownership_mismatch")
        record = self.repository.save_campaign(
            {
                "campaign_id": campaign_id,
                "customer_account_id": customer["customer_account_id"],
                "account_id": account_id,
                "title": str(payload.get("title") or ((existing or {}).get("title") or "")),
                "target_icp_vertical": str(payload.get("target_icp_vertical") or ((existing or {}).get("target_icp_vertical") or "")),
                "cta_text": str(payload.get("cta_text") or ((existing or {}).get("cta_text") or "")),
                "disclosure_text": str(payload.get("disclosure_text") or ((existing or {}).get("disclosure_text") or "")),
                "activation_status": self._validate_status(str(payload.get("activation_status") or (existing.get("activation_status") if existing else "draft") or "draft")),
                "selected_channels": list(payload.get("selected_channels") or (existing.get("selected_channels_json") if existing else []) or []),
                "selected_partner_refs": list(payload.get("selected_partner_refs") or (existing.get("selected_partner_refs_json") if existing else []) or []),
                "primary_review_case_id": existing.get("primary_review_case_id") if existing else None,
                "latest_submission_id": existing.get("latest_submission_id") if existing else None,
                "campaign_payload": {
                    "proof_points": list(payload.get("proof_points") or []),
                    "proof_source_urls": list(payload.get("proof_source_urls") or []),
                    "proof_artifact_refs": list(payload.get("proof_artifact_refs") or []),
                    "selected_channels": list(payload.get("selected_channels") or []),
                    "selected_partner_refs": list(payload.get("selected_partner_refs") or []),
                },
            }
        )
        proof_bundle_payload = {
            "bundle_label": "default",
            "proof_points": list(payload.get("proof_points") or []),
            "source_urls": list(payload.get("proof_source_urls") or []),
            "artifact_refs": list(payload.get("proof_artifact_refs") or []),
            "bundle_payload": {"campaign_id": record["campaign_id"]},
        }
        self.repository.replace_campaign_proof_bundles(campaign_id=record["campaign_id"], bundles=[proof_bundle_payload])
        channel_targets = []
        selected_channels = list(payload.get("selected_channels") or [])
        selected_partner_refs = list(payload.get("selected_partner_refs") or [])
        for index, channel in enumerate(selected_channels):
            channel_targets.append(
                {
                    "channel_name": str(channel),
                    "partner_ref": selected_partner_refs[index] if index < len(selected_partner_refs) else None,
                    "priority": index,
                    "readiness_status": "selected",
                    "target_payload": {},
                }
            )
        self.repository.replace_campaign_channel_targets(campaign_id=record["campaign_id"], targets=channel_targets)
        self._sync_customer_campaign_count(customer_account_id=customer["customer_account_id"])
        bundle = self._campaign_bundle(record["campaign_id"])
        self.audit.record_audit_log(
            actor_id=account_id,
            actor_role="customer",
            account_id=account_id,
            object_type="campaign",
            object_id=record["campaign_id"],
            action_type="campaign_saved",
            source_surface="customer",
            customer_visible_payload={"campaign": bundle.get("campaign")},
            internal_payload=bundle,
        )
        return bundle

    def _submission_validation_errors(self, bundle: Dict[str, Any]) -> List[str]:
        campaign = dict(bundle.get("campaign") or {})
        proof_bundles = list(bundle.get("proof_bundles") or [])
        channel_targets = list(bundle.get("channel_targets") or [])
        errors: List[str] = []
        if not str(campaign.get("title") or "").strip():
            errors.append("campaign_title_required")
        if not str(campaign.get("target_icp_vertical") or "").strip():
            errors.append("campaign_target_icp_vertical_required")
        if not str(campaign.get("cta_text") or "").strip():
            errors.append("campaign_cta_required")
        if not str(campaign.get("disclosure_text") or "").strip():
            errors.append("campaign_disclosure_required")
        if not proof_bundles or not any((item.get("proof_points_json") or item.get("source_urls_json") or item.get("artifact_refs_json")) for item in proof_bundles):
            errors.append("campaign_proof_bundle_required")
        if not channel_targets:
            errors.append("campaign_channel_selection_required")
        return errors

    def submit_campaign(self, *, account_id: str, campaign_id: str) -> Dict[str, Any]:
        bundle = self._campaign_bundle(campaign_id)
        campaign = dict(bundle.get("campaign") or {})
        if str(campaign.get("account_id") or "") != account_id:
            raise PermissionError("campaign_account_ownership_mismatch")
        errors = self._submission_validation_errors(bundle)
        if errors:
            raise ValueError("campaign_submission_invalid:%s" % ",".join(errors))
        review_case = ReviewCase(
            case_id=f"review_case_campaign_{campaign_id}",
            case_type="campaign_activation",
            status="open",
            owner_id=None,
            source_ref={"kind": "campaign", "campaign_id": campaign_id, "account_id": account_id},
            reason_codes=["campaign_activation_review"],
            evidence_refs=[{"kind": "campaign", "ref_id": campaign_id}],
            metadata={"activation_status": "in_review"},
        )
        saved_case = self.repository.save_review_case(
            {
                **review_case.to_dict(),
                "source_surface": "customer",
                "world_version_id": None,
                "session_id": None,
                "score_id": None,
                "case_payload": {
                    "campaign_id": campaign_id,
                    "activation_status": "in_review",
                },
            }
        )
        submission = self.repository.save_campaign_review_submission(
            {
                "campaign_id": campaign_id,
                "review_case_id": saved_case["case_id"],
                "status": "submitted",
                "submitted_by": account_id,
                "submission_payload": {
                    "campaign_snapshot": campaign,
                    "proof_bundles": bundle.get("proof_bundles") or [],
                    "channel_targets": bundle.get("channel_targets") or [],
                },
            }
        )
        self.repository.save_campaign(
            {
                **campaign,
                "activation_status": "in_review",
                "primary_review_case_id": saved_case["case_id"],
                "latest_submission_id": submission["submission_id"],
                "selected_channels_json": campaign.get("selected_channels_json", []),
                "selected_partner_refs_json": campaign.get("selected_partner_refs_json", []),
                "campaign_payload_json": campaign.get("campaign_payload_json", {}),
            }
        )
        result = {
            **self._campaign_bundle(campaign_id),
            "submission": submission,
        }
        self.audit.record_audit_log(
            actor_id=account_id,
            actor_role="customer",
            account_id=account_id,
            object_type="campaign",
            object_id=campaign_id,
            action_type="campaign_submitted",
            source_surface="customer",
            customer_visible_payload={"campaign": result.get("campaign"), "submission": submission},
            internal_payload=result,
        )
        return result

    def decide_campaign(self, *, campaign_id: str, reviewer_id: str, decision: str, note: Optional[str] = None) -> Dict[str, Any]:
        normalized_decision = str(decision or "").strip()
        if normalized_decision not in {"approve", "activate", "needs_changes", "block", "pause"}:
            raise ValueError("campaign_decision_invalid")
        bundle = self._campaign_bundle(campaign_id)
        campaign = dict(bundle.get("campaign") or {})
        submissions = list(bundle.get("review_submissions") or [])
        latest_submission = submissions[0] if submissions else None
        if latest_submission is None:
            raise ValueError("campaign_submission_missing")
        review_case_id = latest_submission.get("review_case_id") or campaign.get("primary_review_case_id")
        activation_status = {
            "approve": "approved",
            "activate": "active",
            "needs_changes": "draft",
            "block": "blocked",
            "pause": "paused",
        }[normalized_decision]
        submission_status = {
            "approve": "approved",
            "activate": "activated",
            "needs_changes": "needs_changes",
            "block": "blocked",
            "pause": "paused",
        }[normalized_decision]
        if review_case_id:
            case_status = "resolved" if normalized_decision in {"approve", "activate", "needs_changes", "block", "pause"} else "open"
            self.repository.update_review_case_status(review_case_id, status=case_status, owner_id=reviewer_id)
        self.repository.save_campaign_review_submission(
            {
                **latest_submission,
                "status": self._validate_review_status(submission_status),
                "reviewer_id": reviewer_id,
                "decision_note": note,
                "decided_at": self._utcnow(),
                "submission_payload_json": latest_submission.get("submission_payload_json", {}),
            }
        )
        self.repository.save_campaign(
            {
                **campaign,
                "activation_status": activation_status,
                "selected_channels_json": campaign.get("selected_channels_json", []),
                "selected_partner_refs_json": campaign.get("selected_partner_refs_json", []),
                "campaign_payload_json": campaign.get("campaign_payload_json", {}),
            }
        )
        result = self._campaign_bundle(campaign_id)
        self.audit.record_audit_log(
            actor_id=reviewer_id,
            actor_role="reviewer",
            account_id=campaign.get("account_id"),
            object_type="campaign",
            object_id=campaign_id,
            action_type="campaign_decided",
            source_surface="ops",
            customer_visible_payload={"campaign": result.get("campaign")},
            internal_payload={**result, "decision": normalized_decision, "note": note},
        )
        return result

    def list_campaigns(self, *, account_id: str, limit: int = 50) -> Dict[str, Any]:
        campaigns = [self._campaign_bundle(item["campaign_id"]) for item in self.repository.list_campaigns(account_id=account_id, limit=limit)]
        status_counts = Counter(str(item["campaign"].get("activation_status") or "unknown") for item in campaigns)
        return {
            "campaigns": campaigns,
            "summary": {
                "campaign_count": len(campaigns),
                "status_counts": dict(status_counts),
            },
        }

    def campaign_detail(self, *, account_id: str, campaign_id: str) -> Dict[str, Any]:
        bundle = self._campaign_bundle(campaign_id)
        if str((bundle.get("campaign") or {}).get("account_id") or "") != account_id:
            raise PermissionError("campaign_account_ownership_mismatch")
        return bundle
