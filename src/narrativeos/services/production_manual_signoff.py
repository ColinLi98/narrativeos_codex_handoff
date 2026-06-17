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
    return f"production_manual_signoff_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manual_items(go_live: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in list(go_live.get("items") or []):
        if item.get("status") != "manual_confirm":
            continue
        prompt = {
            "billing_005": "Confirm live Stripe secret/publishable keys are configured in the production secret manager and the deployment environment points at them.",
            "webhook_001": "Confirm the production webhook endpoint is registered in Stripe, reachable over HTTPS, and the production signing secret matches the server config.",
            "security_003": "Confirm production log drains, customer-safe retention policy, and access boundaries are reviewed by the security/ops owner.",
            "operations_003": "Confirm named on-call owner, finance owner, and support owner are assigned for launch week.",
            "deploy_002": "Confirm production Postgres backup/restore tooling and operator access are available and tested.",
        }.get(item.get("item_id") or "", item.get("notes") or "")
        rows.append(
            {
                "item_id": item.get("item_id"),
                "category": item.get("category"),
                "label": item.get("label"),
                "evidence": item.get("evidence"),
                "prompt": prompt,
                "owner": "",
                "status": "pending_manual_signoff",
                "decision": "",
                "decision_at": "",
                "notes": item.get("notes") or "",
            }
        )
    return rows


def _write_markdown(path: Path, *, worksheet: List[Dict[str, Any]], go_live_summary: Dict[str, Any]) -> None:
    lines = [
        "# Production Manual Signoff Walk-Through",
        "",
        f"- generated_at: {_utcnow()}",
        f"- source_checklist: {go_live_summary.get('checklist_id')}",
        f"- manual_items: {len(worksheet)}",
        "",
        "Use this worksheet to complete the remaining production-only confirmations.",
        "",
    ]
    for item in worksheet:
        lines.extend(
            [
                f"## {item['item_id']} — {item['label']}",
                f"- category: {item['category']}",
                f"- evidence: {item['evidence']}",
                f"- prompt: {item['prompt']}",
                "- owner: ",
                "- decision: pending / approved / rejected",
                "- decision_at: ",
                "- notes: ",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, worksheet: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["item_id", "category", "label", "evidence", "prompt", "owner", "status", "decision", "decision_at", "notes"],
        )
        writer.writeheader()
        for item in worksheet:
            writer.writerow(item)


def _zip_bundle(bundle_dir: Path) -> Path:
    zip_path = bundle_dir.parent / f"{bundle_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(bundle_dir))
    return zip_path


def build_production_manual_signoff_bundle(output_root: str | Path | None = None) -> Dict[str, Any]:
    run_id = _run_id()
    bundle_dir = Path(output_root) if output_root else (ROOT / "artifacts" / "production_manual_signoff" / run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    go_live_summary = _load_json(ROOT / "artifacts/production_go_live_checklist/latest/go_live_checklist.json")
    worksheet = _manual_items(go_live_summary)

    (bundle_dir / "manual_signoff_sheet.json").write_text(json.dumps({"items": worksheet}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(bundle_dir / "manual_signoff_walkthrough.md", worksheet=worksheet, go_live_summary=go_live_summary)
    _write_csv(bundle_dir / "manual_signoff_sheet.csv", worksheet)
    (bundle_dir / "README.md").write_text(
        "\n".join(
            [
                "# Production Manual Signoff Walk-Through",
                "",
                "- `manual_signoff_walkthrough.md` is the operator walkthrough version",
                "- `manual_signoff_sheet.csv` is the editable spreadsheet-friendly version",
                "- `manual_signoff_sheet.json` is the machine-readable version",
                "",
                "This bundle only contains the remaining production-only signoff items.",
            ]
        ),
        encoding="utf-8",
    )

    manifest = {
        "generated_at": _utcnow(),
        "source_checklist_id": go_live_summary.get("checklist_id"),
        "manual_item_count": len(worksheet),
        "items": [item["item_id"] for item in worksheet],
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
        "bundle_id": bundle_dir.name,
        "bundle_dir": str(bundle_dir),
        "latest_dir": str(latest_dir),
        "zip_path": str(zip_path),
        "manual_item_count": len(worksheet),
    }
