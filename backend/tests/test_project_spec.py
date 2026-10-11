from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "PROJECT_SPEC.yaml"


def test_project_spec_is_valid_yaml_with_required_sections():
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

    for section in ("project", "requirements", "technology", "architecture", "security", "milestones"):
        assert section in spec, f"missing section: {section}"

    assert spec["project"]["slug"] == "speakiq-ai-coach"
    assert spec["architecture"]["frontend_directory"] == "frontend/"
    assert spec["architecture"]["backend_directory"] == "backend/"
    assert [m["id"] for m in spec["milestones"]][:2] == [1, 2]
