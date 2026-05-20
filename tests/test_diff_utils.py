from app.diff_utils import TRUNCATION_NOTE, redact_secrets, trim_diff


def test_trim_diff_appends_truncation_note() -> None:
    trimmed = trim_diff("abcdef", max_chars=5)

    assert TRUNCATION_NOTE[:5] == trimmed or TRUNCATION_NOTE in trimmed


def test_redact_secrets_replaces_known_patterns() -> None:
    text = "\n".join(
        [
            "Authorization: Bearer abc123",
            "password = hunter2",
            "token: secret-token",
        ]
    )

    redacted = redact_secrets(text)

    assert "abc123" not in redacted
    assert "hunter2" not in redacted
    assert "secret-token" not in redacted
    assert redacted.count("[REDACTED]") >= 3
