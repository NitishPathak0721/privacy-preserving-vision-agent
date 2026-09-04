# Visual privacy redaction.
from PIL import Image, ImageFilter

from agent.privacy.pii import detect_pii


# Redact one rectangular sensitive region.
def redact_region(
    image,
    box,
    mode="blur",
):
    x = int(box["x"])
    y = int(box["y"])
    width = int(box["width"])
    height = int(box["height"])

    if width <= 0 or height <= 0:
        return image

    padding = 4

    x1 = max(
        0,
        x - padding,
    )

    y1 = max(
        0,
        y - padding,
    )

    x2 = min(
        image.width,
        x + width + padding,
    )

    y2 = min(
        image.height,
        y + height + padding,
    )

    region = image.crop(
        (
            x1,
            y1,
            x2,
            y2,
        )
    )

    if mode == "blur":
        region = region.filter(
            ImageFilter.GaussianBlur(
                radius=18
            )
        )

    elif mode == "black":
        region = Image.new(
            "RGB",
            region.size,
            "black",
        )

    image.paste(
        region,
        (
            x1,
            y1,
        ),
    )

    return image


# Redact sensitive DOM elements.
def redact_sensitive_elements(
    image,
    elements,
    findings,
):
    sensitive_elements = {
        id(finding.get("element"))
        for finding in findings
        if finding.get("element") is not None
    }

    for element in elements:
        if id(element) not in sensitive_elements:
            continue

        box = element.get("box")

        if not box:
            continue

        redact_region(
            image,
            box,
            mode="blur",
        )

    return image


# Group OCR words by their Tesseract line.
def _group_ocr_lines(
    ocr_regions,
):
    lines = {}

    for region in ocr_regions:
        line_key = (
            region.get("block_num", 0),
            region.get("par_num", 0),
            region.get("line_num", 0),
        )

        lines.setdefault(
            line_key,
            [],
        ).append(region)

    for regions in lines.values():
        regions.sort(
            key=lambda item: item["box"]["x"]
        )

    return list(
        lines.values()
    )


# Find sensitive regions inside OCR output.
def find_sensitive_ocr_regions(
    ocr_result,
):
    regions = ocr_result.get(
        "regions",
        [],
    )

    sensitive_regions = []

    lines = _group_ocr_lines(
        regions
    )

    for line in lines:
        if not line:
            continue

        line_text = " ".join(
            region["text"]
            for region in line
        )

        findings = detect_pii(
            line_text
        )

        for finding in findings:
            start = finding["start"]
            end = finding["end"]

            character_position = 0
            matched_regions = []

            for region in line:
                word = region["text"]

                word_start = (
                    character_position
                )

                word_end = (
                    word_start
                    + len(word)
                )

                if (
                    end > word_start
                    and start < word_end
                ):
                    matched_regions.append(
                        region
                    )

                character_position = (
                    word_end + 1
                )

            if not matched_regions:
                continue

            min_x = min(
                region["box"]["x"]
                for region in matched_regions
            )

            min_y = min(
                region["box"]["y"]
                for region in matched_regions
            )

            max_x = max(
                region["box"]["x"]
                + region["box"]["width"]
                for region in matched_regions
            )

            max_y = max(
                region["box"]["y"]
                + region["box"]["height"]
                for region in matched_regions
            )

            sensitive_regions.append(
                {
                    "type": finding["type"],
                    "value": finding["value"],
                    "box": {
                        "x": min_x,
                        "y": min_y,
                        "width": max_x - min_x,
                        "height": max_y - min_y,
                    },
                }
            )

    return sensitive_regions


# Redact PII detected by OCR.
def redact_ocr_regions(
    image,
    ocr_result,
):
    sensitive_regions = (
        find_sensitive_ocr_regions(
            ocr_result
        )
    )

    for region in sensitive_regions:
        redact_region(
            image,
            region["box"],
            mode="blur",
        )

    return image


# Create a privacy-safe screenshot.
def create_safe_screenshot(
    screenshot,
    elements,
    findings,
    ocr_result,
    output_path,
):
    image = Image.open(
        screenshot
    ).convert("RGB")

    redact_sensitive_elements(
        image,
        elements,
        findings,
    )

    redact_ocr_regions(
        image,
        ocr_result,
    )

    image.save(
        output_path
    )

    return output_path