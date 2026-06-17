from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[3]

DEFAULT_BUNDLE_SOURCES = (
    {"source": "docs/commercial_customer_delivery_pack.md", "target": "docs/commercial_customer_delivery_pack.md", "required": True},
    {"source": "docs/commercial_customer_acceptance_checklist.md", "target": "docs/commercial_customer_acceptance_checklist.md", "required": True},
    {"source": "docs/stripe_sandbox_external_acceptance_record.md", "target": "docs/stripe_sandbox_external_acceptance_record.md", "required": True},
    {"source": "artifacts/commercialization_uat/latest/summary.json", "target": "evidence/commercialization_uat_summary.json", "required": True},
    {"source": "artifacts/commercialization_uat/latest/report.md", "target": "evidence/commercialization_uat_report.md", "required": True},
    {"source": "artifacts/commercialization_uat/latest/customer_signoff_packet.md", "target": "evidence/customer_signoff_packet.md", "required": True},
    {"source": "artifacts/stripe_external_acceptance/latest/external_acceptance_summary.json", "target": "evidence/stripe_external_acceptance_summary.json", "required": True},
    {"source": "artifacts/stripe_external_acceptance/latest/external_acceptance_record.md", "target": "evidence/stripe_external_acceptance_record.md", "required": True},
    {"source": "artifacts/stripe_external_acceptance/latest/reader_checkout_verification.json", "target": "evidence/reader_checkout_verification.json", "required": False},
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return f"commercial_delivery_bundle_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_sources(bundle_dir: Path) -> List[Dict[str, Any]]:
    copied: List[Dict[str, Any]] = []
    for item in DEFAULT_BUNDLE_SOURCES:
        source_rel = str(item["source"])
        target_rel = str(item["target"])
        source = ROOT / source_rel
        if not source.exists():
            if bool(item.get("required", True)):
                raise FileNotFoundError(f"missing_bundle_source:{source_rel}")
            continue
        target = bundle_dir / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(
            {
                "source": source_rel,
                "target": target_rel,
                "size_bytes": target.stat().st_size,
                "sha256": _sha256(target),
            }
        )
    return copied


def _build_signoff_summary(bundle_dir: Path, *, uat_summary: Dict[str, Any], stripe_summary: Dict[str, Any]) -> Path:
    acceptance = stripe_summary.get("acceptance") or {}
    lines = [
        "# Customer Signoff Summary",
        "",
        f"- generated_at: {_utcnow()}",
        f"- bundle_status: {'ready_for_signature' if acceptance.get('all_passed') else 'blocked'}",
        "",
        "## Included Evidence",
        "- commercial customer delivery pack",
        "- customer acceptance checklist",
        "- local commercialization UAT evidence",
        "- Stripe sandbox external acceptance evidence",
        "",
        "## Key Commercial Outcomes",
        f"- canonical invoice preview due: {(uat_summary.get('journey') or {}).get('invoice_preview', {}).get('total_due_usd')}",
        f"- external provider invoice due: {(stripe_summary.get('invoice') or {}).get('invoice_payload_json', {}).get('amount_due')}",
        f"- external provider invoice line_count: {(stripe_summary.get('invoice') or {}).get('invoice_payload_json', {}).get('lines', {}).get('total_count')}",
        f"- invoice final status: {(stripe_summary.get('invoice') or {}).get('status')}",
        f"- dunning final status: {(stripe_summary.get('dunning_summary') or {}).get('status')}",
        f"- renewal status: {(stripe_summary.get('renewal_summary') or {}).get('status')}",
        f"- upgrade recommendation: {(stripe_summary.get('expansion_summary') or {}).get('recommended_plan_id')}",
        "",
        "## Acceptance Checks",
    ]
    for key, value in acceptance.items():
        lines.append(f"- {key}: {value}")
    path = bundle_dir / "customer_signoff_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _build_evidence_index(bundle_dir: Path, copied_files: List[Dict[str, Any]]) -> Path:
    path = bundle_dir / "evidence_index.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["source", "target", "size_bytes", "sha256"])
        writer.writeheader()
        for item in copied_files:
            writer.writerow(item)
    return path


def _build_manifest(bundle_dir: Path, *, copied_files: List[Dict[str, Any]]) -> Path:
    uat_summary = _load_json(bundle_dir / "evidence/commercialization_uat_summary.json")
    stripe_summary = _load_json(bundle_dir / "evidence/stripe_external_acceptance_summary.json")
    manifest = {
        "bundle_id": bundle_dir.name,
        "generated_at": _utcnow(),
        "bundle_status": "ready_for_signature" if (stripe_summary.get("acceptance") or {}).get("all_passed") else "blocked",
        "included_files": copied_files,
        "evidence_summary": {
            "commercialization_uat_passed": bool((uat_summary.get("acceptance") or {}).get("all_passed")),
            "stripe_external_acceptance_passed": bool((stripe_summary.get("acceptance") or {}).get("all_passed")),
            "invoice_status": (stripe_summary.get("invoice") or {}).get("status"),
            "renewal_status": (stripe_summary.get("renewal_summary") or {}).get("status"),
            "dunning_status": (stripe_summary.get("dunning_summary") or {}).get("status"),
            "upgrade_recommendation": (stripe_summary.get("expansion_summary") or {}).get("recommended_plan_id"),
        },
    }
    path = bundle_dir / "bundle_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _build_readme(bundle_dir: Path) -> Path:
    text = "\n".join(
        [
            "# Commercial Delivery Bundle",
            "",
            "This bundle is the final customer-facing signature / delivery / acceptance pack.",
            "",
            "## Start Here",
            "- `customer_signoff_summary.md`",
            "- `docs/commercial_customer_delivery_pack.md`",
            "- `docs/commercial_customer_acceptance_checklist.md`",
            "",
            "## Evidence",
            "- `evidence/commercialization_uat_summary.json`",
            "- `evidence/stripe_external_acceptance_summary.json`",
            "- `evidence/customer_signoff_packet.md`",
            "",
            "## Notes",
            "- customer-safe only",
            "- no webhook secrets included",
            "- no local sqlite databases included",
        ]
    )
    path = bundle_dir / "README.md"
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _zip_bundle(bundle_dir: Path) -> Path:
    zip_path = bundle_dir.parent / f"{bundle_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(bundle_dir))
    return zip_path


def build_commercial_delivery_bundle(output_root: str | Path | None = None) -> Dict[str, Any]:
    run_id = _run_id()
    bundle_dir = Path(output_root) if output_root else (ROOT / "artifacts" / "commercial_delivery_bundle" / run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    copied_files = _copy_sources(bundle_dir)
    uat_summary = _load_json(bundle_dir / "evidence/commercialization_uat_summary.json")
    stripe_summary = _load_json(bundle_dir / "evidence/stripe_external_acceptance_summary.json")
    signoff_summary = _build_signoff_summary(bundle_dir, uat_summary=uat_summary, stripe_summary=stripe_summary)
    evidence_index = _build_evidence_index(bundle_dir, copied_files)
    manifest = _build_manifest(bundle_dir, copied_files=copied_files)
    readme = _build_readme(bundle_dir)
    zip_path = _zip_bundle(bundle_dir)

    latest_dir = bundle_dir.parent / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(bundle_dir, latest_dir)

    return {
        "bundle_id": bundle_dir.name,
        "bundle_dir": str(bundle_dir),
        "latest_dir": str(latest_dir),
        "zip_path": str(zip_path),
        "readme": str(readme.relative_to(bundle_dir)),
        "manifest": str(manifest.relative_to(bundle_dir)),
        "signoff_summary": str(signoff_summary.relative_to(bundle_dir)),
        "evidence_index": str(evidence_index.relative_to(bundle_dir)),
        "acceptance_passed": bool((stripe_summary.get("acceptance") or {}).get("all_passed")),
        "included_file_count": len(copied_files) + 4,
    }
