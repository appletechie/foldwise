"""Detect and mask credentials. Patterns come from real files found while building the prototype.

Known backlog (post-v1): prefix-style keys without a key=value context (AKIA..., ghp_..., xoxb-...)
are not detected yet; they never appeared in the prototype's files.
"""
import re

PATTERN = re.compile(
    r"BEGIN [A-Z ]*PRIVATE KEY"
    r"|\bsk-[A-Za-z0-9_\-]{20,}"
    r"|(?i:\b(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|secret|password|passwd)\b[\"']?\s*[:=,\n]\s*[\"']?"
    r"[A-Za-z0-9_\-./+]{16,})"
    r"|(?i:\b(?:recovery (?:key|code)s?|backup codes?)\b)"
)


def is_sensitive(text: str) -> bool:
    return PATTERN.search(text) is not None


def mask(text: str) -> str:
    return PATTERN.sub(lambda m: m.group(0)[:6] + "…[masked]", text)
