import time

from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import sanitize_page, sanitize_page_text


# Benchmark test cases
TEST_CASES = [
    {
        "name": "Email",
        "text": "Contact me at shivansh@example.com",
        "expected": "[EMAIL]",
    },
    {
        "name": "Phone",
        "text": "My phone number is +919876543210",
        "expected": "[PHONE]",
    },
    {
        "name": "Credit Card",
        "text": "Card number: 4111 1111 1111 1111",
        "expected": "[CREDIT_CARD]",
    },
    {
        "name": "Aadhaar",
        "text": "Aadhaar: 1234 5678 9012",
        "expected": "[AADHAAR]",
    },
    {
        "name": "PAN",
        "text": "PAN: ABCDE1234F",
        "expected": "[PAN]",
    },
]


def run_benchmark():
    passed = 0
    total = len(TEST_CASES)

    start_time = time.perf_counter()

    print("=" * 60)
    print("PRIVACY FIREWALL BENCHMARK")
    print("=" * 60)

    for case in TEST_CASES:
        original = case["text"]
        expected = case["expected"]

        findings = inspect_page(
            [],
            original,
        )

        sanitized = sanitize_page_text(
            original,
            findings,
        )

        success = (
            expected in sanitized
            and original not in sanitized
        )

        if success:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"

        print()
        print(f"Test:       {case['name']}")
        print(f"Input:      {original}")
        print(f"Sanitized:  {sanitized}")
        print(f"Expected:   {expected}")
        print(f"Result:     {status}")

    # Test credential redaction through DOM sanitization.
    credential_elements = [
        {
            "type": "input",
            "input_type": "password",
            "text": "",
            "value": "secret-password",
            "placeholder": "Password",
            "aria_label": "",
            "name": "password",
        }
    ]

    credential_findings = inspect_page(
        credential_elements,
        "",
    )

    sanitized_elements = sanitize_page(
        credential_elements,
        credential_findings,
    )

    credential_sanitized = (
        sanitized_elements[0].get("value", "")
        if sanitized_elements
        else ""
    )

    credential_success = (
        credential_sanitized == "[REDACTED]"
        and credential_sanitized != "secret-password"
    )

    if credential_success:
        passed += 1
        status = "PASS"
    else:
        status = "FAIL"

    total += 1

    print()
    print("Test:       Password Credential")
    print("Input:      secret-password")
    print(f"Sanitized:  {credential_sanitized}")
    print("Expected:   [REDACTED]")
    print(f"Result:     {status}")

    elapsed = time.perf_counter() - start_time
    accuracy = (passed / total) * 100

    print()
    print("=" * 60)
    print(f"Passed:     {passed}/{total}")
    print(f"Accuracy:   {accuracy:.2f}%")
    print(f"Runtime:    {elapsed:.4f} seconds")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = run_benchmark()

    if not success:
        raise SystemExit(1)