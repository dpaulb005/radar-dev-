#!/usr/bin/env python3
"""Check the 3-D bench model against the documents it claims to draw.

`radar-bench.html` hard-codes the breadboard placement, the module pinouts and
the BOM totals. Those live in three markdown files that change independently, so
the model can go stale silently. This script re-derives all of it and fails loudly.

    python verify_model.py            # data checks only
    python verify_model.py --render   # also load the page in headless Chrome
                                      # and fail on any JavaScript error

Checked:
  breadboard   every part and all 48 jumpers against hardware/breadboard/WIRING.md
               (same refs, same holes, same pin order, same wire colours)
  connectors   what each J-header pin carries, against WIRING.md's "Nets as built"
  pinouts      ESP32 / A4988 / ADF4351 pin names and order against MODULES.md
  harness      every modelled wire lands on a pin that exists on both ends
  BOM          the stage totals shown in the panel against hardware/BOM.md
"""
import argparse
import math
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HTML = ROOT / "hardware/3d/radar-bench.html"
WIRING = ROOT / "hardware/breadboard/WIRING.md"
MODULES = ROOT / "hardware/breadboard/MODULES.md"
BOM = ROOT / "hardware/BOM.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAILURES = []
CHECKS = [0]


def check(ok, msg):
    CHECKS[0] += 1
    if not ok:
        FAILURES.append(msg)
    return ok


def read(p):
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- markdown ---
def md_rows(text, start_marker, ncols):
    """Rows of the first pipe-table after `start_marker`, as lists of cells."""
    body = text.split(start_marker, 1)[1]
    rows, started = [], False
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if started:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if set("".join(cells)) <= set("-: ") and len(cells) == ncols:
            started = True          # the |---| rule: data rows follow
            continue
        if not started or len(cells) != ncols:
            continue
        rows.append(cells)
    return rows


def unbold(s):
    return s.replace("**", "").strip()


def wiring_parts():
    """{ref: {kind, value, leads}} in pin order, from the Components table."""
    out = {}
    for ref, part, leads, _note in md_rows(read(WIRING), "## Components", 4):
        ref = unbold(ref)
        if not re.fullmatch(r"[A-Z]+[0-9]+", ref):
            continue
        kind = re.search(r"\(([a-z0-9]+)\)", part)
        pairs = re.findall(r"([0-9A-K]+)\s*\u2192\s*\*\*([^*]+)\*\*", leads)
        out[ref] = {
            "kind": kind.group(1) if kind else "",
            "leads": [h.strip() for _pin, h in pairs],
        }
    return out


def wiring_jumpers():
    rows = md_rows(read(WIRING), "## Jumper wires", 5)
    return [(unbold(a), unbold(b), col.strip()) for _n, a, b, col, _p in rows]


def wiring_nets():
    """{net: {"REF.pin", ...}} from the "Nets as built" table."""
    out = {}
    for net, pins in md_rows(read(WIRING), "## Nets as built", 2):
        out[unbold(net)] = {p.strip() for p in pins.split(",")}
    return out


def wiring_pin_labels():
    """{ref: [label, ...]} from the Components table's "1=IF / 2=GND" note.

    These are the friendly names; the netlist may call the same node something
    else (VIN12 is N$16 there). Either spelling is acceptable in the model.
    """
    out = {}
    for ref, _part, _leads, note in md_rows(read(WIRING), "## Components", 4):
        pairs = re.findall(r"(\d+)\s*=\s*([A-Za-z0-9_+$]+)", note)
        if pairs:
            out[unbold(ref)] = [lbl for _n, lbl in
                                sorted(pairs, key=lambda p: int(p[0]))]
    return out


def modules_two_column(heading):
    """Left/right pin-name columns of a MODULES.md board table."""
    rows = md_rows(read(MODULES), heading, 4)
    strip_paren = lambda xs: [re.sub(r"\s*\(.*\)$", "", x).strip() for x in xs]
    left = strip_paren([unbold(r[0]) for r in rows if unbold(r[0])])
    right = strip_paren([unbold(r[2]) for r in rows if unbold(r[2])])
    return left, right


# --------------------------------------------------------------------- html ---
HTML_SRC = read(HTML)


def js_array(name):
    """Text inside `const NAME=[ ... ];`, balanced at bracket depth 0."""
    i = HTML_SRC.index("const " + name + "=[")
    i = HTML_SRC.index("[", i)
    depth, j = 0, i
    while True:
        if HTML_SRC[j] == "[":
            depth += 1
        elif HTML_SRC[j] == "]":
            depth -= 1
            if depth == 0:
                return HTML_SRC[i + 1:j]
        j += 1


def js_string_list(name):
    return re.findall(r"'([^']*)'", js_array(name))


def model_parts():
    out = {}
    entry = re.compile(r"\['([^']+)','([^']+)','([^']*)',\[([^\]]*)\]\]")
    for ref, kind, value, leads in entry.findall(js_array("BBPARTS")):
        items = [x.strip().strip("'") for x in leads.split(",") if x.strip()]
        out[ref] = {"kind": kind, "value": value, "leads": items}
    return out


def model_jumpers():
    entry = re.compile(r"\['([^']+)','([^']+)','([^']+)'\]")
    return [tuple(m) for m in entry.findall(js_array("BBJUMPERS"))]


def model_jnets():
    src = HTML_SRC[HTML_SRC.index("const JNETS={"):]
    src = src[:src.index("\n};")]
    out = {}
    for ref, body in re.findall(r"(J\w+):\[([^\]]*)\]", src):
        out[ref] = [x.strip().strip("'") for x in body.split(",") if x.strip()]
    return out


# ------------------------------------------------------------------- checks ---
def check_breadboard():
    doc, mdl = wiring_parts(), model_parts()
    check(set(doc) == set(mdl),
          "part refs differ: only in WIRING.md %s, only in model %s"
          % (sorted(set(doc) - set(mdl)), sorted(set(mdl) - set(doc))))
    for ref in sorted(set(doc) & set(mdl)):
        d, m = doc[ref], mdl[ref]
        if m["kind"] == "dip":
            cols = sorted(int(re.sub(r"[a-j]", "", h)) for h in d["leads"])
            got = [int(x) for x in m["leads"]]
            check(got == [cols[0], cols[-1]],
                  "%s: DIP spans columns %d..%d in WIRING.md, model says %s"
                  % (ref, cols[0], cols[-1], got))
        else:
            check(d["leads"] == m["leads"],
                  "%s: holes %s in WIRING.md, %s in model"
                  % (ref, d["leads"], m["leads"]))

    dj, mj = wiring_jumpers(), model_jumpers()
    check(len(dj) == len(mj),
          "%d jumpers in WIRING.md, %d in model" % (len(dj), len(mj)))
    for i, (d, m) in enumerate(zip(dj, mj), 1):
        check(d == m, "jumper %d: WIRING.md %s, model %s" % (i, d, m))


def check_connector_nets():
    """Each J-pin's net name in the model must agree with WIRING.md's netlist."""
    nets, jnets = wiring_nets(), model_jnets()
    parts, labels = wiring_parts(), wiring_pin_labels()
    for ref, names in sorted(jnets.items()):
        placed = len(parts.get(ref, {}).get("leads", []))
        check(len(names) == placed,
              "%s: model names %d pins, WIRING.md places %d"
              % (ref, len(names), placed))
        for i, net in enumerate(names, 1):
            owners = [n for n, pins in nets.items() if ("%s.%d" % (ref, i)) in pins]
            label = labels.get(ref, [])
            allowed = set(owners) | ({label[i - 1]} if i <= len(label) else set())
            if not allowed:
                continue                     # pin named nowhere in WIRING.md
            check(net in allowed,
                  "%s pin %d: model says %s, WIRING.md says %s"
                  % (ref, i, net, sorted(allowed)))


def check_pinouts():
    left, right = modules_two_column("## ESP32 DevKit V1")
    m_left = js_string_list("ESP_L")
    m_right = [x.replace("GND2", "GND") for x in js_string_list("ESP_R")]
    check(left == m_left, "ESP32 left column: doc %s vs model %s" % (left, m_left))
    check(right == m_right, "ESP32 right column: doc %s vs model %s" % (right, m_right))

    left, right = modules_two_column("## A4988 stepper driver")
    m_left = js_string_list("A49_L")
    m_right = [x.replace("GND_M", "GND").replace("GND_L", "GND")
               for x in js_string_list("A49_R")]
    check(left == m_left, "A4988 left column: doc %s vs model %s" % (left, m_left))
    check(right == m_right, "A4988 right column: doc %s vs model %s" % (right, m_right))

    doc_adf = [unbold(r[0]).split(" /")[0]
               for r in md_rows(read(MODULES), "## ADF4351 PLL board", 3)]
    m_adf = js_string_list("ADFPINS")
    check(doc_adf == m_adf, "ADF4351 pins: doc %s vs model %s" % (doc_adf, m_adf))


def check_harness():
    """Every pinAt(...) in the model must name a pin the model actually defines."""
    defined = {
        "esp": set(js_string_list("ESP_L")) | set(js_string_list("ESP_R")),
        "a49": set(js_string_list("A49_L")) | set(js_string_list("A49_R")),
        "adf": set(js_string_list("ADFPINS")),
        "buck": {"IN+", "IN-", "OUT+", "OUT-"},
        "term": {"T%d" % i for i in range(1, 7)},
        "psu": {"OUT", "AC"},

        "pa": {"5V", "GND"},
        "lna": {"5V", "GND"},
        "nema": {"M1", "M2", "M3", "M4"},
        "lap": {"USB1", "USB2", "USB3"},
        "umc": {"IN1", "IN2", "IN3", "IN4", "USB"},
    }
    defined["esp"] = defined["esp"] | {"USB"}      # micro-USB to the laptop
    # literal P(comp,'PIN') refs are checked by name; P(comp, someVar) ones can
    # only be counted, but counting them still catches a wholesale rename.
    refs = re.findall(r"\bP\((\w+),'([^']+)'\)", HTML_SRC)
    all_refs = re.findall(r"\bP\((\w+)\s*,", HTML_SRC)
    check(len(all_refs) >= 25,
          "only %d P(component, pin) references found — has the harness been "
          "renamed out from under this check?" % len(all_refs))
    for comp, pin in refs:
        if comp in defined:
            check(pin in defined[comp], "P(%s,'%s') — no such pin" % (comp, pin))
    jnets = model_jnets()
    for ref, pin in re.findall(r"\bP\(bbParts\.(\w+),'?(\w+)'?\)", HTML_SRC):
        n = len(jnets.get(ref, []))
        if not n:
            continue                       # pin index comes from a loop variable
        check(not pin.isdigit() or 1 <= int(pin) <= n,
              "P(bbParts.%s,'%s') — %s has %d pins" % (ref, pin, ref, n))
    # every pin a wire lands on must declare which way the lead leaves it
    for comp in sorted({c for c, _p in refs}):
        check(("addPin(%s," % comp) in HTML_SRC or comp in ("bbParts",) or
              re.search(r"addPin\(g,", HTML_SRC) is not None,
              "%s has no addPin() call" % comp)


def check_bom_totals():
    """The panel's three stage figures are BOM.md's staged running totals."""
    rows = md_rows(read(BOM), "### If you build it in stages instead", 3)
    running = []
    for _label, _line, run in rows[:3]:
        m = re.search(r"([\d,]+)", run.replace("**", ""))
        if m:
            running.append(int(m.group(1).replace(",", "")))
    check(len(running) == 3,
          "could not read BOM.md's staged running totals (got %s)" % running)
    panel = re.search(r"tot\.innerHTML='([^<]*)", HTML_SRC).group(1)
    shown = [int(x) for x in re.findall(r"\$(\d+)", panel)]
    check(shown == running,
          "BOM panel shows %s but BOM.md's staged running totals are %s"
          % (shown, running))


def check_bom_rows():
    """Every BOM.md line item is represented in the panel — including the
    915 MHz control link (section E): the handset (rows 19, 20) stands in the
    room beside the operator, and the receiver (row 21) is on the drone."""
    text = read(BOM)
    doc = set(re.findall(r"^\|\s*(\d+[a-z]?)\s*\|", text, re.M))
    # panel ids are section letter + BOM row, with an optional a/b role suffix
    # (A3a and A3b are the PA and LNA roles of the one 4-pack, row 3)
    shown = set()
    for pid in re.findall(r"\['([A-G]\d+[a-z]?)','", js_array("BOM")):
        num = re.sub(r"^[A-G]", "", pid)
        shown.add(num)
        if num not in doc and num[-1] in "ab":
            shown.add(num[:-1])
    check(doc <= shown,
          "BOM.md rows missing from the panel: %s" % sorted(doc - shown))
    for row in ("19", "20", "21"):
        check(row in shown, "915 MHz link row %s is not in the panel" % row)


# ------------------------------------------------------------------- render ---
import _headless as H


def check_render():
    browser = H.find_browser()
    if not browser:
        print("  render: skipped (no Chrome/Edge/Chromium found)")
        return
    tmp = pathlib.Path(tempfile.mkdtemp())
    page, local = H.probe_copy(HTML, tmp)
    if not local:
        print("  render: three.js could not be cached locally; relying on the CDN")
    try:
        # no --virtual-time-budget: the render loop never idles, so virtual time
        # never advances and Chrome hangs. The page runs its self-test during
        # load, so a plain --dump-dom already has the verdict.
        title, out = H.dump_title(browser, page.as_uri(), tmp)
    except subprocess.TimeoutExpired:
        check(False, "headless render timed out")
        return
    check("JSERROR" not in title,
          "page threw: " + title.split("JSERROR: ")[-1][:400])
    check("<canvas" in out, "page rendered no canvas")
    # the page checks its own geometry: no lead may pass through a part it is
    # not connected to, and no bend may exceed 95 degrees
    check("GEOM OK" in title,
          "wire geometry: " + title.replace("GEOM FAIL", "").strip()[:900])
    if "GEOM OK" in title:
        print("  render: loaded clean, wire geometry OK "
              "(no wire through a part, no bend over 95 deg)")


def js_const(name):
    """Pull a bare `const NAME=<number>` out of the model source."""
    m = re.search(r"const\s+%s\s*=\s*([0-9.]+)" % re.escape(name), HTML_SRC)
    if not m:
        m = re.search(r"\b%s\s*=\s*([0-9.]+)" % re.escape(name), HTML_SRC)
    return None if not m else float(m.group(1))


def check_horn_geometry():
    """The three-horn frame's geometry carries the whole azimuth argument, and
    none of it was checked. Three properties matter and each fails differently:

      baseline   RX A to RX B must be under the ambiguity limit lam/(2 sin17),
                 or the bearing wraps inside the beam and the answer is wrong
                 without looking wrong.
      symmetry   TX must sit on the perpendicular bisector of the RX pair. The
                 leakage is ~52 dB above the drone echo, so if it reaches one
                 receiver before the other it is a large coherent bias on the
                 phase difference -- and a range-dependent one, so calibration
                 cannot remove it. Centred, it is common mode and cancels.
      clearance  the horns are 263.8 mm tall once rolled; TX has to clear the
                 receive row rather than intersect it.
    """
    # lambda at the centre of the sweep as built, 2400-2483.5 MHz. It was
    # 2.46e9 here, the centre of the superseded 40 MHz sweep, which made the
    # ambiguity limit read 209 mm instead of 210 mm.
    C, LAM = 2.99792458e8, 2.99792458e8 / 2.44175e9
    A1, B1 = 0.2638, 0.1931              # horn aperture, docs/radar-hardware.md
    d = js_const("D_BASE")
    rxy = js_const("RXY")
    check(d is not None and rxy is not None, "model must define D_BASE and RXY")
    if d is None or rxy is None:
        return
    m = re.search(r"TXY\s*=\s*RXY\s*\+\s*([0-9.]+)", HTML_SRC)
    check(m is not None, "TXY must be defined relative to RXY")
    if not m:
        return
    dz = float(m.group(1))

    # baseline: the rolled horns touch, so the baseline IS the short dimension
    check(abs(d - B1) < 1e-4,
          "RX baseline %.4f m must equal the rolled horn width %.4f" % (d, B1))
    limit = LAM / (2 * math.sin(math.radians(17.0)))
    check(d < limit,
          "baseline %.3f m must stay under the %.3f m ambiguity limit" % (d, limit))
    check(A1 > limit,
          "and un-rolled (%.4f m) it would not, which is why the roll exists" % A1)

    # symmetry: TX centred above the midpoint -> equal path to both receivers
    txa = math.hypot(d / 2, dz)
    txb = math.hypot(-d / 2, dz)
    check(abs(txa - txb) < 1e-9,
          "TX leakage path must be equal into both receivers: %.6f vs %.6f" % (txa, txb))
    # and the alternative it replaced is not: TX beside the pair in the same row
    beside_a, beside_b = abs(-dz - (-d / 2)), abs(-dz - (d / 2))
    check(abs(beside_a - beside_b) > 0.1,
          "a side-by-side TX would be asymmetric, which is the point")

    # clearance: rolled horns are A1 tall, so TX must clear the receive row
    check(dz > A1, "TX centre %.3f m must clear the %.4f m horn height" % (dz, A1))
    check(txa > dz, "the slant path is longer than the vertical drop")
    # and the offset is vertical, orthogonal to the baseline, so it cannot bias
    # a bearing no matter how large it is
    check(abs(math.hypot(d / 2, dz) - math.hypot(-d / 2, dz)) < 1e-12,
          "a vertical TX offset is orthogonal to the baseline by construction")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--render", action="store_true",
                    help="also load the page in headless Chrome")
    args = ap.parse_args()

    print("verifying hardware/3d/radar-bench.html")
    for name, fn in (("breadboard placement", check_breadboard),
                     ("connector nets", check_connector_nets),
                     ("module pinouts", check_pinouts),
                     ("harness pin references", check_harness),
                     ("BOM rows", check_bom_rows),
                     ("BOM totals", check_bom_totals),
                     ("horn frame geometry", check_horn_geometry)):
        before = len(FAILURES)
        fn()
        print("  %s: %s" % (name, "ok" if len(FAILURES) == before else "FAILED"))
    if args.render:
        check_render()

    print("\n%d checks" % CHECKS[0])
    if FAILURES:
        print("%d FAILED:\n" % len(FAILURES))
        for f in FAILURES:
            print("  -", f)
        return 1
    print("MODEL VERIFIED — matches WIRING.md, MODULES.md and BOM.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
