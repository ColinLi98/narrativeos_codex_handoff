from __future__ import annotations

from typing import Any, Dict


def policy_guard(worldpack: Dict[str, Any], *, reader_band: str = "adult", region: str = "default") -> Dict[str, Any]:
    risk_policy = dict(worldpack.get("risk_policy", {}))
    manifest = dict(worldpack.get("manifest", {}))
    risk_rating = manifest.get("risk_rating", "PG-13")
    blocked = False
    reasons = []
    if reader_band == "teen" and risk_rating in {"R", "18+"}:
        blocked = True
        reasons.append("reader_band_risk_block")
    if risk_policy.get("requires_manual_review") and worldpack.get("status") != "published":
        reasons.append("manual_review_required")
    return {
        "allowed": not blocked,
        "risk_rating": risk_rating,
        "region": region,
        "reasons": reasons,
    }
