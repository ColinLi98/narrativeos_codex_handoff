from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


def build_seed_payload(database_url: str) -> dict:
    repository = SQLAlchemyRepository(database_url=database_url)
    app = create_app(repository=repository)
    registry = FileSystemWorldRegistry()

    account_id = "acct_ops_nav_smoke"
    stale_alert_id = "support_issue::acct_ops_nav_smoke::stale_alert"

    pack = registry.get_published_world("urban_mystery_lotus_lane")["worldpack"]
    pack["version"] = "0.9.9"
    pack["manifest"]["author_id"] = account_id

    draft = app.state.authoring_service.save_draft(pack)
    world_id = draft["world_id"]
    world_version_id = draft["world_version_id"]
    app.state.authoring_service.run_simulation_for_world_version(world_version_id)
    app.state.authoring_service.submit_for_review(world_version_id)

    app.state.analytics_service.track(
        "payment_required",
        reader_id=account_id,
        account_id=account_id,
        session_id=f"session_{account_id}",
        world_id=world_id,
        world_version_id=world_version_id,
        payload_json={"reason": "subscription_required"},
    )

    case = app.state.governance_service.create_case(
        {
            "case_type": "rights",
            "target_type": "world_version",
            "target_id": world_version_id,
            "account_id": account_id,
            "world_id": world_id,
            "world_version_id": world_version_id,
            "severity": "high",
            "summary": "ops navigation stale ref smoke case",
            "reviewer_id": "ops_smoke",
            "owner_id": "ops_smoke",
        }
    )

    return {
        "account_id": account_id,
        "world_id": world_id,
        "world_version_id": world_version_id,
        "case_id": case["case_id"],
        "stale_alert_id": stale_alert_id,
        "database_url": database_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic data for the Ops navigation stale-ref smoke flow.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = build_seed_payload(args.database_url)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
