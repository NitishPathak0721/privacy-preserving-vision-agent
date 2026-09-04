
REPLACEMENTS = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "credit_card": "[CREDIT_CARD]",
    "credential": "[REDACTED]",
}


def sanitize_element(element, findings):
    sanitized = element.copy()

    for finding in findings:
        replacement = REPLACEMENTS.get(finding["type"])

        if not replacement:
            continue

        value = finding.get("value")

        if value:
            for field in ["text", "value", "placeholder", "aria_label", "name"]:
                current = sanitized.get(field)
                if current:
                    sanitized[field] = current.replace(value, replacement)
        else:
            for field in ["value"]:
                if sanitized.get(field):
                    sanitized[field] = replacement

    return sanitized


def sanitize_page(elements, findings):
    sanitized_elements = []

    for element in elements:
        element_findings = [
            finding
            for finding in findings
            if finding.get("element") is element
        ]

        sanitized_elements.append(
            sanitize_element(element, element_findings)
        )

    return sanitized_elements
