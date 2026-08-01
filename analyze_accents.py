"""Detect accent/brand colors (saturated, non-grayscale) in reference images."""
import json
from pathlib import Path
from PIL import Image
import collections
import colorsys


def is_grayscale(r, g, b, threshold=15):
    """Check if a color is essentially grayscale."""
    mx, mn = max(r, g, b), min(r, g, b)
    return (mx - mn) < threshold


def is_extreme(r, g, b):
    """Check if color is too dark or too light to be an accent."""
    brightness = (r + g + b) / 3
    return brightness < 25 or brightness > 235


def get_saturation(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return s


def extract_accent_colors(img, top_n=15):
    """Extract saturated, non-grayscale colors that could be accents."""
    img_small = img.convert("RGB").resize((300, 300))
    pixels = list(img_small.getdata())

    accent_pixels = []
    for r, g, b in pixels:
        if is_grayscale(r, g, b) or is_extreme(r, g, b):
            continue
        sat = get_saturation(r, g, b)
        if sat > 0.15:  # At least 15% saturation
            # Quantize for grouping
            q = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
            accent_pixels.append((q, sat))

    if not accent_pixels:
        return []

    counter = collections.Counter([p[0] for p in accent_pixels])
    total_pixels = len(pixels)
    results = []
    for color, count in counter.most_common(top_n):
        h, s, v = colorsys.rgb_to_hsv(color[0] / 255, color[1] / 255, color[2] / 255)
        results.append({
            "hex": "#{:02x}{:02x}{:02x}".format(*color),
            "rgb": list(color),
            "hsv": [round(h * 360), round(s, 3), round(v, 3)],
            "ratio": round(count / total_pixels, 5),
        })
    return results


def detect_gradients(img):
    """Detect if the image has gradient backgrounds by sampling vertical strips."""
    img_rgb = img.convert("RGB").resize((100, 100))
    w, h = img_rgb.size
    # Sample left edge top to bottom
    left_strip = [img_rgb.getpixel((2, y)) for y in range(0, h, 5)]
    # Sample top edge left to right
    top_strip = [img_rgb.getpixel((x, 2)) for x in range(0, w, 5)]

    def is_gradient(strip):
        if len(strip) < 2:
            return False
        diffs = [abs(sum(strip[i]) - sum(strip[i - 1])) for i in range(1, len(strip))]
        avg_diff = sum(diffs) / len(diffs) if diffs else 0
        # Check if it's a smooth gradient (consistent small changes)
        return avg_diff > 3

    return {
        "left_vertical_gradient": is_gradient(left_strip),
        "top_horizontal_gradient": is_gradient(top_strip),
        "left_strip_colors": ["#{:02x}{:02x}{:02x}".format(*c) for c in left_strip[:5] + left_strip[-5:]],
        "top_strip_colors": ["#{:02x}{:02x}{:02x}".format(*c) for c in top_strip[:5] + top_strip[-5:]],
    }


def main():
    pic_dir = Path(r"d:\BattleFish\BatteryEMCL Lab\pic")
    for img_path in sorted(pic_dir.glob("*.webp")):
        img = Image.open(str(img_path))
        print(f"\n{'='*60}")
        print(f"FILE: {img_path.name}  ({img.size[0]}x{img.size[1]})")
        print(f"{'='*60}")

        accents = extract_accent_colors(img)
        print(f"\nAccent/Brand colors (saturated, non-gray):")
        if accents:
            for a in accents[:8]:
                print(f"  {a['hex']}  HSV={a['hsv']}  ratio={a['ratio']}")
        else:
            print("  (none detected - image is monochromatic)")

        gradients = detect_gradients(img)
        print(f"\nGradient detection:")
        print(f"  Left vertical gradient: {gradients['left_vertical_gradient']}")
        print(f"  Top horizontal gradient: {gradients['top_horizontal_gradient']}")
        print(f"  Left strip (top->bottom): {gradients['left_strip_colors']}")
        print(f"  Top strip (left->right): {gradients['top_strip_colors']}")


if __name__ == "__main__":
    main()
