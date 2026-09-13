"""Best-effort redaction before persistence, not a guarantee of anonymization."""
import re

PATTERNS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)'),
    re.compile(r'\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b'),
    re.compile(r'(?i)\b(?:bearer\s+)[A-Za-z0-9._~+/=-]{8,}'),
    re.compile(r'(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\s*[=:]\s*[\"\']?[^\s\"\',;}{]{6,}'),
    re.compile(r'(?i)https?://(?:127\.0\.0\.1|localhost)(?::\d+)?/[^\s<>\"\']*'),
]


def scrub(text):
    for pattern in PATTERNS:
        text = pattern.sub('[redacted]', text)
    return text
