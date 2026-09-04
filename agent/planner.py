ALLOWED_ACTIONS = {
    "click",
    "type",
}


def validate_action(action, elements):
    if not isinstance(action, dict):
        return False, "Action is not an object."

    action_type = action.get("action")
    target = action.get("target")

    if action_type not in ALLOWED_ACTIONS:
        return False, f"Unsupported action: {action_type}"

    if not target:
        return False, "Action target is missing."

    matching_elements = [
        element
        for element in elements
        if (
            element.get("text", "").lower() == target.lower()
            or element.get("aria_label", "").lower() == target.lower()
            or element.get("placeholder", "").lower() == target.lower()
        )
    ]

    if not matching_elements:
        return False, f"Target not found: {target}"

    if action_type == "type":
        value = action.get("value")

        if not value:
            return False, "Type value is missing."

        if value == "USER_PROVIDED_VALUE":
            return False, "Type value was not provided by the user."

        if not any(
            element.get("type") in {"input", "textarea"}
            for element in matching_elements
        ):
            return False, f"Target is not a text input: {target}"

    if action_type == "click":
        if not any(
            element.get("type") in {"button", "link"}
            for element in matching_elements
        ):
            return False, f"Target is not clickable: {target}"

    return True, "Valid action."


def validate_actions(actions, elements):
    if not isinstance(actions, list):
        return False, ["Action plan is not a list."]

    if not actions:
        return False, ["Action plan is empty."]

    errors = []

    for index, action in enumerate(actions, start=1):
        valid, message = validate_action(
            action,
            elements
        )

        if not valid:
            errors.append(
                f"Step {index}: {message}"
            )

    if errors:
        return False, errors

    return True, []
