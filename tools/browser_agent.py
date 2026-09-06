from playwright.sync_api import sync_playwright
from PIL import Image
import pytesseract
import requests
import io


# Tesseract path
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


# -----------------------------
# Ask Ollama
# -----------------------------
def ask_ollama(text):

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2:3b",
            "prompt": f"""
You are a browser visual assistant.

Here is the text detected from a webpage:

{text}

Explain briefly:
1. What type of webpage is this?
2. What important UI elements can you identify?

Do not perform any action.
""",
            "stream": False
        }
    )

    response.raise_for_status()

    return response.json()["response"]


# -----------------------------
# Browser
# -----------------------------
with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page(
        viewport={"width": 1280, "height": 720}
    )

    page.goto("https://www.google.com")

    page.wait_for_load_state("networkidle")

    print("Browser opened")
    print("URL:", page.url)

    # -----------------------------
    # Screenshot
    # -----------------------------
    screenshot = page.screenshot()

    image = Image.open(io.BytesIO(screenshot))

    # -----------------------------
    # OCR
    # -----------------------------
    text = pytesseract.image_to_string(image)

    print("\n===== OCR TEXT =====")
    print(text)

    # -----------------------------
    # Ollama
    # -----------------------------
    print("\n===== ASKING OLLAMA =====")

    answer = ask_ollama(text)

    print("\n===== OLLAMA RESPONSE =====")
    print(answer)

    page.wait_for_timeout(5000)

    browser.close()