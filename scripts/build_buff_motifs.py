"""Build exact vector glyphs and matching alpha PNGs for the buff v07 compositor."""
from pathlib import Path
import hashlib
import json
import math

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/claude_buff_v07/assets"
SCALE = 4


def save_glyph(name, size, polygons, color):
    OUT.mkdir(parents=True, exist_ok=True)
    svg_polygons = []
    canvas = Image.new("RGBA", (size[0] * SCALE, size[1] * SCALE))
    draw = ImageDraw.Draw(canvas)
    for points in polygons:
        svg_polygons.append('<polygon points="' + " ".join(f"{x:.3f},{y:.3f}" for x, y in points) + '"/>')
        draw.polygon([(round(x * SCALE), round(y * SCALE)) for x, y in points], fill=color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size[0]} {size[1]}">'
           f'<g fill="#{color[0]:02x}{color[1]:02x}{color[2]:02x}">' + "".join(svg_polygons) + "</g></svg>\n")
    (OUT / (name + ".svg")).write_text(svg, encoding="utf-8")
    canvas.resize(size, Image.Resampling.LANCZOS).save(OUT / (name + ".png"))


def main():
    # A + backslash, not a font substitution; explicit top-left to bottom-right slash.
    a_backslash = [
        [(8, 78), (35, 10), (43, 10), (16, 78)],
        [(35, 10), (43, 10), (71, 78), (63, 78)],
        [(22, 51), (56, 51), (59, 58), (19, 58)],
        [(77, 10), (85, 10), (115, 78), (107, 78)],
    ]
    save_glyph("anthropic_a_slash", (128, 88), a_backslash, (255, 224, 164, 255))
    # Native irregular radial motif inspired by the requested Claude visual language.
    # This is a decorative interpretation, not an official logo reproduction.
    rays = []
    lengths = [100, 91, 102, 94, 104, 93, 101, 95, 103, 90, 99, 96]
    jitters = [-3, 2, -2, 2, -3, 1, -2, 3, -1, 2, -2, 1]
    for k, (length, jitter) in enumerate(zip(lengths, jitters)):
        angle = math.radians(k * 30 + jitter)
        u = (math.cos(angle), math.sin(angle))
        v = (-u[1], u[0])
        half = 5 + (k % 3)
        points = []
        for radius, across in [(5, -half), (length, -half * .72), (length + 2, half * .62), (5, half)]:
            points.append((128 + u[0] * radius + v[0] * across, 128 + u[1] * radius + v[1] * across))
        rays.append(points)
    rays.append([(128 + 12 * math.cos(k * math.tau / 24), 128 + 12 * math.sin(k * math.tau / 24)) for k in range(24)])
    save_glyph("claude_starburst", (256, 256), rays, (217, 119, 87, 255))
    records = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob("*")) if p.suffix in {".svg", ".png"}}
    (OUT / "provenance.json").write_text(json.dumps({
        "method": "native vector geometry, rasterized at 4x with Pillow and downsampled",
        "script": "scripts/build_buff_motifs.py",
        "meaning": {"claude_starburst": "Claude-inspired irregular orange radial decorative motif", "anthropic_a_slash": "literal A followed by a backslash, user-requested geometric light sigil"},
        "official_logo_claim": False,
        "sha256": records,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records, ensure_ascii=False))


if __name__ == "__main__":
    main()
