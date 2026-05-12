from src.narrativeos.services.reader_storybook_title_homogenization import (
    append_reader_storybook_title_homogenization_history_entry,
    build_reader_storybook_title_homogenization_trend,
    promoted_reader_storybook_title_homogenization_pairs_for_world,
)


def _entry(*, generated_at: str, world_ids, warning: bool) -> dict:
    comparison = {
        "non_jade_world_id": "urban_mystery_lotus_lane",
        "jade_world_id": "jade_court_romance",
        "title_similarity": 1.0,
        "quote_similarity": 0.013,
        "passes_min_difference": True,
    }
    warnings = []
    if warning:
        warnings.append(
            {
                "non_jade_world_id": "urban_mystery_lotus_lane",
                "jade_world_id": "jade_court_romance",
                "title_similarity": 1.0,
                "quote_similarity": 0.013,
                "warning_kind": "title_homogenization_non_blocking",
                "message": "sampled titles are highly similar across packs, but quote-token overlap remains below the blocking threshold.",
            }
        )
    return {
        "generated_at": generated_at,
        "world_ids": list(world_ids),
        "cross_pack_distinctness": [comparison],
        "title_homogenization_warnings": warnings,
    }


def _pair(trend: dict) -> dict:
    return next(
        item
        for item in trend["pair_trends"]
        if item["non_jade_world_id"] == "urban_mystery_lotus_lane"
        and item["jade_world_id"] == "jade_court_romance"
    )


def test_reader_storybook_title_homogenization_trend_promotes_after_three_consecutive_runs():
    history = {}
    for generated_at in [
        "2026-04-17T10:00:00+00:00",
        "2026-04-18T10:00:00+00:00",
        "2026-04-19T10:00:00+00:00",
    ]:
        history = append_reader_storybook_title_homogenization_history_entry(
            history,
            _entry(
                generated_at=generated_at,
                world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
                warning=True,
            ),
        )

    trend = build_reader_storybook_title_homogenization_trend(history)
    pair = _pair(trend)

    assert pair["consecutive_warning_count"] == 3
    assert pair["trend_status"] == "promoted"
    assert pair["promoted_to_release_review"] is True
    assert trend["promoted_pair_count"] == 1
    assert promoted_reader_storybook_title_homogenization_pairs_for_world(
        trend,
        world_id="urban_mystery_lotus_lane",
    )


def test_reader_storybook_title_homogenization_trend_does_not_promote_before_threshold():
    history = {}
    for generated_at in [
        "2026-04-17T10:00:00+00:00",
        "2026-04-18T10:00:00+00:00",
    ]:
        history = append_reader_storybook_title_homogenization_history_entry(
            history,
            _entry(
                generated_at=generated_at,
                world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
                warning=True,
            ),
        )

    trend = build_reader_storybook_title_homogenization_trend(history)
    pair = _pair(trend)

    assert pair["consecutive_warning_count"] == 2
    assert pair["trend_status"] == "watch"
    assert pair["promoted_to_release_review"] is False
    assert trend["promoted_pair_count"] == 0


def test_reader_storybook_title_homogenization_trend_ignores_runs_that_do_not_cover_both_worlds():
    history = {}
    for entry in [
        _entry(
            generated_at="2026-04-17T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=True,
        ),
        _entry(
            generated_at="2026-04-18T10:00:00+00:00",
            world_ids=["jade_court_exam", "jade_court_romance"],
            warning=False,
        ),
        _entry(
            generated_at="2026-04-19T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=True,
        ),
        _entry(
            generated_at="2026-04-20T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=True,
        ),
    ]:
        history = append_reader_storybook_title_homogenization_history_entry(history, entry)

    trend = build_reader_storybook_title_homogenization_trend(history)
    pair = _pair(trend)

    assert pair["eligible_run_count"] == 3
    assert pair["consecutive_warning_count"] == 3
    assert pair["promoted_to_release_review"] is True


def test_reader_storybook_title_homogenization_trend_resets_after_clean_eligible_run():
    history = {}
    for entry in [
        _entry(
            generated_at="2026-04-17T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=True,
        ),
        _entry(
            generated_at="2026-04-18T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=True,
        ),
        _entry(
            generated_at="2026-04-19T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=False,
        ),
        _entry(
            generated_at="2026-04-20T10:00:00+00:00",
            world_ids=["urban_mystery_lotus_lane", "jade_court_romance"],
            warning=True,
        ),
    ]:
        history = append_reader_storybook_title_homogenization_history_entry(history, entry)

    trend = build_reader_storybook_title_homogenization_trend(history)
    pair = _pair(trend)

    assert pair["consecutive_warning_count"] == 1
    assert pair["trend_status"] == "watch"
    assert pair["promoted_to_release_review"] is False
