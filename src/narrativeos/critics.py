from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Sequence

from .canon import hard_constraint_errors
from .models import CriticDecision, EventAtom, NarrativeState, PromiseLedgerEntry, WorldBible
from .scene_functions import is_terminal_scene_function, normalize_scene_function


class BaseCritic(ABC):
    name = "critic"

    def evaluate(
        self,
        state: NarrativeState,
        event: EventAtom,
        world: WorldBible,
    ) -> CriticDecision:
        return CriticDecision(critic_name=self.name, verdict="accept", reasons=[])

    def evaluate_batch(
        self,
        state: NarrativeState,
        candidates: Sequence[EventAtom],
        world: WorldBible,
    ) -> Dict[str, CriticDecision]:
        return {}


class ConsistencyCritic(BaseCritic):
    name = "consistency"

    def _overdue_promises(self, promises: Sequence[PromiseLedgerEntry], turn_index: int) -> List[str]:
        return [
            promise.promise_id
            for promise in promises
            if promise.status == "open" and promise.due_by_turn <= turn_index
        ]

    def evaluate(
        self,
        state: NarrativeState,
        event: EventAtom,
        world: WorldBible,
    ) -> CriticDecision:
        reasons = hard_constraint_errors(state, event, world=world)
        if reasons:
            return CriticDecision(
                critic_name=self.name,
                verdict="reject",
                reasons=reasons,
                suggested_fix="Satisfy canon preconditions and knowledge boundaries before surfacing this event.",
                score_adjustment=-1.0,
            )

        overdue = self._overdue_promises(state.open_promises, state.turn_index)
        unresolved = [promise_id for promise_id in overdue if promise_id not in event.promises_close]
        if unresolved:
            return CriticDecision(
                critic_name=self.name,
                verdict="revise",
                reasons=["overdue_promises:%s" % ",".join(sorted(unresolved))],
                suggested_fix="Close or explicitly worsen the overdue promise instead of sidestepping it.",
                score_adjustment=-0.08,
            )

        return CriticDecision(
            critic_name=self.name,
            verdict="accept",
            reasons=["canon_consistent"],
            metadata={"world_id": world.world_id},
        )


class DramaCritic(BaseCritic):
    name = "drama"

    def evaluate(
        self,
        state: NarrativeState,
        event: EventAtom,
        world: WorldBible,
    ) -> CriticDecision:
        reasons: List[str] = []
        verdict = "accept"
        score_adjustment = 0.0
        suggested_fix = ""

        if is_terminal_scene_function(event.scene_function, event.metadata) and state.turn_index < 7:
            return CriticDecision(
                critic_name=self.name,
                verdict="reject",
                reasons=["ending_too_early"],
                suggested_fix="Route through a cost-bearing confrontation or consequence before ending beats.",
                score_adjustment=-1.0,
            )

        if state.recent_scene_functions and normalize_scene_function(state.recent_scene_functions[-1]) == normalize_scene_function(event.scene_function):
            verdict = "revise"
            reasons.append("repeated_scene_function:%s" % event.scene_function)
            score_adjustment -= 0.05
            suggested_fix = "Change the dramatic function or escalate the cost."

        if event.tension_delta <= 0 and state.tension < 0.8 and event.scene_function not in ("debt_exchange", "vow_payment"):
            verdict = "revise"
            reasons.append("insufficient_tension_gain")
            score_adjustment -= 0.04
            suggested_fix = "Raise conflict, cost, or consequence in this beat."

        if is_terminal_scene_function(event.scene_function, event.metadata) and state.open_promises and not event.promises_close:
            verdict = "reject"
            reasons.append("ending_without_payoff")
            score_adjustment = -1.0
            suggested_fix = "Resolve or intentionally break promises before an ending beat."

        if not reasons:
            reasons.append("dramatic_progression_ok")

        return CriticDecision(
            critic_name=self.name,
            verdict=verdict,
            reasons=reasons,
            suggested_fix=suggested_fix,
            score_adjustment=score_adjustment,
            metadata={"theme_targets": list(world.creator_controls.theme_targets)},
        )


class DiversityCritic(BaseCritic):
    name = "diversity"

    def evaluate_batch(
        self,
        state: NarrativeState,
        candidates: Sequence[EventAtom],
        world: WorldBible,
    ) -> Dict[str, CriticDecision]:
        _ = state
        scene_groups: Dict[str, List[EventAtom]] = defaultdict(list)
        signature_groups: Dict[str, List[EventAtom]] = defaultdict(list)
        for event in candidates:
            scene_groups[event.scene_function].append(event)
            signature = "|".join(
                sorted(
                    list(event.tags)
                    + list(event.agency_affordances)
                    + [event.scene_function, event.convergence_key]
                )
            )
            signature_groups[signature].append(event)

        decisions: Dict[str, CriticDecision] = {}
        crowded_scenes = {
            scene_function
            for scene_function, grouped in scene_groups.items()
            if len(grouped) > max(2, len(candidates) // 2)
        }
        duplicate_event_ids = {
            grouped_event.event_id
            for grouped in signature_groups.values()
            if len(grouped) > 1
            for grouped_event in grouped
        }

        for event in candidates:
            reasons: List[str] = []
            verdict = "accept"
            score_adjustment = 0.0
            if event.scene_function in crowded_scenes:
                reasons.append("scene_function_cluster:%s" % event.scene_function)
                verdict = "revise"
                score_adjustment -= 0.03
            if event.event_id in duplicate_event_ids:
                reasons.append("near_duplicate_candidate")
                verdict = "revise"
                score_adjustment -= 0.06
            if (
                world.creator_controls.merge_policy == "discourage_early_merge"
                and event.convergence_key
                and state.turn_index <= 1
            ):
                reasons.append("early_convergence_discouraged")
                verdict = "revise"
                score_adjustment -= 0.04

            if not reasons:
                reasons.append("candidate_is_distinct_enough")

            decisions[event.event_id] = CriticDecision(
                critic_name=self.name,
                verdict=verdict,
                reasons=reasons,
                suggested_fix="Diversify scene function, motive, or convergence target.",
                score_adjustment=score_adjustment,
                metadata={
                    "crowded_scenes": sorted(crowded_scenes),
                    "duplicate_event_ids": sorted(duplicate_event_ids),
                },
            )
        return decisions


def default_critics() -> List[BaseCritic]:
    return [ConsistencyCritic(), DramaCritic(), DiversityCritic()]
