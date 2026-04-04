from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .critics import BaseCritic, default_critics
from .memory import apply_event
from .models import CandidateBatch, CriticDecision, EventAtom, NarrativeState, RouteCandidate, ScoredCandidate, SearchWeights, WorldBible
from .providers import CandidateProvider, StaticCandidateProvider
from .scoring import score_event


@dataclass
class BeamNode:
    state: NarrativeState
    events: List[EventAtom]
    total_score: float
    score_breakdown: Dict[str, float]
    critic_trace: List[Dict[str, object]]

    @property
    def explanation(self) -> str:
        event_ids = " -> ".join(event.event_id for event in self.events)
        return "route=%s; total_score=%.3f" % (event_ids, self.total_score)


def _critic_decisions_by_event(
    state: NarrativeState,
    world: WorldBible,
    candidates: Sequence[EventAtom],
    critics: Sequence[BaseCritic],
) -> Dict[str, List[Dict[str, object]]]:
    decisions: Dict[str, List[Dict[str, object]]] = {event.event_id: [] for event in candidates}

    for critic in critics:
        batch_decisions = critic.evaluate_batch(state, candidates, world)
        for event in candidates:
            decision = batch_decisions.get(event.event_id)
            if decision is not None:
                decisions[event.event_id].append(decision.to_dict())

    for critic in critics:
        for event in candidates:
            decision = critic.evaluate(state, event, world)
            if decision.reasons:
                decisions[event.event_id].append(decision.to_dict())

    return decisions


def evaluate_candidates(
    state: NarrativeState,
    world: WorldBible,
    *,
    candidate_provider: CandidateProvider,
    critics: Optional[Sequence[BaseCritic]] = None,
    weights: Optional[SearchWeights] = None,
    depth: int = 0,
    min_candidates: int = 6,
    max_candidates: int = 10,
) -> Tuple[CandidateBatch, List[ScoredCandidate]]:
    critics = list(critics or default_critics())
    candidate_batch = candidate_provider.generate(
        state,
        world,
        depth=depth,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    legal_candidates = list(candidate_batch.legal_candidates)
    decision_map = _critic_decisions_by_event(state, world, legal_candidates, critics)

    rejected_event_ids = []
    scored_candidates: List[ScoredCandidate] = []
    for event in legal_candidates:
        decisions = decision_map.get(event.event_id, [])
        verdicts = [decision["verdict"] for decision in decisions]
        if "reject" in verdicts:
            rejected_event_ids.append(event.event_id)
            continue

        base = score_event(
            state,
            event,
            weights=weights,
            sibling_events=legal_candidates,
            world=world,
        )
        critic_penalty = sum(float(decision.get("score_adjustment", 0.0)) for decision in decisions)
        base.total_score = max(0.0, base.total_score + critic_penalty)
        base.critic_penalty = critic_penalty
        base.critic_decisions = [CriticDecision.from_dict(decision) for decision in decisions]
        base.provider_debug = {
            "provider": candidate_batch.debug.get("provider", "unknown"),
            "depth": depth,
        }
        if decisions:
            verdict_summary = ", ".join(
                "%s:%s" % (decision["critic_name"], decision["verdict"]) for decision in decisions
            )
            base.explanation = "%s; critics=%s" % (base.explanation, verdict_summary)
        scored_candidates.append(base)

    scored_candidates.sort(
        key=lambda candidate: (-candidate.total_score, candidate.event.event_id)
    )
    candidate_batch.debug["critic_rejections"] = rejected_event_ids
    return candidate_batch, scored_candidates


def beam_search(
    initial_state: NarrativeState,
    *,
    world: WorldBible,
    candidate_provider: CandidateProvider,
    critics: Optional[Sequence[BaseCritic]] = None,
    depth: int = 2,
    beam_width: int = 3,
    weights: Optional[SearchWeights] = None,
    min_candidates: int = 6,
    max_candidates: int = 10,
) -> List[RouteCandidate]:
    critics = list(critics or default_critics())
    beams = [
        BeamNode(
            state=initial_state,
            events=[],
            total_score=0.0,
            score_breakdown={},
            critic_trace=[],
        )
    ]

    for current_depth in range(depth):
        expanded: List[BeamNode] = []
        for beam in beams:
            _, scored_candidates = evaluate_candidates(
                beam.state,
                world,
                candidate_provider=candidate_provider,
                critics=critics,
                weights=weights,
                depth=current_depth,
                min_candidates=min_candidates,
                max_candidates=max_candidates,
            )
            if not scored_candidates:
                expanded.append(beam)
                continue

            for scored_candidate in scored_candidates[:beam_width]:
                next_state = apply_event(beam.state, scored_candidate.event)
                aggregate_breakdown = dict(beam.score_breakdown)
                for key, value in scored_candidate.components.items():
                    aggregate_breakdown[key] = aggregate_breakdown.get(key, 0.0) + value

                expanded.append(
                    BeamNode(
                        state=next_state,
                        events=beam.events + [scored_candidate.event],
                        total_score=beam.total_score + scored_candidate.total_score,
                        score_breakdown=aggregate_breakdown,
                        critic_trace=beam.critic_trace
                        + [
                            {
                                "event_id": scored_candidate.event.event_id,
                                "total_score": scored_candidate.total_score,
                                "critic_penalty": scored_candidate.critic_penalty,
                                "components": dict(scored_candidate.components),
                                "critic_decisions": [
                                    decision.to_dict() for decision in scored_candidate.critic_decisions
                                ],
                                "explanation": scored_candidate.explanation,
                            }
                        ],
                    )
                )

        expanded.sort(key=lambda node: (-node.total_score, [event.event_id for event in node.events]))
        beams = expanded[:beam_width]

    results: List[RouteCandidate] = []
    for beam in beams:
        averaged_breakdown = {
            key: value / float(max(len(beam.events), 1))
            for key, value in beam.score_breakdown.items()
        }
        results.append(
            RouteCandidate(
                events=beam.events,
                total_score=beam.total_score,
                score_breakdown=averaged_breakdown,
                critic_trace=beam.critic_trace,
                explanation=beam.explanation,
            )
        )
    results.sort(key=lambda route: (-route.total_score, route.to_dict()["event_ids"]))
    return results


def static_candidate_provider(event_pool: Sequence[EventAtom]) -> CandidateProvider:
    return StaticCandidateProvider(event_pool)
