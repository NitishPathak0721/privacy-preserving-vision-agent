from playwright.sync_api import sync_playwright
from PIL import Image
import pytesseract
import io


# Tesseract location
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


with sync_playwright() as p:

    # Open visible browser
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    # Open website
    page.goto("https://www.google.com")

    # Wait for page
    page.wait_for_load_state("networkidle")

    # Take screenshot directly into memory
    screenshot = page.screenshot()

    # Convert screenshot bytes → PIL image
    image = Image.open(io.BytesIO(screenshot))

    # OCR
    text = pytesseract.image_to_string(image)

    print("\n===== BROWSER OCR RESULT =====\n")
    print(text)

    # Keep browser open for 5 seconds
    page.wait_for_timeout(5000)

    browser.close()