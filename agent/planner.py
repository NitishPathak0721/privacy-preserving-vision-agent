# Browser action validation.

import re


# Allowed browser actions.
ALLOWED_ACTIONS = {
    "click",
    "type",
}


# Resolve a model target against the perceived DOM.
def find_matching_elements(
    target,
    elements,
):
    target = (
        target or ""
    ).strip()

    if not target:
        return []

    target_lower = target.lower()

    # Exact visible UI text and attributes.
    matches = []

    for element in elements:
        candidates = [
            element.get("text"),
            element.get("aria_label"),
            element.get("placeholder"),
            element.get("name"),
            element.get("id"),
        ]

        for candidate in candidates:
            if (
                candidate
                and candidate.strip().lower()
                == target_lower
            ):
                matches.append(element)
                break

    if matches:
        return matches

    # Resolve input[name='...'].
    match = re.fullmatch(
        r"input\s*\[\s*name\s*=\s*['\"]([^'\"]+)['\"]\s*\]",
        target,
        re.IGNORECASE,
    )

    if match:
        requested_name = (
            match.group(1).strip().lower()
        )

        return [
            element
            for element in elements
            if (
                element.get("type")
                in {
                    "input",
                    "textarea",
                }
                and (
                    element.get("name")
                    or ""
                ).strip().lower()
                == requested_name
            )
        ]

    # Resolve textarea[name='...'].
    match = re.fullmatch(
        r"textarea\s*\[\s*name\s*=\s*['\"]([^'\"]+)['\"]\s*\]",
        target,
        re.IGNORECASE,
    )

    if match:
        requested_name = (
            match.group(1).strip().lower()
        )

        return [
            element
            for element in elements
            if (
                element.get("type")
                == "textarea"
                and (
                    element.get("name")
                    or ""
                ).strip().lower()
                == requested_name
            )
        ]

    # Resolve input[id='...'].
    match = re.fullmatch(
        r"input\s*\[\s*id\s*=\s*['\"]([^'\"]+)['\"]\s*\]",
        target,
        re.IGNORECASE,
    )

    if match:
        requested_id = (
            match.group(1).strip().lower()
        )

        return [
            element
            for element in elements
            if (
                element.get("type")
                == "input"
                and (
                    element.get("id")
                    or ""
                ).strip().lower()
                == requested_id
            )
        ]

    # Resolve textarea[id='...'].
    match = re.fullmatch(
        r"textarea\s*\[\s*id\s*=\s*['\"]([^'\"]+)['\"]\s*\]",
        target,
        re.IGNORECASE,
    )

    if match:
        requested_id = (
            match.group(1).strip().lower()
        )

        return [
            element
            for element in elements
            if (
                element.get("type")
                == "textarea"
                and (
                    element.get("id")
                    or ""
                ).strip().lower()
                == requested_id
            )
        ]

    # Resolve input[placeholder='...'].
    match = re.fullmatch(
        r"input\s*\[\s*placeholder\s*=\s*['\"]([^'\"]+)['\"]\s*\]",
        target,
        re.IGNORECASE,
    )

    if match:
        requested_placeholder = (
            match.group(1).strip().lower()
        )

        return [
            element
            for element in elements
            if (
                element.get("type")
                == "input"
                and (
                    element.get("placeholder")
                    or ""
                ).strip().lower()
                == requested_placeholder
            )
        ]

    # Resolve input[aria-label='...'].
    match = re.fullmatch(
        r"input\s*\[\s*aria-label\s*=\s*['\"]([^'\"]+)['\"]\s*\]",
        target,
        re.IGNORECASE,
    )

    if match:
        requested_label = (
            match.group(1).strip().lower()
        )

        return [
            element
            for element in elements
            if (
                element.get("type")
                == "input"
                and (
                    element.get("aria_label")
                    or ""
                ).strip().lower()
                == requested_label
            )
        ]

    return []


# Convert model target into canonical UI target.
def normalize_action_target(
    action,
    elements,
):
    if not isinstance(action, dict):
        return action

    matches = find_matching_elements(
        action.get("target"),
        elements,
    )

    if not matches:
        return action

    element = matches[0]

    action_type = (
        action.get("action")
        or ""
    ).strip().lower()

    if action_type == "type":
        canonical_target = (
            element.get("placeholder")
            or element.get("aria_label")
            or element.get("name")
            or element.get("id")
            or ""
        )

    elif action_type == "click":
        canonical_target = (
            element.get("text")
            or element.get("aria_label")
            or ""
        )

    else:
        canonical_target = ""

    if canonical_target:
        action["target"] = canonical_target

    return action


# Validate one browser action.
def validate_action(
    action,
    elements,
):
    if not isinstance(action, dict):
        return False, "Action is not an object."

    action_type = (
        action.get("action") or ""
    ).strip().lower()

    if action_type not in ALLOWED_ACTIONS:
        return False, (
            f"Unsupported action: "
            f"{action_type}"
        )

    action["action"] = action_type

    target = (
        action.get("target") or ""
    ).strip()

    if not target:
        return False, "Action target is missing."

    # Resolve CSS selectors before validation.
    matching_elements = find_matching_elements(
        target,
        elements,
    )

    if not matching_elements:
        return False, (
            f"Target not found: "
            f"{target}"
        )

    # Normalize to the exact perceived target.
    normalize_action_target(
        action,
        elements,
    )

    target = (
        action.get("target") or ""
    ).strip()

    matching_elements = find_matching_elements(
        target,
        elements,
    )

    if not matching_elements:
        return False, (
            f"Target not found after "
            f"normalization: {target}"
        )

    # Validate TYPE actions.
    if action_type == "type":
        value = action.get("value")

        if value is None or value == "":
            return False, "Type value is missing."

        if value == "USER_PROVIDED_VALUE":
            return False, (
                "Type value was not provided "
                "by the user."
            )

        if not any(
            element.get("type")
            in {
                "input",
                "textarea",
            }
            for element in matching_elements
        ):
            return False, (
                f"Target is not a text input: "
                f"{target}"
            )

    # Validate CLICK actions.
    if action_type == "click":
        if not any(
            element.get("type")
            in {
                "button",
                "link",
            }
            for element in matching_elements
        ):
            return False, (
                f"Target is not clickable: "
                f"{target}"
            )

    return True, "Valid action."


# Validate the complete action plan.
def validate_actions(
    actions,
    elements,
):
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


# Standalone planner validation test.
if __name__ == "__main__":
    test_elements = [
        {
            "type": "button",
            "text": "Search",
            "aria_label": "",
            "placeholder": "",
            "name": "",
            "id": "",
        },
        {
            "type": "input",
            "text": "",
            "aria_label": "",
            "placeholder": "Enter your name",
            "name": "name",
            "id": "name",
        },
    ]

    test_actions = [
        {
            "action": "type",
            "target": "input[name='name']",
            "value": "Shivansh",
        },
        {
            "action": "click",
            "target": "Search",
        },
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