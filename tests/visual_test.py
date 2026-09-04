import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright
from PIL import Image
import pytesseract


def test_visual_perception():
    test_page = Path(__file__).resolve().parents[1] / 'demo' / 'test_page.html'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 720})

        page.goto('file://' + str(test_page))
        page.wait_for_timeout(500)

        screenshot_path = Path(__file__).resolve().parent / 'test.png'
        page.screenshot(path=str(screenshot_path))

        browser.close()

    image = Image.open(screenshot_path)
    text = pytesseract.image_to_string(image)

    assert 'Privacy Browser Agent Demo' in text
    assert 'Profile' in text
    assert 'Search' in text

    screenshot_path.unlink(missing_ok=True)


if __name__ == '__main__':
    test_visual_perception()
    print('Visual perception test passed.')
