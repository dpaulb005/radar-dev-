#!/usr/bin/env python3
"""render_png.py — rasterise the generated SVGs to PNG.

GitHub will not render an <img> pointing at a repo SVG from inside a markdown
file, so README.md and ASSEMBLY.md need PNGs. Headless Chrome does the work;
it is already a dependency of ../../3d/render.py, and unlike the previous
playwright version this runs against a plain Chrome or Edge install.

    python layout.py && python render_png.py
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent
BOARD = TOOLS.parent
SCALE = 2                      # retina-ish, keeps the 6 pt hole labels legible

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome():
    for name in ("google-chrome", "chromium", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    for c in CHROME_CANDIDATES:
        if pathlib.Path(c).exists():
            return c
    for pat in ("chromium-*/chrome-linux/chrome", "chromium/chrome-linux/chrome"):
        for c in sorted(pathlib.Path("/opt/pw-browsers").glob(pat), reverse=True):
            if c.is_file():
                return str(c)
    return None


def size_of(svg):
    head = svg.read_text(encoding="utf-8")[:400]
    w = float(re.search(r'width="([\d.]+)"', head).group(1))
    h = float(re.search(r'height="([\d.]+)"', head).group(1))
    return int(round(w)), int(round(h))


def main():
    chrome = find_chrome()
    if not chrome:
        sys.exit("no Chrome or Edge found; set one of CHROME_CANDIDATES")
    targets = [(BOARD / "layout" / "breadboard.svg", BOARD / "layout" / "breadboard.png")]
    for svg in sorted((BOARD / "assembly" / "steps").glob("step-*.svg")):
        targets.append((svg, svg.with_suffix(".png")))
    tmp = pathlib.Path(tempfile.mkdtemp())
    for src, dst in targets:
        w, h = size_of(src)
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--force-device-scale-factor={SCALE}", f"--window-size={w},{h}",
             f"--user-data-dir={tmp}", f"--screenshot={dst}", src.as_uri()],
            capture_output=True, timeout=300)
        if not dst.exists():
            sys.exit(f"failed to render {src.name}")
        print(f"  {dst.relative_to(BOARD)}  {w*SCALE}x{h*SCALE}")
    print(f"rendered {len(targets)} PNG")


if __name__ == "__main__":
    main()
