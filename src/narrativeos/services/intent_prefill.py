from __future__ import annotations

from typing import List

from ..models import IntentPrefill, SessionRecord, StepRecord


class IntentPrefillService:
    def build(self, session_record: SessionRecord, latest_step: StepRecord | None) -> IntentPrefill:
        if latest_step is None:
            return IntentPrefill(
                last_player_intent="",
                current_pressure="故事还没真正卷起来。",
                suggested_prefill="我想先看看这条命会把我带去哪里。",
            )

        last_player_intent = latest_step.player_input.strip()
        relationship_hint = latest_step.reader_view.relationship_hints[0] if latest_step.reader_view and latest_step.reader_view.relationship_hints else ""
        scene_goal = latest_step.chapter_plan.scene_intent.label if latest_step.chapter_plan else "局势正在继续收紧"
        current_pressure = "；".join(
            part for part in [
                latest_step.reader_view.recap if latest_step.reader_view else "",
                relationship_hint,
                scene_goal,
            ] if part
        ) or "上一章留下的余波还没散。"

        hook = ""
        if latest_step.rendered_scene:
            hook = latest_step.rendered_scene.story_title or latest_step.rendered_scene.chapter_summary
        if latest_step.state_after.unresolved_debts:
            suggested = "我想先顺着这点余波追下去，看看该还的那笔亏欠会不会先追到门前。"
        elif latest_step.state_after.karmic_weather.get("temptation", 0.0) >= 0.3:
            suggested = "我想先试探对方真正站在哪一边，再决定要不要把心里的话说全。"
        elif latest_step.state_after.karmic_weather.get("suspicion", 0.0) >= 0.3:
            suggested = "我想先弄清眼前这层隐瞒到底已经牵扯到谁，再决定是不是当面摊开。"
        else:
            suggested = "我想先顺着刚刚留下的那点裂口追一步，看看下一次开口会把谁逼到更难退的位置。"
        if hook:
            suggested = suggested.rstrip("。") + "。"

        return IntentPrefill(
            last_player_intent=last_player_intent,
            current_pressure=current_pressure,
            suggested_prefill=suggested,
        )
