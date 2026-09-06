SENSITIVE_INPUT_TYPES = {
    "password",
}

SENSITIVE_KEYWORDS = {
    "password",
    "passwd",
    "passcode",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "token",
}

def is_sensitive_element(element):
    input_type = (element.get("input_type") or "").lower()
    if input_type in SENSITIVE_INPUT_TYPES:
        return True

    fields = [
        element.get("name"),
        element.get("id"),
        element.get("placeholder"),
        element.get("aria_label"),
    ]

    text = " ".join(value or "" for value in fields).lower()

    return any(keyword in text for keyword in SENSITIVE_KEYWORDS)