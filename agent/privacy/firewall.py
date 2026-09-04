from agent.privacy.credentials import is_sensitive_element
from agent.privacy.pii import detect_pii


def inspect_element(element):
    findings = []

    if is_sensitive_element(element):
        findings.append({
            "type": "credential",
            "element": element,
        })

    fields = [
        element.get("text"),
        element.get("value"),
        element.get("placeholder"),
        element.get("aria_label"),
        element.get("name"),
    ]

    for field in fields:
        for finding in detect_pii(field or ""):
            findings.append({
                "type": finding["type"],
                "value": finding["value"],
                "element": element,
            })

    return findings


def inspect_page(elements):
    findings = []

    for element in elements:
        findings.extend(inspect_element(element))

    return findings
