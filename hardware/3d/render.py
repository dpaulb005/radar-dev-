#!/usr/bin/env python3
"""Regenerate the screenshots in this directory from the models themselves.

    python render.py            # all of them
    python render.py drone      # just one model's set

Each view is a URL query the page understands (?view=… &stage=… &labels=…),
so a screenshot is reproducible rather than a hand-framed capture.
"""
import pathlib
import shutil
import sys
import tempfile

import _headless as H

HERE = pathlib.Path(__file__).resolve().parent
SHOTS = {
    "radar-bench": [
        ("radar-bench-bench.png", "view=bench&stage=1"),
        ("radar-bench-breadboard.png", "view=bb&stage=1"),
        ("radar-bench-stage2.png", "view=bench&stage=2"),
        ("radar-bench-room.png", "view=room&stage=2"),
        ("radar-bench-plan.png", "view=top&stage=1&labels=0"),
        ("radar-bench-desk.png", "view=desk&stage=1&labels=0"),
    ],
    "drone": [
        ("drone-overview.png", "view=over"),
        ("drone-top.png", "view=top"),
        ("drone-exploded.png", "view=over&explode=1"),
        ("drone-receiver.png", "view=rx"),
        ("drone-underside.png", "view=under"),
    ],
}


def main():
    want = [a for a in sys.argv[1:] if a in SHOTS] or list(SHOTS)
    browser = H.find_browser()
    if not browser:
        print("no Chromium found"); return 1
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        for model in want:
            page, local = H.probe_copy(HERE / (model + ".html"), tmp, hook=False)
            if not local:
                print("  warning: three.js not cached; the CDN must be reachable from Chromium")
            for png, q in SHOTS[model]:
                shutil.rmtree(tmp / "p", ignore_errors=True)
                ok = H.screenshot(browser, page.as_uri() + "?" + q, str(HERE / png), tmp)
                print("  %s %s" % ("wrote" if ok else "FAILED", png))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
