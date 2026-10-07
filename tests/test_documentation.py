"""Keep copyable partial configs and local documentation links usable offline."""

import json
import re
from pathlib import Path

import pytest

from nape_cli.config import load_config, validate_config

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_configs_validate_offline(path: Path) -> None:
    load_config(path)


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.name)
def test_documented_partial_configs_validate_offline(path: Path) -> None:
    for block in re.findall(r"```json\n(.*?)\n```", path.read_text(), re.DOTALL):
        data = json.loads(block)
        # Some fenced blocks intentionally illustrate an exported object, not input.
        if isinstance(data, dict) and data.get("schema_version") == 1:
            validate_config(data)


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.name)
def test_local_documentation_links_exist(path: Path) -> None:
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        if "://" in target or target.startswith("#"):
            continue
        relative_path = target.split("#", 1)[0]
        assert (path.parent / relative_path).is_file(), f"{path.name}: {target}"


def test_vertical_scroll_browser_back_recipe_matches_example() -> None:
    catalog = (ROOT / "docs" / "action-catalog.md").read_text()
    block = re.findall(r"```json\n(.*?)\n```", catalog, re.DOTALL)[0]
    expected = load_config(ROOT / "examples" / "vertical-scroll-browser-back.json")
    assert validate_config(json.loads(block)) == expected
    assert expected.to_dict()["layers"] == [
        {
            "layer": 0,
            "buttons": {"01": "0x00D4"},
            "dial": {"ccw": "0x00D9", "cw": "0x00DA"},
        }
    ]
