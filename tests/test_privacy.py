import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import sanitize_page, sanitize_page_text


# Test PII detection and sanitization.
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
        {
            "type": "input",
            "text": "",
            "value": "1234 5678 9012",
            "placeholder": "Aadhaar",
            "aria_label": "",
            "name": "aadhaar",
        },
        {
            "type": "input",
            "text": "",
            "value": "ABCDE1234F",
            "placeholder": "PAN",
            "aria_label": "",
            "name": "pan",
        },
    ]

    page_text = (
        "Name: Shivansh Srivastava\n"
        "Email: shivansh@example.com\n"
        "Phone: +919876543210\n"
        "Card: 4111 1111 1111 1111\n"
        "Aadhaar: 1234 5678 9012\n"
        "PAN: ABCDE1234F"
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
    assert "aadhaar" in finding_types
    assert "pan" in finding_types

    raw_values = [
        "shivansh@example.com",
        "+919876543210",
        "4111 1111 1111 1111",
        "secret-password",
        "1234 5678 9012",
        "ABCDE1234F",
    ]

    sanitized_dom = str(sanitized)

    for value in raw_values:
        assert value not in sanitized_dom
        assert value not in sanitized_text

    assert "[EMAIL]" in sanitized_dom
    assert "[PHONE]" in sanitized_dom
    assert "[CREDIT_CARD]" in sanitized_dom
    assert "[REDACTED]" in sanitized_dom
    assert "[AADHAAR]" in sanitized_dom
    assert "[PAN]" in sanitized_dom

    assert "[EMAIL]" in sanitized_text
    assert "[PHONE]" in sanitized_text
    assert "[CREDIT_CARD]" in sanitized_text
    assert "[AADHAAR]" in sanitized_text
    assert "[PAN]" in sanitized_text


# Test standalone Aadhaar and PAN detection.
def test_aadhaar_and_pan_detection():
    page_text = (
        "Aadhaar: 1234 5678 9012\n"
        "PAN: ABCDE1234F"
    )

    findings = inspect_page(
        [],
        page_text,
    )

    finding_types = {
        finding["type"]
        for finding in findings
    }

    assert "aadhaar" in finding_types
    assert "pan" in finding_types


if __name__ == "__main__":
    test_pii_detection_and_sanitization()
    test_aadhaar_and_pan_detection()
    print("Privacy tests passed.")