#!/usr/bin/env python3
"""Build breadboard.html — an interactive, hole-by-hole view of layout.json.

Hover or click any part, wire, net or hole and the page highlights every hole and
strip it touches and lists what else sits on the same net.  Checkboxes keep a
build tally in the browser.  Run `python layout.py` first (it refuses to write
layout.json unless the placement passes the netlist check).
"""
import json, pathlib

HERE = pathlib.Path(__file__).parent
D = json.loads((HERE / "layout.json").read_text())

ALIAS = {"N$2": "AP", "N$4": "AM", "N$5": "AOUT", "N$6": "BP", "N$7": "BM", "N$8": "BOUT", "N$9": "LP",
         "N$10": "OBUF", "N$11": "OISO", "N$14": "VDIV", "N$15": "VBUF", "N$16": "VIN12"}
NET_DESC = {
    "IF": "mixer IF output, terminated by R1/C20", "AP": "U1A non-inverting input (after C1)", "AM": "U1A inverting node, gain set by R3/R4",
    "AOUT": "U1A output", "BP": "U1B non-inverting input (after C2)", "BM": "U1B inverting node, gain set by R7/R8", "BOUT": "U1B output",
    "LP": "15.9 kHz low-pass node into the buffer", "OBUF": "U2B unity-gain buffer output", "OISO": "after the 100 Ω isolation resistor",
    "AUDIO_L": "sound-card left channel (beat signal)", "AUDIO_R": "sound-card right channel (0.3 V sync)", "VREF": "mid-rail reference (VANA/2, buffered)",
    "VDIV": "R9/R10 divider, U2A input", "VBUF": "U2A buffer output before R11", "VANA": "analog supply after D1 and the R15/C13 filter",
    "VPROT": "reverse-protected 12 V (after D1)", "VIN12": "raw 12 V input", "V5": "5 V from the buck module", "V5_ADF": "filtered 5 V for the ADF4351",
    "V5_PA": "filtered 5 V for the PA", "V5_LNA": "filtered 5 V for the LNA", "GND": "ground (both blue rails)", "+3V3": "3.3 V from the ESP32",
    "SCK": "SPI clock from the ESP32", "MOSI": "SPI data from the ESP32", "LE": "ADF4351 latch enable from the ESP32", "SCK_O": "SPI clock after 33 Ω",
    "MOSI_O": "SPI data after 33 Ω", "LE_O": "latch enable after 33 Ω", "LD": "ADF4351 lock detect back to the ESP32", "CE": "ADF4351 chip enable (JP3, 10 k pull-down)",
    "SYNC": "sweep sync pulse from the ESP32", "STEP": "A4988 step", "DIR": "A4988 direction", "EN": "A4988 enable (10 k pull-up)",
}
KIND = {"res": "resistor", "cer": "ceramic capacitor", "film": "film capacitor", "elec": "electrolytic capacitor", "diode": "Schottky diode",
        "bead": "ferrite bead", "dip8": "op-amp, DIP-8", "hdr2": "2-pin header", "hdr5": "5-pin header", "hdr6": "6-pin header", "hdr10": "10-pin header"}
UNITS = {"res": "Ω", "cer": "F", "film": "F", "elec": "F"}

STEPS = [
    ("Rails", "Bridge each rail at columns 31|32 if your board's rails are split. Tie the two GND rails together at column 1."),
    ("Op-amps", "Seat U1 (pin 1 at e5) and U2 (pin 1 at e30), notch toward the low column number. Add their V+ and V− wires and the 100 n caps C3/C7."),
    ("Signal chain", "Left to right on the top bank: J1, R1, C20, C1, R2, then R3/C2/R4/R6 around U1, R7/R8/R12/C9, then U2's R13/C10/R14/J2."),
    ("Bias", "R9, R10, C5 (VDIV), R11 and C6 (VREF) around U2. Then the four violet VREF wires."),
    ("Power", "Bottom bank: J3, D1, C11, J4, R15, C13, J5, C12. Then the VANA feed to the bottom red rail and the V5 feed to the top red rail."),
    ("5 V feeds", "FB1–FB3 with their 10 µ + 100 n pairs and J6–J8, top bank columns 38, 41, 44."),
    ("Digital", "J9, R16–R18 across the channel, J10, R19/JP3, J11, R20–R22, R23/R24, J12, then the blue, yellow, white and grey wires."),
    ("Check", "Ohm-meter: GND to VANA, GND to V5, GND to +3V3 must all read open (> 1 kΩ) before power. Then run hardware/spice test cards against the built board."),
]


DIP8 = {"1": "OUT A", "2": "IN- A", "3": "IN+ A", "4": "V-", "5": "IN+ B", "6": "IN- B", "7": "OUT B", "8": "V+"}

# Real-board pin maps. Each module: outline in mm, pins as rows top->bottom on the left and right edge
# (board seen from above, antenna / SMA at the top, USB at the bottom), and what each used pin connects to.
MODULES = {
  "esp32_30": dict(title="ESP32 DevKit V1 (DOIT, 30-pin)", w=28.5, h=51.5, pitch=2.54, ant="top", usb="bottom", note="Pins 2.54 mm apart, rows 0.9 in apart. This is the usual '$10 ESP-WROOM-32 devkit'. Power it over USB from the laptop (serial link); VIN is optional.",
    left=["EN","VP (36)","VN (39)","D34","D35","D32","D33","D25","D26","D27","D14","D12","D13","GND","VIN"],
    right=["D23","D22","TX0 (1)","RX0 (3)","D21","D19","D18","D5","TX2 (17)","RX2 (16)","D4","D2","D15","GND","3V3"]),
  "esp32_38": dict(title="ESP32-DevKitC V4 (38-pin)", w=27.9, h=55.0, pitch=2.54, ant="top", usb="bottom", note="Espressif's own board. Rows 1.0 in apart: it covers a whole breadboard bank, so keep it on the harness, not the board.",
    left=["3V3","EN","VP (36)","VN (39)","D34","D35","D32","D33","D25","D26","D27","D14","D12","GND","D13","SD2 (9)","SD3 (10)","CMD (11)","5V"],
    right=["GND","D23","D22","TX0 (1)","RX0 (3)","D21","GND","D19","D18","D5","D17","D16","D4","D0","D2","D15","SD1 (8)","SD0 (7)","CLK (6)"]),
  "a4988": dict(title="A4988 stepper driver (Pololu pinout)", w=15.2, h=20.3, pitch=2.54, pot="top", note="Seen from above with the trimpot at the top. MS1–MS3 all to VDD = 1/16 microstep (STEPS_PER_DEG 8.889). Tie RESET to SLEEP. Set the trimpot for about 0.8 A before connecting the motor.",
    left=["ENABLE","MS1","MS2","MS3","RESET","SLEEP","STEP","DIR"], right=["VMOT","GND (motor)","2B","2A","1A","1B","VDD","GND (logic)"]),
  "adf4351": dict(title="ADF4351 PLL board (SMA out, 25 MHz TCXO)", w=45, h=32, pitch=2.54, sma="top", generic=True, note="The eBay/Amazon boards share these pin NAMES but not their order on the header — match by the silkscreen label, not by position. Logic is 3.3 V, so the ESP32 drives it directly (33 Ω in series).",
    left=["VCC / 5V","GND","CLK","DATA","LE","CE","LD","MUX"], right=[]),
  "uca202": dict(title="Behringer UCA202 (rear panel)", w=90, h=30, rca=True, note="Both breadboard audio outputs go to the RCA INPUT pair. Input switch to LINE. Monitor off. 48 kHz / 16-bit in the OS, every 'enhancement' off.",
    left=["INPUT L (white)","INPUT L shell","INPUT R (red)","INPUT R shell"], right=[]),
}
# used pins: module -> pin label -> (what it carries, breadboard hole to check with an ohm-meter)
USED = {
  "esp32_30": {"D18":("SCK → J9 pin 2","j45"), "D23":("MOSI → J9 pin 3","j46"), "D5":("LE → J9 pin 4","j47"), "D19":("LD ← J9 pin 5","j48"),
               "D25":("SYNC → J9 pin 6","j49"), "D26":("STEP → J9 pin 7","j50"), "D27":("DIR → J9 pin 8","j51"), "D14":("EN → J9 pin 9","j52"),
               "3V3":("3.3 V out → J9 pin 10","j53"), "GND":("GND → J9 pin 1","j44"), "VIN":("5 V in from LM2596 #1 (optional; USB powers it)", None)},
  "esp32_38": {"D18":("SCK → J9 pin 2","j45"), "D23":("MOSI → J9 pin 3","j46"), "D5":("LE → J9 pin 4","j47"), "D19":("LD ← J9 pin 5","j48"),
               "D25":("SYNC → J9 pin 6","j49"), "D26":("STEP → J9 pin 7","j50"), "D27":("DIR → J9 pin 8","j51"), "D14":("EN → J9 pin 9","j52"),
               "3V3":("3.3 V out → J9 pin 10","j53"), "GND":("GND → J9 pin 1","j44"), "5V":("5 V in from LM2596 #1 (optional; USB powers it)", None)},
  "a4988": {"ENABLE":("EN ← J11 pin 5 (10 k pull-up: off at boot)","j62"), "STEP":("STEP ← J11 pin 3","j60"), "DIR":("DIR ← J11 pin 4","j61"),
            "VDD":("3.3 V ← J11 pin 2","j59"), "GND (logic)":("← J11 pin 1","j58"), "GND (motor)":("12 V supply −",None),
            "MS1":("→ VDD (1/16 step)",None), "MS2":("→ VDD",None), "MS3":("→ VDD",None), "RESET":("→ SLEEP (wire link)",None), "SLEEP":("→ RESET",None),
            "VMOT":("12 V supply +, 100 µF (C21) right at the pins",None), "1A":("NEMA-17 coil A",None), "1B":("NEMA-17 coil A",None), "2A":("NEMA-17 coil B",None), "2B":("NEMA-17 coil B",None)},
  "adf4351": {"VCC / 5V":("← J6 pin 1 (V5_ADF, through FB1)","d38"), "GND":("← J6 pin 2 / J10 pin 1","d39"), "CLK":("← J10 pin 2 SCK_O","a53"),
              "DATA":("← J10 pin 3 MOSI_O","a54"), "LE":("← J10 pin 4 LE_O","a55"), "LD":("→ J10 pin 5 (lock detect)","a56"), "CE":("← J10 pin 6 (JP3 to 3.3 V)","a57"), "MUX":("leave open",None)},
  "uca202": {"INPUT L (white)":("← J2 pin 1 AUDIO_L (beat signal)","f36"), "INPUT L shell":("← J2 pin 2 GND","f37"), "INPUT R (red)":("← J12 pin 1 AUDIO_R (0.3 V sync)","d63"), "INPUT R shell":("← J12 pin 2 GND","d62")},
}

def alias(n): return ALIAS.get(n, n)


MOD_JS = r'''
// ---------- chips & modules: real pinouts ----------
function drawModule(key) {
  const m = D.modules[key], used = D.used[key] || {}; const K = 6;   // 6 px per mm
  const pad = 62, nL = m.left.length, nR = m.right.length, n = Math.max(nL, nR);
  const w = m.w*K, h = m.h*K, W = w + pad*2, Hh = h + 34;
  const box = document.createElementNS(NS, "svg"); box.setAttribute("viewBox", `0 0 ${W} ${Hh}`); box.setAttribute("width", W); box.setAttribute("role","img"); box.setAttribute("aria-label", m.title);
  const E = (t, a, parent) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); (parent||box).appendChild(e); return e; };
  const T = (a, s, parent) => { const t = E("text", a, parent); t.textContent = s; return t; };
  const x0 = pad, y0 = 10;
  E("rect", {x:x0, y:y0, width:w, height:h, rx:6, fill: m.rca ? "#2b2d31" : "#1f3a2f", stroke:"#0d1a14", "stroke-width":1.5});
  if (m.ant) { E("rect", {x:x0+w*0.25, y:y0+4, width:w*0.5, height:9*K, rx:2, fill:"#c9c4b6"}); T({x:x0+w/2, y:y0+4+9*K/2+3, "font-size":8, "text-anchor":"middle", fill:"#333", "font-family":"var(--mono)"}, "antenna", box);
             E("rect", {x:x0+w*0.25, y:y0+4+9*K+4, width:w*0.5, height:10*K, rx:2, fill:"#8f8f8f"}); T({x:x0+w/2, y:y0+4+9*K+4+10*K/2+3, "font-size":8, "text-anchor":"middle", fill:"#111", "font-family":"var(--mono)"}, "ESP-WROOM-32", box); }
  if (m.usb) { E("rect", {x:x0+w/2-4*K, y:y0+h-3*K, width:8*K, height:3*K+4, rx:2, fill:"#aaa"}); T({x:x0+w/2, y:y0+h+14, "font-size":8, "text-anchor":"middle", fill:"var(--ink-2)", "font-family":"var(--mono)"}, "micro-USB → laptop (serial + power)", box); }
  if (m.pot) { E("circle", {cx:x0+w/2, cy:y0+3*K, r:2.2*K, fill:"#3a6fb0"}); T({x:x0+w/2, y:y0+3*K+3, "font-size":7, "text-anchor":"middle", fill:"#fff", "font-family":"var(--mono)"}, "Vref", box);
              E("rect", {x:x0+w/2-3*K, y:y0+h/2-2*K, width:6*K, height:6*K, rx:1, fill:"#111"}); T({x:x0+w/2, y:y0+h/2+1.5*K, "font-size":7, "text-anchor":"middle", fill:"#ccc", "font-family":"var(--mono)"}, "A4988", box); }
  if (m.sma) { E("rect", {x:x0+w-8*K, y:y0-6, width:6*K, height:6*K, rx:3*K, fill:"#d4b25a"}); T({x:x0+w-5*K, y:y0-10, "font-size":8, "text-anchor":"middle", fill:"var(--ink-2)", "font-family":"var(--mono)"}, "RF OUT (SMA) → 3 dB pad → PA", box);
              E("rect", {x:x0+8, y:y0+h/2-3*K, width:9*K, height:6*K, rx:1, fill:"#111"}); T({x:x0+8+4.5*K, y:y0+h/2+1, "font-size":7, "text-anchor":"middle", fill:"#ccc", "font-family":"var(--mono)"}, "ADF4351", box);
              E("rect", {x:x0+w/2-4*K, y:y0+h/2+4*K, width:7*K, height:5*K, rx:1, fill:"#8f8f8f"}); T({x:x0+w/2-0.5*K, y:y0+h/2+7*K+1, "font-size":7, "text-anchor":"middle", fill:"#111", "font-family":"var(--mono)"}, "25 MHz", box); }
  if (m.rca) { [["INPUT L", "#eee", 0.3], ["INPUT R", "#c33", 0.42], ["OUTPUT L", "#eee", 0.62], ["OUTPUT R", "#c33", 0.74]].forEach(([l,c,f]) => { E("circle", {cx:x0+w*f, cy:y0+h/2, r:1.9*K, fill:"#555"}); E("circle", {cx:x0+w*f, cy:y0+h/2, r:1.1*K, fill:c}); T({x:x0+w*f, y:y0+h-4, "font-size":7, "text-anchor":"middle", fill:"#ddd", "font-family":"var(--mono)"}, l, box); });
              E("rect", {x:x0+w*0.88, y:y0+h/2-1.5*K, width:2.5*K, height:3*K, fill:"#aaa"}); T({x:x0+w*0.9, y:y0+h-4, "font-size":7, "text-anchor":"middle", fill:"#ddd", "font-family":"var(--mono)"}, "USB", box);
              T({x:x0+w*0.1, y:y0+h/2+3, "font-size":7, "text-anchor":"middle", fill:"#ddd", "font-family":"var(--mono)"}, "LINE", box); }
  const pinsTop = y0 + (m.rca ? 0 : Math.max(8, (h - (n-1)*m.pitch*K)/2));
  const side = (list, isLeft) => list.forEach((lab, i) => {
    const y = m.rca ? y0 + 8 + i*14 : pinsTop + i*m.pitch*K; const x = isLeft ? x0 : x0 + w; const u = used[lab];
    const g = E("g", {class:"pinrow" + (u ? " used" : "")});
    if (!m.rca) { E("rect", {x:x-4, y:y-4, width:8, height:8, rx:1, fill: u ? "var(--hl)" : "#d4b25a", stroke:"#222", "stroke-width":.6}, g);
                  E("rect", {x:x-2, y:y-2, width:4, height:4, fill:"#222"}, g); }
    const tx = isLeft ? x-8 : x+8;
    T({x:tx, y:y+3, "font-size":u?9:8, "text-anchor":isLeft?"end":"start", fill: u ? "var(--ink)" : "var(--ink-3)", "font-weight": u ? 700 : 400, "font-family":"var(--mono)"}, m.rca ? "" : lab, g);
    if (m.rca) { E("circle", {cx:x0+w+10, cy:y, r:4, fill: u ? "var(--hl)" : "#888"}, g); T({x:x0+w+18, y:y+3, "font-size":9, fill:"var(--ink)", "font-weight":700, "font-family":"var(--mono)"}, lab, g); }
    if (u) { const t = E("title", {}, g); t.textContent = u[0] + (u[1] ? ` — board hole ${u[1]}` : "");
             if (u[1]) { g.addEventListener("mouseenter", () => { if (!locked) { selectHole(u[1]); scrollTo(u[1]); } }); g.addEventListener("click", () => { locked = {type:"hole", id:u[1]}; selectHole(u[1]); scrollTo(u[1]); }); } }
  });
  if (!m.rca) { side(m.left, true); side(m.right, false); }
  return box;
}
function moduleTable(key) {
  const used = D.used[key] || {}; const m = D.modules[key];
  const rows = [...m.left, ...m.right].filter(l => used[l]).map(l => `<tr><td class="h">${l}</td><td>${used[l][0]}</td><td>${used[l][1] ? H(used[l][1]) : "<span class=mut>off-board</span>"}</td></tr>`).join("");
  return `<div class="tablewrap"><table><thead><tr><th>pin</th><th>goes to</th><th>hole</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
const modRoot = document.getElementById("modules");
// TL072 card: pin map for both chips
(() => {
  const card = document.createElement("div"); card.className = "mod";
  const rows = Object.keys(D.dip8).map(pin => { const holes = ["U1","U2"].map(r => { const h = partByRef[r].pins.find(([p])=>p===pin)[1]; return `${H(h)} ${N(netOfHole(h))}`; }); return `<tr><td class="h">${pin}</td><td>${D.dip8[pin]}</td><td>${holes[0]}</td><td>${holes[1]}</td></tr>`; }).join("");
  card.innerHTML = `<h3>TL072CP dual op-amp, DIP-8</h3><span class="mut">Seen from above with the notch and pin-1 dot on the RIGHT (toward the higher column): the top row reads 4 3 2 1 left→right, the bottom row 5 6 7 8. Pin numbering runs counter-clockwise from the notch. Straddles the channel, 7.62 mm between rows.</span>
    <svg viewBox="0 0 300 120" width="300" role="img" aria-label="TL072 top view"><rect x="60" y="30" width="180" height="60" rx="3" fill="#1b1f24"/><path d="M240,50 A10,10 0 0 0 240,70 Z" fill="var(--card)"/><circle cx="226" cy="42" r="4" fill="#ddd"/>
      ${[4,3,2,1].map((p,i)=>`<rect x="${74+i*45}" y="12" width="8" height="18" fill="#9a9a9a"/><text x="${78+i*45}" y="9" font-size="9" text-anchor="middle" fill="var(--ink)" font-family="var(--mono)">${p}</text><text transform="translate(${78+i*45},48) rotate(-90)" font-size="7.5" text-anchor="end" fill="#ddd" font-family="var(--mono)">${D.dip8[String(p)]}</text>`).join("")}
      ${[5,6,7,8].map((p,i)=>`<rect x="${74+i*45}" y="90" width="8" height="18" fill="#9a9a9a"/><text x="${78+i*45}" y="118" font-size="9" text-anchor="middle" fill="var(--ink)" font-family="var(--mono)">${p}</text><text transform="translate(${78+i*45},72) rotate(-90)" font-size="7.5" text-anchor="start" fill="#ddd" font-family="var(--mono)">${D.dip8[String(p)]}</text>`).join("")}
      <text x="150" y="63" font-size="9" text-anchor="middle" fill="#fff" font-family="var(--cond)" font-weight="700">TL072CP</text></svg>
    <div class="tablewrap"><table><thead><tr><th>pin</th><th>function</th><th>U1 (video amp)</th><th>U2 (buffers)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  modRoot.appendChild(card);
})();
// ESP32 with a variant switch
(() => {
  const card = document.createElement("div"); card.className = "mod"; let cur = "esp32_30";
  const render = () => { const m = D.modules[cur];
    card.innerHTML = `<h3>${m.title}</h3><span class="mut">${m.note} GPIO numbers come straight from <span class="h">radar_ctl.ino</span>: SCK 18, MOSI 23, LE 5, LD 19, SYNC 25, STEP 26, DIR 27, EN 14.</span><div class="variant"><button type="button" data-v="esp32_30" aria-pressed="${cur==="esp32_30"}">30-pin DevKit V1</button><button type="button" data-v="esp32_38" aria-pressed="${cur==="esp32_38"}">38-pin DevKitC V4</button></div>`;
    card.appendChild(drawModule(cur)); card.insertAdjacentHTML("beforeend", moduleTable(cur));
    card.querySelectorAll(".variant button").forEach(b => b.onclick = () => { cur = b.dataset.v; render(); }); };
  render(); modRoot.appendChild(card);
})();
["a4988","adf4351","uca202"].forEach(key => { const m = D.modules[key]; const card = document.createElement("div"); card.className = "mod";
  card.innerHTML = `<h3>${m.title}</h3><span class="mut">${m.note}</span>`; card.appendChild(drawModule(key)); card.insertAdjacentHTML("beforeend", moduleTable(key)); modRoot.appendChild(card); });
'''


def modules_md():
    L = ["# Chips and modules — real pinouts\n",
         "Generated by `gen_page.py`. Boards seen from above, antenna / SMA / trimpot at the top, USB at the bottom.",
         "`hole` is the breadboard hole the signal must reach (ohm-meter check from the module pin).\n",
         "## TL072CP (DIP-8)\n",
         "Notch and pin-1 dot toward the higher column (right). Top row reads 4 3 2 1 left→right, bottom row 5 6 7 8.\n",
         "| pin | function | U1 hole | U2 hole |", "|---|---|---|---|"]
    u = {p["ref"]: dict(p["pins"]) for p in D["parts"] if p["kind"] == "dip8"}
    for pin, name in DIP8.items(): L.append(f"| {pin} | {name} | {u['U1'][pin]} | {u['U2'][pin]} |")
    for key, m in MODULES.items():
        L += [f"\n## {m['title']}\n", m["note"] + "\n"]
        if m.get("right"):
            L += ["| left, top→bottom | | right, top→bottom | |", "|---|---|---|---|"]
            for i in range(max(len(m["left"]), len(m["right"]))):
                l = m["left"][i] if i < len(m["left"]) else ""; r = m["right"][i] if i < len(m["right"]) else ""
                ul = USED[key].get(l); ur = USED[key].get(r)
                L.append(f"| {('**'+l+'**') if ul else l} | {ul[0] + (' — '+ul[1] if ul and ul[1] else '') if ul else ''} | {('**'+r+'**') if ur else r} | {ur[0] + (' — '+ur[1] if ur and ur[1] else '') if ur else ''} |")
        else:
            L += ["| pin | goes to | hole |", "|---|---|---|"]
            for l in m["left"]:
                ul = USED[key].get(l); L.append(f"| {l} | {ul[0] if ul else 'leave as shipped'} | {ul[1] if ul and ul[1] else ''} |")
    (HERE / "MODULES.md").write_text("\n".join(L) + "\n")


def build():
    data = dict(parts=D["parts"], wires=D["wires"], rails=D["rails"], nets=D["nets"], group_net=D["group_net"],
                alias=ALIAS, net_desc=NET_DESC, kind=KIND, steps=STEPS, dip8=DIP8, modules=MODULES, used=USED)
    js_data = json.dumps(data, separators=(",", ":"))
    n_parts, n_wires, n_nets = len(D["parts"]), len(D["wires"]), len(D["nets"])
    html = f"""<title>ESP-FLY Radar Breadboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root {{
  --paper:#f5f2ea; --paper-2:#ece7da; --ink:#1e1b16; --ink-2:#5a544a; --ink-3:#8b8477; --line:#d8d1c1;
  --board:#efe9d6; --hole:#4a4640; --hole-2:#7c766c; --rail-red:#c23a2b; --rail-blue:#2c6fad;
  --accent:#b8541c; --accent-ink:#fff; --hl:#ffcc2e; --hl-2:rgba(255,204,46,.45); --card:#fbf9f3; --ok:#2f8f5b;
  --mono:"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans:"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --cond:"IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --paper:#17191c; --paper-2:#1f2226; --ink:#ece7dc; --ink-2:#b3ab9c; --ink-3:#7d766b; --line:#33373d;
  --board:#e6dfcb; --card:#1d2024; --hl:#ffd54a; --hl-2:rgba(255,213,74,.5); --accent:#e0803f; --accent-ink:#17191c; --ok:#5cc38a;
}} }}
:root[data-theme="dark"] {{
  --paper:#17191c; --paper-2:#1f2226; --ink:#ece7dc; --ink-2:#b3ab9c; --ink-3:#7d766b; --line:#33373d;
  --board:#e6dfcb; --card:#1d2024; --hl:#ffd54a; --hl-2:rgba(255,213,74,.5); --accent:#e0803f; --accent-ink:#17191c; --ok:#5cc38a;
}}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans); font-size:14px; line-height:1.45 }}
header {{ padding:22px 28px 14px; display:flex; flex-wrap:wrap; gap:8px 28px; align-items:baseline; border-bottom:1px solid var(--line) }}
h1 {{ font-family:var(--cond); font-weight:700; font-size:26px; margin:0; letter-spacing:.01em; text-wrap:balance }}
header p {{ margin:0; color:var(--ink-2); max-width:70ch }}
.stat {{ font-family:var(--mono); font-size:12px; color:var(--ink-2); display:flex; gap:18px; margin-left:auto }}
.stat b {{ color:var(--ink); font-weight:600 }}
.stat .ok {{ color:var(--ok) }}
.boardwrap {{ position:sticky; top:0; z-index:5; background:var(--paper-2); border-bottom:1px solid var(--line); padding:10px 0 8px }}
.toolbar {{ display:flex; gap:10px; align-items:center; padding:0 28px 8px; flex-wrap:wrap }}
.toolbar input {{ font:13px var(--mono); padding:6px 10px; border:1px solid var(--line); border-radius:4px; background:var(--card); color:var(--ink); width:26ch }}
.toolbar button, .tabs button {{ font:600 12px var(--cond); letter-spacing:.06em; text-transform:uppercase; padding:6px 12px; border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:4px; cursor:pointer }}
.toolbar button:hover, .tabs button:hover {{ border-color:var(--accent) }}
.toolbar button:focus-visible, .tabs button:focus-visible, input:focus-visible, tr:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px }}
.legend {{ margin-left:auto; display:flex; gap:12px; font-family:var(--mono); font-size:11px; color:var(--ink-2); flex-wrap:wrap }}
.legend i {{ display:inline-block; width:14px; height:4px; border-radius:2px; vertical-align:middle; margin-right:5px }}
.scroller {{ overflow-x:auto; overflow-y:hidden; padding:0 28px }}
svg.board {{ display:block; height:auto; user-select:none }}
.hole {{ fill:var(--hole) }}  .rhole {{ fill:var(--hole-2) }}
.strip-hl {{ fill:var(--hl-2); stroke:var(--hl); stroke-width:1.2; opacity:0; pointer-events:none; transition:opacity .12s }}
.strip-hl.on {{ opacity:1 }}
.pin-hl {{ fill:none; stroke:var(--hl); stroke-width:2.2; opacity:0; pointer-events:none }}
.pin-hl.on {{ opacity:1 }}
.wire {{ cursor:pointer; transition:opacity .12s }}
.part {{ cursor:pointer }}
.dimmed .wire:not(.on) {{ opacity:.18 }}
.dimmed .part:not(.on) {{ opacity:.35 }}
.wire.on path {{ stroke-width:4.2; filter:drop-shadow(0 0 3px var(--hl)) }}
.hit {{ fill:transparent; cursor:pointer }}
main {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(300px,420px); gap:0; align-items:start }}
@media (max-width:900px) {{ main {{ grid-template-columns:1fr }} aside {{ position:static !important }} }}
section.lists {{ padding:16px 28px 40px; min-width:0 }}
aside {{ position:sticky; top:290px; padding:16px 28px 16px 0; min-width:0 }}
.tabs {{ display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap }}
.tabs button[aria-selected="true"] {{ background:var(--accent); color:var(--accent-ink); border-color:var(--accent) }}
.tab {{ display:none }} .tab.on {{ display:block }}
.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:6px; background:var(--card) }}
table {{ border-collapse:collapse; width:100%; font-size:13px }}
th {{ text-align:left; font:600 11px var(--cond); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-2); padding:8px 10px; border-bottom:1px solid var(--line); background:var(--card); position:sticky; top:0 }}
td {{ padding:6px 10px; border-bottom:1px solid var(--line); vertical-align:top }}
tr:last-child td {{ border-bottom:0 }}
tbody tr {{ cursor:pointer }} tbody tr:hover, tbody tr.on {{ background:var(--hl-2) }}
tbody tr.done td {{ color:var(--ink-3) }} tbody tr.done td .h {{ text-decoration:line-through }}
.h {{ font-family:var(--mono); font-weight:600; font-size:12.5px; white-space:nowrap }}
.net {{ font-family:var(--mono); font-size:12px; padding:1px 6px; border:1px solid var(--line); border-radius:3px; white-space:nowrap; background:var(--paper-2) }}
.mut {{ color:var(--ink-2) }}
.sw {{ display:inline-block; width:10px; height:10px; border-radius:50%; border:1px solid rgba(0,0,0,.3); vertical-align:-1px; margin-right:6px }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:6px; padding:14px 16px; min-height:120px; font-variant-numeric:tabular-nums }}
.card h2 {{ font-family:var(--cond); font-size:20px; margin:0 0 2px; font-weight:700 }}
.card .sub {{ color:var(--ink-2); margin:0 0 10px; font-size:13px }}
.card ul {{ list-style:none; padding:0; margin:0; display:grid; gap:6px }}
.card li {{ padding:6px 8px; border:1px solid var(--line); border-radius:4px; background:var(--paper-2); font-size:13px }}
.card li .h {{ font-size:13px }} .card li .mut {{ display:block; font-size:12px }}
.card .empty {{ color:var(--ink-3); font-style:italic }}
.steps {{ counter-reset:s; display:grid; gap:8px; margin:0; padding:0; list-style:none; max-width:70ch }}
.steps li {{ display:grid; grid-template-columns:34px 1fr; gap:10px; padding:10px 12px; border:1px solid var(--line); border-radius:6px; background:var(--card) }}
.steps li::before {{ counter-increment:s; content:counter(s); font:700 18px var(--cond); color:var(--accent) }}
.steps b {{ display:block; font-family:var(--cond); font-size:15px; margin-bottom:2px }}
.modgrid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:14px }}
.mod {{ background:var(--card); border:1px solid var(--line); border-radius:6px; padding:12px 14px; min-width:0 }}
.mod h3 {{ font-family:var(--cond); font-size:16px; margin:0 0 2px }}
.mod .mut {{ font-size:12.5px; display:block; margin-bottom:8px; max-width:60ch }}
.mod svg {{ display:block; max-width:100%; height:auto }}
.mod .variant {{ display:flex; gap:6px; margin-bottom:8px }}
.mod .variant button {{ font:600 11px var(--cond); letter-spacing:.05em; text-transform:uppercase; padding:4px 9px; border:1px solid var(--line); background:var(--paper-2); color:var(--ink); border-radius:4px; cursor:pointer }}
.mod .variant button[aria-pressed="true"] {{ background:var(--accent); color:var(--accent-ink); border-color:var(--accent) }}
.mod table {{ font-size:12.5px; margin-top:8px }} .mod td, .mod th {{ padding:4px 6px }}
.pinrow {{ cursor:default }} .pinrow.used {{ cursor:pointer }}
.pinrow.used:hover rect, .pinrow.used:hover text {{ filter:brightness(1.15) }}
kbd {{ font-family:var(--mono); font-size:11px; padding:1px 5px; border:1px solid var(--line); border-radius:3px; background:var(--paper-2) }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important }} }}
</style>

<header>
  <div>
    <h1>ESP-FLY Radar Breadboard</h1>
    <p>Every part lead and every jumper on the 830-point board, hole by hole. Hover or click a part, a wire, a net or a hole; the board lights up what shares that connection. The placement is checked by <span class="h">layout.py</span> against the KiCad netlist before this page is generated.</p>
  </div>
  <div class="stat"><span><b>{n_parts}</b> parts</span><span><b>{n_wires}</b> wires</span><span><b>{n_nets}</b> nets</span><span class="ok">netlist verified</span><span id="progress"></span></div>
</header>

<div class="boardwrap">
  <div class="toolbar">
    <input id="find" type="search" placeholder="find: R3, b14, VREF, J9 …" aria-label="find a part, hole or net">
    <button id="zin" type="button">Zoom +</button><button id="zout" type="button">Zoom −</button><button id="clear" type="button">Clear</button>
    <div class="legend">
      <span><i style="background:#111"></i>GND</span><span><i style="background:#d33"></i>VANA</span><span><i style="background:#e07a20"></i>V5</span>
      <span><i style="background:#2a9d5c"></i>signal</span><span><i style="background:#7a4fbf"></i>VREF</span><span><i style="background:#2f77b0"></i>SPI</span>
      <span><i style="background:#e0b020"></i>3V3</span><span><i style="background:#ddd;border:1px solid #999"></i>step/dir/en</span><span><i style="background:#8a8f96"></i>sync</span>
    </div>
  </div>
  <div class="scroller"><svg class="board" id="board" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 235" role="img" aria-label="breadboard top view"></svg></div>
</div>

<main>
  <section class="lists">
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected="true" data-tab="parts">Parts</button>
      <button role="tab" aria-selected="false" data-tab="modules">Chips &amp; modules</button>
      <button role="tab" aria-selected="false" data-tab="wires">Wires</button>
      <button role="tab" aria-selected="false" data-tab="nets">Nets</button>
      <button role="tab" aria-selected="false" data-tab="steps">Build order</button>
    </div>
    <div class="tab on" id="tab-parts"><div class="tablewrap"><table><thead><tr><th>✓</th><th>Ref</th><th>Part</th><th>Lead → hole</th><th>Note</th></tr></thead><tbody id="parts"></tbody></table></div></div>
    <div class="tab" id="tab-modules">
      <p class="mut" style="max-width:70ch;margin:0 0 12px">Real pinouts, boards seen from above. Highlighted pins are the ones this build uses; hover one and the board shows the hole it must end up on. Everything else on a module is left as the board ships.</p>
      <div class="modgrid" id="modules"></div>
    </div>
    <div class="tab" id="tab-wires"><div class="tablewrap"><table><thead><tr><th>✓</th><th>#</th><th>From</th><th>To</th><th>Colour</th><th>Length</th><th>Purpose</th></tr></thead><tbody id="wires"></tbody></table></div></div>
    <div class="tab" id="tab-nets"><div class="tablewrap"><table><thead><tr><th>Net</th><th>What it is</th><th>Strips / rails</th><th>Pins</th></tr></thead><tbody id="nets"></tbody></table></div></div>
    <div class="tab" id="tab-steps"><ol class="steps" id="steps"></ol>
      <p class="mut" style="max-width:70ch">Hole names: row letter then column number, <span class="h">b14</span> = row b, column 14. The five holes a–e of a column are one strip (top bank), f–j another (bottom bank). <span class="h">TR-@12</span> = the top blue rail, hole nearest column 12; on a real board use the closest free rail hole. Rails: top red V5, top blue GND, bottom red VANA, bottom blue GND. Checkboxes are remembered in this browser only.</p></div>
  </section>
  <aside><div class="card" id="detail"><h2>Nothing selected</h2><p class="sub">Hover the board or a table row. Click to keep a selection; <kbd>Esc</kbd> or Clear releases it.</p></div></aside>
</main>

<script>
const D = {js_data};
const S = 5;
const RAIL_Y = {{"TR+":2.0,"TR-":4.54,"BR+":38.6,"BR-":41.1}};
const COL = {{black:"#111",red:"#d33",blue:"#2f77b0",yellow:"#e0b020",green:"#2a9d5c",orange:"#e07a20",white:"#e8e8e8",grey:"#8a8f96",violet:"#7a4fbf"}};
const KCOL = {{res:"#d9c39a",film:"#d8b53a",cer:"#d08a3a",elec:"#2a3140",diode:"#222",bead:"#666"}};
const ROWS = "abcdefghij";
const alias = n => D.alias[n] || n;

function parse(h) {{
  let m = /^([a-j])(\\d+)$/.exec(h);
  if (m) return {{kind:"strip", row:m[1], col:+m[2], key:(ROWS.indexOf(m[1])<5?"T":"B")+m[2]}};
  m = /^(TR\\+|TR-|BR\\+|BR-)@(\\d+)$/.exec(h);
  return {{kind:"rail", rail:m[1], col:+m[2], key:m[1]+(+m[2]<=31?"L":"R")}};
}}
function xy(h) {{
  const k = parse(h); const x = 7 + (k.col-1)*2.54;
  if (k.kind==="strip") {{ const i = ROWS.indexOf(k.row); return [x, 9 + i*2.54 + (i>=5?3:0)]; }}
  return [x, RAIL_Y[k.rail]];
}}
const netOfHole = h => D.group_net[parse(h).key] || null;
// hole -> [{{ref,pin}}] and net -> pins/wires
const holePins = {{}};
D.parts.forEach(p => p.pins.forEach(([pin,h]) => (holePins[h] = holePins[h]||[]).push({{ref:p.ref,pin}})));
const netWires = {{}};
D.wires.forEach((w,i) => {{ const n = netOfHole(w.a); (netWires[n] = netWires[n]||[]).push(i); }});
const partByRef = Object.fromEntries(D.parts.map(p=>[p.ref,p]));

// ---------- draw ----------
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("board");
const el = (t, a, parent) => {{ const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); (parent||svg).appendChild(e); return e; }};
el("rect", {{x:0,y:0,width:850,height:235,rx:8,fill:"var(--board)"}});
const gStrips = el("g",{{id:"strips"}}), gRails = el("g",{{}}), gHoles = el("g",{{}}), gWires = el("g",{{}}), gParts = el("g",{{}}), gPins = el("g",{{}}), gHit = el("g",{{}});
// rail lines + labels
for (const r in RAIL_Y) {{ const y = RAIL_Y[r], c = r.includes("+") ? "#c23a2b" : "#2c6fad", off = r.includes("+") ? -1.4 : 1.4;
  el("line", {{x1:5*S,y1:(y+off)*S,x2:165*S,y2:(y+off)*S,stroke:c,"stroke-width":2}}, gRails);
  const t = el("text", {{x:1.0*S,y:(y+0.6)*S,"font-size":8,fill:c,"font-family":"var(--mono)","font-weight":600}}, gRails); t.textContent = D.rails[r]; }}
// strip highlight overlays
const stripHL = {{}};
for (let c=1;c<=63;c++) for (const b of "TB") {{ const [x,y0] = xy((b==="T"?"a":"f")+c), [,y1] = xy((b==="T"?"e":"j")+c);
  stripHL[b+c] = el("rect", {{x:(x-1.1)*S,y:(y0-1.1)*S,width:2.2*S,height:(y1-y0+2.2)*S,rx:3,class:"strip-hl"}}, gStrips); }}
for (const r in RAIL_Y) for (const half of "LR") {{ const c0 = half==="L"?1:32, c1 = half==="L"?31:63; const [x0,y] = xy(r+"@"+c0), [x1] = xy(r+"@"+c1);
  stripHL[r+half] = el("rect", {{x:(x0-1.1)*S,y:(y-1.1)*S,width:(x1-x0+2.2)*S,height:2.2*S,rx:3,class:"strip-hl"}}, gStrips); }}
// holes
for (let c=1;c<=63;c++) {{
  for (const row of ROWS) {{ const h = row+c, [x,y] = xy(h); el("rect", {{x:(x-.5)*S,y:(y-.5)*S,width:S,height:S,class:"hole"}}, gHoles); }}
  for (const r in RAIL_Y) {{ const [x,y] = xy(r+"@"+c); el("rect", {{x:(x-.5)*S,y:(y-.5)*S,width:S,height:S,class:"rhole"}}, gHoles); }}
  if (c%5===0||c===1) {{ const [x] = xy("a"+c); const t = el("text", {{x:x*S,y:7.2*S,"font-size":7.5,"text-anchor":"middle",fill:"#6b655a","font-family":"var(--mono)"}}, gHoles); t.textContent=c; }}
}}
for (const row of ROWS) {{ const [,y] = xy(row+"1"); const t = el("text", {{x:4.6*S,y:(y+0.6)*S,"font-size":7.5,"text-anchor":"end",fill:"#6b655a","font-family":"var(--mono)"}}, gHoles); t.textContent=row; }}
// wires
const wireEls = D.wires.map((w,i) => {{
  const [x1,y1] = xy(w.a), [x2,y2] = xy(w.b); const c = COL[w.colour];
  const sag = ((y1+y2)/2 < 22 ? -1 : 1) * Math.max(1.5, Math.abs(x2-x1)*0.12);
  const g = el("g", {{class:"wire","data-wire":i}}, gWires);
  el("path", {{d:`M${{x1*S}},${{y1*S}} Q${{(x1+x2)/2*S}},${{((y1+y2)/2+sag)*S}} ${{x2*S}},${{y2*S}}`,fill:"none",stroke:c,"stroke-width":3,"stroke-linecap":"round",opacity:.92}}, g);
  el("circle", {{cx:x1*S,cy:y1*S,r:2.4,fill:c}}, g); el("circle", {{cx:x2*S,cy:y2*S,r:2.4,fill:c}}, g);
  const t = el("title", {{}}, g); t.textContent = `wire ${{i+1}}: ${{w.a}} → ${{w.b}} (${{w.colour}}) — ${{w.why}}`;
  return g;
}});
// parts
const partEls = {{}};
D.parts.forEach(p => {{
  const pts = p.pins.map(([,h]) => xy(h)); const g = el("g", {{class:"part","data-ref":p.ref}}, gParts); partEls[p.ref] = g;
  const txt = (a, s) => {{ const t = el("text", a, g); t.textContent = s; return t; }};
  if (p.kind==="dip8") {{   // true to life: 9.9 x 6.4 mm body, 7.62 mm row pitch, notch at the pin-1/8 end (right), dot beside pin 1
    const xs = pts.map(q=>q[0]); const xc = (Math.min(...xs)+Math.max(...xs))/2, x0 = xc-4.95, x1 = xc+4.95;
    const yc = (pts[0][1]+pts[4][1])/2, y0 = yc-3.2, y1 = yc+3.2;
    p.pins.forEach(([pin,h],i) => el("line", {{x1:pts[i][0]*S,y1:(h[0]==="e"?y0:y1)*S,x2:pts[i][0]*S,y2:pts[i][1]*S,stroke:"#9a9a9a","stroke-width":3}}, g));
    el("rect", {{x:x0*S,y:y0*S,width:(x1-x0)*S,height:(y1-y0)*S,rx:1.5,fill:"#1b1f24"}}, g);
    el("path", {{d:`M${{x1*S}},${{(yc-1.1)*S}} A${{1.1*S}},${{1.1*S}} 0 0 0 ${{x1*S}},${{(yc+1.1)*S}} Z`,fill:"var(--board)"}}, g);
    el("circle", {{cx:(x1-1.3)*S,cy:(y0+1.2)*S,r:2.2,fill:"#ddd"}}, g);
    txt({{x:xc*S,y:(yc+0.45)*S,"font-size":6,fill:"#fff",stroke:"#1b1f24","stroke-width":2,"paint-order":"stroke","text-anchor":"middle","font-weight":"bold","font-family":"var(--cond)"}}, `${{p.ref}} ${{p.value}}`);
    p.pins.forEach(([pin,h],i) => {{ const top = h[0]==="e";
      txt({{x:pts[i][0]*S,y:(pts[i][1]+(top?-1.35:1.95))*S,"font-size":5.5,fill:"#333","text-anchor":"middle","font-family":"var(--mono)"}}, pin);
      txt({{transform:`translate(${{pts[i][0]*S}},${{(top?y0+0.35:y1-0.35)*S}}) rotate(-90)`,"font-size":4.2,fill:"#cfcfcf","text-anchor":top?"end":"start","dominant-baseline":"middle","font-family":"var(--mono)"}}, D.dip8[pin]); }});
  }} else if (p.kind.startsWith("hdr")) {{
    const x0 = pts[0][0]-1.27, x1 = pts[pts.length-1][0]+1.27, y = pts[0][1];
    el("rect", {{x:x0*S,y:(y-1.27)*S,width:(x1-x0)*S,height:2.54*S,rx:2,fill:"#222"}}, g);
    pts.forEach(([x,yy]) => el("rect", {{x:(x-.45)*S,y:(yy-.45)*S,width:.9*S,height:.9*S,fill:"#d4b25a"}}, g));
    txt({{x:(x0+x1)/2*S,y:(y+(y>22?3.4:-2.2))*S,"font-size":7.5,fill:"#222","text-anchor":"middle","font-weight":"bold","font-family":"var(--cond)"}}, p.ref + (p.pins.length>=5?" "+p.value:""));
  }} else {{
    const [[x1,y1],[x2,y2]] = pts; const mx=(x1+x2)/2, my=(y1+y2)/2, ang = Math.abs(x2-x1)>=Math.abs(y2-y1)?0:90;
    const [bw,bh] = (p.kind==="res"||p.kind==="diode") ? [5.5,2.2] : [3.4,2.4];
    el("line", {{x1:x1*S,y1:y1*S,x2:x2*S,y2:y2*S,stroke:"#999","stroke-width":1.5}}, g);
    const gb = el("g", {{transform:`translate(${{mx*S}},${{my*S}}) rotate(${{ang}})`}}, g);
    el("rect", {{x:-bw/2*S,y:-bh/2*S,width:bw*S,height:bh*S,rx:p.kind==="film"?0:2,fill:KCOL[p.kind],stroke:"#333","stroke-width":.6}}, gb);
    if (p.kind==="diode") el("rect", {{x:1.4*S,y:-bh/2*S,width:.5*S,height:bh*S,fill:"#ddd"}}, gb);
    if (p.kind==="elec") txt({{x:x1*S,y:(y1-1.2)*S,"font-size":7,fill:"#c33","text-anchor":"middle","font-weight":"bold"}}, "+");
    if (ang===0) {{ txt({{x:mx*S,y:(my-1.9)*S,"font-size":7,fill:"#111","text-anchor":"middle","font-weight":"bold","font-family":"var(--cond)"}}, p.ref);
                    txt({{x:mx*S,y:(my-0.7)*S,"font-size":6.5,fill:"#333","text-anchor":"middle","font-family":"var(--mono)"}}, p.value); }}
    else txt({{transform:`translate(${{mx*S}},${{my*S}}) rotate(-90)`,"font-size":6.5,fill:(p.kind==="elec"||p.kind==="diode")?"#fff":"#111","text-anchor":"middle","dominant-baseline":"middle","font-weight":"bold","font-family":"var(--cond)"}}, `${{p.ref}} ${{p.value}}`);
  }}
  const t = el("title", {{}}, g); t.textContent = `${{p.ref}} ${{p.value}} — ` + p.pins.map(([pin,h])=>`${{pin}}→${{h}}`).join(", ");
}});
// pin rings
const pinHL = {{}};
D.parts.forEach(p => p.pins.forEach(([,h]) => {{ if (pinHL[h]) return; const [x,y] = xy(h); pinHL[h] = el("circle", {{cx:x*S,cy:y*S,r:1.3*S,class:"pin-hl"}}, gPins); }}));
// hit targets for holes (top, transparent) — hover a hole to see its net
for (let c=1;c<=63;c++) {{ for (const row of ROWS) {{ const h=row+c, [x,y]=xy(h); el("rect", {{x:(x-1.27)*S,y:(y-1.27)*S,width:2.54*S,height:2.54*S,class:"hit","data-hole":h}}, gHit); }}
  for (const r in RAIL_Y) {{ const h=r+"@"+c, [x,y]=xy(h); el("rect", {{x:(x-1.27)*S,y:(y-1.2)*S,width:2.54*S,height:2.4*S,class:"hit","data-hole":h}}, gHit); }} }}
// parts and wires must stay clickable above the hit layer
gHit.style.pointerEvents = "all"; svg.appendChild(gWires); svg.appendChild(gParts); svg.appendChild(gPins);

// ---------- highlight + detail ----------
const detail = document.getElementById("detail");
let locked = null;
function clearHL() {{
  svg.classList.remove("dimmed");
  Object.values(stripHL).forEach(e=>e.classList.remove("on")); Object.values(pinHL).forEach(e=>e.classList.remove("on"));
  wireEls.forEach(e=>e.classList.remove("on")); Object.values(partEls).forEach(e=>e.classList.remove("on"));
  document.querySelectorAll("tbody tr.on").forEach(r=>r.classList.remove("on"));
}}
const H = h => `<span class="h">${{h}}</span>`, N = n => n ? `<span class="net">${{alias(n)}}</span>` : `<span class="mut">unused</span>`;
const stripName = h => {{ const k = parse(h); return k.kind==="strip" ? `strip ${{k.key}} (${{k.key[0]==="T"?"a–e":"f–j"}} of column ${{k.col}})` : `${{k.rail}} rail, ${{k.key.endsWith("L")?"left":"right"}} half`; }};
function netMembers(n, exceptRef) {{ return (D.nets[n]||[]).filter(([r])=>r!==exceptRef).map(([r,p])=>`${{r}}.${{p}}`).join(", "); }}
function showNet(n, opts={{}}) {{
  for (const k in D.group_net) if (D.group_net[k]===n) stripHL[k].classList.add("on");
  (D.nets[n]||[]).forEach(([r,p]) => {{ const part = partByRef[r]; const h = part.pins.find(([pp])=>pp===p)[1]; pinHL[h].classList.add("on"); if (!opts.noParts) partEls[r].classList.add("on"); }});
  (netWires[n]||[]).forEach(i => wireEls[i].classList.add("on"));
}}
function selectPart(ref) {{
  clearHL(); const p = partByRef[ref]; svg.classList.add("dimmed"); partEls[ref].classList.add("on");
  p.pins.forEach(([,h]) => {{ pinHL[h].classList.add("on"); const k = parse(h).key; if (stripHL[k]) stripHL[k].classList.add("on"); }});
  const rows = p.pins.map(([pin,h]) => {{ const n = netOfHole(h); return `<li>${{H("pin "+pin)}} → ${{H(h)}} &nbsp;${{N(n)}}<span class="mut">${{stripName(h)}}<br>${{n?"also on this net: "+(netMembers(n,ref)||"nothing else on the board"):""}}</span></li>`; }}).join("");
  detail.innerHTML = `<h2>${{ref}} · ${{p.value}}</h2><p class="sub">${{D.kind[p.kind]||p.kind}}${{p.note?" — "+p.note:""}}</p><ul>${{rows}}</ul>`;
  document.querySelector(`tr[data-ref="${{ref}}"]`)?.classList.add("on");
}}
function selectWire(i) {{
  clearHL(); const w = D.wires[i]; svg.classList.add("dimmed"); wireEls[i].classList.add("on");
  [w.a,w.b].forEach(h => {{ const k = parse(h).key; if (stripHL[k]) stripHL[k].classList.add("on"); }});
  const n = netOfHole(w.a);
  const [x1,y1]=xy(w.a),[x2,y2]=xy(w.b); const len = Math.round(Math.hypot(x1-x2,y1-y2)+12);
  detail.innerHTML = `<h2>Wire ${{i+1}} · <span class="sw" style="background:${{COL[w.colour]}}"></span>${{w.colour}}</h2><p class="sub">${{w.why}}</p>
    <ul><li>${{H(w.a)}} <span class="mut">${{stripName(w.a)}}</span></li><li>${{H(w.b)}} <span class="mut">${{stripName(w.b)}}</span></li>
    <li>carries ${{N(n)}} <span class="mut">${{n?netMembers(n):""}}</span></li><li>cut about ${{len}} mm of 22 AWG solid core (${{Math.round(Math.hypot(x1-x2,y1-y2))}} mm hole to hole)</li></ul>`;
  document.querySelector(`tr[data-wire="${{i}}"]`)?.classList.add("on");
}}
function selectNet(n) {{
  clearHL(); svg.classList.add("dimmed"); showNet(n);
  const strips = Object.keys(D.group_net).filter(k=>D.group_net[k]===n);
  const pins = (D.nets[n]||[]).map(([r,p]) => {{ const h = partByRef[r].pins.find(([pp])=>pp===p)[1]; return `<li>${{H(r+"."+p)}} → ${{H(h)}}</li>`; }}).join("");
  const ws = (netWires[n]||[]).map(i => `<li>wire ${{i+1}}: ${{H(D.wires[i].a)}} → ${{H(D.wires[i].b)}} <span class="mut">${{D.wires[i].colour}}</span></li>`).join("");
  detail.innerHTML = `<h2>${{N(n)}}${{alias(n)!==n?` <span class="mut">(${{n}})</span>`:""}}</h2><p class="sub">${{D.net_desc[alias(n)]||""}}</p>
    <p class="mut" style="margin:0 0 8px">on strips ${{strips.map(H).join(" ")}}</p><ul>${{pins}}${{ws}}</ul>`;
  document.querySelector(`tr[data-net="${{n}}"]`)?.classList.add("on");
}}
function selectHole(h) {{
  const n = netOfHole(h); const pins = holePins[h]||[]; const k = parse(h).key;
  clearHL(); if (stripHL[k]) stripHL[k].classList.add("on"); if (pinHL[h]) pinHL[h].classList.add("on");
  if (n) {{ svg.classList.add("dimmed"); showNet(n, {{noParts:true}}); }}
  const w = D.wires.map((w,i)=>[w,i]).filter(([w])=>w.a===h||w.b===h);
  detail.innerHTML = `<h2>Hole ${{h}}</h2><p class="sub">${{stripName(h)}} — ${{n?"carries ":"no net on this strip"}}${{n?N(n):""}}</p><ul>` +
    (pins.map(q=>`<li>${{H(q.ref+" pin "+q.pin)}} sits here</li>`).join("")) + (w.map(([w,i])=>`<li>wire ${{i+1}} (${{w.colour}}) to ${{H(w.a===h?w.b:w.a)}}</li>`).join("")) +
    (n ? `<li><span class="mut">same net: ${{netMembers(n)}}</span></li>` : "") + `</ul>` + (!pins.length && !w.length && !n ? `<p class="empty">empty hole</p>` : "");
}}
const dispatch = t => t.type==="part" ? selectPart(t.id) : t.type==="wire" ? selectWire(t.id) : t.type==="net" ? selectNet(t.id) : selectHole(t.id);
function target(e) {{
  const p = e.target.closest?.(".part"); if (p) return {{type:"part", id:p.dataset.ref}};
  const w = e.target.closest?.(".wire"); if (w) return {{type:"wire", id:+w.dataset.wire}};
  const h = e.target.closest?.(".hit"); if (h) return {{type:"hole", id:h.dataset.hole}};
  return null;
}}
svg.addEventListener("mousemove", e => {{ if (locked) return; const t = target(e); if (t) dispatch(t); }});
svg.addEventListener("click", e => {{ const t = target(e); if (!t) return; locked = t; dispatch(t); }});
svg.addEventListener("mouseleave", () => {{ if (!locked) clearHL(); }});
function release() {{ locked = null; clearHL(); detail.innerHTML = `<h2>Nothing selected</h2><p class="sub">Hover the board or a table row. Click to keep a selection; <kbd>Esc</kbd> or Clear releases it.</p>`; }}
document.getElementById("clear").onclick = release;
document.addEventListener("keydown", e => {{ if (e.key==="Escape") release(); }});

// ---------- tables ----------
let done = {{}}; try {{ done = JSON.parse(localStorage.getItem("bb-done")||"{{}}"); }} catch (_) {{ done = {{}}; }}
function saveDone() {{ try {{ localStorage.setItem("bb-done", JSON.stringify(done)); }} catch (_) {{}} updateProgress(); }}
function updateProgress() {{ const total = D.parts.length + D.wires.length; const n = Object.values(done).filter(Boolean).length; document.getElementById("progress").textContent = `${{n}} / ${{total}} built`; }}
function row(tb, attrs, cells, key) {{
  const tr = document.createElement("tr"); for (const k in attrs) tr.dataset[k] = attrs[k]; tr.tabIndex = 0;
  if (key) {{ const td = document.createElement("td"); const cb = document.createElement("input"); cb.type="checkbox"; cb.checked = !!done[key]; cb.setAttribute("aria-label","built");
    cb.onchange = () => {{ done[key] = cb.checked; tr.classList.toggle("done", cb.checked); saveDone(); }}; cb.onclick = e => e.stopPropagation(); td.appendChild(cb); tr.appendChild(td); if (done[key]) tr.classList.add("done"); }}
  cells.forEach(c => {{ const td = document.createElement("td"); td.innerHTML = c; tr.appendChild(td); }});
  tb.appendChild(tr); return tr;
}}
const tp = document.getElementById("parts");
D.parts.forEach(p => {{ const tr = row(tp, {{ref:p.ref}}, [`<b>${{p.ref}}</b>`, `${{p.value}}<br><span class="mut">${{D.kind[p.kind]||p.kind}}</span>`, p.pins.map(([pin,h])=>`${{pin}}→${{H(h)}}`).join("<br>"), `<span class="mut">${{p.note}}</span>`], "p:"+p.ref);
  tr.onmouseenter = () => {{ if (!locked) selectPart(p.ref); }}; tr.onclick = () => {{ locked = {{type:"part",id:p.ref}}; selectPart(p.ref); }}; }});
const tw = document.getElementById("wires");
D.wires.forEach((w,i) => {{ const [x1,y1]=xy(w.a),[x2,y2]=xy(w.b);
  const tr = row(tw, {{wire:i}}, [`${{i+1}}`, H(w.a), H(w.b), `<span class="sw" style="background:${{COL[w.colour]}}"></span>${{w.colour}}`, `${{Math.round(Math.hypot(x1-x2,y1-y2)+12)}} mm`, w.why], "w:"+i);
  tr.onmouseenter = () => {{ if (!locked) selectWire(i); }}; tr.onclick = () => {{ locked = {{type:"wire",id:i}}; selectWire(i); }}; }});
const tn = document.getElementById("nets");
Object.keys(D.nets).sort((a,b)=>alias(a).localeCompare(alias(b))).forEach(n => {{
  const strips = Object.keys(D.group_net).filter(k=>D.group_net[k]===n);
  const tr = row(tn, {{net:n}}, [N(n)+(alias(n)!==n?`<br><span class="mut">${{n}}</span>`:""), `<span class="mut">${{D.net_desc[alias(n)]||""}}</span>`, strips.map(H).join(" "), D.nets[n].map(([r,p])=>`${{r}}.${{p}}`).join(", ")]);
  tr.onmouseenter = () => {{ if (!locked) selectNet(n); }}; tr.onclick = () => {{ locked = {{type:"net",id:n}}; selectNet(n); }}; }});
document.getElementById("steps").innerHTML = D.steps.map(([t,d]) => `<li><div><b>${{t}}</b>${{d}}</div></li>`).join("");
updateProgress();
const fitAside = () => {{ document.querySelector("aside").style.top = (document.querySelector(".boardwrap").offsetHeight + 12) + "px"; }}; fitAside(); window.addEventListener("resize", fitAside);
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {{
  document.querySelectorAll(".tabs button").forEach(x=>x.setAttribute("aria-selected", x===b)); document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("on", t.id==="tab-"+b.dataset.tab)); }});

// ---------- zoom + find ----------
let zoom = 1.9; const applyZoom = () => {{ svg.style.width = (850*zoom) + "px"; }}; applyZoom();
document.getElementById("zin").onclick = () => {{ zoom = Math.min(4, zoom*1.25); applyZoom(); fitAside(); }};
document.getElementById("zout").onclick = () => {{ zoom = Math.max(1, zoom/1.25); applyZoom(); fitAside(); }};
const scroller = document.querySelector(".scroller");
function scrollTo(h) {{ const [x] = xy(h); scroller.scrollTo({{left: x*S*zoom - scroller.clientWidth/2, behavior:"smooth"}}); }}
document.getElementById("find").addEventListener("input", e => {{
  const q = e.target.value.trim(); if (!q) {{ release(); return; }}
  const up = q.toUpperCase();
  if (partByRef[up]) {{ locked = {{type:"part",id:up}}; selectPart(up); scrollTo(partByRef[up].pins[0][1]); return; }}
  const net = Object.keys(D.nets).find(n => n.toUpperCase()===up || alias(n).toUpperCase()===up);
  if (net) {{ locked = {{type:"net",id:net}}; selectNet(net); return; }}
  const lo = q.toLowerCase(); if (/^[a-j]\\d{{1,2}}$/.test(lo) || /^(tr\\+|tr-|br\\+|br-)@\\d+$/.test(lo)) {{ const h = lo.replace(/^(tr|br)/, s=>s.toUpperCase()); locked = {{type:"hole",id:h}}; selectHole(h); scrollTo(h); }}
}});
</script>
""" + "<script>" + MOD_JS + "</script>\n"
    (HERE / "breadboard.html").write_text(html)
    modules_md()
    print("wrote breadboard.html", len(html), "bytes")


if __name__ == "__main__":
    build()
