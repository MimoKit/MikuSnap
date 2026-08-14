from __future__ import annotations

import unittest
from pathlib import Path
from sys import path

from PIL import Image, ImageDraw

path.insert(0, str(Path(__file__).parents[1] / "MikuSnap" / "utils"))

from image_quality import is_blank_image  # noqa: E402


class BlankImageDetectionTest(unittest.TestCase):
    def test_solid_white_image_is_blank(self) -> None:
        image = Image.new("RGB", (1365, 900), "white")

        self.assertTrue(is_blank_image(image))

    def test_solid_dark_image_is_blank(self) -> None:
        image = Image.new("RGB", (1365, 900), (8, 8, 8))

        self.assertTrue(is_blank_image(image))

    def test_rendered_content_is_not_blank(self) -> None:
        image = Image.new("RGB", (1365, 900), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 80, 700, 500), fill=(39, 132, 255))
        draw.rectangle((120, 540, 1100, 620), fill=(30, 30, 30))

        self.assertFalse(is_blank_image(image))


if __name__ == "__main__":
    unittest.main()
