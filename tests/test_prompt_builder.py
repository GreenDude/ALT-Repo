from pathlib import Path

from app.prompt_builder import build_review_prompt


def test_prompt_contains_diff(tmp_path: Path) -> None:
    template = tmp_path / "template.md"
    template.write_text("DIFF:\n{{DIFF}}", encoding="utf-8")

    prompt = build_review_prompt(template, "sample diff content")

    assert "sample diff content" in prompt
    assert "{{DIFF}}" not in prompt
