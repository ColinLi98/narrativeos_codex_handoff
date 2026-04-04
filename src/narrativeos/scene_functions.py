from __future__ import annotations

from typing import Dict


SCENE_FUNCTIONS = {
    "temptation",
    "mask_crack",
    "debt_exchange",
    "misrecognition",
    "truth_trial",
    "mercy_vs_control",
    "humiliation",
    "confession_window",
    "karma_ripening",
    "vow_payment",
    "false_peace",
}

LEGACY_SCENE_FUNCTION_MAP: Dict[str, str] = {
    "setup": "false_peace",
    "commitment": "false_peace",
    "temptation": "temptation",
    "discovery": "confession_window",
    "confrontation": "truth_trial",
    "trust_test": "truth_trial",
    "reversal": "mask_crack",
    "ordeal": "humiliation",
    "sacrifice": "vow_payment",
    "consequence": "debt_exchange",
    "reveal": "karma_ripening",
    "ending": "vow_payment",
}


def normalize_scene_function(scene_function: str) -> str:
    return LEGACY_SCENE_FUNCTION_MAP.get(scene_function, scene_function)


def is_terminal_scene_function(scene_function: str, metadata: Dict[str, object] | None = None) -> bool:
    payload = metadata or {}
    if bool(payload.get("terminal")):
        return True
    if payload.get("endgame_shape"):
        return True
    return scene_function == "vow_payment" and bool(payload.get("ending_gate"))
