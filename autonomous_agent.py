from playwright.sync_api import sync_playwright
from agent.perception.dom import get_dom_elements
from PIL import Image
import pytesseract
import requests
import io
import json
import os
import re
import shutil


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_PAGE = os.path.join(BASE_DIR, "demo", "test_page.html")


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


def ask_ollama(user_goal, elements):
    prompt = f"""
You are a browser automation planner.

USER GOAL:
{user_goal}

AVAILABLE UI ELEMENTS:
{json.dumps(elements, indent=2)}

Break the user's goal into the smallest possible sequence
of browser actions.

Allowed actions:

CLICK:
{{
    "action": "click",
    "target": "Search"
}}

TYPE:
{{
    "action": "type",
    "target": "Enter your name",
    "value": "Kishan"
}}

Return ONLY a JSON array.

Rules:
- Return ONLY valid JSON.
- No markdown.
- No explanation.
- target must exactly match an available UI element.
- Execute actions in logical order.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )

    response.raise_for_status()

    return response.json()["response"]


def extract_actions(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)

    if not match:
        return None

    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def get_ocr_text(page):
    screenshot = page.screenshot()

    image = Image.open(
        io.BytesIO(screenshot)
    )

    return pytesseract.image_to_string(image).strip()


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


def print_ocr_text(text):
    print("\nOCR TEXT")
    print("-" * 72)

    if text:
        print(text)
    else:
        print("No text detected.")

    print("-" * 72)


def execute_click(page, target):
    buttons = page.locator("button")

    for i in range(buttons.count()):
        button = buttons.nth(i)

        try:
            text = button.inner_text().strip()

            if text.lower() == target.lower():
                print(f"Clicking: {target}")

                button.click()

                print("Click completed.")

                return True

        except Exception:
            continue

    print(f"Button not found: {target}")

    return False


def execute_type(page, target, value):
    inputs = page.locator("input")

    for i in range(inputs.count()):
        input_element = inputs.nth(i)

        try:
            placeholder = input_element.get_attribute("placeholder")

            if (
                placeholder
                and placeholder.lower() == target.lower()
            ):
                print(f"Typing into: {target}")

                input_element.fill(value)

                actual_value = input_element.input_value()

                if actual_value == value:
                    print("Type completed.")
                    return True

                print("Type verification failed.")

                return False

        except Exception:
            continue

    print(f"Input not found: {target}")

    return False


def main():
    configure_tesseract()

    print("\n" + "=" * 72)
    print("                    VISUAL BROWSER AGENT")
    print("=" * 72)

    if not os.path.exists(TEST_PAGE):
        print(f"\nTest page not found:")
        print(TEST_PAGE)
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page(
            viewport={
                "width": 1280,
                "height": 720
            }
        )

        page.goto(
            "file://" + TEST_PAGE
        )

        page.wait_for_timeout(1000)

        print("\nBrowser opened.")

        print("\nPERCEPTION")
        print("=" * 72)

        elements = get_dom_elements(page)

        print_ui_elements(elements)

        ocr_text = get_ocr_text(page)

        print_ocr_text(ocr_text)

        user_goal = input(
            "\nEnter task:\n> "
        ).strip()

        if not user_goal:
            print("No task provided. Try again.")
            page.wait_for_timeout(3000)
            return

        print("\nPLANNER")
        print("=" * 72)
        print("Sending task to Ollama...")

        try:
            raw_response = ask_ollama(
                user_goal,
                elements
            )

        except Exception as e:
            print(f"\nOllama error: {e}")
            browser.close()
            return

        actions = extract_actions(
            raw_response
        )

        if not actions:
            print("\nCould not parse Ollama action plan.")
            print(raw_response)
            browser.close()
            return

        print(f"Action plan generated: {len(actions)} step(s)")

        print("\nACTION PLAN")
        print("-" * 72)

        for number, action in enumerate(
            actions,
            start=1
        ):
            action_type = action.get("action", "").upper()
            target = action.get("target", "")

            if action_type == "TYPE":
                value = action.get("value", "")
                print(
                    f"{number}. TYPE   {target} -> {value}"
                )
            else:
                print(
                    f"{number}. {action_type:<6} {target}"
                )

        print("-" * 72)

        all_success = True

        for number, action in enumerate(
            actions,
            start=1
        ):
            action_type = action.get("action")
            target = action.get("target")

            print(f"\nSTEP {number}/{len(actions)}")

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
                    f"Unsupported action: {action_type}"
                )

                success = False

            if not success:
                print(f"Step {number} failed.")
                all_success = False
                break

            print(f"Step {number} completed.")

            page.wait_for_timeout(1000)

        print("\n" + "=" * 72)

        if all_success:
            print("                         TASK COMPLETED")
        else:
            print("                           TASK FAILED")

        print("=" * 72)

        page.wait_for_timeout(3000)

        browser.close()


if __name__ == "__main__":
    main()