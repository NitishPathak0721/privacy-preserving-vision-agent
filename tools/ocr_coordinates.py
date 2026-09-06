from playwright.sync_api import sync_playwright
from PIL import Image
import pytesseract
import io


# Tesseract path
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page(
        viewport={"width": 1280, "height": 720}
    )

    page.goto("https://www.google.com")
    page.wait_for_load_state("networkidle")

    # Take screenshot
    screenshot = page.screenshot()

    image = Image.open(io.BytesIO(screenshot))

    # OCR with coordinates
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT
    )

    print("\n===== DETECTED UI TEXT =====\n")

    for i in range(len(data["text"])):

        text = data["text"][i].strip()

        if text:
            x = data["left"][i]
            y = data["top"][i]
            width = data["width"][i]
            height = data["height"][i]

            print(
                f"Text: {text:20} "
                f"X: {x:4} "
                f"Y: {y:4} "
                f"W: {width:4} "
                f"H: {height:4}"
            )

    page.wait_for_timeout(5000)

    browser.close()