import os
import requests
import json
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

def ask_ollama(prompt):
    response = requests.post(
       f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    response.raise_for_status()
    return response.json()["response"]


with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    # Test webpage
    page.set_content("""
        <html>
            <body>
                <h1>Browser Agent Test</h1>

                <button id="login">Login</button>
                <button id="search">Search</button>
                <button id="cancel">Cancel</button>

                <p id="status">No action yet</p>
            </body>
        </html>
    """)

    # User's goal
    user_goal = "Click the Search button"

    # Get available buttons
    buttons = page.locator("button").all_inner_texts()

    print("Available buttons:", buttons)

    # Ask Ollama
    prompt = f"""
You are a browser automation agent.

User goal:
{user_goal}

Available buttons:
{buttons}

Choose the button that should be clicked.

Return ONLY valid JSON in this exact format:
{{"action": "click", "target": "button text"}}
"""

    answer = ask_ollama(prompt)

    print("\nOllama raw response:")
    print(answer)

    # Extract JSON
    try:
        action = json.loads(answer)

        target = action["target"]

        print("\nSelected target:", target)

        # Execute action
        page.get_by_role("button", name=target).click()

        print("✅ Button clicked successfully!")

    except Exception as e:
        print("❌ Could not execute action:", e)

    page.wait_for_timeout(3000)

    browser.close()