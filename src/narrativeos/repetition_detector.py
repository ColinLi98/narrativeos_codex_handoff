from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from itertools import combinations
from math import sqrt
from typing import Dict, Iterable, List, Sequence, Tuple


_SPLIT_PATTERN = re.compile(r"[\s，。、“”‘’！？：；,.!?]+")
_TEXT_UNIT_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？!?]+")
_DISALLOWED_LATIN_ANCHOR_PATTERN = re.compile(r"\b[a-zA-Z_][A-Za-z0-9_]*\b")
LONG_ROUTE_SUSPICIOUS_REFRAINS = (
    "眼前这一处",
    "这一处",
    "真话窗口",
    "把每一步都接住",
    "别再漏掉",
    "真正要转向的那句终于逼到眼前",
    "被压回去的",
    "顺着此刻的局势先退半步再找一个更稳的开口",
)
SCENE_FUNCTION_LABELS = {
    "false_peace": "表面平静",
    "temptation": "试探",
    "truth_trial": "真相逼近",
    "mask_crack": "裂口",
    "confession_window": "真话窗口",
    "debt_exchange": "旧账回潮",
    "karma_ripening": "因果回响",
    "humiliation": "难堪代价",
    "vow_payment": "誓言偿付",
    "misrecognition": "误解升级",
}


def _tokenize(line: str) -> List[str]:
    return [token for token in _SPLIT_PATTERN.split(str(line or "")) if token]


def _normalized_text_units(text: str) -> str:
    return "".join(_TEXT_UNIT_PATTERN.findall(str(text or "")))


@lru_cache(maxsize=16384)
def _cached_char_ngrams(text: str, size: int) -> Tuple[str, ...]:
    normalized = _normalized_text_units(text)
    if len(normalized) < size:
        return ()
    return tuple(normalized[index : index + size] for index in range(0, len(normalized) - size + 1))


def _char_ngrams(text: str, size: int) -> List[str]:
    return list(_cached_char_ngrams(str(text or ""), int(size)))


def _jaccard_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 0.0
    return len(left_set & right_set) / float(max(1, len(left_set | right_set)))


def _build_semantic_feature_vector(text: str) -> Counter[str]:
    features: Counter[str] = Counter()
    raw_text = str(text or "")
    for token in _tokenize(raw_text):
        features[f"w:{token}"] += 1
    normalized = _normalized_text_units(raw_text)
    for size in (2, 3, 4):
        if len(normalized) < size:
            continue
        for index in range(0, len(normalized) - size + 1):
            features[f"c{size}:{normalized[index:index + size]}"] += 1
    return features


@lru_cache(maxsize=16384)
def _cached_semantic_feature_items(text: str) -> Tuple[Tuple[str, int], ...]:
    return tuple(sorted(_build_semantic_feature_vector(text).items()))


def _semantic_feature_vector(text: str) -> Counter[str]:
    return Counter(dict(_cached_semantic_feature_items(str(text or ""))))


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(float(value) * float(right.get(key, 0.0)) for key, value in left.items())
    if numerator <= 0.0:
        return 0.0
    left_norm = sqrt(sum(float(value) ** 2 for value in left.values()))
    right_norm = sqrt(sum(float(value) ** 2 for value in right.values()))
    denominator = left_norm * right_norm
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _anchor_token_coverage(paragraph: str, anchor: str) -> float:
    paragraph_units = _normalized_text_units(paragraph)
    anchor_tokens = [
        _normalized_text_units(token)
        for token in _tokenize(anchor)
        if len(_normalized_text_units(token)) >= 2
    ]
    anchor_tokens = list(dict.fromkeys(anchor_tokens))
    if not paragraph_units or not anchor_tokens:
        return 0.0
    matched = sum(1 for token in anchor_tokens if token in paragraph_units)
    return matched / float(max(1, len(anchor_tokens)))


def _paragraph_similarity_score(lines: Sequence[str]) -> Tuple[float, List[Dict[str, object]]]:
    paragraph_ngrams = [
        _char_ngrams(line, 6)
        for line in lines
    ]
    scored_pairs: List[Dict[str, object]] = []
    similarities: List[float] = []
    for (left_index, left_ngrams), (right_index, right_ngrams) in combinations(enumerate(paragraph_ngrams), 2):
        similarity = _jaccard_similarity(left_ngrams, right_ngrams)
        if similarity <= 0.0:
            continue
        similarities.append(similarity)
        scored_pairs.append(
            {
                "left_paragraph_index": left_index,
                "right_paragraph_index": right_index,
                "similarity": round(similarity, 3),
            }
        )
    scored_pairs.sort(key=lambda item: (-float(item["similarity"]), int(item["left_paragraph_index"]), int(item["right_paragraph_index"])))
    return (max(similarities) if similarities else 0.0), scored_pairs[:3]


def _semantic_paragraph_similarity_score(lines: Sequence[str]) -> Tuple[float, List[Dict[str, object]]]:
    vectors = [_semantic_feature_vector(line) for line in lines]
    scored_pairs: List[Dict[str, object]] = []
    similarities: List[float] = []
    for (left_index, left_vector), (right_index, right_vector) in combinations(enumerate(vectors), 2):
        similarity = _cosine_similarity(left_vector, right_vector)
        if similarity <= 0.0:
            continue
        similarities.append(similarity)
        scored_pairs.append(
            {
                "left_paragraph_index": left_index,
                "right_paragraph_index": right_index,
                "similarity": round(similarity, 3),
                "left_preview": str(lines[left_index])[:48],
                "right_preview": str(lines[right_index])[:48],
            }
        )
    scored_pairs.sort(key=lambda item: (-float(item["similarity"]), int(item["left_paragraph_index"]), int(item["right_paragraph_index"])))
    return (max(similarities) if similarities else 0.0), scored_pairs[:3]


def _n_gram_repetition_score(lines: Sequence[str]) -> float:
    grams: List[str] = []
    for line in lines:
        grams.extend(_char_ngrams(line, 12))
    if not grams:
        return 0.0
    counts = Counter(grams)
    repeated_distinct = sum(1 for count in counts.values() if count > 1)
    return repeated_distinct / float(len(counts))


def _length_bucket(text: str) -> str:
    size = len(_normalized_text_units(text))
    if size < 80:
        return "short"
    if size < 180:
        return "medium"
    return "long"


def _structure_signature(text: str) -> str:
    normalized = _normalized_text_units(text)
    action_markers = sum(text.count(marker) for marker in ["抬", "落", "偏", "按", "推", "站", "看", "握", "停", "拢", "压", "掠", "碰", "擦", "收", "绷", "卷", "撞", "回", "拨", "绕", "贴", "拖"])
    detail_markers = sum(text.count(marker) for marker in ["灯", "袖", "茶", "风", "门", "阶", "檐", "影", "衣", "案", "纸", "雨", "香", "窗"])
    return "|".join(
        [
            _length_bucket(text),
            "dialogue" if "“" in text else "narration",
            "hook" if any(token in text for token in ["下一次", "还会", "还没", "追上来", "没有散", "未说尽"]) else "plain",
            "action_high" if action_markers >= 8 else ("action_mid" if action_markers >= 4 else "action_low"),
            "detail_high" if detail_markers >= 6 else ("detail_mid" if detail_markers >= 3 else "detail_low"),
            normalized[:12],
        ]
    )


def _beat_structure_repetition_score(lines: Sequence[str]) -> float:
    signatures = [_structure_signature(line) for line in lines if _normalized_text_units(line)]
    if not signatures:
        return 0.0
    counts = Counter(signatures)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / float(len(signatures))


def _suspicious_refrain_count(lines: Sequence[str]) -> Tuple[int, List[str]]:
    fragments: List[str] = []
    raw_text = "\n".join(str(line or "") for line in lines)
    for line in lines:
        for sentence in _SENTENCE_SPLIT_PATTERN.split(str(line or "")):
            normalized = _normalized_text_units(sentence)
            if len(normalized) >= 14:
                fragments.append(normalized)
    counts = Counter(fragments)
    repeated = sorted(
        [fragment for fragment, count in counts.items() if count >= 2],
        key=lambda fragment: (-counts[fragment], fragment),
    )
    known_refrains = []
    normalized_raw_text = _normalized_text_units(raw_text)
    for phrase in LONG_ROUTE_SUSPICIOUS_REFRAINS:
        normalized_phrase = _normalized_text_units(phrase)
        if normalized_phrase and normalized_raw_text.count(normalized_phrase) >= 2:
            known_refrains.append(normalized_phrase)
    combined = list(dict.fromkeys(repeated + known_refrains))
    return len(combined), [fragment[:32] for fragment in combined[:3]]


def _payload_from_beat(raw: object) -> Dict[str, object]:
    if hasattr(raw, "to_dict"):
        raw = raw.to_dict()
    payload = dict(raw or {})
    event = payload.get("event") or {}
    if hasattr(event, "to_dict"):
        event = event.to_dict()
    event_payload = dict(event or {})
    return {
        "event_id": str(event_payload.get("event_id") or ""),
        "event_title": str(event_payload.get("title") or ""),
        "event_summary": str(event_payload.get("summary") or ""),
        "scene_function": str(event_payload.get("scene_function") or ""),
        "location": str(event_payload.get("location") or ""),
        "tags": [str(item) for item in list(event_payload.get("tags") or []) if str(item).strip()],
        "beat_label": str(payload.get("beat_label") or ""),
        "dramatic_job": str(payload.get("dramatic_job") or ""),
    }


def _reader_visible_anchor_text(text: str) -> str:
    cleaned = _DISALLOWED_LATIN_ANCHOR_PATTERN.sub(" ", str(text or ""))
    cleaned = re.sub(r"让人物进一步卷入[^。！？!?]*[。！？!?]?", " ", cleaned)
    cleaned = re.sub(r"这一拍不再新增事件[^。！？!?]*[。！？!?]?", " ", cleaned)
    cleaned = cleaned.replace("真正要转向的那句终于逼到眼前", " ")
    cleaned = re.sub(r"刚才没说透的态度、代价和退路都被逼到明处[。！？!?]?", " ", cleaned)
    cleaned = re.sub(r"\b中[，,]\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?:\s*[·:：/|_-]\s*){2,}", " · ", cleaned)
    return cleaned.strip(" ·:：/|_-")


def _compact_anchor_component(text: str, *, max_chars: int = 28) -> str:
    cleaned = _reader_visible_anchor_text(text)
    cleaned = re.sub(r"(?:\s*[·:：/|_-]\s*\d+\s*)+$", "", cleaned).strip(" ·:：/|_-")
    if not cleaned:
        return ""
    parts = [part.strip(" ·:：/|_-") for part in re.split(r"\s*·\s*", cleaned) if part.strip(" ·:：/|_-")]
    generic_fragments = ("真正要转向", "这一拍留下来的余波", "说出口后的余波")
    meaningful = [part for part in parts if not any(fragment in part for fragment in generic_fragments)]
    candidate = meaningful[0] if meaningful else cleaned
    return candidate[:max(4, int(max_chars))]


def _salient_anchor_terms(payload: Dict[str, object]) -> List[str]:
    terms: List[str] = []
    title = _reader_visible_anchor_text(str(payload.get("event_title") or ""))
    summary = _reader_visible_anchor_text(str(payload.get("event_summary") or ""))
    location = str(payload.get("location") or "").strip()
    scene_label = SCENE_FUNCTION_LABELS.get(str(payload.get("scene_function") or ""), "")
    for source in (title, summary):
        if not source:
            continue
        match = re.match(r"([\u4e00-\u9fff]{2,5})(?:在|把|顺着|当|借|递|没有|先|看|听|抬|走|停|接|问|逼|压)", source)
        if match:
            terms.append(match.group(1))
        for cue in ("余澄", "林绾", "徐师", "荣老太君", "书房", "回廊", "花厅", "春闱", "真话", "退路", "代价", "试探", "认", "糊涂"):
            if cue in source:
                terms.append(cue)
    if location:
        terms.append(location)
    if scene_label:
        terms.append(scene_label)
    return list(dict.fromkeys(term for term in terms if term))


def _event_anchor_text(payload: Dict[str, object]) -> str:
    scene_label = SCENE_FUNCTION_LABELS.get(str(payload.get("scene_function") or ""), "")
    salient_terms = _salient_anchor_terms(payload)
    title_anchor = _compact_anchor_component(str(payload.get("event_title") or ""), max_chars=26)
    summary_anchor = _compact_anchor_component(str(payload.get("event_summary") or ""), max_chars=30)
    tag_anchors: List[str] = []
    for raw_tag in list(payload.get("tags") or [])[:3]:
        tag_anchor = _reader_visible_anchor_text(str(raw_tag or ""))
        if not tag_anchor:
            continue
        tag_anchors.append(tag_anchor[:42])
    return _reader_visible_anchor_text(" ".join(
        item
        for item in [
            " ".join(salient_terms),
            "" if salient_terms else title_anchor,
            "" if salient_terms else summary_anchor,
            str(payload.get("location") or "").strip(),
            scene_label,
            " ".join(tag_anchors),
        ]
        if item
    ).strip())


def _beat_anchor_text(payload: Dict[str, object]) -> str:
    scene_label = SCENE_FUNCTION_LABELS.get(str(payload.get("scene_function") or ""), "")
    salient_terms = _salient_anchor_terms(payload)
    title_anchor = _compact_anchor_component(str(payload.get("event_title") or ""), max_chars=26)
    summary_anchor = _compact_anchor_component(str(payload.get("event_summary") or ""), max_chars=30)
    return _reader_visible_anchor_text(" ".join(
        item
        for item in [
            " ".join(salient_terms),
            _compact_anchor_component(str(payload.get("beat_label") or ""), max_chars=24),
            str(payload.get("dramatic_job") or "").strip(),
            scene_label,
            "" if salient_terms else title_anchor,
            "" if salient_terms else summary_anchor,
        ]
        if item
    ).strip())


def _best_anchor_scores(
    lines: Sequence[str],
    paragraph_vectors: Sequence[Counter[str]],
    anchor_texts: Sequence[str],
    anchor_vectors: Sequence[Counter[str]],
) -> List[float]:
    scores: List[float] = []
    for anchor_text, anchor_vector in zip(anchor_texts, anchor_vectors):
        vector_score = max((_cosine_similarity(paragraph_vector, anchor_vector) for paragraph_vector in paragraph_vectors), default=0.0)
        token_score = max((_anchor_token_coverage(line, anchor_text) for line in lines), default=0.0)
        score = max(vector_score, min(1.0, token_score) * 0.50)
        scores.append(score)
    return scores


def _coverage_gap_signal_bundle(
    lines: Sequence[str],
    *,
    coverage_context: Dict[str, object] | None = None,
) -> Dict[str, object]:
    context = dict(coverage_context or {})
    raw_beats = list(context.get("scene_beats") or [])
    beat_payloads = [_payload_from_beat(item) for item in raw_beats]
    selected_event_ids = list(
        dict.fromkeys(
            str(item)
            for item in list(context.get("selected_event_ids") or [])
            if str(item).strip()
        )
    )
    if selected_event_ids:
        beat_payloads = [item for item in beat_payloads if item.get("event_id") in selected_event_ids] or beat_payloads
    if not beat_payloads or not lines:
        return {
            "selected_event_ids": selected_event_ids,
            "semantic_paragraph_similarity_score": 0.0,
            "semantic_paragraph_similarity_pairs": [],
            "event_coverage_gap_score": 0.0,
            "beat_coverage_gap_score": 0.0,
            "uncovered_event_count": 0,
            "uncovered_beat_count": 0,
            "overcovered_beat_count": 0,
            "coverage_gap_examples": [],
        }

    paragraph_vectors = [_semantic_feature_vector(line) for line in lines]
    semantic_similarity_score, semantic_pairs = _semantic_paragraph_similarity_score(lines)

    event_anchors = []
    seen_event_ids = set()
    for payload in beat_payloads:
        event_id = str(payload.get("event_id") or "").strip()
        anchor_text = _event_anchor_text(payload)
        if not event_id or not anchor_text or event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        event_anchors.append(
            {
                "event_id": event_id,
                "label": payload["event_title"] or event_id,
                "text": anchor_text,
            }
        )
    beat_anchors = [
        {
            "event_id": payload["event_id"],
            "label": payload["beat_label"] or payload["event_title"] or payload["event_id"],
            "text": _beat_anchor_text(payload),
        }
        for payload in beat_payloads
        if _beat_anchor_text(payload)
    ]

    event_texts = [item["text"] for item in event_anchors]
    beat_texts = [item["text"] for item in beat_anchors]
    event_vectors = [_semantic_feature_vector(text) for text in event_texts]
    beat_vectors = [_semantic_feature_vector(text) for text in beat_texts]
    event_best_scores = _best_anchor_scores(lines, paragraph_vectors, event_texts, event_vectors) if event_vectors else []
    raw_beat_best_scores = _best_anchor_scores(lines, paragraph_vectors, beat_texts, beat_vectors) if beat_vectors else []
    event_score_by_id = {
        str(anchor.get("event_id") or ""): score
        for anchor, score in zip(event_anchors, event_best_scores)
        if str(anchor.get("event_id") or "")
    }
    beat_best_scores = [
        max(score, event_score_by_id.get(str(anchor.get("event_id") or ""), 0.0))
        for anchor, score in zip(beat_anchors, raw_beat_best_scores)
    ]

    uncovered_event_count = sum(1 for score in event_best_scores if score < 0.16)
    uncovered_beat_count = sum(1 for score in beat_best_scores if score < 0.14)

    paragraph_best_beats: List[int] = []
    for paragraph_vector in paragraph_vectors:
        best_index = None
        best_score = 0.0
        for beat_index, beat_vector in enumerate(beat_vectors):
            score = _cosine_similarity(paragraph_vector, beat_vector)
            if score > best_score:
                best_score = score
                best_index = beat_index
        if best_index is not None and best_score >= 0.1:
            paragraph_best_beats.append(best_index)
    beat_assignment_counts = Counter(paragraph_best_beats)
    expected_per_beat = max(1, round(len(lines) / float(max(1, len(beat_anchors)))))
    overcovered_beat_count = sum(1 for count in beat_assignment_counts.values() if count > expected_per_beat + 1)

    event_coverage_gap_score = 0.0
    if event_best_scores:
        event_coverage_gap_score = (
            sum(max(0.0, 1.0 - score) for score in event_best_scores) / float(len(event_best_scores))
            + (uncovered_event_count / float(len(event_best_scores)))
        ) / 2.0
    beat_coverage_gap_score = 0.0
    if beat_best_scores:
        beat_coverage_gap_score = (
            sum(max(0.0, 1.0 - score) for score in beat_best_scores) / float(len(beat_best_scores))
            + (uncovered_beat_count / float(len(beat_best_scores)))
            + (overcovered_beat_count / float(len(beat_best_scores)))
        ) / 3.0
    if beat_best_scores and uncovered_beat_count == 0 and beat_coverage_gap_score <= 0.35:
        event_coverage_gap_score = min(event_coverage_gap_score, 0.42)

    examples: List[Dict[str, object]] = []
    for anchor, score in zip(event_anchors, event_best_scores):
        if score < 0.16:
            examples.append(
                {
                    "kind": "uncovered_event",
                    "event_id": anchor["event_id"],
                    "label": anchor["label"],
                    "score": round(score, 3),
                }
            )
    for beat_index, (anchor, score) in enumerate(zip(beat_anchors, beat_best_scores)):
        if score < 0.14:
            examples.append(
                {
                    "kind": "uncovered_beat",
                    "event_id": anchor["event_id"],
                    "label": anchor["label"],
                    "score": round(score, 3),
                }
            )
        if beat_assignment_counts.get(beat_index, 0) > expected_per_beat + 1:
            examples.append(
                {
                    "kind": "overcovered_beat",
                    "event_id": anchor["event_id"],
                    "label": anchor["label"],
                    "assigned_paragraph_count": int(beat_assignment_counts.get(beat_index, 0)),
                }
            )
    return {
        "selected_event_ids": selected_event_ids or [item["event_id"] for item in beat_payloads if item["event_id"]],
        "semantic_paragraph_similarity_score": round(semantic_similarity_score, 3),
        "semantic_paragraph_similarity_pairs": semantic_pairs,
        "event_coverage_gap_score": round(event_coverage_gap_score, 3),
        "beat_coverage_gap_score": round(beat_coverage_gap_score, 3),
        "uncovered_event_count": int(uncovered_event_count),
        "uncovered_beat_count": int(uncovered_beat_count),
        "overcovered_beat_count": int(overcovered_beat_count),
        "coverage_gap_examples": examples[:5],
    }


def repetition_score(lines: Iterable[str]) -> float:
    tokens = []
    for line in lines:
        words = _tokenize(line)
        tokens.extend(words)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / float(len(tokens))


def repetition_signal_bundle(
    lines: Iterable[str],
    *,
    coverage_context: Dict[str, object] | None = None,
) -> Dict[str, object]:
    normalized_lines = [str(line or "").strip() for line in lines if str(line or "").strip()]
    lexical = repetition_score(normalized_lines)
    paragraph_similarity, top_pairs = _paragraph_similarity_score(normalized_lines)
    n_gram = _n_gram_repetition_score(normalized_lines)
    beat_structure = _beat_structure_repetition_score(normalized_lines)
    suspicious_refrain_count, suspicious_examples = _suspicious_refrain_count(normalized_lines)
    coverage_bundle = _coverage_gap_signal_bundle(normalized_lines, coverage_context=coverage_context)
    overall = max(
        lexical * 0.55,
        paragraph_similarity * 0.7,
        float(coverage_bundle["semantic_paragraph_similarity_score"]),
        float(coverage_bundle["event_coverage_gap_score"]) * 0.95,
        float(coverage_bundle["beat_coverage_gap_score"]),
        n_gram * 0.35,
        beat_structure * 0.85,
        min(1.0, suspicious_refrain_count / 8.0),
        min(1.0, (int(coverage_bundle["uncovered_beat_count"]) + int(coverage_bundle["overcovered_beat_count"])) / 4.0),
    )
    return {
        "lexical_repetition_score": round(lexical, 3),
        "paragraph_similarity_score": round(paragraph_similarity, 3),
        "n_gram_repetition_score": round(n_gram, 3),
        "beat_structure_repetition_score": round(beat_structure, 3),
        "suspicious_refrain_count": int(suspicious_refrain_count),
        "suspicious_refrain_examples": suspicious_examples,
        "top_repeated_paragraph_pairs": top_pairs,
        **coverage_bundle,
        "overall_repetition_pressure": round(overall, 3),
    }
