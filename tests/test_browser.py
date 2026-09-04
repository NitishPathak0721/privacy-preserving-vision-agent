import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright


def test_demo_page_browser():
    test_page = Path(__file__).resolve().parents[1] / 'demo' / 'test_page.html'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto('file://' + str(test_page))

        assert page.title() == 'Privacy Browser Agent Demo'
        assert page.get_by_role('button', name='Search').is_visible()
        assert page.get_by_role('button', name='Login').is_visible()
        assert page.get_by_placeholder('Enter your name').is_visible()
        assert page.get_by_placeholder('Enter password').is_visible()

        browser.close()


if __name__ == '__main__':
    test_demo_page_browser()
    print('Browser test passed.')
