from pathlib import Path

from PIL import Image, ImageDraw

from agent.privacy.visual import (
    find_sensitive_ocr_regions,
    redact_ocr_regions,
)


# Test OCR detects a sensitive email region.
def test_find_sensitive_ocr_regions():
    ocr_result = {
        "regions": [
            {
                "text": "Email:",
                "box": {
                    "x": 10,
                    "y": 10,
                    "width": 50,
                    "height": 20,
                },
                "block_num": 1,
                "par_num": 1,
                "line_num": 1,
            },
            {
                "text": "shivansh@example.com",
                "box": {
                    "x": 65,
                    "y": 10,
                    "width": 180,
                    "height": 20,
                },
                "block_num": 1,
                "par_num": 1,
                "line_num": 1,
            },
        ]
    }

    regions = find_sensitive_ocr_regions(
        ocr_result
    )

    assert len(regions) == 1
    assert regions[0]["type"] == "email"
    assert regions[0]["value"] == "shivansh@example.com"

    box = regions[0]["box"]

    assert box["x"] == 65
    assert box["y"] == 10
    assert box["width"] == 180
    assert box["height"] == 20


# Test OCR-sensitive regions are visually changed.
def test_redact_ocr_regions(tmp_path):
    image = Image.new(
        "RGB",
        (300, 100),
        "white",
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (65, 10, 245, 30),
        fill="black",
    )

    original_pixel = image.getpixel(
        (150, 20)
    )

    ocr_result = {
        "regions": [
            {
                "text": "Email:",
                "box": {
                    "x": 10,
                    "y": 10,
                    "width": 50,
                    "height": 20,
                },
                "block_num": 1,
                "par_num": 1,
                "line_num": 1,
            },
            {
                "text": "shivansh@example.com",
                "box": {
                    "x": 65,
                    "y": 10,
                    "width": 180,
                    "height": 20,
                },
                "block_num": 1,
                "par_num": 1,
                "line_num": 1,
            },
        ]
    }

    redacted_image = redact_ocr_regions(
        image.copy(),
        ocr_result,
    )

    redacted_pixel = redacted_image.getpixel(
        (150, 20)
    )

    assert redacted_pixel != original_pixel

    output_path = tmp_path / "redacted.png"

    redacted_image.save(
        output_path
    )

    assert output_path.exists()


if __name__ == "__main__":
    test_find_sensitive_ocr_regions()

    temporary_directory = Path(
        ".visual_privacy_test"
    )

    temporary_directory.mkdir(
        exist_ok=True
    )

    test_redact_ocr_regions(
        temporary_directory
    )

    for file in temporary_directory.iterdir():
        file.unlink()

    temporary_directory.rmdir()

    print("Visual privacy tests passed.")