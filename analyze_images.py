"""Analyze reference images to extract design characteristics."""
import sys
import json
from pathlib import Path

try:
    from PIL import Image
    import collections
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image
    import collections


def extract_palette(img, n_colors=10):
    """Extract dominant colors via simple quantization."""
    img_small = img.convert("RGB").resize((150, 150))
    pixels = list(img_small.getdata())
    # Quantize to reduce color space
    quantized = [(r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in pixels]
    counter = collections.Counter(quantized)
    total = len(pixels)
    palette = []
    for color, count in counter.most_common(n_colors):
        palette.append({
            "hex": "#{:02x}{:02x}{:02x}".format(*color),
            "rgb": list(color),
            "ratio": round(count / total, 4),
        })
    return palette


def analyze_regions(img):
    """Analyze average color in regions (top/header, left/sidebar, center, etc.)."""
    img_rgb = img.convert("RGB").resize((100, 100))
    w, h = img_rgb.size
    pixels = list(img_rgb.getdata())

    def region_avg(x1, y1, x2, y2):
        vals = []
        for y in range(y1, y2):
            for x in range(x1, x2):
                vals.append(pixels[y * w + x])
        if not vals:
            return None
        r = sum(p[0] for p in vals) // len(vals)
        g = sum(p[1] for p in vals) // len(vals)
        b = sum(p[2] for p in vals) // len(vals)
        return {"hex": "#{:02x}{:02x}{:02x}".format(r, g, b), "rgb": [r, g, b]}

    return {
        "top_left": region_avg(0, 0, 20, 15),
        "top_center": region_avg(40, 0, 60, 15),
        "top_right": region_avg(80, 0, 100, 15),
        "left_sidebar": region_avg(0, 30, 15, 70),
        "center": region_avg(30, 30, 70, 70),
        "bottom": region_avg(20, 85, 80, 100),
        "overall_bg": region_avg(0, 0, 100, 100),
    }


def brightness(rgb):
    return (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000


def analyze_image(path):
    img = Image.open(path)
    w, h = img.size
    palette = extract_palette(img, 12)
    regions = analyze_regions(img)
    overall = regions["overall_bg"]["rgb"]
    is_dark_theme = brightness(overall) < 128

    # Detect if there's a sidebar (left region different from center)
    left = regions["left_sidebar"]["rgb"]
    center = regions["center"]["rgb"]
    left_diff = abs(brightness(left) - brightness(center))

    return {
        "file": Path(path).name,
        "size": [w, h],
        "aspect_ratio": round(w / h, 3),
        "is_dark_theme": is_dark_theme,
        "overall_brightness": round(brightness(overall), 1),
        "has_distinct_sidebar": left_diff > 30,
        "dominant_colors": palette,
        "region_colors": regions,
    }


def main():
    pic_dir = Path(r"d:\BattleFish\BatteryEMCL Lab\pic")
    results = []
    for img_path in sorted(pic_dir.glob("*.webp")):
        print(f"Analyzing {img_path.name}...")
        try:
            info = analyze_image(str(img_path))
            results.append(info)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"file": img_path.name, "error": str(e)})

    print("\n" + "=" * 80)
    print("ANALYSIS RESULTS")
    print("=" * 80)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
