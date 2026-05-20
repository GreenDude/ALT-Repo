from __future__ import annotations

import re


TRUNCATION_NOTE = "[Diff truncated due to configured max_diff_chars limit]"

SECRET_PATTERNS = (
    re.compile(r"(?im)^([ \t>*-]*authorization\s*:\s*)(.+)$"),
    re.compile(r"(?im)^([ \t>*-]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret)\s*[:=]\s*)(.+)$"),
    re.compile(r"(?im)^([ \t>*-]*bearer\s+)([a-z0-9._\-+/=]+)$"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS[:-1]:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[-1].sub("[REDACTED]", redacted)
    return redacted


def trim_diff(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return TRUNCATION_NOTE

    if len(text) <= max_chars:
        return text

    suffix = f"\n\n{TRUNCATION_NOTE}"
    available = max_chars - len(suffix)
    if available <= 0:
        return TRUNCATION_NOTE[:max_chars]
    trimmed = text[:available].rstrip()
    return f"{trimmed}{suffix}"

