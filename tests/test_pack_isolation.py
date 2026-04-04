from pathlib import Path
import re

from src.narrativeos.worldpacks.registry import FileSystemWorldRegistry


PACK_SPECIFIC_TOKENS = [
    "yu_cheng",
    "lin_wan",
    "tutor_xu",
    "lady_rong",
    "花厅",
    "书房",
    "回廊",
    "花园",
    "渡口",
    "门楣",
    "家门",
    "礼法",
]


def test_core_and_rendering_do_not_hardcode_current_pack_tokens():
    root = Path(__file__).resolve().parents[1] / "src" / "narrativeos"
    files = [
        *sorted((root / "core").rglob("*.py")),
        root / "rendering.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    published_world_ids = [
        item["world_id"]
        for item in FileSystemWorldRegistry().list_benchmark_worldpacks()
    ]
    for token in [*PACK_SPECIFIC_TOKENS, *published_world_ids]:
        assert token not in combined


def test_core_and_rendering_do_not_import_worldpacks_package():
    root = Path(__file__).resolve().parents[1] / "src" / "narrativeos"
    files = [
        *sorted((root / "core").rglob("*.py")),
        root / "rendering.py",
    ]
    patterns = [
        r"from\s+\.\.worldpacks",
        r"from\s+src\.narrativeos\.worldpacks",
        r"from\s+narrativeos\.worldpacks",
        r"import\s+src\.narrativeos\.worldpacks",
        r"import\s+narrativeos\.worldpacks",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert re.search(pattern, text) is None, f"worldpacks import leak in {path}: {pattern}"


def test_synthetic_min_pack_exists():
    pack_path = Path(__file__).resolve().parents[1] / "examples" / "worldpacks" / "synthetic_min_pack.json"
    assert pack_path.exists()
