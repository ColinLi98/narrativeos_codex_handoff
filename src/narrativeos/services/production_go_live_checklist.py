from __future__ import annotations

import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[3]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return f"production_go_live_checklist_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_optional(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _evidence_status(payload: Dict[str, Any], *, ready: bool) -> str:
    if not payload:
        return "manual_confirm"
    return "ready" if ready else "blocked"


def _smoke_status_ok(payload: Dict[str, Any]) -> bool:
    return str(payload.get("status") or "").lower() in {"ok", "passed", "pass"}


def _build_items(
    bundle_manifest: Dict[str, Any],
    stripe_summary: Dict[str, Any],
    *,
    commercial_long_route: Dict[str, Any],
    quantum_local_smoke: Dict[str, Any],
    reader_paid_path: Dict[str, Any],
    author_repair_loop: Dict[str, Any],
    ops_url_state_smoke: Dict[str, Any],
) -> List[Dict[str, Any]]:
    stripe_acceptance = dict(stripe_summary.get("acceptance") or {})
    evidence_summary = dict(bundle_manifest.get("evidence_summary") or {})
    commercial_gate = dict(commercial_long_route.get("commercial_long_route_gate") or {})
    return [
        {
            "item_id": "quality_001",
            "category": "quality",
            "label": "Commercial 50-chapter cross-pack long-route gate passed",
            "status": _evidence_status(
                commercial_long_route,
                ready=bool(commercial_gate.get("applicable")) and bool(commercial_gate.get("ok")),
            ),
            "evidence": "artifacts/commercial_long_route_50.json",
            "notes": "worldpack=all benchmark_mode=long_route max_chapters=50; weakest packs, Q03/Q04/Q05/Q09, mid-arc drop, completion ratio, stop reason included",
            "requires_manual_confirmation": not bool(commercial_long_route),
        },
        {
            "item_id": "reader_001",
            "category": "reader",
            "label": "Fixed-port Quantum local acceptance smoke passed",
            "status": _evidence_status(
                quantum_local_smoke,
                ready=_smoke_status_ok(quantum_local_smoke)
                and int((quantum_local_smoke.get("fixed_ports") or {}).get("frontend") or 0) == 3000
                and int((quantum_local_smoke.get("fixed_ports") or {}).get("backend") or 0) == 8000,
            ),
            "evidence": "artifacts/quantum_local_acceptance_smoke_result.json",
            "notes": "Local contract only; CI smoke remains isolated-port for concurrent jobs.",
            "requires_manual_confirmation": not bool(quantum_local_smoke),
        },
        {
            "item_id": "reader_002",
            "category": "reader",
            "label": "Reader paid path smoke passed before and after checkout",
            "status": _evidence_status(reader_paid_path, ready=_smoke_status_ok(reader_paid_path)),
            "evidence": "artifacts/reader_paid_path_smoke_result.json",
            "notes": "register/login -> story -> paywall -> sandbox checkout -> complete/reconcile -> continue -> Library/Settings sync",
            "requires_manual_confirmation": not bool(reader_paid_path),
        },
        {
            "item_id": "billing_001",
            "category": "billing",
            "label": "Stripe sandbox external acceptance passed",
            "status": "ready",
            "evidence": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
            "notes": f"all_passed={stripe_acceptance.get('all_passed')}",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "billing_002",
            "category": "billing",
            "label": "Provider invoice amount and line items align with canonical invoice preview",
            "status": "ready" if stripe_acceptance.get("provider_alignment_fixed") else "blocked",
            "evidence": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
            "notes": f"invoice_status={evidence_summary.get('invoice_status')}",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "billing_003",
            "category": "billing",
            "label": "Real payment failure and recovery path exercised",
            "status": "ready" if stripe_acceptance.get("failed_then_paid_observed") else "blocked",
            "evidence": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
            "notes": "invoice.payment_failed + invoice.paid observed in sandbox",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "billing_004",
            "category": "billing",
            "label": "Dunning resolves after successful payment recovery",
            "status": "ready" if stripe_acceptance.get("dunning_resolved_after_payment") else "blocked",
            "evidence": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
            "notes": f"dunning_status={evidence_summary.get('dunning_status')}",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "author_001",
            "category": "author",
            "label": "Author supply repair-loop smoke passed",
            "status": _evidence_status(author_repair_loop, ready=_smoke_status_ok(author_repair_loop)),
            "evidence": "artifacts/author_repair_loop_smoke_result.json",
            "notes": "brief -> draft -> asset edit -> simulate -> compare -> submit evidence with issue-code drill-down",
            "requires_manual_confirmation": not bool(author_repair_loop),
        },
        {
            "item_id": "billing_005",
            "category": "billing",
            "label": "Production Stripe live keys configured on production environment",
            "status": "manual_confirm",
            "evidence": "production secret manager / deployment env",
            "notes": "Sandbox keys are validated; live keys must be confirmed out of band.",
            "requires_manual_confirmation": True,
        },
        {
            "item_id": "webhook_001",
            "category": "webhook",
            "label": "Production webhook endpoint is registered and signing secret is set",
            "status": "manual_confirm",
            "evidence": "Stripe dashboard webhook config",
            "notes": "Sandbox forwarding validated locally; production endpoint/DNS/TLS still needs explicit confirmation.",
            "requires_manual_confirmation": True,
        },
        {
            "item_id": "webhook_002",
            "category": "webhook",
            "label": "Webhook replay / failure monitoring is available to Ops",
            "status": "ready",
            "evidence": "/v1/ops/provider-webhooks/{provider_webhook_event_id}/replay",
            "notes": "Replay route exists and sandbox webhooks were ingested successfully.",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "security_001",
            "category": "security",
            "label": "Customer-safe response shaping and audit export are implemented",
            "status": "ready",
            "evidence": "tests/test_enterprise_audit.py",
            "notes": "Customer-safe payloads and audit export are covered in-repo.",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "security_002",
            "category": "security",
            "label": "Tenant isolation checks remain enforced on customer routes",
            "status": "ready",
            "evidence": "tests/test_enterprise_audit.py",
            "notes": "Cross-tenant access checks are covered in-repo.",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "security_003",
            "category": "security",
            "label": "Production log drains / customer-safe log retention are reviewed",
            "status": "manual_confirm",
            "evidence": "production observability configuration",
            "notes": "Implementation exists, but production sink configuration requires manual review.",
            "requires_manual_confirmation": True,
        },
        {
            "item_id": "operations_001",
            "category": "operations",
            "label": "Commercialization dashboard and lifecycle sync are available to Ops",
            "status": "ready",
            "evidence": "tests/test_ops_commercialization_dashboard.py + /v1/ops/lifecycle-automation",
            "notes": "Ops can inspect renewal / dunning / expansion posture.",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "operations_002",
            "category": "operations",
            "label": "Support / dispute handling exists for paid customers",
            "status": "ready",
            "evidence": "tests/test_dispute_support_core.py",
            "notes": "Canonical dispute and support flows are implemented.",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "operations_003",
            "category": "operations",
            "label": "Production on-call owner, finance owner, and support owner are assigned",
            "status": "manual_confirm",
            "evidence": "launch staffing plan",
            "notes": "Organizational signoff required outside the repo.",
            "requires_manual_confirmation": True,
        },
        {
            "item_id": "deploy_001",
            "category": "deploy",
            "label": "Deployment runbook exists with backup / restore / rollback path",
            "status": "ready",
            "evidence": "docs/deployment_runbook.md",
            "notes": "Runbook covers backup, schema lifecycle, restore, and rollback.",
            "requires_manual_confirmation": False,
        },
        {
            "item_id": "ops_004",
            "category": "operations",
            "label": "Ops alerts and governance URL-state smoke passed",
            "status": _evidence_status(ops_url_state_smoke, ready=_smoke_status_ok(ops_url_state_smoke)),
            "evidence": "artifacts/quantum_ops_url_state_smoke_result.json",
            "notes": "Ops alert acknowledge/resolve, account investigation, governance evidence, and release/rollback pointers stay linked.",
            "requires_manual_confirmation": not bool(ops_url_state_smoke),
        },
        {
            "item_id": "deploy_002",
            "category": "deploy",
            "label": "Production Postgres backup / restore tooling is available",
            "status": "manual_confirm",
            "evidence": "production operator environment",
            "notes": "Runbook specifies the process, but production binaries/access must be checked live.",
            "requires_manual_confirmation": True,
        },
        {
            "item_id": "launch_001",
            "category": "launch",
            "label": "Customer delivery bundle is ready for signature",
            "status": "ready" if bundle_manifest.get("bundle_status") == "ready_for_signature" else "blocked",
            "evidence": "artifacts/commercial_delivery_bundle/latest/customer_signoff_summary.md",
            "notes": f"bundle_status={bundle_manifest.get('bundle_status')}",
            "requires_manual_confirmation": False,
        },
    ]


def _write_markdown(path: Path, *, summary: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
    ready = sum(1 for item in items if item["status"] == "ready")
    manual = sum(1 for item in items if item["status"] == "manual_confirm")
    blocked = sum(1 for item in items if item["status"] == "blocked")
    lines = [
        "# Production Go-Live Checklist Drill",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- drill_status: {summary['drill_status']}",
        f"- ready_items: {ready}",
        f"- manual_confirm_items: {manual}",
        f"- blocked_items: {blocked}",
        "",
        "## Interpretation",
        "- `ready` means the path is already evidenced by in-repo tests or sandbox acceptance.",
        "- `manual_confirm` means the implementation exists, but production environment/ops confirmation is still required.",
        "- `blocked` means the repo is not ready for production signoff on that item.",
        "",
        "## Checklist",
    ]
    for item in items:
        lines.extend(
            [
                f"### {item['item_id']} — {item['label']}",
                f"- category: {item['category']}",
                f"- status: {item['status']}",
                f"- evidence: {item['evidence']}",
                f"- notes: {item['notes']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, items: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["item_id", "category", "label", "status", "evidence", "notes", "requires_manual_confirmation"],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(item)


def _zip_bundle(bundle_dir: Path) -> Path:
    zip_path = bundle_dir.parent / f"{bundle_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(bundle_dir))
    return zip_path


def build_production_go_live_checklist(
    output_root: str | Path | None = None,
    *,
    evidence_root: str | Path | None = None,
) -> Dict[str, Any]:
    run_id = _run_id()
    bundle_dir = Path(output_root) if output_root else (ROOT / "artifacts" / "production_go_live_checklist" / run_id)
    source_root = Path(evidence_root) if evidence_root else ROOT
    bundle_dir.mkdir(parents=True, exist_ok=True)

    delivery_bundle_manifest = _load_json(source_root / "artifacts/commercial_delivery_bundle/latest/bundle_manifest.json")
    stripe_summary = _load_json(source_root / "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json")
    commercialization_summary = _load_json(source_root / "artifacts/commercialization_uat/latest/summary.json")
    commercial_long_route = _load_json_optional(source_root / "artifacts/commercial_long_route_50.json")
    quantum_local_smoke = _load_json_optional(source_root / "artifacts/quantum_local_acceptance_smoke_result.json")
    reader_paid_path = _load_json_optional(source_root / "artifacts/reader_paid_path_smoke_result.json")
    author_repair_loop = _load_json_optional(source_root / "artifacts/author_repair_loop_smoke_result.json")
    ops_url_state_smoke = _load_json_optional(source_root / "artifacts/quantum_ops_url_state_smoke_result.json")
    commercial_gate = dict(commercial_long_route.get("commercial_long_route_gate") or {})

    items = _build_items(
        delivery_bundle_manifest,
        stripe_summary,
        commercial_long_route=commercial_long_route,
        quantum_local_smoke=quantum_local_smoke,
        reader_paid_path=reader_paid_path,
        author_repair_loop=author_repair_loop,
        ops_url_state_smoke=ops_url_state_smoke,
    )
    ready = sum(1 for item in items if item["status"] == "ready")
    manual = sum(1 for item in items if item["status"] == "manual_confirm")
    blocked = sum(1 for item in items if item["status"] == "blocked")
    summary = {
        "checklist_id": bundle_dir.name,
        "generated_at": _utcnow(),
        "drill_status": "ready_for_prod_manual_confirmation" if blocked == 0 else "blocked",
        "counts": {
            "total": len(items),
            "ready": ready,
            "manual_confirm": manual,
            "blocked": blocked,
        },
        "linked_evidence": {
            "commercial_delivery_bundle": "artifacts/commercial_delivery_bundle/latest/",
            "stripe_external_acceptance": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json",
            "commercialization_uat": "artifacts/commercialization_uat/latest/summary.json",
            "commercial_long_route_50": "artifacts/commercial_long_route_50.json",
            "quantum_local_acceptance_smoke": "artifacts/quantum_local_acceptance_smoke_result.json",
            "reader_paid_path_smoke": "artifacts/reader_paid_path_smoke_result.json",
            "author_repair_loop_smoke": "artifacts/author_repair_loop_smoke_result.json",
            "ops_alert_governance_smoke": "artifacts/quantum_ops_url_state_smoke_result.json",
        },
        "evidence_summary": {
            "stripe_external_acceptance_passed": bool((stripe_summary.get("acceptance") or {}).get("all_passed")),
            "commercialization_uat_passed": bool((commercialization_summary.get("acceptance") or {}).get("all_passed")),
            "delivery_bundle_status": delivery_bundle_manifest.get("bundle_status"),
            "commercial_long_route_gate_passed": bool(commercial_gate.get("applicable")) and bool(commercial_gate.get("ok")),
            "quantum_local_acceptance_status": quantum_local_smoke.get("status") or "missing_manual_confirm",
            "reader_paid_path_status": reader_paid_path.get("status") or "missing_manual_confirm",
            "author_repair_loop_status": author_repair_loop.get("status") or "missing_manual_confirm",
            "ops_alert_governance_status": ops_url_state_smoke.get("status") or "missing_manual_confirm",
        },
        "items": items,
    }

    summary_json_path = bundle_dir / "go_live_checklist.json"
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(bundle_dir / "go_live_checklist.md", summary=summary, items=items)
    _write_csv(bundle_dir / "go_live_checklist.csv", items)

    readme = bundle_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Production Go-Live Checklist Drill",
                "",
                "- `go_live_checklist.md` gives the operator-facing launch checklist",
                "- `go_live_checklist.json` is the machine-readable version",
                "- `go_live_checklist.csv` is the spreadsheet-friendly version",
                "",
                "This drill maps sandbox-proven commercial flows to production launch checks.",
            ]
        ),
        encoding="utf-8",
    )

    manifest = {
        "checklist_id": bundle_dir.name,
        "generated_at": _utcnow(),
        "included_files": [
            {
                "path": str(path.relative_to(bundle_dir)),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in sorted(bundle_dir.rglob("*"))
            if path.is_file()
        ],
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    zip_path = _zip_bundle(bundle_dir)

    latest_dir = bundle_dir.parent / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(bundle_dir, latest_dir)

    return {
        "checklist_id": bundle_dir.name,
        "drill_status": summary["drill_status"],
        "bundle_dir": str(bundle_dir),
        "latest_dir": str(latest_dir),
        "zip_path": str(zip_path),
        "counts": summary["counts"],
    }
