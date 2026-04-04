from src.narrativeos.eval.regression import run_regression
from src.narrativeos.repository import SQLAlchemyRepository


def test_regression_runner_outputs_multi_world_summary(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "regression.db"))
    summary = run_regression("all", golden_dir=tmp_path / "golden_routes", repository=repository)
    assert summary["worldpacks"]
    assert any(item["world_id"] == "jade_court_exam" for item in summary["worldpacks"])
    assert all(item["world_id"] != "world_template_minimal" for item in summary["worldpacks"])
