#!/usr/bin/env python3
"""Check the 3-D drone model against the documents it claims to draw.

`drone.html` hard-codes the ESP-FLY's dimensions and masses, the XIAO pin map
esp-fc uses, the motor order, and how the 915 MHz receiver is wired. Those
facts also live in docs/ and hardware/BOM.md, and either side can change on its
own. This script reads both and fails loudly on any disagreement.

    python verify_drone.py            # data checks only
    python verify_drone.py --render   # also load the page in headless Chrome,
                                      # fail on any JavaScript error or on the
                                      # page's own geometry self-test

Checked:
  pin map      every XIAO pad's GPIO and job against docs/drone-link-espfc.md § 2b
  receiver     TX -> GPIO9, RX -> GPIO8, power from 3V3, against docs/drone-link.md
  motors       Betaflight order and the CW/CCW pattern against § 2b
  the kit      615 motors, 30 mm props, 80 mm antenna, 0.7 g receiver against
               docs/drone-hardware.md; the drone rows of hardware/BOM.md § E
  airframe     the X-frame's parts and its 24 / 37 / 46 / 29 / 31 mm against
               the airframe section of docs/drone-hardware.md
  the bench    radar-bench.html's drone row says the same receiver and tail
  masses       the roll-up in the page lands on Seeed's 18 g / 25 g
  render       (--render) the page loads clean and reports GEOM OK
"""
import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HTML = HERE / "drone.html"
BENCH = HERE / "radar-bench.html"
ESPFC = ROOT / "docs/drone-link-espfc.md"
LINK = ROOT / "docs/drone-link.md"
HW = ROOT / "docs/drone-hardware.md"
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


SRC = read(HTML)


# ------------------------------------------------------------- the page ---
def js_const(name):
    m = re.search(r"(?:\bconst |, )%s=([-0-9.e()+*/A-Z_\[\]]+)" % re.escape(name), SRC)
    if not m:
        raise SystemExit("drone.html: no constant " + name)
    expr = m.group(1)
    # BAT is the one array constant the levels are built from
    for idx in set(re.findall(r"BAT\[(\d)\]", expr)):
        expr = expr.replace("BAT[%s]" % idx, repr(js_array_const("BAT")[int(idx)]))
    # the rest of the derived constants are simple arithmetic over earlier ones
    for other in re.findall(r"[A-Z_][A-Z_0-9]+", expr):
        expr = expr.replace(other, repr(js_const(other)))
    return float(eval(expr))


def js_array_const(name):
    m = re.search(r"\bconst %s=\[([-0-9.,e ]+)\]" % re.escape(name), SRC)
    if not m:
        raise SystemExit("drone.html: no array constant " + name)
    return [float(v) for v in m.group(1).split(",")]


def js_table(name):
    """A const NAME=[[...],[...]] table of string/number literals, as Python."""
    m = re.search(r"\bconst %s=(\[.*?\]);" % re.escape(name), SRC, re.S)
    if not m:
        raise SystemExit("drone.html: no table " + name)
    txt = m.group(1)
    txt = re.sub(r"//[^\n]*", "", txt)
    return eval(txt.replace("true", "True").replace("false", "False"))


def js_mass():
    m = re.search(r"const MASS=\{([^}]*)\}", SRC)
    return {k: float(v) for k, v in re.findall(r"(\w+):([0-9.]+)", m.group(1))}


def panel_rows():
    """[id, name, qty, mass-or-'-', note] rows of the page's panel."""
    body = SRC.split("const ROWS=[", 1)[1].split("\n];", 1)[0]
    rows = []
    for m in re.finditer(r"\['([A-Z]\d+[a-z]?)','([^']*)','([^']*)',([^,]*),'([^']*)'\]", body):
        rows.append(list(m.groups()))
    return rows


# ------------------------------------------------------------- the docs ---
def espfc_pin_table():
    """{silk: (gpio, function)} from docs/drone-link-espfc.md § 2b."""
    text = read(ESPFC).split("## 2b.", 1)[1]
    out = {}
    for line in text.splitlines():
        cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and re.fullmatch(r"D\d+|3V3|5V", cells[0]):
            out[cells[0]] = (cells[1], cells[2])
    return out


def check_pin_map():
    doc = espfc_pin_table()
    model = {}
    for silk, gpio, fn in js_table("XIAO_LEFT") + js_table("XIAO_RIGHT"):
        model[silk] = (gpio, fn)
    check(len(doc) >= 12, "drone-link-espfc.md § 2b: pin table not found or short")
    for silk, (gpio, fn) in doc.items():
        if gpio.isdigit():
            check(silk in model and model[silk][0] == "GPIO" + gpio,
                  "XIAO %s: model says %s, § 2b says GPIO%s" % (silk, model.get(silk, ("?",))[0], gpio))
        # the job: the first word of the doc's description must appear in the model's
        key = re.split(r"[ —(]", fn)[0].lower()
        if silk in model:
            check(key in model[silk][1].lower(),
                  "XIAO %s: model job '%s' vs § 2b '%s'" % (silk, model[silk][1], fn))
    # the receiver pins, both ways round
    check(model.get("D10", ("",))[0] == "GPIO9" and "receiver TX" in model["D10"][1],
          "D10 must be GPIO9, UART2 RX from the receiver's TX")
    check(model.get("D9", ("",))[0] == "GPIO8" and "receiver RX" in model["D9"][1],
          "D9 must be GPIO8, UART2 TX to the receiver's RX")


def check_receiver_wiring():
    link = read(LINK)
    check("GPIO 9 = serial 2 RX" in link and "GPIO 8 = serial 2 TX" in link,
          "drone-link.md no longer states GPIO 9 = serial 2 RX / GPIO 8 = serial 2 TX")
    check(re.search(r"power to \*\*3V3\*\*", link) is not None, "drone-link.md no longer powers the receiver from 3V3")
    pads = dict((n, d) for n, s, d in js_table("RXPADS"))
    check("GPIO9" in pads.get("PRX", ""), "FC RX pad is not described as GPIO9")
    check("GPIO8" in pads.get("PTX", ""), "FC TX pad is not described as GPIO8")
    check("3.3 V" in pads.get("P3V3", "") and "5 V" in pads.get("P3V3", ""),
          "the receiver power pad must say 3.3 V and why not 5 V")
    # the four wires, receiver pad -> FC pad, as drawn
    wires = re.findall(r"\[\['VCC','P3V3','\w+'\],\['GND','PGND','\w+'\],\['TX','PRX','\w+'\],\['RX','PTX','\w+'\]\]", SRC)
    check(len(wires) == 1, "receiver wiring table is not VCC->P3V3, GND->PGND, TX->PRX, RX->PTX")


def check_motors():
    text = read(ESPFC).split("## 2b.", 1)[1]
    m = re.search(r"Motor order is Betaflight's \((.*?)\)", text, re.S)
    check(m is not None, "§ 2b no longer states the motor order")
    order = dict(re.findall(r"(\d) ([a-z]+-[a-z]+)", m.group(1))) if m else {}
    model = {mid[1]: pos for mid, pos, *_ in js_table("MOTORS")}
    for k, pos in order.items():
        check(model.get(k) == pos, "motor %s: model '%s', § 2b '%s'" % (k, model.get(k), pos))
    cw = {pos: d for mid, pos, sx, sz, d, *_ in js_table("MOTORS")}
    check(cw.get("rear-right") == "CW" and cw.get("front-left") == "CW"
          and cw.get("front-right") == "CCW" and cw.get("rear-left") == "CCW",
          "props-in pattern: rear-right and front-left must be CW, the other two CCW")
    # the sign table puts each motor in its named corner: +x right, +z rear
    for mid, pos, sx, sz, *_ in js_table("MOTORS"):
        fb, lr = pos.split("-")
        check((sz > 0) == (fb == "rear") and (sx > 0) == (lr == "right"),
              "motor %s is placed at (%+d,%+d) but named %s" % (mid, sx, sz, pos))
    # the GPIO column of the motor table matches the pin map
    gp = {silk: gpio for silk, gpio, fn in js_table("XIAO_LEFT") + js_table("XIAO_RIGHT")}
    for mid, pos, sx, sz, d, gpio, silk in js_table("MOTORS"):
        check(gp.get(silk) == gpio, "motor %s: pad %s is %s in the pin map, %s in the motor table" % (mid, silk, gp.get(silk), gpio))


def check_kit():
    hw = read(HW)
    check("615 coreless" in hw, "drone-hardware.md no longer names 615 coreless motors")
    check(abs(js_const("MOTOR_D") - 0.006) < 1e-6 and abs(js_const("MOTOR_L") - 0.015) < 1e-6,
          "model motor is not 6 x 15 mm")
    check("30 mm props" in hw and abs(js_const("PROP_D") - 0.030) < 1e-6, "prop diameter vs drone-hardware.md")
    m = re.search(r"~(\d+) mm wire", hw)
    check(m is not None and abs(js_const("ANT_LEN") - int(m.group(1)) / 1000) < 1e-6,
          "antenna length: model %s, drone-hardware.md says %s" % (js_const("ANT_LEN"), m.group(1) if m else "?"))
    mass = js_mass()
    m = re.search(r"BetaFPV ELRS Nano 915 \(([0-9.]+) g\)", hw)
    check(m is not None and abs(mass["rx"] - float(m.group(1))) < 1e-6,
          "receiver mass: model %s g, drone-hardware.md %s" % (mass["rx"], m.group(1) if m else "?"))
    check(abs(js_const("MOTOR_PITCH") - (js_const("OVERALL") - js_const("PROP_D"))) < 1e-9
          and js_const("MOTOR_PITCH") > js_const("PROP_D"),
          "motor pitch must be overall minus one prop, and larger than a prop")
    # the panel's frame row carries the kit envelope the constants encode
    rows = {r[0]: r for r in panel_rows()}
    note = rows["K6"][4]
    for v in (js_const("BODY"), js_const("H_NOPROP"), js_const("OVERALL"), js_const("H_PROP")):
        check(("%d" % round(v * 1000)) in note, "K6 note lacks %d mm" % round(v * 1000))


def check_airframe():
    """The shape itself, against what drone-hardware.md now says it is."""
    hw = read(HW)
    check("X-frame" in hw, "drone-hardware.md no longer calls the airframe an X-frame")
    check("two-prong arms" in hw, "drone-hardware.md no longer describes the two-prong arms")
    # every named piece of the airframe exists in the model
    for want in ("frame — centre plate", "frame — arm prong", "bumper rail",
                 "frame — motor pod", "landing leg", "canopy — ", "top cover"):
        check(want in SRC, "the model has no part named '%s'" % want)
    # the numbers the doc quotes are the numbers the model is built from
    for mm, name in ((24, "centre plate"), (37, "pod pitch"), (46, "across the pods")):
        check(("%d mm" % mm) in hw, "drone-hardware.md no longer quotes %d mm (%s)" % (mm, name))
    check(abs(js_const("HUB") - 0.024) < 1e-9, "centre plate is not 24 mm")
    check(abs(js_const("CAN_W") - 0.024) < 1e-9, "canopy is not 24 mm square")
    check(js_const("POD_ID") > js_const("MOTOR_D") and js_const("POD_ID") < js_const("MOTOR_D") + 0.0005,
          "the pod bore must be a press fit on the 6 mm can, not loose")
    check(js_const("FC_W") <= js_const("CAN_W") - 0.0015, "the FC board does not fit inside the canopy")
    check(js_const("XIAO_L") <= js_const("CAN_W") - 0.0015, "the XIAO does not fit inside the canopy")
    # the stack lands on the kit's two heights
    for expr, want, what in (("Y_MOTOR1", js_const("H_NOPROP"), "top of a motor"),
                             ("Y_PROP", js_const("H_PROP") - 0.0005, "blade plane")):
        check(abs(js_const(expr) - want) < 0.0006, "%s is at %.1f mm, the kit says %.1f"
              % (what, js_const(expr) * 1e3, want * 1e3))


def check_bom_rows():
    bom = read(BOM)
    sec = bom.split("## E.", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in sec.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"\d+[a-z]?", cells[0]):
            rows[cells[0]] = cells
    check("21" in rows and "21b" in rows, "BOM.md § E must carry rows 21 (receiver) and 21b (antenna)")
    panel = {r[0]: r for r in panel_rows()}
    check("E21" in panel and "E21b" in panel, "the drone panel must list E21 and E21b")
    if "21" in rows and "E21" in panel:
        check("915" in rows["21"][1] and "915" in panel["E21"][1], "row 21 / E21 are not the 915 MHz receiver")
        check("GPIO9" in panel["E21"][4] and "GPIO8" in panel["E21"][4] and "3V3" in panel["E21"][4],
              "E21 note must state 3V3, GPIO9, GPIO8")
    if "21b" in rows and "E21b" in panel:
        check("antenna" in rows["21b"][1] and "80 mm" in panel["E21b"][1], "row 21b / E21b are not the 80 mm antenna")
    # every kit row in the panel is a real part of the model (registered)
    for rid in panel:
        check(("reg('%s'" % rid) in SRC, "panel row %s is not registered on any object" % rid)


def check_bench_agrees():
    bench = read(BENCH)
    m = re.search(r"reg\('E21',drone,'([^']*)'", bench)
    check(m is not None, "radar-bench.html has no E21 drone registration")
    if m:
        mass = js_mass()
        check(("%.1f g" % mass["rx"]) in m.group(1), "bench E21 text does not carry the receiver mass %.1f g" % mass["rx"])
        check(("%d mm" % round(js_const("ANT_LEN") * 1000)) in m.group(1), "bench E21 text does not carry the %d mm tail" % round(js_const("ANT_LEN") * 1000))
    check("drone.html" in bench, "radar-bench.html does not link to drone.html")


def check_masses():
    mass = js_mass()
    no_lipo = mass["frame"] + mass["fc"] + mass["xiao"] + 4 * mass["motor"] + 4 * mass["prop"] + mass["wiring"]
    kit = no_lipo + mass["lipo"]
    check(abs(no_lipo - js_const("KIT_MASS_NO_LIPO")) <= 0.1 * js_const("KIT_MASS_NO_LIPO"),
          "roll-up without LiPo %.1f g vs Seeed's %g g" % (no_lipo, js_const("KIT_MASS_NO_LIPO")))
    check(abs(kit - js_const("KIT_MASS")) <= 0.1 * js_const("KIT_MASS"),
          "roll-up with LiPo %.1f g vs Seeed's %g g" % (kit, js_const("KIT_MASS")))
    check(mass["rx"] + mass["ant"] < 1.5, "the 915 MHz link adds %.1f g; it should be about a gram" % (mass["rx"] + mass["ant"]))


def check_render():
    sys.path.insert(0, str(HERE))
    import _headless as H
    browser = H.find_browser()
    if not check(bool(browser), "render: no Chromium found"):
        return
    with tempfile.TemporaryDirectory() as td:
        page, local = H.probe_copy(HTML, td)
        if not local:
            print("  warning: three.js not cached; the CDN must be reachable from Chromium")
        title, _ = H.dump_title(browser, page.as_uri(), td)
    check(title == "GEOM OK", "render: page reports '%s'" % title)
    print("  render: %s" % title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true", help="also load the page in headless Chrome")
    args = ap.parse_args()
    print("verifying hardware/3d/drone.html")
    for name, fn in (("XIAO pin map", check_pin_map), ("receiver wiring", check_receiver_wiring),
                     ("motors", check_motors), ("the kit", check_kit), ("airframe", check_airframe),
                     ("BOM rows", check_bom_rows),
                     ("bench agrees", check_bench_agrees), ("masses", check_masses)):
        before = len(FAILURES)
        fn()
        print("  %s: %s" % (name, "ok" if len(FAILURES) == before else "%d FAILED" % (len(FAILURES) - before)))
    if args.render:
        check_render()
    print()
    print("%d checks" % CHECKS[0])
    if FAILURES:
        print("%d FAILED:" % len(FAILURES))
        for f in FAILURES:
            print("  - " + f)
        return 1
    print("DRONE MODEL VERIFIED — matches drone-link.md, drone-link-espfc.md, drone-hardware.md and BOM.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
