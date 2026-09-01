from playwright.sync_api import sync_playwright
from PIL import Image
import pytesseract
import requests
import io
import json
import os
import re


# ============================================================
# CONFIG
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

TESSERACT_PATH = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ============================================================
# OLLAMA
# ============================================================

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

Example:

[
    {{
        "action": "type",
        "target": "Enter your name",
        "value": "Kishan"
    }},
    {{
        "action": "click",
        "target": "Search"
    }}
]

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


# ============================================================
# EXTRACT JSON ARRAY
# ============================================================

def extract_actions(text):

    match = re.search(
        r"\[.*\]",
        text,
        re.DOTALL
    )

    if not match:
        return None

    try:

        return json.loads(
            match.group()
        )

    except json.JSONDecodeError:

        return None


# ============================================================
# GET DOM ELEMENTS
# ============================================================

def get_dom_elements(page):

    elements = []

    # --------------------------------------------------------
    # BUTTONS
    # --------------------------------------------------------

    buttons = page.locator("button")

    for i in range(buttons.count()):

        button = buttons.nth(i)

        try:

            text = button.inner_text().strip()

            box = button.bounding_box()

            if box and text:

                elements.append({
                    "type": "button",
                    "text": text,
                    "x": round(box["x"], 2),
                    "y": round(box["y"], 2),
                    "width": round(box["width"], 2),
                    "height": round(box["height"], 2)
                })

        except Exception:

            continue


    # --------------------------------------------------------
    # INPUTS
    # --------------------------------------------------------

    inputs = page.locator("input")

    for i in range(inputs.count()):

        input_element = inputs.nth(i)

        try:

            placeholder = (
                input_element
                .get_attribute("placeholder")
            )

            input_type = (
                input_element
                .get_attribute("type")
            )

            box = input_element.bounding_box()

            if box:

                elements.append({
                    "type": "input",
                    "text": placeholder or "input",
                    "input_type": input_type or "text",
                    "x": round(box["x"], 2),
                    "y": round(box["y"], 2),
                    "width": round(box["width"], 2),
                    "height": round(box["height"], 2)
                })

        except Exception:

            continue

    return elements


# ============================================================
# OCR
# ============================================================

def get_ocr_text(page):

    screenshot = page.screenshot()

    image = Image.open(
        io.BytesIO(screenshot)
    )

    return pytesseract.image_to_string(
        image
    )


# ============================================================
# CLICK
# ============================================================

def execute_click(page, target):

    buttons = page.locator("button")

    for i in range(buttons.count()):

        button = buttons.nth(i)

        try:

            text = button.inner_text().strip()

            if text.lower() == target.lower():

                print(
                    f"🖱️ Clicking '{target}'..."
                )

                button.click()

                print(
                    "✅ CLICK COMPLETED"
                )

                return True

        except Exception:

            continue


    print(
        f"❌ Button '{target}' not found."
    )

    return False


# ============================================================
# TYPE
# ============================================================

def execute_type(page, target, value):

    inputs = page.locator("input")

    for i in range(inputs.count()):

        input_element = inputs.nth(i)

        try:

            placeholder = (
                input_element
                .get_attribute("placeholder")
            )

            if (
                placeholder
                and
                placeholder.lower()
                == target.lower()
            ):

                print(
                    f"⌨️ Typing '{value}' "
                    f"into '{target}'..."
                )

                input_element.fill(value)

                # -------------------------
                # VERIFY
                # -------------------------

                actual_value = (
                    input_element.input_value()
                )

                print(
                    f"🔍 Value after typing: "
                    f"'{actual_value}'"
                )

                if actual_value == value:

                    print(
                        "✅ TYPE VERIFIED"
                    )

                    return True

                else:

                    print(
                        "❌ TYPE VERIFICATION FAILED"
                    )

                    return False

        except Exception:

            continue


    print(
        f"❌ Input '{target}' not found."
    )

    return False


# ============================================================
# MAIN
# ============================================================

with sync_playwright() as p:

    print(
        "\n===================================="
    )

    print(
        "       VISUAL BROWSER AGENT"
    )

    print(
        "===================================="
    )


    # --------------------------------------------------------
    # Browser
    # --------------------------------------------------------

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page(
        viewport={
            "width": 1280,
            "height": 720
        }
    )


    # --------------------------------------------------------
    # Local webpage
    # --------------------------------------------------------

    file_path = os.path.abspath(
        "test_page.html"
    )

    page.goto(
        "file://" + file_path
    )

    page.wait_for_timeout(
        1000
    )

    print(
        "\n🌐 Browser opened"
    )


    # ========================================================
    # PERCEPTION
    # ========================================================

    print(
        "\n===== PERCEPTION ====="
    )

    elements = get_dom_elements(
        page
    )


    print(
        "\n--- UI ELEMENTS ---"
    )

    for element in elements:

        print(
            element
        )


    # --------------------------------------------------------
    # OCR
    # --------------------------------------------------------

    ocr_text = get_ocr_text(
        page
    )

    print(
        "\n--- OCR TEXT ---"
    )

    print(
        ocr_text
    )


    # ========================================================
    # USER GOAL
    # ========================================================

    user_goal = input(
        "\nWhat do you want the agent to do?\n> "
    )


    # ========================================================
    # PLANNING
    # ========================================================

    print(
        "\n===== ASKING OLLAMA FOR PLAN ====="
    )


    try:

        raw_response = ask_ollama(
            user_goal,
            elements
        )

    except Exception as e:

        print(
            "\n❌ Ollama Error:"
        )

        print(e)

        browser.close()

        exit()


    print(
        "\nOLLAMA PLAN:"
    )

    print(
        raw_response
    )


    # ========================================================
    # PARSE PLAN
    # ========================================================

    actions = extract_actions(
        raw_response
    )


    if not actions:

        print(
            "\n❌ Could not parse action plan."
        )

        browser.close()

        exit()


    print(
        "\n===== ACTION PLAN ====="
    )


    for number, action in enumerate(
        actions,
        start=1
    ):

        print(
            f"{number}. {action}"
        )


    # ========================================================
    # EXECUTE PLAN
    # ========================================================

    all_success = True


    for number, action in enumerate(
        actions,
        start=1
    ):

        print(
            f"\n===== STEP {number} ====="
        )


        action_type = action.get(
            "action"
        )

        target = action.get(
            "target"
        )


        # ----------------------------------------------------
        # CLICK
        # ----------------------------------------------------

        if action_type == "click":

            success = execute_click(
                page,
                target
            )


        # ----------------------------------------------------
        # TYPE
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # UNKNOWN
        # ----------------------------------------------------

        else:

            print(
                f"❌ Unknown action: "
                f"{action_type}"
            )

            success = False


        # ----------------------------------------------------
        # Stop if failed
        # ----------------------------------------------------

        if not success:

            print(
                f"\n❌ STEP {number} FAILED"
            )

            all_success = False

            break


        print(
            f"✅ STEP {number} SUCCESS"
        )


        # Small wait before next step

        page.wait_for_timeout(
            1000
        )


    # ========================================================
    # FINAL RESULT
    # ========================================================

    print(
        "\n===================================="
    )


    if all_success:

        print(
            "       🎉 TASK COMPLETED"
        )

    else:

        print(
            "       ❌ TASK FAILED"
        )


    print(
        "===================================="
    )


    # Keep browser open

    page.wait_for_timeout(
        5000
    )


    browser.close()