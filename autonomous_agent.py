# Browser automation and page interaction.
from playwright.sync_api import sync_playwright

from agent.security.policy import (
    MAX_ACTIONS_PER_TASK,
    MAX_REPLANS_PER_TASK,
    MAX_TASK_RUNTIME_SECONDS,
    is_action_allowed,
)

# Browser perception modules.
from agent.perception.dom import get_dom_elements

# Privacy protection modules.
from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import sanitize_page

# AI action validation module.
from agent.planner import validate_actions

# OCR and image processing.
from PIL import Image
import pytesseract

# HTTP communication with local Ollama.
import requests

# Standard Python utilities.
import base64
import io
import json
import os
import re
import shutil
import time

# Visual privacy redaction.
from agent.privacy.visual import create_safe_screenshot


# Local Ollama configuration.
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5vl:3b",
)


# Demo webpage location.
BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TEST_PAGE = os.path.join(
    BASE_DIR,
    "demo",
    "test_page.html",
)


# Configure Tesseract OCR for the current operating system.
def configure_tesseract():
    tesseract_path = shutil.which(
        "tesseract"
    )

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = (
            tesseract_path
        )

        print(
            f"Tesseract: {tesseract_path}"
        )

        return

    windows_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for path in windows_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = (
                path
            )

            print(
                f"Tesseract: {path}"
            )

            return

    raise RuntimeError(
        "Tesseract OCR not found. "
        "Install Tesseract and add it to PATH."
    )


# Infer deterministic constraints from explicit task wording.
def infer_task_constraint(
    user_goal,
    elements,
):
    goal = user_goal.strip()

    # Detect an explicit ordered sequence before handling single-action tasks.
    sequence_pattern = re.compile(
        r"type\s+[\"'](.+?)[\"']\s+into\s+(.+?)\s+and\s+click\s+(.+?)\s*$",
        re.IGNORECASE,
    )

    sequence_match = sequence_pattern.match(
        goal
    )

    if sequence_match:
        type_value = (
            sequence_match.group(1).strip()
        )

        type_target = (
            sequence_match.group(2).strip()
        )

        click_target = (
            sequence_match.group(3).strip()
        )

        resolved_type_target = (
            type_target
        )

        resolved_click_target = (
            click_target
        )

        for element in elements:
            if element.get(
                "type"
            ) in {
                "input",
                "textarea",
            }:
                candidates = [
                    element.get(
                        "placeholder",
                        "",
                    ),
                    element.get(
                        "aria_label",
                        "",
                    ),
                    element.get(
                        "name",
                        "",
                    ),
                    element.get(
                        "id",
                        "",
                    ),
                ]

                for candidate in candidates:
                    if (
                        candidate
                        and candidate.strip().lower()
                        == type_target.lower()
                    ):
                        resolved_type_target = (
                            candidate.strip()
                        )

                        break

            if element.get(
                "type"
            ) in {
                "button",
                "link",
            }:
                candidates = [
                    element.get(
                        "text",
                        "",
                    ),
                    element.get(
                        "aria_label",
                        "",
                    ),
                ]

                for candidate in candidates:
                    if (
                        candidate
                        and candidate.strip().lower()
                        == click_target.lower()
                    ):
                        resolved_click_target = (
                            candidate.strip()
                        )

                        break

        return {
            "intent": "sequence",
            "steps": [
                {
                    "action": "type",
                    "target": resolved_type_target,
                    "value": type_value,
                },
                {
                    "action": "click",
                    "target": resolved_click_target,
                },
            ],
        }

    click_match = re.match(
        r"^\s*click\s+(?:the\s+)?(.+?)(?:\s+(?:button|link))?\s*$",
        goal,
        re.IGNORECASE,
    )

    if click_match:
        requested_target = (
            click_match.group(1).strip()
        )

        for element in elements:
            if element.get(
                "type"
            ) not in {
                "button",
                "link",
            }:
                continue

            candidates = [
                element.get(
                    "text",
                    "",
                ),
                element.get(
                    "aria_label",
                    "",
                ),
            ]

            for candidate in candidates:
                if (
                    candidate
                    and candidate.strip().lower()
                    == requested_target.lower()
                ):
                    return {
                        "intent": "click_only",
                        "target": candidate.strip(),
                    }

        return {
            "intent": "click_only",
            "target": requested_target,
        }

    type_match = re.match(
        r'^\s*type\s+["\'](.+?)["\']\s+into\s+(.+?)\s*$',
        goal,
        re.IGNORECASE,
    )

    if type_match:
        value = type_match.group(
            1
        )

        requested_target = (
            type_match.group(2).strip()
        )

        for element in elements:
            if element.get(
                "type"
            ) not in {
                "input",
                "textarea",
            }:
                continue

            candidates = [
                element.get(
                    "placeholder",
                    "",
                ),
                element.get(
                    "aria_label",
                    "",
                ),
                element.get(
                    "name",
                    "",
                ),
                element.get(
                    "id",
                    "",
                ),
            ]

            for candidate in candidates:
                if (
                    candidate
                    and candidate.strip().lower()
                    == requested_target.lower()
                ):
                    return {
                        "intent": "type_only",
                        "target": candidate.strip(),
                        "value": value,
                    }

        return {
            "intent": "type_only",
            "target": requested_target,
            "value": value,
        }

    return {
        "intent": "general",
        "target": "",
    }


# Send sanitized webpage context and safe visual context to the local AI planner.
def ask_ollama(
    user_goal,
    elements,
    task_constraint,
    action_history,
    safe_screenshot_path,
):
    prompt = f"""
You are a strict browser automation planner operating in a closed-loop agent.

USER GOAL:
{user_goal}

TASK CONSTRAINT:
{json.dumps(task_constraint, indent=2)}

CURRENT SAFE UI ELEMENTS:
{json.dumps(elements, indent=2)}

ACTIONS ALREADY EXECUTED:
{json.dumps(action_history, indent=2)}

The attached image is a PRIVACY-SAFE screenshot.
Use it only as visual context for the current webpage.
Do not infer or reconstruct redacted information.

Choose ONLY the NEXT browser action.

CLICK:
{{
    "action": "click",
    "target": "exact UI element text"
}}

TYPE:
{{
    "action": "type",
    "target": "exact input placeholder or label",
    "value": "exact value explicitly provided by the user"
}}

STRICT RULES:
1. Return ONLY a valid JSON array.
2. The array must contain ZERO or ONE action.
3. Never return more than one action.
4. Every target must exactly match a CURRENT SAFE UI ELEMENT.
5. Never invent targets or personal information.
6. Never invent names, emails, phone numbers, passwords, tokens, or other values.
7. Never use placeholder values or USER_PROVIDED_VALUE.
8. Never create TYPE unless the user explicitly supplied the value.
9. Use CLICK only for buttons or links.
10. Use TYPE only for input or textarea elements.
11. Do not perform prerequisite actions unless explicitly required.
12. Do not fill forms automatically.
13. If the goal is already complete, return [].
14. If required information is missing, return [].
15. Do not repeat a successfully completed action unless the current page state requires it.
16. Use the TASK CONSTRAINT as a hard restriction.
17. Minimize actions.
18. For click-only tasks, output exactly one CLICK action for the requested target.
19. For type-only tasks, output exactly one TYPE action for the requested target and exact user-provided value.
20. For general tasks, output only the single NEXT action required.

Return [] only when the goal is complete or cannot safely continue.
"""

    with open(
        safe_screenshot_path,
        "rb",
    ) as image_file:
        image_base64 = (
            base64.b64encode(
                image_file.read()
            ).decode(
                "utf-8"
            )
        )

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [
                image_base64
            ],
            "stream": False,
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()[
        "response"
    ]


# Extract a JSON action array from the model response.
def extract_actions(
    text,
):
    match = re.search(
        r"\[.*\]",
        text,
        re.DOTALL,
    )

    if not match:
        return None

    try:
        return json.loads(
            match.group()
        )

    except json.JSONDecodeError:
        return None


# Capture the current webpage and return structured OCR output.
def get_ocr_result(
    page,
):
    screenshot = page.screenshot()

    image = Image.open(
        io.BytesIO(
            screenshot
        )
    )

    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
    )

    regions = []
    text_parts = []

    for index, text in enumerate(
        data["text"]
    ):
        text = (
            text
            or ""
        ).strip()

        if not text:
            continue

        try:
            confidence = float(
                data["conf"][index]
            )

        except (
            ValueError,
            TypeError,
        ):
            confidence = -1

        if confidence < 0:
            continue

        regions.append(
            {
                "text": text,
                "confidence": confidence,
                "block_num": data[
                    "block_num"
                ][index],
                "par_num": data[
                    "par_num"
                ][index],
                "line_num": data[
                    "line_num"
                ][index],
                "box": {
                    "x": int(
                        data[
                            "left"
                        ][index]
                    ),
                    "y": int(
                        data[
                            "top"
                        ][index]
                    ),
                    "width": int(
                        data[
                            "width"
                        ][index]
                    ),
                    "height": int(
                        data[
                            "height"
                        ][index]
                    ),
                },
            }
        )

        text_parts.append(
            text
        )

    return {
        "text": " ".join(
            text_parts
        ).strip(),
        "regions": regions,
    }


# Return OCR text for console output.
def get_ocr_text(
    page,
):
    return get_ocr_result(
        page
    )["text"]


# Display the DOM elements discovered by the perception layer.
def print_ui_elements(
    elements,
):
    print(
        "\nUI ELEMENTS"
    )

    print(
        "-" * 72
    )

    if not elements:
        print(
            "No visible interactive elements found."
        )

        return

    print(
        f"{'#':<4} "
        f"{'TYPE':<10} "
        f"{'TEXT':<25} "
        f"{'POSITION':<20}"
    )

    print(
        "-" * 72
    )

    for index, element in enumerate(
        elements,
        start=1,
    ):
        element_type = element.get(
            "type",
            "",
        )

        text = (
            element.get(
                "text"
            )
            or element.get(
                "aria_label"
            )
            or element.get(
                "placeholder"
            )
            or "-"
        )

        box = element.get(
            "box",
            {},
        )

        position = (
            f"({box.get('x', 0):.0f}, "
            f"{box.get('y', 0):.0f}) "
            f"{box.get('width', 0):.0f}x"
            f"{box.get('height', 0):.0f}"
        )

        text = text[:23]

        print(
            f"{index:<4} "
            f"{element_type:<10} "
            f"{text:<25} "
            f"{position:<20}"
        )

    print(
        "-" * 72
    )


# Display OCR output from the current webpage.
def print_ocr_text(
    text,
):
    print(
        "\nOCR TEXT"
    )

    print(
        "-" * 72
    )

    if text:
        print(
            text
        )

    else:
        print(
            "No text detected."
        )

    print(
        "-" * 72
    )

# Display sensitive information detected by the privacy firewall.
def print_privacy_findings(
    findings,
):
    print(
        "\nPRIVACY FIREWALL"
    )

    print(
        "-" * 72
    )

    if not findings:
        print(
            "No sensitive information detected."
        )

        print(
            "-" * 72
        )

        return

    print(
        f"Sensitive findings detected: "
        f"{len(findings)}"
    )

    for index, finding in enumerate(
        findings,
        start=1,
    ):
        finding_type = finding.get(
            "type",
            "unknown",
        )

        element = finding.get(
            "element"
        )

        if element is not None:
            element_type = element.get(
                "type",
                "unknown",
            )
        else:
            element_type = "page_text"

        print(
            f"{index}. "
            f"{finding_type.upper():<15} "
            f"source={element_type}"
        )

    print(
        "-" * 72
    )


# Display the sanitized context that will be provided to the AI.
def print_safe_elements(
    elements,
):
    print(
        "\nSAFE UI CONTEXT"
    )

    print(
        "-" * 72
    )

    if not elements:
        print(
            "No safe UI elements available."
        )

        print(
            "-" * 72
        )

        return

    for index, element in enumerate(
        elements,
        start=1,
    ):
        element_type = element.get(
            "type",
            "",
        )

        text = (
            element.get(
                "text"
            )
            or element.get(
                "aria_label"
            )
            or element.get(
                "placeholder"
            )
            or "-"
        )

        value = (
            element.get(
                "value"
            )
            or ""
        )

        print(
            f"{index}. "
            f"{element_type.upper():<10} "
            f"{text:<30} "
            f"value={value}"
        )

    print(
        "-" * 72
    )


# Execute a validated click action against the real webpage.
def execute_click(
    page,
    target,
):
    locators = [
        page.locator(
            "button"
        ),
        page.locator(
            "a"
        ),
    ]

    for locator in locators:
        for i in range(
            locator.count()
        ):
            element = locator.nth(
                i
            )

            try:
                text = (
                    element.inner_text().strip()
                    or element.get_attribute(
                        "aria-label"
                    )
                    or ""
                )

                if (
                    text.lower()
                    == target.lower()
                ):
                    print(
                        f"Clicking: {target}"
                    )

                    element.click()

                    print(
                        "Click completed."
                    )

                    return True

            except Exception:
                continue

    print(
        f"Clickable element not found: {target}"
    )

    return False


# Execute a validated type action against the real webpage.
def execute_type(
    page,
    target,
    value,
):
    locators = [
        page.locator(
            "input"
        ),
        page.locator(
            "textarea"
        ),
    ]

    for locator in locators:
        for i in range(
            locator.count()
        ):
            input_element = locator.nth(
                i
            )

            try:
                candidates = [
                    input_element.get_attribute(
                        "placeholder"
                    )
                    or "",
                    input_element.get_attribute(
                        "aria-label"
                    )
                    or "",
                    input_element.get_attribute(
                        "name"
                    )
                    or "",
                    input_element.get_attribute(
                        "id"
                    )
                    or "",
                ]

                if any(
                    candidate.lower()
                    == target.lower()
                    for candidate in candidates
                    if candidate
                ):
                    print(
                        f"Typing into: {target}"
                    )

                    input_element.fill(
                        value
                    )

                    if (
                        input_element.input_value()
                        == value
                    ):
                        print(
                            "Type completed."
                        )

                        return True

                    print(
                        "Type verification failed."
                    )

                    return False

            except Exception:
                continue

    print(
        f"Input not found: {target}"
    )

    return False


# Capture the target state before a click so verification can detect a real effect.
def capture_click_state(
    page,
    target,
):
    target_state = None

    locators = [
        page.locator(
            "button"
        ),
        page.locator(
            "a"
        ),
    ]

    for locator in locators:
        for i in range(
            locator.count()
        ):
            element = locator.nth(
                i
            )

            try:
                text = (
                    element.inner_text().strip()
                    or element.get_attribute(
                        "aria-label"
                    )
                    or ""
                )

                if (
                    text.lower()
                    == target.lower()
                ):
                    target_state = {
                        "visible": element.is_visible(),
                        "enabled": element.is_enabled(),
                        "aria_expanded": (
                            element.get_attribute(
                                "aria-expanded"
                            )
                            or ""
                        ),
                        "aria_pressed": (
                            element.get_attribute(
                                "aria-pressed"
                            )
                            or ""
                        ),
                        "class": (
                            element.get_attribute(
                                "class"
                            )
                            or ""
                        ),
                    }

                    break

            except Exception:
                continue

        if target_state is not None:
            break

    try:
        body_text = page.locator(
            "body"
        ).inner_text()

    except Exception:
        body_text = ""

    try:
        body_html = page.locator(
            "body"
        ).inner_html()

    except Exception:
        body_html = ""

    return {
        "url": page.url,
        "body_text": body_text,
        "body_html": body_html,
        "target": target_state,
    }


# Verify that a browser action produced the expected result.
def verify_action(
    page,
    action,
    before_state=None,
):
    action_type = action.get(
        "action"
    )

    target = action.get(
        "target",
        "",
    )

    if action_type == "type":
        value = action.get(
            "value",
            "",
        )

        locators = [
            page.locator(
                "input"
            ),
            page.locator(
                "textarea"
            ),
        ]

        for locator in locators:
            for i in range(
                locator.count()
            ):
                element = locator.nth(
                    i
                )

                try:
                    candidates = [
                        element.get_attribute(
                            "placeholder"
                        )
                        or "",
                        element.get_attribute(
                            "aria-label"
                        )
                        or "",
                        element.get_attribute(
                            "name"
                        )
                        or "",
                        element.get_attribute(
                            "id"
                        )
                        or "",
                    ]

                    if any(
                        candidate.lower()
                        == target.lower()
                        for candidate in candidates
                        if candidate
                    ):
                        actual_value = (
                            element.input_value()
                        )

                        return (
                            actual_value
                            == value
                        )

                except Exception:
                    continue

        return False

    if action_type == "click":
        # Require a real target state captured before execution.
        if not before_state:
            return False

        if (
            before_state.get(
                "target"
            )
            is None
        ):
            return False

        try:
            page.wait_for_timeout(
                500
            )

        except Exception:
            pass

        after_state = (
            capture_click_state(
                page,
                target,
            )
        )

        # Navigation proves that the click caused a page transition.
        if (
            after_state.get(
                "url"
            )
            != before_state.get(
                "url"
            )
        ):
            return True

        # Page text changes prove that the click changed visible content.
        if (
            after_state.get(
                "body_text"
            )
            != before_state.get(
                "body_text"
            )
        ):
            return True

        # DOM changes prove that the click changed page structure.
        if (
            after_state.get(
                "body_html"
            )
            != before_state.get(
                "body_html"
            )
        ):
            return True

        before_target = (
            before_state.get(
                "target"
            )
            or {}
        )

        after_target = (
            after_state.get(
                "target"
            )
            or {}
        )

        # Target state changes prove that the intended control reacted.
        for key in [
            "visible",
            "enabled",
            "aria_expanded",
            "aria_pressed",
            "class",
        ]:
            if (
                before_target.get(
                    key
                )
                != after_target.get(
                    key
                )
            ):
                return True

        # No observable change means the click cannot be verified.
        return False

    return False


# Re-perceive the page and create a privacy-safe screenshot.
def reperceive_page(
    page,
):
    elements = get_dom_elements(
        page
    )

    ocr_result = get_ocr_result(
        page
    )

    page_text = page.locator(
        "body"
    ).inner_text()

    privacy_findings = inspect_page(
        elements,
        page_text,
    )

    safe_elements = sanitize_page(
        elements,
        privacy_findings,
    )

    screenshot_path = os.path.join(
        BASE_DIR,
        ".privacy_safe_screenshot.png",
    )

    raw_screenshot_path = os.path.join(
        BASE_DIR,
        ".privacy_raw_screenshot.png",
    )

    page.screenshot(
        path=raw_screenshot_path,
    )

    create_safe_screenshot(
        raw_screenshot_path,
        elements,
        privacy_findings,
        ocr_result,
        screenshot_path,
    )

    try:
        os.remove(
            raw_screenshot_path
        )

    except OSError:
        pass

    return (
        elements,
        ocr_result["text"],
        privacy_findings,
        safe_elements,
        screenshot_path,
    )


# Run the complete perception, privacy, planning, validation, and execution pipeline.
def main():
    configure_tesseract()

    print(
        "\n"
        + "=" * 72
    )

    print(
        "                    PRIVACY-PRESERVING"
    )

    print(
        "                     VISUAL BROWSER AGENT"
    )

    print(
        "=" * 72
    )

    if not os.path.exists(
        TEST_PAGE
    ):
        print(
            "\nTest page not found:"
        )

        print(
            TEST_PAGE
        )

        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page(
            viewport={
                "width": 1280,
                "height": 720,
            }
        )

        page.goto(
            "file://"
            + TEST_PAGE
        )

        page.wait_for_timeout(
            1000
        )

        print(
            "\nBrowser opened."
        )

        # Initial perception.
        print(
            "\nPERCEPTION"
        )

        print(
            "=" * 72
        )

        (
            elements,
            ocr_text,
            privacy_findings,
            safe_elements,
            safe_screenshot_path,
        ) = reperceive_page(
            page
        )

        print_ui_elements(
            elements
        )

        print_ocr_text(
            ocr_text
        )

        # Initial privacy analysis.
        print(
            "\nPRIVACY ANALYSIS"
        )

        print(
            "=" * 72
        )

        print_privacy_findings(
            privacy_findings
        )

        print_safe_elements(
            safe_elements
        )

        # Receive the natural-language browser task.
        user_goal = input(
            "\nEnter task:\n> "
        ).strip()

        if not user_goal:
            print(
                "No task provided."
            )

            browser.close()

            return

        # Initialize deterministic task constraints.
        task_constraint = (
            infer_task_constraint(
                user_goal,
                safe_elements,
            )
        )

        action_count = 0

        replan_count = 0

        task_start_time = (
            time.monotonic()
        )

        action_history = []

        all_success = True

        task_completed = False

        print(
            "\nAGENT LOOP"
        )

        print(
            "=" * 72
        )

        print(
            f"Task constraint: "
            f"{task_constraint}"
        )

        # Closed-loop planning and execution.
        while True:
            elapsed = (
                time.monotonic()
                - task_start_time
            )

            if (
                elapsed
                > MAX_TASK_RUNTIME_SECONDS
            ):
                print(
                    f"SECURITY STOP: "
                    f"Task runtime limit reached "
                    f"({MAX_TASK_RUNTIME_SECONDS}s)."
                )

                all_success = False

                break

            if (
                action_count
                >= MAX_ACTIONS_PER_TASK
            ):
                print(
                    f"SECURITY STOP: "
                    f"Maximum action limit reached "
                    f"({MAX_ACTIONS_PER_TASK})."
                )

                all_success = False

                break

            if (
                replan_count
                > MAX_REPLANS_PER_TASK
            ):
                print(
                    f"SECURITY STOP: "
                    f"Maximum replan limit reached "
                    f"({MAX_REPLANS_PER_TASK})."
                )

                all_success = False

                break

            print(
                f"\nPLAN CYCLE "
                f"{replan_count + 1}"
            )

            print(
                "-" * 72
            )

            print(
                "Sending sanitized UI context to Ollama..."
            )

            try:
                raw_response = ask_ollama(
                    user_goal,
                    safe_elements,
                    task_constraint,
                    action_history,
                    safe_screenshot_path,
                )

            except Exception as e:
                print(
                    f"\nOllama error: {e}"
                )

                all_success = False

                break

            actions = extract_actions(
                raw_response
            )

            if actions is None:
                print(
                    "\nCould not parse Ollama action plan."
                )

                print(
                    raw_response
                )

                all_success = False

                break

            # Explicit sequences must continue even when Ollama returns an empty plan.
            if not actions:
                if task_constraint[
                    "intent"
                ] == "sequence":
                    step_index = len(
                        action_history
                    )

                    expected_steps = (
                        task_constraint.get(
                            "steps",
                            [],
                        )
                    )

                    if (
                        step_index
                        >= len(
                            expected_steps
                        )
                    ):
                        task_completed = True

                        break

                    action = expected_steps[
                        step_index
                    ]

                    actions = [
                        action
                    ]

                    print(
                        "\nPlanner returned no action. "
                        "Using required sequence step: "
                        f"{action['action'].upper()} "
                        f"{action['target']}"
                    )

                elif task_constraint[
                    "intent"
                ] in {
                    "click_only",
                    "type_only",
                }:
                    print(
                        "\nNo safe action generated "
                        "for the requested task."
                    )

                    all_success = False

                    break

                else:
                    print(
                        "\nPlanner returned no action. "
                        "Task complete or unable to continue."
                    )

                    task_completed = True

                    break

            # For explicit sequences, only the exact expected next action is eligible.
            if task_constraint[
                "intent"
            ] == "sequence":
                step_index = len(
                    action_history
                )

                expected_steps = (
                    task_constraint[
                        "steps"
                    ]
                )

                if (
                    step_index
                    >= len(
                        expected_steps
                    )
                ):
                    task_completed = True

                    break

                expected = (
                    expected_steps[
                        step_index
                    ]
                )

                # Require action type, target, and TYPE value to match the expected step.
                matching_actions = [
                    candidate
                    for candidate in actions
                    if (
                        candidate.get(
                            "action"
                        )
                        == expected[
                            "action"
                        ]
                        and candidate.get(
                            "target",
                            "",
                        ).strip().lower()
                        == expected.get(
                            "target",
                            "",
                        ).strip().lower()
                        and (
                            expected[
                                "action"
                            ]
                            != "type"
                            or candidate.get(
                                "value"
                            )
                            == expected.get(
                                "value"
                            )
                        )
                    )
                ]

                if not matching_actions:
                    print(
                        "\nACTION POLICY FAILED"
                    )

                    print(
                        "-" * 72
                    )

                    print(
                        "Expected next action:"
                    )

                    print(
                        json.dumps(
                            expected,
                            indent=2,
                        )
                    )

                    print(
                        "Planner returned:"
                    )

                    print(
                        json.dumps(
                            actions,
                            indent=2,
                        )
                    )

                    print(
                        "-" * 72
                    )

                    all_success = False

                    break

                action = (
                    matching_actions[
                        0
                    ]
                )

                if len(
                    actions
                ) > 1:
                    print(
                        "Planner returned extra actions; "
                        "discarding them."
                    )

            else:
                if len(
                    actions
                ) != 1:
                    print(
                        "\nACTION POLICY FAILED"
                    )

                    print(
                        "-" * 72
                    )

                    print(
                        "Closed-loop planner must return exactly one action."
                    )

                    print(
                        "-" * 72
                    )

                    all_success = False

                    break

                action = actions[
                    0
                ]

            # Enforce deterministic click-only intent.
            if task_constraint[
                "intent"
            ] == "click_only":
                if action.get(
                    "action"
                ) != "click":
                    print(
                        "\nACTION POLICY FAILED"
                    )

                    print(
                        "Click-only task cannot contain another action."
                    )

                    all_success = False

                    break

                action[
                    "target"
                ] = task_constraint[
                    "target"
                ]

            # Enforce deterministic type-only intent.
            if task_constraint[
                "intent"
            ] == "type_only":
                if action.get(
                    "action"
                ) != "type":
                    print(
                        "\nACTION POLICY FAILED"
                    )

                    print(
                        "Type-only task must contain a TYPE action."
                    )

                    all_success = False

                    break

                action[
                    "target"
                ] = task_constraint[
                    "target"
                ]

                action[
                    "value"
                ] = task_constraint[
                    "value"
                ]

            # Validate the single action against current DOM state.
            valid, validation_errors = (
                validate_actions(
                    [action],
                    elements,
                )
            )

            if not valid:
                print(
                    "\nACTION VALIDATION FAILED"
                )

                print(
                    "-" * 72
                )

                for error in validation_errors:
                    print(
                        error
                    )

                print(
                    "-" * 72
                )

                all_success = False

                break

            # Enforce security capability policy.
            allowed, reason = (
                is_action_allowed(
                    action
                )
            )

            if not allowed:
                print(
                    f"SECURITY BLOCK: "
                    f"{reason}"
                )

                all_success = False

                break

            action_type = action.get(
                "action"
            )

            target = action.get(
                "target"
            )

            print(
                f"Action selected: "
                f"{action_type.upper()} "
                f"{target}"
            )

            if action_type == "type":
                print(
                    f"Value: "
                    f"{action.get('value', '')}"
                )

            # Capture the intended target state before executing a click.
            click_before_state = None

            if action_type == "click":
                click_before_state = (
                    capture_click_state(
                        page,
                        target,
                    )
                )

            # Execute exactly one validated action.
            if action_type == "click":
                success = execute_click(
                    page,
                    target,
                )

            elif action_type == "type":
                success = execute_type(
                    page,
                    target,
                    action.get(
                        "value",
                        "",
                    ),
                )

            else:
                print(
                    f"Unsupported action: "
                    f"{action_type}"
                )

                success = False

            if not success:
                print(
                    "Action execution failed."
                )

                all_success = False

                break

            action_count += 1

            print(
                f"Action completed. "
                f"Total actions: "
                f"{action_count}"
            )

            page.wait_for_timeout(
                500
            )

            # Verify the action before allowing another planning cycle.
            verified = verify_action(
                page,
                action,
                click_before_state,
            )

            if not verified:
                print(
                    "Action verification failed."
                )

                all_success = False

                break

            print(
                "Action verification passed."
            )

            action_history.append(
                action.copy()
            )

            # Explicit one-step tasks are complete after successful execution.
            if task_constraint[
                "intent"
            ] in {
                "click_only",
                "type_only",
            }:
                task_completed = True

                break

            # Complete an explicit sequence after all required steps execute.
            if task_constraint[
                "intent"
            ] == "sequence":
                if len(
                    action_history
                ) >= len(
                    task_constraint.get(
                        "steps",
                        [],
                    )
                ):
                    task_completed = True

                    break

            # Re-perceive before the next planning cycle.
            print(
                "Re-perceiving webpage..."
            )

            (
                elements,
                ocr_text,
                privacy_findings,
                safe_elements,
                safe_screenshot_path,
            ) = reperceive_page(
                page
            )

            print(
                f"Perception updated: "
                f"{len(elements)} UI element(s)."
            )

            replan_count += 1

        # Report final security state.
        print(
            f"Security counters: "
            f"actions={action_count}, "
            f"replans={replan_count}, "
            f"runtime="
            f"{time.monotonic() - task_start_time:.2f}s"
        )

        print(
            "\nACTION HISTORY"
        )

        print(
            "-" * 72
        )

        if action_history:
            for number, action in enumerate(
                action_history,
                start=1,
            ):
                action_type = (
                    action.get(
                        "action",
                        "",
                    )
                    .upper()
                )

                target = action.get(
                    "target",
                    "",
                )

                if action_type == "TYPE":
                    print(
                        f"{number}. "
                        f"TYPE "
                        f"{target} -> "
                        f"{action.get('value', '')}"
                    )

                else:
                    print(
                        f"{number}. "
                        f"{action_type} "
                        f"{target}"
                    )

        else:
            print(
                "No actions executed."
            )

        # Result.
        print(
            "\n"
            + "=" * 72
        )

        if (
            all_success
            and task_completed
        ):
            print(
                "                    TASK COMPLETED"
            )

        else:
            print(
                "                      TASK FAILED"
            )

        print(
            "=" * 72
        )

        page.wait_for_timeout(
            3000
        )

        browser.close()


if __name__ == "__main__":
    main()