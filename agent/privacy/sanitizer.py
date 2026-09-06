# Privacy-safe replacements.
REPLACEMENTS = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "credit_card": "[CREDIT_CARD]",
    "aadhaar": "[AADHAAR]",
    "pan": "[PAN]",
    "credential": "[REDACTED]",
}


# Sanitize one DOM element.
def sanitize_element(element, findings):
    sanitized = element.copy()

    for finding in findings:
        replacement = REPLACEMENTS.get(
            finding["type"]
        )

        if not replacement:
            continue

        value = finding.get("value")

        if value:
            for field in [
                "text",
                "value",
                "placeholder",
                "aria_label",
                "name",
            ]:
                current = sanitized.get(field)

                if current:
                    sanitized[field] = current.replace(
                        value,
                        replacement,
                    )
        else:
            if sanitized.get("value"):
                sanitized["value"] = replacement

    return sanitized


# Sanitize all DOM elements.
def sanitize_page(elements, findings):
    sanitized_elements = []

    for element in elements:
        element_findings = [
            finding
            for finding in findings
            if finding.get("element") is element
        ]

        sanitized_elements.append(
            sanitize_element(
                element,
                element_findings,
            )
        )

    return sanitized_elements


# Sanitize visible page text.
def sanitize_page_text(page_text, findings):
    sanitized_text = page_text or ""

    for finding in findings:
        value = finding.get("value")
        replacement = REPLACEMENTS.get(
            finding.get("type")
        )

        if value and replacement:
            sanitized_text = sanitized_text.replace(
                value,
                replacement,
            )

    return sanitized_text