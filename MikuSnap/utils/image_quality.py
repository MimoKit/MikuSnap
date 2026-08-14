from __future__ import annotations

from PIL import Image, ImageStat


def is_blank_image(image: Image.Image) -> bool:
    sample = image.convert("RGB")
    sample.thumbnail((160, 160), Image.Resampling.LANCZOS)
    extrema = sample.getextrema()
    if all(high - low <= 3 for low, high in extrema):
        return True

    stats = ImageStat.Stat(sample)
    if max(stats.stddev) <= 1.5:
        return True

    pixels = list(sample.getdata())
    near_white = sum(1 for pixel in pixels if min(pixel) >= 248)
    near_black = sum(1 for pixel in pixels if max(pixel) <= 7)
    return max(near_white, near_black) / len(pixels) >= 0.998
