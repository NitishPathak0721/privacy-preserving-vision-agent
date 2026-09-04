import sys
from pathlib import Path
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright
from PIL import Image
import pytesseract

from agent.perception.dom import get_dom_elements
from agent.privacy.firewall import inspect_page
from agent.privacy.visual import create_safe_screenshot


# Configure Tesseract on Windows.
if shutil.which("tesseract") is None:
    tesseract_path = Path(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    if tesseract_path.exists():
        pytesseract.pytesseract.tesseract_cmd = str(
            tesseract_path
        )


# Test screenshot privacy redaction.
def test_visual_privacy_redaction():
    root = Path(__file__).resolve().parents[1]
    test_page = root / "demo" / "test_page.html"
    screenshot_path = root / "tests" / "privacy_original.png"
    safe_screenshot_path = root / "tests" / "privacy_safe.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={
                "width": 1280,
                "height": 720,
            }
        )

        page.goto(
            "file://" + str(test_page)
        )

        page.wait_for_timeout(500)

        elements = get_dom_elements(page)

        page_text = page.locator("body").inner_text()

        findings = inspect_page(
            elements,
            page_text,
        )

        page.screenshot(
            path=str(screenshot_path)
        )

        browser.close()

    image = Image.open(
        screenshot_path
    ).convert("RGB")

    ocr_data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
    )

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
        except ValueError:
            confidence = -1

        regions.append(
            {
                "text": text,
                "confidence": confidence,
                "block_num": ocr_data["block_num"][index],
                "par_num": ocr_data["par_num"][index],
                "line_num": ocr_data["line_num"][index],
                "box": {
                    "x": ocr_data["left"][index],
                    "y": ocr_data["top"][index],
                    "width": ocr_data["width"][index],
                    "height": ocr_data["height"][index],
                },
            }
        )

    ocr_result = {
        "text": " ".join(
            region["text"]
            for region in regions
        ),
        "regions": regions,
    }

    create_safe_screenshot(
        screenshot_path,
        elements,
        findings,
        ocr_result,
        safe_screenshot_path,
    )

    assert safe_screenshot_path.exists()

    screenshot_path.unlink(
        missing_ok=True
    )

    safe_screenshot_path.unlink(
        missing_ok=True
    )

    print(
        "Visual privacy redaction test passed."
    )


if __name__ == "__main__":
    test_visual_privacy_redaction()