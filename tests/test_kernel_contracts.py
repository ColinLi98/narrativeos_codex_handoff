from pathlib import Path

from src.narrativeos.core.contracts import (
    CharacterReasoner,
    ChoiceGenerator,
    DialogueRealismPolicy,
    EmotionActionPolicy,
    NarrativeJudge,
    PlotPlanner,
    PressureResponseStyle,
    ProseWriter,
    ResponseCadenceProfile,
    SceneRealizationContract,
    SensoryGroundingPolicy,
    VoiceProfile,
    WorldNarrativeStylePack,
)


def test_kernel_contracts_exist():
    assert DialogueRealismPolicy().to_dict()
    assert VoiceProfile().to_dict()
    assert ResponseCadenceProfile().to_dict()
    assert PressureResponseStyle().to_dict()
    assert EmotionActionPolicy().to_dict()
    assert SensoryGroundingPolicy().to_dict()
    assert SceneRealizationContract().to_dict()
    assert WorldNarrativeStylePack().to_dict()
    assert CharacterReasoner
    assert ChoiceGenerator
    assert NarrativeJudge
    assert PlotPlanner
    assert ProseWriter


def test_writer_is_orchestration_and_not_pack_blob():
    writer_path = Path(__file__).resolve().parents[1] / "src" / "narrativeos" / "core" / "writer.py"
    content = writer_path.read_text(encoding="utf-8")
    assert "realize_scene_opening" in content
    assert "realize_beat" in content
    assert "realize_hook" in content
