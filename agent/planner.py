# Allowed browser actions.
ALLOWED_ACTIONS = {
    "click",
    "type",
}


# Validate one browser action.
def validate_action(action, elements):
    if not isinstance(action, dict):
        return False, "Action is not an object."

    action_type = (
        action.get("action") or ""
    ).strip().lower()

    target = (
        action.get("target") or ""
    ).strip()

    # Normalize model output.
    action["action"] = action_type
    action["target"] = target

    if action_type not in ALLOWED_ACTIONS:
        return False, f"Unsupported action: {action_type}"

    if not target:
        return False, "Action target is missing."

    # Find matching UI elements.
    matching_elements = [
        element
        for element in elements
        if (
            (element.get("text") or "").lower() == target.lower()
            or (element.get("aria_label") or "").lower() == target.lower()
            or (element.get("placeholder") or "").lower() == target.lower()
        )
    ]

    if not matching_elements:
        return False, f"Target not found: {target}"

    # Validate TYPE actions.
    if action_type == "type":
        value = action.get("value")

        if not value:
            return False, "Type value is missing."

        if value == "USER_PROVIDED_VALUE":
            return False, "Type value was not provided by the user."

        if not any(
            element.get("type") in {
                "input",
                "textarea",
            }
            for element in matching_elements
        ):
            return False, (
                f"Target is not a text input: {target}"
            )

    # Validate CLICK actions.
    if action_type == "click":
        if not any(
            element.get("type") in {
                "button",
                "link",
            }
            for element in matching_elements
        ):
            return False, (
                f"Target is not clickable: {target}"
            )

    return True, "Valid action."


# Validate the complete action plan.
def validate_actions(actions, elements):
    if not isinstance(actions, list):
        return False, [
            "Action plan is not a list."
        ]

    if not actions:
        return False, [
            "Action plan is empty."
        ]

    errors = []

    for index, action in enumerate(
        actions,
        start=1,
    ):
        valid, message = validate_action(
            action,
            elements,
        )

        if not valid:
            errors.append(
                f"Step {index}: {message}"
            )

    if errors:
        return False, errors

    return True, []


# Basic standalone validation test.
if __name__ == "__main__":
    test_elements = [
        {
            "type": "button",
            "text": "Login",
            "aria_label": "",
            "placeholder": "",
        },
        {
            "type": "input",
            "text": "",
            "aria_label": "",
            "placeholder": "Enter your name",
        },
    ]

    test_actions = [
        {
            "action": "CLICK",
            "target": "Login",
        }
    ]

    valid, errors = validate_actions(
        test_actions,
        test_elements,
    )

    if valid:
        print("Planner test passed.")
    else:
        print("Planner test failed.")
        for error in errors:
            print(error)