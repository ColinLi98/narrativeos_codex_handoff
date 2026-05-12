from src.narrativeos.eval.validators import (
    chapter_structure_validator,
    engineering_leak_validator,
    meta_narration_validator,
    paragraph_repetition_validator,
    premature_ending_validator,
)
from src.narrativeos.repetition_detector import repetition_signal_bundle
from src.narrativeos.models import NarrativeState


def test_engineering_and_meta_validators():
    assert engineering_leak_validator("event_id seed_id foo_bar a -> b")
    assert meta_narration_validator("这一章如果把这一章放远一点看，第1拍就会显得很明显。")


def test_repetition_validator_hits_repeated_paragraphs():
    issues = paragraph_repetition_validator(
        ["同一句话重复很多次", "同一句话重复很多次", "另一句"],
        text_unit_count_value=60,
    )
    assert issues


def test_repetition_validator_uses_longform_context_for_1600_unit_chapters():
    bundle = {
        "lexical_repetition_score": 0.164,
        "paragraph_similarity_score": 0.473,
        "n_gram_repetition_score": 0.162,
        "beat_structure_repetition_score": 0.1,
        "suspicious_refrain_count": 0,
        "semantic_paragraph_similarity_score": 0.759,
        "event_coverage_gap_score": 0.273,
        "beat_coverage_gap_score": 0.182,
        "uncovered_event_count": 0,
        "uncovered_beat_count": 0,
        "overcovered_beat_count": 0,
        "selected_event_ids": ["evt_1", "evt_2", "evt_3"],
        "coverage_gap_examples": [],
    }

    shortform_issues = paragraph_repetition_validator(
        ["潮声落下。", "纸页翻动。", "她抬眼。"],
        text_unit_count_value=1633,
        precomputed_bundle=bundle,
    )
    longform_issues = paragraph_repetition_validator(
        ["潮声落下。", "纸页翻动。", "她抬眼。"],
        text_unit_count_value=1633,
        coverage_context={"chapter_task": {"target_words": 1600}},
        precomputed_bundle=bundle,
    )

    assert shortform_issues
    assert not longform_issues


def test_longform_repetition_validator_uses_structural_signals_not_length_alone():
    lines = [
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。",
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。",
        "灯影落在窗纸上，风从檐下掠过去，她没有立刻说话，只把那卷录音带重新压回掌心里。",
        "他抬眼看她，知道这一步不是把真相说出来就算完，而是要连代价一起接住。",
    ]
    issues = paragraph_repetition_validator(lines, text_unit_count_value=1900)
    assert issues


def test_longform_repetition_validator_uses_semantic_similarity_and_coverage_gap():
    lines = [
        "她把录音带翻到背面，指腹慢慢擦过已经泡开的纸签，像在确认那道旧伤是不是还留在这里。",
        "她把录音带翻到背面，指腹慢慢擦过已经泡开的纸签，像在确认那道旧伤是不是还留在这里。",
        "她把录音带翻到背面，指腹慢慢擦过已经泡开的纸签，像在确认那道旧伤是不是还留在这里。",
        "他没有立即接话，只把潮湿的纸袋压在案边，像是先让真正该出现的那一句话自己浮上来。",
    ]
    issues = paragraph_repetition_validator(
        lines,
        text_unit_count_value=1900,
        coverage_context={
            "selected_event_ids": ["evt_1", "evt_2", "evt_3"],
            "scene_beats": [
                {
                    "beat_label": "翻出旧物",
                    "dramatic_job": "entry",
                    "event": {"event_id": "evt_1", "title": "翻出旧录音带", "summary": "她从纸袋里翻出旧录音带。", "scene_function": "truth_trial", "location": "档案仓", "tags": ["truth", "memory"]},
                },
                {
                    "beat_label": "追问来源",
                    "dramatic_job": "pressure",
                    "event": {"event_id": "evt_2", "title": "追问录音带来源", "summary": "他逼问这卷带子为什么会回到这里。", "scene_function": "temptation", "location": "档案仓", "tags": ["truth", "pressure"]},
                },
                {
                    "beat_label": "揭出名字",
                    "dramatic_job": "pivot",
                    "event": {"event_id": "evt_3", "title": "看见旧名字", "summary": "她在纸签背面看见旧案里那个人的名字。", "scene_function": "confession_window", "location": "档案仓", "tags": ["truth", "memory"]},
                },
            ],
        },
    )
    assert issues


def test_longform_repetition_bundle_dedupes_repeated_event_ids_for_event_coverage():
    lines = [
        "余澄当众接下春闱之命这一刻，花厅里的风、灯影和脚步声像一起把这步表面平静推到了明处。",
        "荣老太君顺着体面把最难认的那句逼到余澄面前，这一拍不再新增事件，而是把真正要转向的那句终于逼到眼前直接推回当前章节正文。",
        "门影、茶气和席间静气都没有散，反而把后半句留在了余澄自己身前。",
    ]
    bundle = repetition_signal_bundle(
        lines,
        coverage_context={
            "selected_event_ids": ["evt_1", "evt_2", "evt_2"],
            "scene_beats": [
                {
                    "beat_label": "起势：余澄当众接下春闱之命",
                    "dramatic_job": "entry",
                    "event": {"event_id": "evt_1", "title": "余澄当众接下春闱之命", "summary": "余澄在花厅当众应下应试。", "scene_function": "false_peace", "location": "花厅", "tags": ["duty"]},
                },
                {
                    "beat_label": "逼近：荣老太君顺着体面把最难认的那句逼到余澄面前",
                    "dramatic_job": "pressure",
                    "event": {"event_id": "evt_2", "title": "荣老太君顺着体面把最难认的那句逼到余澄面前", "summary": "荣老太君借体面逼余澄认下心意。", "scene_function": "truth_trial", "location": "花厅", "tags": ["duty", "truth"]},
                },
                {
                    "beat_label": "转向：荣老太君顺着体面把最难认的那句逼到余澄面前 · 真正要转向的那句终于逼到眼前",
                    "dramatic_job": "pivot",
                    "event": {"event_id": "evt_2", "title": "荣老太君顺着体面把最难认的那句逼到余澄面前", "summary": "这一拍不再新增事件，而是把真正要转向的那句逼回正文。", "scene_function": "truth_trial", "location": "花厅", "tags": ["duty", "truth"]},
                },
            ],
        },
    )
    assert bundle["selected_event_ids"] == ["evt_1", "evt_2"]


def test_structure_and_premature_ending_validators():
    issues = chapter_structure_validator(
        text="太短了。",
        paragraphs=["太短了。"],
        dialogue_count=0,
        action_count=0,
        detail_count=0,
    )
    assert issues

    state = NarrativeState.from_dict(
        {
            "state_id": "s",
            "world_id": "w",
            "turn_index": 0,
            "story_phase": "setup",
            "chapter_index": 1,
            "min_end_turn": 8,
            "fate_pressure": 0.1,
            "karmic_weather": {},
            "unresolved_debts": [],
            "world_facts": [],
            "timeline": [],
            "characters": {},
            "relationship_graph": [],
            "open_promises": [],
            "tension": 0.2,
            "themes": {},
            "player_intent": {},
            "recent_scene_functions": [],
            "visited_event_ids": [],
            "route_fingerprint": [],
            "rating_ceiling": "PG13",
        }
    )
    ending_issues = premature_ending_validator(state_after=state, ending_ready=True, body="")
    assert ending_issues
