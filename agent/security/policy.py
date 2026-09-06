# Security limits
MAX_ACTIONS_PER_TASK = 20
MAX_REPLANS_PER_TASK = 5
MAX_TASK_RUNTIME_SECONDS = 120

# Allowed browser actions
ALLOWED_ACTIONS = {
    "click",
    "type",
}

# Actions requiring explicit user confirmation
CONFIRMATION_ACTIONS = {
    "submit",
    "delete",
    "purchase",
    "send",
    "upload",
    "download",
    "navigate",
}

def is_action_allowed(action):
    if not isinstance(action, dict):
        return False, "Action is not an object."

    action_type = action.get("action")

    if action_type in ALLOWED_ACTIONS:
        return True, "Allowed."

    if action_type in CONFIRMATION_ACTIONS:
        return False, f"User confirmation required for: {action_type}"

    return False, f"Blocked action: {action_type}"

# Domain sandbox
ALLOWED_DOMAINS = {
    "localhost",
    "127.0.0.1",
}

def is_domain_allowed(url):
    from urllib.parse import urlparse

    hostname = urlparse(url).hostname

    if not hostname:
        return False

    return hostname in ALLOWED_DOMAINS