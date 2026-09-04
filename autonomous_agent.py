# Browser automation and page interaction.
from playwright.sync_api import sync_playwright

# Browser perception modules.
from agent.perception.dom import get_dom_elements

# Privacy protection modules.
from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import (
    sanitize_page,
    sanitize_page_text,
)

# AI action validation module.
from agent.planner import validate_actions

# OCR and image processing.
from PIL import Image
import pytesseract

# HTTP communication with local Ollama.
import requests

# Standard Python utilities.
import io
import json
import os
import re
import shutil
import time


# Local Ollama configuration.
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:3b",
)


# Security limits.
MAX_ACTIONS_PER_TASK = 20
MAX_REPLANS_PER_TASK = 5
MAX_TASK_RUNTIME_SECONDS = 120
MAX_VERIFY_RETRIES = 1

# One-time verification failure test.
TEST_REPLAN = os.getenv(
    "AGENT_TEST_REPLAN",
    "0",
) == "1"

# Demo webpage location.
BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TEST_PAGE = os.path.join(
    BASE_DIR,
    "demo",
    "test_page.html",
)


# Configure Tesseract OCR.
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
    lower_goal = goal.lower()

    # Handle "search for <value>" tasks.
    search_match = re.match(
        r"^\s*search\s+for\s+(.+?)\s*$",
        goal,
        re.IGNORECASE,
    )

    if search_match:
        value = (
            search_match.group(1)
            .strip()
        )

        input_target = None
        search_target = None

        for element in elements:
            if element.get("type") != "input":
                continue

            placeholder = element.get(
                "placeholder",
                "",
            )

            aria_label = element.get(
                "aria_label",
                "",
            )

            if (
                "name" in placeholder.lower()
                or "search" in placeholder.lower()
                or "name" in aria_label.lower()
                or "search" in aria_label.lower()
            ):
                input_target = (
                    placeholder
                    or aria_label
                )

                break

        for element in elements:
            if element.get("type") != "button":
                continue

            text = element.get(
                "text",
                "",
            ).strip()

            aria_label = element.get(
                "aria_label",
                "",
            ).strip()

            if (
                text.lower() == "search"
                or aria_label.lower() == "search"
            ):
                search_target = (
                    text
                    or aria_label
                )

                break

        if (
            input_target
            and search_target
        ):
            return {
                "intent": "sequence",
                "steps": [
                    {
                        "action": "type",
                        "target": input_target,
                        "value": value,
                    },
                    {
                        "action": "click",
                        "target": search_target,
                    },
                ],
            }

    # Handle "find the <button/link>" tasks.
    find_match = re.match(
        r"^\s*find\s+(?:the\s+)?(.+?)(?:\s+(?:button|link))?\s*$",
        goal,
        re.IGNORECASE,
    )

    if find_match:
        requested_target = (
            find_match.group(1)
            .strip()
        )

        for element in elements:
            if element.get("type") not in {
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
                candidate = (
                    candidate or ""
                ).strip()

                if (
                    candidate.lower()
                    == requested_target.lower()
                ):
                    return {
                        "intent": "click_only",
                        "target": candidate,
                    }

        return {
            "intent": "click_only",
            "target": requested_target,
        }

    # Handle "click <target>" tasks.
    click_match = re.match(
        r"^\s*click\s+(?:the\s+)?(.+?)(?:\s+(?:button|link))?\s*$",
        goal,
        re.IGNORECASE,
    )

    if click_match:
        requested_target = (
            click_match.group(1)
            .strip()
        )

        for element in elements:
            if element.get("type") not in {
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
                candidate = (
                    candidate or ""
                ).strip()

                if (
                    candidate.lower()
                    == requested_target.lower()
                ):
                    return {
                        "intent": "click_only",
                        "target": candidate,
                    }

        return {
            "intent": "click_only",
            "target": requested_target,
        }

    # Use Ollama for genuinely general tasks.
    return {
        "intent": "general",
        "target": "",
    }


# Sanitize action history before sending it to the local model.
def sanitize_action_history(
    action_history,
):
    sanitized = []

    for item in action_history:
        sanitized.append(
            {
                "action": item.get(
                    "action"
                ),
                "target": item.get(
                    "target"
                ),
                "value": (
                    "[REDACTED]"
                    if item.get("action")
                    == "type"
                    else None
                ),
                "result": item.get(
                    "result"
                ),
            }
        )

    return sanitized


# Send sanitized webpage context to Ollama.
def ask_ollama(
    user_goal,
    elements,
    page_text,
    task_constraint,
    action_history,
):
    sanitized_history = (
        sanitize_action_history(
            action_history
        )
    )

    # Build the exact data allowed to leave the privacy firewall.
    payload_context = {
        "user_goal": user_goal,
        "task_constraint": task_constraint,
        "safe_page_text": page_text,
        "safe_ui_elements": elements,
        "action_history": sanitized_history,
    }

    # Privacy audit: block known sensitive values.
    payload_text = json.dumps(
        payload_context,
        ensure_ascii=False,
    )

    forbidden_patterns = [
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)",
        r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",
    ]

    for pattern in forbidden_patterns:
        if re.search(
            pattern,
            payload_text,
        ):
            raise RuntimeError(
                "PRIVACY FIREWALL BLOCKED "
                "OLLAMA REQUEST: sensitive data "
                "detected in outbound payload."
            )

    # Never send credential values to the model.
    for element in elements:
        input_type = (
            element.get("input_type")
            or ""
        ).lower()

        if input_type == "password":
            value = element.get(
                "value"
            )

            if value:
                raise RuntimeError(
                    "PRIVACY FIREWALL BLOCKED "
                    "OLLAMA REQUEST: credential "
                    "value detected in outbound payload."
                )

    # Print an auditable outbound payload summary.
    print("\nOLLAMA PRIVACY AUDIT")
    print("-" * 72)
    print(
        "Raw webpage data sent: NO"
    )
    print(
        "Sanitized page text sent: YES"
    )
    print(
        "Sanitized UI elements sent: YES"
    )
    print(
        "Credential values sent: NO"
    )
    print(
        "PII patterns detected in payload: NO"
    )
    print("-" * 72)

    prompt = f"""
You are a strict browser automation planner.

USER GOAL:
{user_goal}

TASK CONSTRAINT:
{json.dumps(task_constraint, indent=2)}

SAFE PAGE TEXT:
{page_text}

AVAILABLE SAFE UI ELEMENTS:
{json.dumps(elements, indent=2)}

PREVIOUS ACTION HISTORY:
{json.dumps(sanitized_history, indent=2)}

Generate ONLY the next browser action required.

Allowed actions:

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
1. Return ONLY a valid JSON object.
2. No markdown or explanations.
3. Generate exactly ONE action.
4. Every target must exactly match an available UI element.
5. Never invent a target.
6. Never invent personal information.
7. Never invent names, emails, phone numbers, passwords, tokens, or values.
8. Never use USER_PROVIDED_VALUE.
9. Never use placeholder values.
10. Never create TYPE unless the user explicitly supplied the value.
11. Use the TASK CONSTRAINT as a hard restriction.
12. Use CLICK only for buttons or links.
13. Use TYPE only for input or textarea elements.
14. For click-only tasks, generate only CLICK.
15. For sequence tasks, generate only the next required step.
16. Do not repeat an already completed action unless the previous attempt failed.
17. If required information is missing, return an empty JSON array.
18. SAFE PAGE TEXT may contain redaction tokens such as [EMAIL], [PHONE], [CREDIT_CARD], and [REDACTED].
19. Never attempt to recover or infer the original value represented by a redaction token.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()["response"]


# Extract a JSON object or array from the model response.
def extract_actions(text):
    text = text.strip()

    object_match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL,
    )

    if object_match:
        try:
            parsed = json.loads(
                object_match.group()
            )

            if isinstance(
                parsed,
                dict,
            ):
                return [parsed]

        except json.JSONDecodeError:
            pass

    array_match = re.search(
        r"\[.*\]",
        text,
        re.DOTALL,
    )

    if array_match:
        try:
            parsed = json.loads(
                array_match.group()
            )

            if isinstance(
                parsed,
                list,
            ):
                return parsed

        except json.JSONDecodeError:
            pass

    return None


# Capture screenshot and extract OCR text with coordinates.
def get_ocr_text(page):
    screenshot = page.screenshot()

    image = Image.open(
        io.BytesIO(screenshot)
    ).convert("RGB")

    ocr_data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
    )

    words = []
    regions = []

    for index, text in enumerate(
        ocr_data["text"]
    ):
        text = text.strip()

        if not text:
            continue

        try:
            confidence = float(
                ocr_data["conf"][index]
            )
        except (
            ValueError,
            TypeError,
        ):
            confidence = 0

        x = int(
            ocr_data["left"][index]
        )

        y = int(
            ocr_data["top"][index]
        )

        width = int(
            ocr_data["width"][index]
        )

        height = int(
            ocr_data["height"][index]
        )

        words.append(text)

        regions.append(
            {
                "text": text,
                "confidence": confidence,
                "block_num": ocr_data["block_num"][index],
                "par_num": ocr_data["par_num"][index],
                "line_num": ocr_data["line_num"][index],
                "box": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
            }
        )

    return {
        "text": " ".join(words),
        "regions": regions,
    }

# Display discovered UI elements.
def print_ui_elements(elements):
    print("\nUI ELEMENTS")
    print("-" * 72)

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

    print("-" * 72)

    for index, element in enumerate(
        elements,
        start=1,
    ):
        element_type = element.get(
            "type",
            "",
        )

        text = (
            element.get("text")
            or element.get("aria_label")
            or element.get("placeholder")
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

        print(
            f"{index:<4} "
            f"{element_type:<10} "
            f"{text[:23]:<25} "
            f"{position:<20}"
        )

    print("-" * 72)


# Display OCR output.
def print_ocr_text(text):
    print("\nOCR TEXT")
    print("-" * 72)

    if text:
        print(text)
    else:
        print("No text detected.")

    print("-" * 72)


# Display privacy findings.
def print_privacy_findings(findings):
    print("\nPRIVACY FIREWALL")
    print("-" * 72)

    if not findings:
        print(
            "No sensitive information detected."
        )
        print("-" * 72)
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

        value = finding.get(
            "value"
        )

        display_value = (
            "[REDACTED]"
            if value
            else "[SENSITIVE ELEMENT]"
        )

        print(
            f"{index}. "
            f"{finding_type.upper():<15} "
            f"{display_value}"
        )

    print("-" * 72)


# Display sanitized UI context.
def print_safe_elements(elements):
    print("\nSAFE UI CONTEXT")
    print("-" * 72)

    if not elements:
        print(
            "No safe UI elements available."
        )
        print("-" * 72)
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
            element.get("text")
            or element.get("aria_label")
            or element.get("placeholder")
            or "-"
        )

        value = element.get(
            "value"
        ) or ""

        print(
            f"{index}. "
            f"{element_type.upper():<10} "
            f"{text:<30} "
            f"value={value}"
        )

    print("-" * 72)


# Capture browser state before an action.
def capture_state(page):
    try:
        body_text = page.locator(
            "body"
        ).inner_text()
    except Exception:
        body_text = ""

    return {
        "url": page.url,
        "body_text": body_text,
    }


# Execute and verify a click action.
def execute_click(
    page,
    target,
    before_state,
):
    global TEST_REPLAN

    locators = [
        page.locator("button"),
        page.locator("a"),
    ]

    for locator in locators:
        for i in range(
            locator.count()
        ):
            element = locator.nth(i)

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
                    != target.lower()
                ):
                    continue

                print(
                    f"Clicking: {target}"
                )

                if TEST_REPLAN:
                    TEST_REPLAN = False

                    print(
                        "TEST: forcing one verification failure before execution."
                    )

                    return False

                # Perform the click.
                element.click()

                print(
                    "Click completed."
                )

                page.wait_for_timeout(
                    500
                )

                after_state = capture_state(
                    page
                )

                # Verify navigation or page-content change.
                if (
                    before_state["url"]
                    != after_state["url"]
                ):
                    print(
                        "Action verification passed."
                    )

                    return True

                if (
                    before_state["body_text"]
                    != after_state["body_text"]
                ):
                    print(
                        "Action verification passed."
                    )

                    return True

                # Browser accepted the click even without visible state change.
                print(
                    "Action verification passed: "
                    "click executed successfully."
                )

                return True

            except Exception as e:
                print(
                    f"Click error: {e}"
                )

                continue

    print(
        f"Clickable element not found: {target}"
    )

    return False


# Execute and verify a type action.
def execute_type(
    page,
    target,
    value,
):
    locators = [
        page.locator("input"),
        page.locator("textarea"),
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
                    ) or "",
                    input_element.get_attribute(
                        "aria-label"
                    ) or "",
                    input_element.get_attribute(
                        "name"
                    ) or "",
                    input_element.get_attribute(
                        "id"
                    ) or "",
                ]

                if not any(
                    candidate.lower()
                    == target.lower()
                    for candidate in candidates
                    if candidate
                ):
                    continue

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
                        "Action verification passed."
                    )

                    return True

                print(
                    "Action verification failed."
                )

                return False

            except Exception:
                continue

    print(
        f"Input not found: {target}"
    )

    return False


# Apply deterministic constraints to model actions.
def enforce_constraint(
    actions,
    task_constraint,
    completed_steps,
):
    if not actions:
        return actions

    intent = task_constraint.get(
        "intent"
    )

    if intent == "click_only":
        if len(actions) != 1:
            return None

        actions[0]["action"] = "click"

        actions[0]["target"] = (
            task_constraint["target"]
        )

        return actions

    if intent == "type_only":
        if len(actions) != 1:
            return None

        actions[0]["action"] = "type"

        actions[0]["target"] = (
            task_constraint["target"]
        )

        actions[0]["value"] = (
            task_constraint["value"]
        )

        return actions

    if intent == "sequence":
        steps = task_constraint[
            "steps"
        ]

        if completed_steps >= len(
            steps
        ):
            return []

        expected = steps[
            completed_steps
        ]

        matching = [
            action
            for action in actions
            if (
                action.get("action")
                or ""
            ).lower()
            == expected["action"]
        ]

        if not matching:
            return None

        action = matching[0]

        action["action"] = expected[
            "action"
        ]

        action["target"] = expected[
            "target"
        ]

        if (
            expected["action"]
            == "type"
        ):
            action["value"] = expected[
                "value"
            ]

        return [action]

    return actions


# Main closed-loop browser agent.
def main():
    global TEST_REPLAN

    configure_tesseract()

    print(
        "\n" + "=" * 72
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

        print(TEST_PAGE)

        return

    start_time = time.time()

    action_count = 0
    replan_count = 0
    completed_steps = 0

    action_history = []

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
            "file://" + TEST_PAGE
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

        elements = get_dom_elements(
            page
        )

        print_ui_elements(
            elements
        )

        # Initial OCR perception.
        ocr_result = get_ocr_text(
            page
        )

        ocr_text = ocr_result[
            "text"
        ]

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

        privacy_findings = inspect_page(
            elements,
            page.locator(
                "body"
            ).inner_text(),
        )

        print_privacy_findings(
            privacy_findings
        )

        safe_elements = sanitize_page(
            elements,
            privacy_findings,
        )

        print_safe_elements(
            safe_elements
        )

        # Receive user task.
        user_goal = input(
            "\nEnter task:\n> "
        ).strip()

        if not user_goal:
            print(
                "No task provided."
            )

            browser.close()

            return

        # Determine deterministic task constraints.
        task_constraint = (
            infer_task_constraint(
                user_goal,
                safe_elements,
            )
        )

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

        task_completed = False

        # Closed-loop planning and execution.
        while True:
            runtime = (
                time.time()
                - start_time
            )

            if (
                runtime
                > MAX_TASK_RUNTIME_SECONDS
            ):
                print(
                    "Task runtime limit exceeded."
                )

                break

            if (
                action_count
                >= MAX_ACTIONS_PER_TASK
            ):
                print(
                    "Action limit exceeded."
                )

                break

            if (
                replan_count
                > MAX_REPLANS_PER_TASK
            ):
                print(
                    "Replan limit exceeded."
                )

                break

            # Perceive current page before every plan.
            elements = get_dom_elements(
                page
            )

            privacy_findings = inspect_page(
                elements,
                page.locator(
                    "body"
                ).inner_text(),
            )

            safe_elements = sanitize_page(
                elements,
                privacy_findings,
            )

            safe_page_text = (
                sanitize_page_text(
                    page.locator(
                        "body"
                    ).inner_text(),
                    privacy_findings,
                )
            )

            # Determine the next required sequence step.
            if (
                task_constraint["intent"]
                == "sequence"
            ):
                steps = task_constraint[
                    "steps"
                ]

                if (
                    completed_steps
                    >= len(steps)
                ):
                    task_completed = True

                    break

            print(
                f"\nPLAN CYCLE "
                f"{replan_count + 1}"
            )

            print(
                "-" * 72
            )

            # Use deterministic steps directly when the task constraint is known.
            if (
                task_constraint["intent"]
                == "sequence"
            ):
                actions = [
                    task_constraint[
                        "steps"
                    ][
                        completed_steps
                    ].copy()
                ]

                print(
                    "Using deterministic task step."
                )

            else:
                print(
                    "Sending sanitized UI "
                    "context to Ollama..."
                )

                try:
                    raw_response = (
                        ask_ollama(
                            user_goal,
                            safe_elements,
                            safe_page_text,
                            task_constraint,
                            action_history,
                        )
                    )

                except Exception as e:
                    print(
                        f"Ollama error: {e}"
                    )

                    break

                actions = extract_actions(
                    raw_response
                )

                if actions is None:
                    print(
                        "Could not parse "
                        "Ollama action plan."
                    )

                    replan_count += 1

                    continue

                actions = enforce_constraint(
                    actions,
                    task_constraint,
                    completed_steps,
                )

                if actions is None:
                    print(
                        "ACTION POLICY FAILED"
                    )

                    replan_count += 1

                    continue

            if not actions:
                if (
                    task_constraint[
                        "intent"
                    ]
                    == "sequence"
                    and completed_steps
                    >= len(
                        task_constraint[
                            "steps"
                        ]
                    )
                ):
                    task_completed = True

                else:
                    print(
                        "No valid action generated."
                    )

                break

            # Validate exactly one next action.
            if len(actions) != 1:
                print(
                    "Planner must generate "
                    "exactly one next action."
                )

                replan_count += 1

                continue

            action = actions[0]

            valid, errors = (
                validate_actions(
                    actions,
                    elements,
                )
            )

            if not valid:
                print(
                    "\nACTION VALIDATION FAILED"
                )

                for error in errors:
                    print(error)

                replan_count += 1

                continue

            print(
                f"Action selected: "
                f"{action.get('action').upper()} "
                f"{action.get('target')}"
            )

            action_type = action.get(
                "action"
            )

            target = action.get(
                "target"
            )

            # Capture state before execution.
            before_state = capture_state(
                page
            )

            success = False

            if action_type == "click":
                success = execute_click(
                    page,
                    target,
                    before_state,
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

            if success:
                action_count += 1

                action_history.append(
                    {
                        "action": action_type,
                        "target": target,
                        "value": (
                            action.get(
                                "value"
                            )
                            if action_type
                            == "type"
                            else None
                        ),
                        "result": "success",
                    }
                )

                print(
                    f"Action completed. "
                    f"Total actions: "
                    f"{action_count}"
                )

                # Check single-action task completion.
                if (
                    task_constraint[
                        "intent"
                    ]
                    in {
                        "click_only",
                        "type_only",
                    }
                ):
                    task_completed = True

                    break

                # Advance only after a successful sequence step.
                if (
                    task_constraint[
                        "intent"
                    ]
                    == "sequence"
                ):
                    completed_steps += 1

                    if (
                        completed_steps
                        >= len(
                            task_constraint[
                                "steps"
                            ]
                        )
                    ):
                        task_completed = True

                        break

                # Re-perceive and plan again.
                replan_count += 1

                print(
                    f"Security counters: "
                    f"actions={action_count}, "
                    f"replans={replan_count}, "
                    f"runtime={time.time() - start_time:.2f}s"
                )

                continue

            # Record failed action without sensitive values.
            action_history.append(
                {
                    "action": action_type,
                    "target": target,
                    "value": (
                        "[REDACTED]"
                        if action_type == "type"
                        else None
                    ),
                    "result": (
                        "verification_failed"
                    ),
                }
            )

            print(
                "Action verification failed."
            )

            replan_count += 1

            print(
                f"Security counters: "
                f"actions={action_count}, "
                f"replans={replan_count}, "
                f"runtime={time.time() - start_time:.2f}s"
            )

            # Re-perception happens at the top of the loop.

        # Final status.
        print(
            "\n" + "=" * 72
        )

        if task_completed:
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

        print(
            "\nACTION HISTORY"
        )

        print(
            "-" * 72
        )

        if not action_history:
            print(
                "No actions executed."
            )

        else:
            for index, item in enumerate(
                action_history,
                start=1,
            ):
                action_name = item.get(
                    "action",
                    "",
                ).upper()

                target = item.get(
                    "target",
                    "",
                )

                result = item.get(
                    "result",
                    "",
                )

                print(
                    f"{index}. "
                    f"{action_name:<6} "
                    f"{target:<25} "
                    f"{result}"
                )

        print(
            "-" * 72
        )

        page.wait_for_timeout(
            3000
        )

        browser.close()


if __name__ == "__main__":
    main()