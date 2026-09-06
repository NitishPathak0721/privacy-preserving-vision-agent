from typing import Any


def _get_box(element):
    try:
        box = element.bounding_box()

        if not box:
            return None

        return {
            "x": round(box["x"], 2),
            "y": round(box["y"], 2),
            "width": round(box["width"], 2),
            "height": round(box["height"], 2),
        }

    except Exception:
        return None


def _get_text(element):
    try:
        return element.inner_text().strip()
    except Exception:
        return ""


def _get_attribute(element, name):
    try:
        return element.get_attribute(name) or ""
    except Exception:
        return ""


def _is_visible(element):
    try:
        return element.is_visible()
    except Exception:
        return False


def _is_enabled(element):
    try:
        return element.is_enabled()
    except Exception:
        return False


def _build_element(element, element_type):
    if not _is_visible(element):
        return None

    box = _get_box(element)

    if not box:
        return None

    return {
        "type": element_type,
        "tag": _get_attribute(element, "tagName").lower(),
        "role": _get_attribute(element, "role"),
        "text": _get_text(element),
        "aria_label": _get_attribute(element, "aria-label"),
        "placeholder": _get_attribute(element, "placeholder"),
        "input_type": _get_attribute(element, "type"),
        "name": _get_attribute(element, "name"),
        "id": _get_attribute(element, "id"),
        "value": _get_attribute(element, "value"),
        "visible": True,
        "enabled": _is_enabled(element),
        "box": box,
    }


def get_dom_elements(page) -> list[dict[str, Any]]:
    elements = []

    selectors = {
        "button": "button",
        "input": "input",
        "textarea": "textarea",
        "select": "select",
        "link": "a",
    }

    for element_type, selector in selectors.items():
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):
            element = locator.nth(index)

            try:
                data = _build_element(element, element_type)

                if data:
                    elements.append(data)

            except Exception:
                continue

    return elements
