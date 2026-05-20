from __future__ import annotations

from pathlib import Path


def write_report(output_path: str | Path, markdown: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path

