# Test privacy firewall and sanitization.
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import (
    sanitize_page,
    sanitize_page_text,
)


# Test PII detection and DOM sanitization.
def test_pii_detection_and_sanitization():
    elements = [
        {
            "type": "input",
            "text": "",
            "value": "shivansh@example.com",
            "placeholder": "Email",
            "aria_label": "",
            "name": "email",
        },
        {
            "type": "input",
            "text": "",
            "value": "+919876543210",
            "placeholder": "Phone",
            "aria_label": "",
            "name": "phone",
        },
        {
            "type": "input",
            "text": "",
            "value": "4111 1111 1111 1111",
            "placeholder": "Card",
            "aria_label": "",
            "name": "card",
        },
        {
            "type": "input",
            "input_type": "password",
            "text": "",
            "value": "secret-password",
            "placeholder": "Password",
            "aria_label": "",
            "name": "password",
        },
    ]

    page_text = (
        "Name: Shivansh Srivastava\n"
        "Email: shivansh@example.com\n"
        "Phone: +919876543210\n"
        "Card: 4111 1111 1111 1111"
    )

    findings = inspect_page(
        elements,
        page_text,
    )

    sanitized = sanitize_page(
        elements,
        findings,
    )

    sanitized_text = sanitize_page_text(
        page_text,
        findings,
    )

    finding_types = {
        finding["type"]
        for finding in findings
    }

    assert "email" in finding_types
    assert "phone" in finding_types
    assert "credit_card" in finding_types
    assert "credential" in finding_types

    raw_values = [
        "shivansh@example.com",
        "+919876543210",
        "4111 1111 1111 1111",
        "secret-password",
    ]

    assert all(
        value not in str(sanitized)
        for value in raw_values
    )

    assert all(
        value not in sanitized_text
        for value in raw_values
    )

    assert "[EMAIL]" in sanitized_text
    assert "[PHONE]" in sanitized_text
    assert "[CREDIT_CARD]" in sanitized_text


# Run directly without pytest.
if __name__ == "__main__":
    test_pii_detection_and_sanitization()
    print("Privacy test passed.")