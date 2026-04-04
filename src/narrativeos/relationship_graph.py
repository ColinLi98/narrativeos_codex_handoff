from __future__ import annotations

from typing import Dict, List, Optional

from .models import CharacterState, DebtEntry, NarrativeState, RelationshipEdge


RELATION_METRICS = (
    "attachment",
    "resentment",
    "shame",
    "obligation",
    "projection",
    "possession",
    "gratitude",
    "fear",
)


def edge_key(source: str, target: str) -> str:
    return "%s->%s" % (source, target)


def get_edge(state: NarrativeState, source: str, target: str) -> Optional[RelationshipEdge]:
    for edge in state.relationship_graph:
        if edge.source == source and edge.target == target:
            return edge
    return None


def ensure_edge(state: NarrativeState, source: str, target: str) -> RelationshipEdge:
    existing = get_edge(state, source, target)
    if existing is not None:
        return existing
    edge = RelationshipEdge(source=source, target=target)
    state.relationship_graph.append(edge)
    return edge


def apply_debt_deltas(state: NarrativeState, debt_deltas: List[Dict[str, object]], *, opened_at_turn: int) -> NarrativeState:
    for delta in debt_deltas:
        source = str(delta.get("source") or "")
        target = str(delta.get("target") or "")
        if not source or not target:
            continue
        edge = ensure_edge(state, source, target)
        for metric in RELATION_METRICS:
            if metric in delta:
                setattr(edge, metric, max(0.0, min(1.0, float(getattr(edge, metric)) + float(delta[metric]))))
        if delta.get("note"):
            edge.notes.append(str(delta["note"]))
        debt_type = str(delta.get("debt_type") or "")
        if debt_type:
            edge.debts.append(
                DebtEntry(
                    relation_with=target,
                    debt_type=debt_type,
                    magnitude=float(delta.get("magnitude", 0.0)),
                    opened_at_turn=opened_at_turn,
                    notes=str(delta.get("note", "")),
                )
            )
    return state


def unresolved_debt_keys(state: NarrativeState) -> List[str]:
    keys: List[str] = []
    for edge in state.relationship_graph:
        for debt in edge.debts:
            if debt.magnitude > 0:
                keys.append("%s:%s:%s" % (edge.source, edge.target, debt.debt_type))
    return list(dict.fromkeys(keys))


def sync_character_debts(state: NarrativeState) -> NarrativeState:
    per_character: Dict[str, List[DebtEntry]] = {character_id: [] for character_id in state.characters}
    for edge in state.relationship_graph:
        per_character.setdefault(edge.source, [])
        for debt in edge.debts:
            per_character[edge.source].append(DebtEntry.from_dict(debt.to_dict()))
    for character_id, character in state.characters.items():
        character.debts = per_character.get(character_id, [])
    return state


def relation_pressure_for_actor(state: NarrativeState, actor_id: str, counterpart_ids: List[str]) -> float:
    magnitudes: List[float] = []
    for counterpart_id in counterpart_ids:
        edge = get_edge(state, actor_id, counterpart_id)
        if edge is None:
            continue
        relation_weight = (
            edge.attachment
            + edge.resentment
            + edge.shame
            + edge.obligation
            + edge.projection
            + edge.possession
            + edge.gratitude
            + edge.fear
        ) / float(len(RELATION_METRICS))
        debt_weight = sum(debt.magnitude for debt in edge.debts)
        magnitudes.append(min(1.0, relation_weight + 0.25 * debt_weight))
    return sum(magnitudes) / len(magnitudes) if magnitudes else 0.0


def summarize_relationship_changes(before: NarrativeState, after: NarrativeState) -> List[str]:
    changes: List[str] = []
    for edge in after.relationship_graph:
        prev = get_edge(before, edge.source, edge.target)
        if prev is None:
            if edge.debts:
                changes.append("%s对%s多了一笔说不清的亏欠。" % (before.characters[edge.source].name, before.characters[edge.target].name))
            continue
        if edge.attachment > prev.attachment + 0.05:
            changes.append("%s对%s更难放下。" % (before.characters[edge.source].name, before.characters[edge.target].name))
        if edge.resentment > prev.resentment + 0.05:
            changes.append("%s心里对%s多了一层怨。" % (before.characters[edge.source].name, before.characters[edge.target].name))
    return list(dict.fromkeys(changes))
