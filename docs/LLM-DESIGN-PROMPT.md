# Design-prompt pack — horn-fed FMCW radar + phone-flown ESP-FLY

A set of prompts to hand to an LLM (or a design partner) to produce the
detailed engineering for this project. Every number below is fixed by the
work already done in this repo; the prompts ask the model to design *to*
them, not to re-derive or "improve" them.

**How to use.** Paste **§0 (shared context)** first, then one of the task
prompts §1–§5. Each task prompt is independent and ends with the deliverable
format it expects. Run §5 (band plan) and §1 (schematic) before §2 (PCB);
run §3 (antenna tests) any time after the horn geometry is accepted.

---

## §0 · Shared context — paste this before every task prompt

```text
You are the RF / systems engineer for a hobby-scale but rigorous project:
an MIT RES.LL-003 "coffee-can" FMCW radar rebuilt with custom pyramidal
horns, tracking a 25 g quadcopter (Seeed ESP-FLY: XIAO ESP32-S3, ESP-Drone
firmware, flown from a phone over the drone's own WiFi access point) at
3-10 m indoors. Range + Doppler first, azimuth by mechanically scanning the
horn pair, elevation later from a second stacked receive horn.

FIXED DECISIONS (design to these; do not reopen them):
- Radar architecture, in MIT's signal order:
    sweep generator -> 3 dB attenuator -> PA -> 2-way splitter
      -> (TX horn) and (mixer LO);
    RX horn -> LNA -> mixer RF; mixer IF -> video amp -> sound card.
- Sweep generator: ADF4351 PLL board (25 MHz TCXO) stepped over SPI by an
  ESP32, NOT an analog VCO (the MIT ZX95-2536C+ is non-catalog).
  64 steps x 100 us = 6.4 ms up-chirp, 1 ms retrace -> PRI 7.4 ms.
- Band: the drone's WiFi AP is on 802.11 channel 1 (2401-2423 MHz).
  Radar sweep 2440.0 -> 2483.5 MHz (43.5 MHz). The sweep never leaves
  2400-2483.5 MHz (US ISM). 2360-2395 MHz is NOT usable (AMT/medical).
- Parts on hand / chosen: Mini-Circuits ZX05-43MH-S+ mixer (level 13),
  2x SPF5189Z LNA modules (PA role and LNA role), 800-2500 MHz 2-way SMA
  splitter, SMA 3 dB attenuator, Behringer UCA202 USB sound card
  (44.1 kHz, 16-bit, L = beat, R = sync), ESP32-WROOM-32 devkit,
  TL072 video amp on 12 V, NEMA-17 + A4988 turntable, 12 V 3 A supply
  with LM2596 5 V buck.
- Design levels at 2.44 GHz: ADF4351 +5 dBm -> att +2 -> PA +14 ->
  splitter +10.5 dBm to TX horn and +10.5 dBm to LO. TX horn 13.4 dBi
  -> +23 dBm EIRP. Drone RCS assumed 0.01 m^2 -> echo -74 dBm at 10 m
  at the RX horn, SNR 71 dB after 64-chirp integration. Beat frequency
  f_b = 2*B*R/(c*T_up) = 401 Hz at 10 m; IF band of interest 0-2.6 kHz;
  TX->RX leakage appears as a ~26 Hz tone ~40 dB above the drone echo.
- Horn (per horn, three built): optimum pyramidal horn on a WR-340 guide.
  Aperture 263.8 x 193.1 mm, throat 86.4 x 43.2 mm, flare 91.5 mm axial,
  guide section 115 mm, SMA probe through the broad wall 43.7 mm from
  the shorted back wall, probe 28 mm long. Predicted: 13.4 dBi, -3 dB
  beamwidths 34 deg (E) x 36 deg (H), pe == ph satisfied, 51 % aperture
  efficiency. 0.021" copper, soldered seams. TX and RX horns 290 mm
  centre-to-centre, E-plane (193 mm side) vertical on both.
- Scanning: 12 deg beam steps over ~100 deg, 64 chirps per dwell (0.47 s),
  amplitude-weighted centroid across beams -> 2.5 deg azimuth RMS.
  Stage 3: second RX horn 193 mm directly below the first (1.57 lambda,
  unambiguous +/-18.5 deg), second LNA + mixer + video channel, 4-input
  audio interface on one clock (Behringer UMC404HD).
- Drone: stock ESP-FLY hardware. ESP-Drone firmware rebuilt with
  CONFIG_WIFI_CHANNEL=1. The RadioMaster RP1 V2 (ELRS 2.4 GHz) receiver
  is REMOVED so no FHSS link hops through the sweep. No 5 GHz, no
  Bluetooth, no 915 MHz unless the coexistence test fails.
- Interference budget at the drone's receiver, 5 m, beam on it: radar
  -31 dBm raw, ~ -55 dBm after adjacent-channel rejection; phone signal
  ~ -35 dBm; SIR ~ 20 dB (802.11 needs 5-10 dB).
- Interference INTO the radar: the drone's AP (+20 dBm, always in the
  beam) reaches the LNA at -21 dBm at 5 m and the mixer at -9 dBm --
  ~8 dB from compression with WiFi peaks. Mitigations that are part of
  the design: drone AP power set to +8 dBm in firmware; a 2400-2500 MHz
  band-pass filter between RX horn and LNA (the horn and the SPF5189Z
  are wideband); the operator with the phone stands behind the horns.
- Processing on the laptop (Python, exists): sync-edge segmentation ->
  per-chirp range FFT (3.45 m cells, parabolic peak interpolation) ->
  Doppler FFT across chirps (axis from the measured PRI, +/-4.2 m/s) ->
  CA-CFAR (linear power, guard 4, train 6, 15 dB, peak-picked) ->
  beam centroid -> Kalman tracker -> web console.

HARD CONSTRAINTS:
- Never propose a sweep outside 2400-2483.5 MHz or overlapping 2401-2423.
- Never propose moving the phone link to 5 GHz/Bluetooth (the S3 cannot)
  or to the T8L radio (2.4 GHz only, no module bay).
- Keep every RF path 50 ohm; SMA everywhere; no bias-tee assumptions
  (the SPF5189Z and ADF4351 boards have their own 5 V pins).
- State every assumption you add, and mark which numbers are computed
  versus assumed. Where a value depends on a datasheet figure at
  2.4 GHz (SPF5189Z gain, mixer conversion loss), quote the figure and
  its source line.
- Prefer parts in stock at Mini-Circuits, Mouser, Digi-Key, LCSC, or Amazon
  in September 2026; say so per part.
```

---

## §1 · Task prompt — system design and full circuit diagram

```text
TASK: Produce the complete electrical design of the radar as built from
the coax modules in §0, ready for a person to wire on a plywood board and
a breadboard, and produce the circuit diagram.

Deliver, in this order:

1. BLOCK DIAGRAM with every signal level (dBm) at every port at 2.44 GHz,
   in MIT order. Include the ESP32's three control lines (SPI to the
   ADF4351, SYNC to the sound card's right channel, STEP/DIR/EN to the
   A4988). Show the two horns and the drone as the RF "load".

2. SCHEMATIC (text form, KiCad-importable if you can: a netlist or a
   KiCad 8 .kicad_sch S-expression; otherwise an unambiguous ASCII
   schematic per sheet) with these sheets:
   a. RF chain: SMA-to-SMA interconnects between modules, including
      the 2400-2500 MHz band-pass filter between the RX horn and the
      LNA, module DC
      feeds (5 V, 100 nF + 10 uF at each module), the 3 dB pad, the
      splitter, the mixer's LO/RF/IF ports labeled.
   b. Video amplifier: TL072 on a single 12 V rail with a 6 V mid-rail
      bias. Stage A non-inverting gain 101 with an input high-pass at
      160 Hz (100 nF / 10 k); stage B gain 11 with a second 160 Hz
      high-pass; then a 15.9 kHz RC low-pass (1 k / 10 nF) and a 10 uF
      AC-coupled output into the sound card's left channel. Justify each
      corner: the two high-passes are there to keep the ~26 Hz leakage
      tone from saturating the gain; the low-pass is anti-alias for
      44.1 kHz. State the leakage and drone-echo amplitudes at the
      output (targets: ~200 mV and ~20 mV) and show neither clips a
      line input.
   c. Sync: ESP32 GPIO25 -> 10 k series -> sound card right tip, 1 k to
      ground (0.3 V square wave, high during the up-chirp).
   d. Control: ESP32 devkit pinout (SCK 18, MOSI 23, LE 5, LD 19,
      SYNC 25, STEP 26, DIR 27, EN 14), A4988 with VMOT 12 V, 1/16
      microstep straps, VREF for ~0.8 A, 100 uF at VMOT.
   e. Power tree: 12 V 3 A input -> LM2596 5.0 V (ADF4351 board, both
      SPF5189Z modules, ESP32 VIN) ; 12 V direct to TL072 and A4988;
      star ground at a terminal block; note the stepper's wires must be
      routed away from the IF/breadboard side.

3. BILL OF MATERIALS for the schematic, with one vendor and stock status
   per line, and a total.

4. BRING-UP CHECKLIST in order, with an expected measurement at each
   step (e.g. "5.00 V on the SPF5189Z pin", "LO drive +10.5 +/-2 dBm",
   "leakage tone with a strong ~135 Hz component on the left channel").
   The first end-to-end test is the MIT one: walk toward the horns from
   5 m and see range decrease with negative velocity.

5. A list of every place your design deviates from the MIT RES.LL-003
   schematic and why (e.g. PLL instead of VCO+XR-2206, TL072 instead of
   LT1214, stepped sweep).

Do not design a PCB here; that is a separate task. Do not change any
fixed decision in §0.
```

---

## §2 · Task prompt — PCB design for the MIT-architecture radar (v2)

```text
TASK: Design a single printed circuit board that replaces the coax-module
build of §1 with an integrated "MIT radar on a board", keeping the same
architecture, levels and band. This is the v2 board built only after the
coax v1 has been proven (v1 is the reference; the PCB must match its
measured performance, not exceed it on paper).

Requirements:

ARCHITECTURE (unchanged): ADF4351 -> pad -> PA -> Wilkinson splitter ->
{TX SMA, mixer LO}; RX SMA -> LNA -> mixer RF; IF -> video amp -> audio
out. ESP32 module on board for sweep, sync and stepper. External: the
two horns (SMA), the sound card (3.5 mm or RCA), 12 V in, USB.

PART SELECTION (propose, with datasheet figures at 2.44 GHz and stock):
- Synthesiser: ADF4351 chip with a 25 MHz TCXO, or justify keeping the
  bought ADF4351 board as a daughterboard on pin headers.
- PA and LNA: SPF5189Z bare parts (Qorvo) with their reference matching
  networks, or an equivalent in stock; state gain, NF, P1dB at 2.44 GHz.
- Mixer: a surface-mount double-balanced mixer covering 2.4-2.5 GHz
  with LO drive matching the +10.5 dBm available (or add a driver and
  say so). If nothing SMT is available with adequate stock, keep the
  ZX05-43MH-S+ as a bolt-on and design the board around three SMA
  jumpers to it; say which you chose and why.
- Splitter: printed Wilkinson at 2.44 GHz on the chosen stackup, with
  the isolation resistor value and the quarter-wave line dimensions.
- Video amp: as in §1 (TL072 or a rail-to-rail equivalent), single
  12 V rail, same corners.
- ESP32-WROOM-32E module (or -S3), USB-UART, 3.3 V LDO, A4988 socket.

STACKUP AND RF LAYOUT:
- 4-layer FR-4 (or 2-layer with a stated controlled-impedance core if
  you argue it is adequate at 2.44 GHz); give the stackup, dielectric
  (Er, thickness), and the 50 ohm CPWG or microstrip width/gap for it.
- Via fencing along RF traces, ground stitching pitch, keep-outs.
- Partition: RF (TX side / RX side separated, LO isolation), baseband
  (video amp far from the PA and the stepper driver), digital (ESP32,
  USB) with a single ground plane and a stated star point.
- SMA edge-launch footprints for TX, RX; test points or 0 ohm links at
  every RF stage so each block can be measured alone (LO drive, PA out,
  LNA in/out, IF).
- DC: per-module 100 nF + 10 uF, ferrite on each 5 V RF feed, LM2596 or
  an equivalent buck with its inductor away from the RF section.
- ESD and reverse-polarity protection on 12 V in.

DELIVERABLES:
1. Schematic per sheet (KiCad 8 S-expression preferred; else netlist +
   ASCII), BOM with LCSC/Mouser part numbers and stock.
2. Layout plan: board outline (target <= 100 x 80 mm), placement
   drawing, layer assignments, RF trace routing description, DRC rules
   (min trace/space, via size, annular ring, solder mask expansion for
   the RF pads).
3. A test-point list mapping every §1 bring-up measurement to a TP name.
4. A comparison table: v1 coax build vs v2 PCB for cost, size, expected
   gain/loss per stage, expected TX-RX isolation, and the risks the PCB
   adds (matching network tolerance, Wilkinson resistor placement, LO
   leakage through the plane).
5. A one-page "what must be equal to v1" acceptance list: LO drive
   within 1 dB, PA out within 1 dB, LNA gain within 1 dB, leakage tone
   level within 3 dB, walking-person test identical.

Do not add features (no on-board ADC replacing the sound card, no second
receive channel) in this revision. Stage 3 (second RX channel) is a
later board.
```

---

## §3 · Task prompt — horn antenna test and acceptance requirements

```text
TASK: Write the verification and acceptance test plan for the three
hand-built pyramidal horns in §0, using hobby-grade instruments: a
NanoVNA (or LibreVNA), an RTL-SDR or the radar's own receive chain as a
power detector, a tape measure, a turntable, and optionally an openEMS
or HFSS model for correlation. The plan must let a builder decide
PASS / FAIL for each horn and diagnose the common failures.

Cover, with numeric acceptance limits and the procedure to measure each:

1. MECHANICAL INSPECTION
   - Aperture 263.8 x 193.1 mm (+/- 2 mm), throat 86.4 x 43.2 mm
     (+/- 0.5 mm), flare axial length 91.5 mm (+/- 1 mm), guide 115 mm,
     probe centred on the broad wall at 43.7 mm (+/- 0.5 mm) from the
     back wall, probe length 28 mm (+/- 0.5 mm), perpendicular to the
     wall.
   - Seam continuity: < 0.5 ohm between any two panels at both ends;
     visual: no gaps > 0.2 mm on any seam (why: a slot radiates).
   - Flatness / squareness of the mouth: diagonals equal within 2 mm.

2. RETURN LOSS (S11), NanoVNA at the SMA
   - Acceptance: S11 <= -10 dB over 2400-2483.5 MHz; note the
     minimum and its frequency. Target from the design: better than
     -15 dB at 2440-2483.5.
   - Procedure: calibrate at the cable end (SOL), horn pointed at open
     space > 2 m from any object, sweep 2.2-2.7 GHz, 201 points.
   - Diagnosis table: resonance too low/high -> probe length; broad
     mismatch -> probe position or a leaking seam; ripple -> reflection
     from nearby objects.
   - Probe tuning procedure: trim in 0.5 mm steps, re-measure, stop at
     the minimum S11 across the sweep band (not at one frequency).

3. TX-RX ISOLATION, the pair at 290 mm centre-to-centre, same
   polarisation, NanoVNA S21
   - Acceptance: S21 <= -35 dB across the sweep band (the radar's
     leakage budget in §0 assumes 35 dB). Record the value; it sets the
     leakage tone level.
   - Improvement steps if it fails: foil septum between the guide
     sections, absorber behind, re-check seams on the facing walls.

4. GAIN (two-antenna method with the two identical horns, Friis)
   - Acceptance: 13.4 dBi +/- 1.5 dB at 2440 and 2480 MHz.
   - Procedure: horns boresighted at d >= 2*D^2/lambda = 1.13 m (use
     3 m), measure S21 with the NanoVNA, compute G = (S21_dB - FSPL)/2
     with FSPL at each frequency; state the far-field justification and
     the reflection-free zone needed (Fresnel radius at 3 m).
   - Three-antenna method with the third horn to bound the error.

5. RADIATION PATTERN (E- and H-plane cuts on the turntable)
   - Acceptance: -3 dB beamwidth 34 +/- 4 deg (E), 36 +/- 4 deg (H);
     first sidelobe <= -12 dB; pattern symmetric within 2 deg (asymmetry
     -> probe off-centre or a seam gap).
   - Procedure: the radar's own turntable steps the horn under test in
     5 deg increments (2 deg near boresight) against a fixed illuminating
     horn 3 m away, receive power read as S21 or with the RTL-SDR; two
     cuts (rotate the horn 90 deg for the second plane).
   - Cross-polarisation at boresight: <= -20 dB (rotate the fixed horn
     90 deg).

6. LEAKAGE / SEAM RADIATION
   - Probe the outside of every seam with a small loop on the NanoVNA
     port 2 (or the RTL-SDR) while port 1 drives the horn: any seam
     reading within 20 dB of the aperture level fails.

7. CORRELATION TO SIMULATION (if a model exists)
   - Compare measured S11, gain, beamwidths to the openEMS/HFSS results
     from antenna.md's five-study methodology; acceptance: gain within
     1.5 dB, beamwidths within 4 deg, S11 minimum within 40 MHz.

8. STACKED-PAIR CHECK for stage 3 (two RX horns 193 mm vertical
   spacing, mouths touching)
   - Mutual coupling S21 <= -20 dB; boresight phase difference between
     the two channels measured against a target at 0 deg elevation
     (this is the fixed phase offset the software calibrates out);
     verify the phase slope sign by raising the target 0.5 m at 5 m.

Format: one section per test with Purpose / Setup / Procedure /
Acceptance / If it fails. End with a one-page acceptance sheet (table:
test, limit, horn 1, horn 2, horn 3, PASS/FAIL) to print and fill in.
Note which tests are needed before stage 1 (2, 3), before stage 2 (4, 5),
and before stage 3 (8).
```

---

## §4 · Task prompt — the drone build (phone-flown ESP-FLY as a radar target)

```text
TASK: Specify the drone side of the system: a stock Seeed ESP-FLY
(XIAO ESP32-S3, 25 g) flown from a phone, prepared as a non-cooperative
target for the radar. The drone runs nothing from this project; the work
is configuration, removal, and flight-envelope definition.

Deliver:

1. BUILD STATE
   - Stock ESP-FLY hardware. List what stays (XIAO ESP32-S3, FC board,
     IMU, 4 coreless motors, 1S battery, frame) and what is REMOVED:
     the RadioMaster RP1 V2 ELRS 2.4 GHz receiver and its antenna
     (reason: a bound ELRS link hops across 2400-2480 MHz, straight
     through the radar sweep, at 25-100 mW). Weight before/after.
   - Firmware: ESP-Drone (Seeed Co-Create_ESP-FLY fork) rebuilt with
     CONFIG_WIFI_CHANNEL=1 (default is 6, which sits inside the sweep).
     Give the menuconfig path, the sdkconfig line, and the flash
     command. Give the AP name/password settings and the app's default
     endpoint (192.168.43.42, UDP 2390) and how to verify the channel
     with a WiFi analyser app.
   - Explicitly: no 5 GHz (the S3 cannot), no Bluetooth control, no
     T8L, no 915 MHz unless the coexistence test in item 4 fails.

2. RADAR-TARGET CONSIDERATIONS
   - The link budget assumes RCS 0.01 m^2 with 71 dB SNR margin at
     10 m; state whether any change is warranted (it is not) and what
     the optional 30 mm copper-tape patch would do to RCS and weight.
   - Zero-Doppler behaviour: a perfectly stationary target is removed
     with the clutter; explain why a hovering quad is still seen (rotor
     micro-Doppler +/- ~1 kHz, body jitter) and what flight behaviour
     makes detection most reliable during first tests (slow drift
     0.3-1 m/s, not a locked hover).
   - Doppler window +/-4.2 m/s at PRI 7.4 ms: define the speed limit for
     tracked flight and what happens above it (velocity aliases; range
     does not).

3. FLIGHT ENVELOPE relative to the radar
   - Beams 34 x 36 deg; scan sector ~100 deg at 12 deg steps; horns at
     ~1.0 m height. Define the box: 3-10 m from the horns, horn height
     +/- 1.5 m, inside the sector minus one beam step each side (the
     centroid biases inward at the edges). Floor marks at 3, 5, 8 m on
     boresight and tape at the sector edges.
   - Where the operator stands (behind the horns: a person is a 0.5 m^2
     target 50x the drone).

4. COEXISTENCE TEST (the decision test)
   - Drone on the bench 1 m in front of the horns, in the beam, props
     off, phone connected. Ping the drone (100 pings at 100 ms) with:
     radar SWEEP 0; radar SWEEP 1 on 2440-2483.5; radar deliberately
     on 2400-2483.5 (crossing channel 1). Acceptance: ~0 % loss and
     unchanged RTT in the second case; visible loss in the third case
     proves the margin is real. Escalation: sweep from 2450 (33.5 MHz,
     4.5 m cell); then, only if still failing, the 915 MHz ELRS
     fallback (RadioMaster Pocket + Bandit Nano + Nano 915 RX, esp-fc
     with CRSF).

5. SAFETY
   - Indoor, props guarded, netted area for first radar-tracked flights;
     phone link failsafe behaviour of ESP-Drone on link loss (state what
     the firmware does and the test to confirm it); LiPo handling; the
     radar's +23 dBm EIRP is below Part 15 limits but keep the mouths
     away from people at < 1 m.

Format: numbered checklist with a checkpoint (an observable) after each
group, plus a one-page "before every session" card.
```

---

## §5 · Task prompt — signal and bandwidth layout (band plan, timing, link budget)

```text
TASK: Produce the definitive signal plan for the system: every emitter,
every band, every time constant, and the budgets that prove they
coexist. This document is the reference that §1-§4 must agree with.

Deliver:

1. SPECTRUM MAP of 2400-2483.5 MHz, to scale (ASCII or SVG), showing:
   WiFi channel 1 (2401-2423, centre 2412) = phone <-> drone AP;
   guard 2423-2440; radar sweep 2440.0-2483.5 (43.5 MHz, 64 steps of
   0.690 MHz); ESP-Drone's default channel 6 (2426-2448) marked as the
   collision to avoid; ELRS 2.4 GHz FHSS 2400-2480 marked as removed;
   the ISM edges; the unusable 2360-2395 MHz below the band.
   Alternative plan for channel 11 (2451-2473) with the sweep below
   (2400-2440) and why channel 1 is preferred (3.5 MHz more sweep).

2. RADAR WAVEFORM TABLE: f_start, f_stop, B, N_steps, step size,
   step dwell, T_up, retrace, PRI, chirps per dwell, dwell time, beams
   per scan, scan time; and the derived quantities with formulas:
   range cell c/2B (3.45 m), beat frequency vs range (401 Hz at 10 m;
   give the 1-30 m curve), IF band of interest, sound-card Nyquist and
   the anti-alias corner, max unambiguous range from the step size
   (c/2*delta_f), Doppler resolution and window (+/- lambda/(4*PRI) =
   4.2 m/s), micro-Doppler band of the rotors.

3. TIMING DIAGRAM (two chirps): frequency staircase, SYNC line high
   during the up-chirp, beat present during the up-chirp, PLL settle
   (first 5 % of each chirp dropped). State that T_up and PRI are
   measured from SYNC by the software and are different numbers.

4. RADAR LINK BUDGET, one row per stage: ADF4351 out, pad, PA, splitter
   (both arms), TX horn gain, EIRP, path loss to 3/5/10 m, RCS 0.01 m^2,
   return path, RX horn gain, LNA, mixer conversion loss, IF level,
   video amp gain, sound-card level; noise floor with NF 0.6 dB LNA in
   the 15 kHz video band; processing gain from 64 chirps and the
   range FFT; SNR at 3/5/10 m. Then the leakage row: 35 dB isolation
   -> leakage tone level at the IF and at the sound card after the two
   160 Hz high-passes, and the check that neither leakage nor the
   drone echo clips.

5. INTERFERENCE BUDGET, both directions:
   a. Radar into the drone's WiFi receiver at 3/5/10 m, beam on:
      raw level, adjacent-channel rejection assumed (16 dB at 20 MHz
      offset, 32 dB at 40 MHz, interpolated at the 28 MHz centre
      offset), resulting level vs the phone's -35 dBm, SIR, and the
      802.11 rate that survives (needs 5-10 dB). Include the fraction
      of time the beam is on the drone during a scan.
   b. Phone and AP into the radar receiver. The horn is wideband and
      the SPF5189Z is a 50-4000 MHz amplifier: compute the drone AP
      (+20 dBm, in beam, 3/5/10 m) and the phone (+15 dBm, in beam vs
      behind the horns at ~25 dB front-to-back) at the LNA input and at
      the mixer RF port, against SPF5189Z input P1dB (~+6 dBm) and the
      mixer's RF compression (~+9 dBm), including WiFi's ~10 dB
      peak-to-average. Show the margin with the AP at +20 dBm and at
      +8 dBm (the drone's AP power is turned down in firmware). Specify
      the 2400-2500 MHz band-pass filter between RX horn and LNA and
      state plainly what it does (out-of-ISM rejection) and does not
      (it cannot separate channel 1 from the sweep). Only then argue
      the linear case: channel-1 energy lands at 17-80 MHz IF, above
      the 15 kHz video filter.
   c. The failure case: sweep 2400-2483.5 crossing channel 1 ->
      in-channel radar level vs phone level, expected loss; this is
      the deliberate "see the loss appear" calibration in the
      coexistence test.

6. AUDIO / DIGITAL SIDE: sound card sample rate options (44.1 / 48 kHz)
   and what changes; sync divider levels; USB serial protocol timing
   between the laptop and the radar ESP32 (one AZ per beam, settle
   time); HTTP fix rate to the console (~1 per 1.5 s scan) and the
   10 Hz WebSocket state.

7. STAGE 3 ADDENDUM: second RX channel at 193 mm vertical spacing ->
   phase-to-elevation formula, unambiguous +/-18.5 deg vs the 17 deg
   half-beam, the fixed cable-phase calibration, and the 4-input
   audio interface requirement (single sample clock).

Format: tables with units and formulas beside every derived number;
mark each value COMPUTED, DATASHEET (with source), or ASSUMED. Finish
with a one-line consistency check against §0 (any number that differs
from §0 must be flagged, not silently changed).
```

---

## Appendix — where each fixed number comes from in this repo

| number | source |
|---|---|
| sweep, range cell, beat, Doppler window, link budget | `ground_station/fmcw_sim.py --f0 2.44 --sweep-bw 43.5 --chirp-ms 6.4 --gain 13.4 --budget` |
| horn geometry, gain, beamwidths, pe==ph | `antenna/horn.py` |
| 12° steps, 2.5° azimuth, centroid | `ground_station/scan_design.py`, `docs/scanning.md` |
| CFAR / centroid / PRI handling, self-test | `ground_station/radar_acquire.py --selftest --f0-mhz 2440 --bw-mhz 43.5` |
| interference budget, channel choice | `docs/drone-software.md` §0 |
| MIT chain order, video amp, sync, power | `docs/radar-hardware.md` |
| firmware protocol (`SET f0_mhz`, `AZ`, SYNC) | `firmware/radar_ctl/radar_ctl.ino` |
| parts and stock (Sept 2026) | `hardware/BOM.md` |
