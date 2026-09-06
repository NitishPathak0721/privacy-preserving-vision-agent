# PII detection patterns.
import re


# Supported PII patterns.
PATTERNS = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "phone": re.compile(
        r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"
    ),
    "credit_card": re.compile(
        r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"
    ),
    "aadhaar": re.compile(
        r"(?<!\d)\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)"
    ),
    "pan": re.compile(
        r"(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])",
        re.IGNORECASE,
    ),
}


# Detect PII values in text.
def detect_pii(text):
    if not text:
        return []

    findings = []

    for pii_type, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(
                {
                    "type": pii_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    findings.sort(
        key=lambda finding: finding["start"]
    )

    return findings