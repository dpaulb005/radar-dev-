# Testing — how you know each part works

Every test in the project, in the order you will actually run them. Each one
names the tool, the stimulus, and the number that means PASS. Nothing here
needs the whole system working: the software is tested with no hardware, the
circuits before any RF exists, the RF chain before the horns are mounted,
the drone before the radar sweeps.

| stage | what is under test | tool | where the procedure lives |
|---|---|---|---|
| 0 | the signal processing | `radar_acquire.py --selftest` | §1 |
| 1 | the breadboard circuits | ngspice / Multisim, then a scope | §2 |
| 2 | the horns | a VNA **reaching 2.5 GHz** | §3 |
| 3 | the RF chain | power meter or SDR + pad, the leakage tone | §4 |
| 4 | the radar end to end | walking-person test, tape measure | §5 |
| 5 | drone ↔ radar coexistence | ping on the phone with the sweep on | §6 |
| 6 | tracking | console, floor marks | §7 |

---

## §1 · Software, no hardware (10 minutes)

```bash
cd ground_station && pip install -r requirements.txt
python radar_acquire.py --selftest                                   # scanning, 8 m at 15°
python radar_acquire.py --selftest --f0-mhz 2440 --bw-mhz 40 --st-range 5 --st-az -30 --st-vel -2
python radar_acquire.py --selftest --st-range-only --st-range 6 --st-vel 1.5   # stage-1 path
python radar_twin.py --track 20                                      # 0.09 m RMS
```

PASS: `SELFTEST PASS` on each; the twin's RMS track error ≤ 0.15 m. The
self-test synthesises exactly what the sound card records — single-ended beat,
AC-coupled sync with droop, TX leakage, noise, the horn beam pattern — and
runs it through the live code path. If it fails after you touch the DSP, the
hardware is not the problem.

## §2 · Breadboard circuits — simulate, then measure

**Simulate first.** `hardware/spice/README.md` has one test card per block
with part values, stimulus and expected readings; `hardware/spice/multisim/`
has the same blocks for Multisim: `multisim/import/*.cir` open straight
through **File ▸ Open ▸ SPICE netlist (*.cir)** and draw themselves as a
schematic; the `.sub` files are for pasting into an Arbitrary SPICE Block.
The ngspice decks in `hardware/spice/` itself do **not** import — they carry
`.control` blocks. See `hardware/spice/multisim/README.md`. The schematic with
every value on it is `hardware/kicad/radar_multisim.kicad_sch` (PNG beside it).

| block | stimulus | PASS |
|---|---|---|
| video amp, first-power-up gain (R4 4.7k, R7 link) | 10 mVpk 1 kHz through 50 Ω | 107 mVpk at the output; −6 dB at 159 Hz, −3 dB at 15.9 kHz |
| video amp, full gain | 8 mV @ 12.5 Hz + 40 µV @ 417 Hz | 27 mV leakage, 19 mV echo at the output — the 46 dB input ratio becomes 3 dB |
| half-rail reference | 100 mVpk 150 kHz on VANA | VREF 5.70 V, ripple < 1 µV |
| 12 V input | 200 mVpp 150 kHz; then −12 V | VANA 11.6 V, 4 mVpp; reversed: VPROT −0.1 mV |
| sync divider | 3.3 V pulse 6.4 / 7.4 ms | 283 mV at the divider; +201 / −100 mV after the card's coupling |
| IF input | AC sweep to 10 GHz | −58 dB at 2.44 GHz, −6 dB at 417 Hz |
| the radar, scaled | VCO 1→5 MHz over 6.4 ms, 667 ns delay | peak at 417 Hz at the beat output |

**Then measure** (`radar-hardware.md` checkpoints 4–6): 5.00 V on every module
pin; finger-touch hum at the amp input with the mixer disconnected; 1 kHz tone
in → the same 107 mV out; sync square wave on the right audio channel.

## §3 · Horns (before mounting)

### You do not need a VNA to build this

Say this plainly, because an earlier version of these docs implied otherwise.
A VNA that reaches 2.5 GHz is the most expensive item anywhere near this
project — a LiteVNA-64 is ~$165, a NanoVNA V2 Plus4 ~$150, and the common
$65 NanoVNA-H4 stops at 1.5 GHz and **cannot see this antenna at all**. None of
that is worth buying for one measurement.

You do not need it because the link has ~54 dB of margin at 10 m. A horn with a
poor 3:1 match loses 1.25 dB, and you have two of them, so a badly tuned pair
costs 2.5 dB out of 54. The horn dimensions come from closed-form optimum-horn
theory and are reliable if you cut to them; the VNA only confirms it.

**Build without one, and tune with the radar itself.** Once the chain is alive
(checkpoint 7), park the PLL with `CW 2460`, put a corner reflector at a fixed
range on boresight, and adjust the probe depth in 0.5 mm steps for maximum
detection SNR. That optimises the exact quantity you care about, which is more
than S11 tells you anyway. Do the two receive horns the same way and stop when
they read within 1 dB of each other.

**If you want the real measurement,** borrow rather than buy:

- the Penn State ECE teaching labs — any bench that runs the RF or microwave
  course has a VNA reaching well past 2.5 GHz; ask the lab manager or a TA,
- the Radar and Communications Lab or the Computational Electromagnetics and
  Antennas Research Lab, both of which live at 2.4 GHz and above,
- a local amateur radio club — LiteVNAs are common and members lend them.

Twenty minutes on a borrowed instrument covers every row below.

### With a VNA, if you get one

Horn at the SMA, pointed at open space.

| test | PASS |
|---|---|
| seams | < 0.5 Ω panel to panel; no visible gap — **an ohm-meter does this one, no VNA** |
| return loss | S11 ≤ −10 dB over 2400–2480 MHz (tune the 28 mm probe in 0.5 mm steps for the minimum) |
| TX–RX isolation, TX 290 mm above the RX row | S21 ≤ −35 dB |
| **RX A vs RX B match** | S11 curves within 2 dB of each other across the band — the two receive horns feed a phase comparison, so they want to be twins |
| gain, two-antenna method at 3 m | 13.4 ± 1.5 dBi |
| beamwidths (rotate the horn by hand against a protractor) | 34 ± 4° E, 36 ± 4° H; first sidelobe ≤ −12 dB |

Full procedure and the printable pass/fail sheet: `archive/LLM-DESIGN-PROMPT.md` §3.

## §4 · RF chain (horns on, `radar-hardware.md` checkpoint 7)

1. `?` on the radar ESP32 shows `lock:1`, `rf:0`. Nothing radiates yet.
2. `CW 2460` → +10.5 ± 2 dBm at the splitter's LO arm (power meter, or an
   RTL-SDR behind a 30 dB pad). PA out +14 ± 2 dBm.
3. `SWEEP 1` → **the leakage tone**: a low tone with a strong ~135 Hz
   component on the left audio channel. It proves VCO, PA, splitter, LO
   drive, LNA, mixer and video amp in one shot. No tone: work backwards.

## §5 · The radar end to end (`radar-software.md` §4)

```bash
python radar_acquire.py --device N --ctl /dev/ttyUSB0 --range-only --record first-walk.wav
```

Walk toward the horns from 5 m: `range` counts down, `vel` negative and about
your speed; walk away: positive; stand still: you vanish. PASS: at 3, 5 and
8 m (tape measure, sway gently) the printed range is within 0.4 m; the
reported `t_chirp_ms` matches the ESP32's within 1 %.

Then scanning (`--ctl` without `--range-only`, `--server http://localhost:8080`):
stand at three marked spots across the sector; the console's X/Y agree within
~0.4 m cross-range at 8 m.

## §6 · Drone and radar on the same band (`drone-software.md` §4)

Drone on the bench 1 m in front of the horns, phone connected, props off,
100 pings at 100 ms:

| radar | PASS |
|---|---|
| `SWEEP 0` | ~0 % loss (baseline) |
| `SWEEP 1`, 2440–2480 | **~0 % loss, RTT unchanged** |
| `SET f0_mhz 2400`, full band (crosses channel 1) | loss appears — proves the margin is real |
| drone AP on/off, phone streaming | radar noise floor and CFAR threshold do not move |

Fail → confirm the AP is at 10 dBm, then the band-pass filter, then `SET f0_mhz 2450`,
then the 915 MHz fallback (`archive/drone-915.md`).

## §7 · Tracking (`drone-hardware.md` §4)

Floor marks at 3, 5, 8 m on boresight and tape at the sector edges. Hover
at each mark: console range within 0.4 m, azimuth within 3°. A 2-minute
hover with a continuous track and no phone-link glitches is the end state.
