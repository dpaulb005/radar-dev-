#!/usr/bin/env python3
"""render_png.py — rasterise the generated SVGs to PNG.

GitHub will not render an <img> pointing at a repo SVG inside a markdown file,
so ASSEMBLY.md needs PNGs. There is no rsvg/inkscape/cairosvg here; Chromium is
already a dependency of ../3d/render.py, so use that.

    python3 layout.py && python3 render_png.py
"""
import pathlib, sys

OUT = pathlib.Path(__file__).resolve().parent
SCALE = 2                      # retina-ish, keeps the 6 pt hole labels legible


def find_chrome():
    for pat in ("chromium-*/chrome-linux/chrome", "chromium/chrome-linux/chrome"):
        for c in sorted(pathlib.Path("/opt/pw-browsers").glob(pat), reverse=True):
            if c.is_file():
                return str(c)
    return None


def main():
    targets = [(OUT / "breadboard.svg", OUT / "breadboard.png")]
    for svg in sorted((OUT / "steps").glob("step-*.svg")):
        targets.append((svg, svg.with_suffix(".png")))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed: pip install playwright (the browser is already at /opt/pw-browsers)")
    chrome = find_chrome()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome) if chrome else pw.chromium.launch()
        for src, dst in targets:
            head = src.read_text()[:400]
            w = float(head.split('width="')[1].split('"')[0])
            h = float(head.split('height="')[1].split('"')[0])
            pg = b.new_page(viewport={"width": int(w), "height": int(h)},
                            device_scale_factor=SCALE)
            pg.goto(src.as_uri(), wait_until="load")
            pg.screenshot(path=str(dst), omit_background=False)
            pg.close()
            print(f"  {dst.relative_to(OUT)}  {int(w*SCALE)}x{int(h*SCALE)}")
        b.close()
    print(f"rendered {len(targets)} PNG")


if __name__ == "__main__":
    main()
