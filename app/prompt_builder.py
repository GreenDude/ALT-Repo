from __future__ import annotations

from pathlib import Path


def build_review_prompt(template_path: str | Path, diff_text: str) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    return template.replace("{{DIFF}}", diff_text)

