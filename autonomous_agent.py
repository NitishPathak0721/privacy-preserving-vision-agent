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
import io
import json
import os
import re
import shutil
import time


# Local Ollama configuration.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# Demo webpage location.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_PAGE = os.path.join(BASE_DIR, "demo", "test_page.html")


# Configure Tesseract OCR for the current operating system.
def configure_tesseract():
    tesseract_path = shutil.which("tesseract")

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        print(f"Tesseract: {tesseract_path}")
        return

    windows_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for path in windows_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            print(f"Tesseract: {path}")
            return

    raise RuntimeError(
        "Tesseract OCR not found. Install Tesseract and add it to PATH."
    )


# Infer deterministic constraints from explicit task wording.
def infer_task_constraint(user_goal, elements):
    goal = user_goal.strip()

    click_match = re.match(
        r"^\s*click\s+(?:the\s+)?(.+?)(?:\s+(?:button|link))?\s*$",
        goal,
        re.IGNORECASE,
    )

    if click_match:
        requested_target = click_match.group(1).strip()

        for element in elements:
            if element.get("type") not in {"button", "link"}:
                continue

            candidates = [
                element.get("text", ""),
                element.get("aria_label", ""),
            ]

            for candidate in candidates:
                if candidate and candidate.strip().lower() == requested_target.lower():
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
        value = type_match.group(1)
        requested_target = type_match.group(2).strip()

        for element in elements:
            if element.get("type") not in {"input", "textarea"}:
                continue

            candidates = [
                element.get("placeholder", ""),
                element.get("aria_label", ""),
                element.get("name", ""),
                element.get("id", ""),
            ]

            for candidate in candidates:
                if candidate and candidate.strip().lower() == requested_target.lower():
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


# Send only sanitized webpage context and explicit task constraints to the local AI planner.
def ask_ollama(user_goal, elements, task_constraint):
    prompt = f"""
You are a strict browser automation planner.

USER GOAL:
{user_goal}

TASK CONSTRAINT:
{json.dumps(task_constraint, indent=2)}

AVAILABLE SAFE UI ELEMENTS:
{json.dumps(elements, indent=2)}

Generate the smallest possible action sequence required to accomplish the user's goal.

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
1. Return ONLY a valid JSON array.
2. No markdown or explanations.
3. Every target must exactly match an available UI element.
4. Never invent a target or personal information.
5. Never invent names, emails, phone numbers, passwords, tokens, or other values.
6. Never use placeholder values or USER_PROVIDED_VALUE.
7. Never use "actual user-provided value".
8. Never create TYPE unless the user explicitly supplied the value.
9. If the user asks to click something, generate ONLY the required CLICK action.
10. For a click-only task, NEVER generate TYPE, SCROLL, NAVIGATE, or any other action.
11. Do not perform prerequisite actions unless explicitly required.
12. Do not fill forms automatically.
13. Do not assume an input must be filled before clicking.
14. If required information is missing, return [].
15. Use the TASK CONSTRAINT as a hard restriction.
16. Minimize the number of actions.
17. Use CLICK only for buttons or links.
18. Use TYPE only for input or textarea elements.

For a click-only task, output exactly one CLICK action for the requested target.
"""

    response = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"]


# Extract a JSON action array from the model response.
def extract_actions(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)

    if not match:
        return None

    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


# Capture the current webpage and convert visible text through OCR.
def get_ocr_text(page):
    screenshot = page.screenshot()

    image = Image.open(
        io.BytesIO(screenshot)
    )

    return pytesseract.image_to_string(image).strip()


# Display the DOM elements discovered by the perception layer.
def print_ui_elements(elements):
    print("\nUI ELEMENTS")
    print("-" * 72)

    if not elements:
        print("No visible interactive elements found.")
        return

    print(f"{'#':<4} {'TYPE':<10} {'TEXT':<25} {'POSITION':<20}")
    print("-" * 72)

    for index, element in enumerate(elements, start=1):
        element_type = element.get("type", "")

        text = (
            element.get("text")
            or element.get("aria_label")
            or element.get("placeholder")
            or "-"
        )

        box = element.get("box", {})

        position = (
            f"({box.get('x', 0):.0f}, {box.get('y', 0):.0f}) "
            f"{box.get('width', 0):.0f}x{box.get('height', 0):.0f}"
        )

        text = text[:23]

        print(
            f"{index:<4} "
            f"{element_type:<10} "
            f"{text:<25} "
            f"{position:<20}"
        )

    print("-" * 72)


# Display OCR output from the current webpage.
def print_ocr_text(text):
    print("\nOCR TEXT")
    print("-" * 72)

    if text:
        print(text)
    else:
        print("No text detected.")

    print("-" * 72)


# Display sensitive information detected by the privacy firewall.
def print_privacy_findings(findings):
    print("\nPRIVACY FIREWALL")
    print("-" * 72)

    if not findings:
        print("No sensitive information detected.")
        print("-" * 72)
        return

    print(f"Sensitive findings detected: {len(findings)}")

    for index, finding in enumerate(findings, start=1):
        finding_type = finding.get("type", "unknown")
        value = finding.get("value")

        if value:
            display_value = value
        else:
            display_value = "[SENSITIVE ELEMENT]"

        print(
            f"{index}. "
            f"{finding_type.upper():<15} "
            f"{display_value}"
        )

    print("-" * 72)


# Display the sanitized context that will be provided to the AI.
def print_safe_elements(elements):
    print("\nSAFE UI CONTEXT")
    print("-" * 72)

    if not elements:
        print("No safe UI elements available.")
        print("-" * 72)
        return

    for index, element in enumerate(elements, start=1):
        element_type = element.get("type", "")

        text = (
            element.get("text")
            or element.get("aria_label")
            or element.get("placeholder")
            or "-"
        )

        value = element.get("value") or ""

        print(
            f"{index}. "
            f"{element_type.upper():<10} "
            f"{text:<30} "
            f"value={value}"
        )

    print("-" * 72)


# Execute a validated click action against the real webpage.
def execute_click(page, target):
    locators = [page.locator("button"), page.locator("a")]

    for locator in locators:
        for i in range(locator.count()):
            element = locator.nth(i)

            try:
                text = (
                    element.inner_text().strip()
                    or element.get_attribute("aria-label")
                    or ""
                )

                if text.lower() == target.lower():
                    print(f"Clicking: {target}")
                    element.click()
                    print("Click completed.")
                    return True

            except Exception:
                continue

    print(f"Clickable element not found: {target}")
    return False


# Execute a validated type action against the real webpage.
def execute_type(page, target, value):
    locators = [page.locator("input"), page.locator("textarea")]

    for locator in locators:
        for i in range(locator.count()):
            input_element = locator.nth(i)

            try:
                candidates = [
                    input_element.get_attribute("placeholder") or "",
                    input_element.get_attribute("aria-label") or "",
                    input_element.get_attribute("name") or "",
                    input_element.get_attribute("id") or "",
                ]

                if any(
                    candidate.lower() == target.lower()
                    for candidate in candidates
                    if candidate
                ):
                    print(f"Typing into: {target}")
                    input_element.fill(value)

                    if input_element.input_value() == value:
                        print("Type completed.")
                        return True

                    print("Type verification failed.")
                    return False

            except Exception:
                continue

    print(f"Input not found: {target}")
    return False


# Verify that a browser action produced the expected result.
def verify_action(page, action):
    action_type = action.get("action")
    target = action.get("target", "")

    if action_type == "type":
        value = action.get("value", "")
        locators = [page.locator("input"), page.locator("textarea")]

        for locator in locators:
            for i in range(locator.count()):
                element = locator.nth(i)

                try:
                    candidates = [
                        element.get_attribute("placeholder") or "",
                        element.get_attribute("aria-label") or "",
                        element.get_attribute("name") or "",
                        element.get_attribute("id") or "",
                    ]

                    if any(
                        candidate.lower() == target.lower()
                        for candidate in candidates
                        if candidate
                    ):
                        actual_value = element.input_value()
                        return actual_value == value

                except Exception:
                    continue

        return False

    if action_type == "click":
        # Confirm that the clicked target remains a valid clickable element after execution.
        locators = [page.locator("button"), page.locator("a")]

        for locator in locators:
            for i in range(locator.count()):
                element = locator.nth(i)

                try:
                    text = (
                        element.inner_text().strip()
                        or element.get_attribute("aria-label")
                        or ""
                    )

                    if text.lower() == target.lower():
                        return element.is_visible() and element.is_enabled()

                except Exception:
                    continue

        return True

    return False


# Re-perceive the page after an action.
def reperceive_page(page):
    elements = get_dom_elements(page)
    ocr_text = get_ocr_text(page)
    privacy_findings = inspect_page(elements)
    safe_elements = sanitize_page(elements, privacy_findings)

    return elements, ocr_text, privacy_findings, safe_elements


# Run the complete perception, privacy, planning, validation, and execution pipeline.
def main():
    configure_tesseract()

    print("\n" + "=" * 72)
    print("                    PRIVACY-PRESERVING")
    print("                     VISUAL BROWSER AGENT")
    print("=" * 72)

    if not os.path.exists(TEST_PAGE):
        print("\nTest page not found:")
        print(TEST_PAGE)
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
            "file://" + TEST_PAGE
        )

        page.wait_for_timeout(1000)

        print("\nBrowser opened.")

        # Perception: collect the webpage structure and visible text.
        print("\nPERCEPTION")
        print("=" * 72)

        elements = get_dom_elements(page)

        print_ui_elements(elements)

        ocr_text = get_ocr_text(page)

        print_ocr_text(ocr_text)

        # Privacy: detect and sanitize sensitive webpage information.
        print("\nPRIVACY ANALYSIS")
        print("=" * 72)

        privacy_findings = inspect_page(elements)

        print_privacy_findings(
            privacy_findings
        )

        safe_elements = sanitize_page(
            elements,
            privacy_findings
        )

        print_safe_elements(
            safe_elements
        )

        # User: receive the natural-language browser task.
        user_goal = input(
            "\nEnter task:\n> "
        ).strip()

        if not user_goal:
            print("No task provided.")
            browser.close()
            return

        # Planning: derive task constraints before asking the local model to plan.
        print("\nPLANNER")
        print("=" * 72)

        task_constraint = infer_task_constraint(
            user_goal,
            safe_elements
        )

        print(f"Task constraint: {task_constraint}")
        print("Sending sanitized UI context to Ollama...")

        try:
            raw_response = ask_ollama(
                user_goal,
                safe_elements,
                task_constraint
            )

        except Exception as e:
            print(f"\nOllama error: {e}")
            browser.close()
            return

        actions = extract_actions(raw_response)

        if actions is None:
            print("\nCould not parse Ollama action plan.")
            print(raw_response)
            browser.close()
            return

        # Handle a deliberate empty plan before normal action validation.
        if not actions:
            print("\nNo actions required or required information is missing.")
            browser.close()
            return

        # Enforce explicit click-only intent after model generation.
        if task_constraint["intent"] == "click_only":
            if len(actions) != 1:
                print("\nACTION POLICY FAILED")
                print("-" * 72)
                print("Click-only task must contain exactly one action.")
                print("-" * 72)
                browser.close()
                return

            if actions[0].get("action") != "click":
                print("\nACTION POLICY FAILED")
                print("-" * 72)
                print("Click-only task cannot contain a TYPE action.")
                print("-" * 72)
                browser.close()
                return

            actions[0]["target"] = task_constraint["target"]

        # Enforce explicit type-only intent after model generation.
        if task_constraint["intent"] == "type_only":
            if len(actions) != 1:
                print("\nACTION POLICY FAILED")
                print("-" * 72)
                print("Type-only task must contain exactly one action.")
                print("-" * 72)
                browser.close()
                return

            if actions[0].get("action") != "type":
                print("\nACTION POLICY FAILED")
                print("-" * 72)
                print("Type-only task must contain exactly one TYPE action.")
                print("-" * 72)
                browser.close()
                return

            actions[0]["target"] = task_constraint["target"]
            actions[0]["value"] = task_constraint["value"]

        # Validation: prevent invalid or unsafe model actions from reaching the browser.
        valid, validation_errors = validate_actions(
            actions,
            elements
        )

        if not valid:
            print("\nACTION VALIDATION FAILED")
            print("-" * 72)

            for error in validation_errors:
                print(error)

            print("-" * 72)

            browser.close()
            return

        print("Action plan passed validation.")

        print(
            f"Action plan generated: "
            f"{len(actions)} step(s)"
        )

        print("\nACTION PLAN")
        print("-" * 72)

        for number, action in enumerate(
            actions,
            start=1
        ):
            action_type = action.get(
                "action",
                ""
            ).upper()

            target = action.get(
                "target",
                ""
            )

            if action_type == "TYPE":
                value = action.get(
                    "value",
                    ""
                )

                print(
                    f"{number}. TYPE   "
                    f"{target} -> {value}"
                )

            else:
                print(
                    f"{number}. "
                    f"{action_type:<6} "
                    f"{target}"
                )

        print("-" * 72)

        # Execution: perform validated actions and verify each result.
        all_success = True
        action_count = 0
        replan_count = 0
        task_start_time = time.monotonic()

        for number, action in enumerate(
            actions,
            start=1
        ):
            # Enforce task runtime limit.
            elapsed = time.monotonic() - task_start_time
            if elapsed > MAX_TASK_RUNTIME_SECONDS:
                print(
                    f"SECURITY STOP: Task runtime limit reached "
                    f"({MAX_TASK_RUNTIME_SECONDS}s)."
                )
                all_success = False
                break

            # Enforce action count limit.
            if action_count >= MAX_ACTIONS_PER_TASK:
                print(
                    f"SECURITY STOP: Maximum action limit reached "
                    f"({MAX_ACTIONS_PER_TASK})."
                )
                all_success = False
                break

            # Enforce action capability policy.
            allowed, reason = is_action_allowed(action)

            if not allowed:
                print(f"SECURITY BLOCK: {reason}")
                all_success = False
                break
            action_type = action.get("action")
            target = action.get("target")

            print(
                f"\nSTEP "
                f"{number}/{len(actions)}"
            )

            if action_type == "click":
                success = execute_click(
                    page,
                    target
                )

            elif action_type == "type":
                value = action.get(
                    "value",
                    ""
                )

                success = execute_type(
                    page,
                    target,
                    value
                )

            else:
                print(
                    f"Unsupported action: "
                    f"{action_type}"
                )
                success = False

            if not success:
                print(
                    f"Step {number} failed during execution."
                )
                all_success = False
                break

            # Count successfully executed actions.
            action_count += 1

            print(
                f"Step {number} completed."
            )

            page.wait_for_timeout(500)

            # Verify the action before continuing.
            verified = verify_action(
                page,
                action
            )

            if verified:
                print(
                    f"Step {number} verification passed."
                )
            else:
                print(
                    f"Step {number} verification failed."
                )
                all_success = False
                break

            # Re-perceive the webpage after every successful action.
            print(
                "Re-perceiving webpage..."
            )

            elements, ocr_text, privacy_findings, safe_elements = (
                reperceive_page(page)
            )

            print(
                f"Perception updated: "
                f"{len(elements)} UI element(s)."
            )

        # Result: report security counters before task status.
        print(
            f"Security counters: actions={action_count}, "
            f"replans={replan_count}, "
            f"runtime={time.monotonic() - task_start_time:.2f}s"
        )

        # Result: report whether the complete task succeeded.
        print("\n" + "=" * 72)

        if all_success:
            print(
                "                    TASK COMPLETED"
            )
        else:
            print(
                "                      TASK FAILED"
            )

        print("=" * 72)

        page.wait_for_timeout(
            3000
        )

        browser.close()


if __name__ == "__main__":
    main()