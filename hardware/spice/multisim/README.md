# Multisim — importing the radar blocks

Multisim does not open a schematic from another tool, but it **does** take a
SPICE netlist two ways ([NI: Importing a SPICE Netlist](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA03q000000YG0ACAW&l=en-US)):

1. **Arbitrary SPICE Block** — a component you place on the sheet and paste a
   `.subckt` into; its pins become the block's terminals. This is the route
   used here: one block per test card, wired to Multisim's own sources and
   instruments.
2. Tools › Component Wizard — for single component models (not needed).

Every file in this directory is plain SPICE 3 (R, C, D, E incl. POLY, T, V,
X) — no B-sources, no ngspice syntax — and each has been run through ngspice
via the `_h_*.cir` harnesses to prove it parses and gives the test-card
numbers.

| file | subcircuit · pins | stands for |
|---|---|---|
| `opamp_tl072.sub` | `TL072X inp inn vcc vee out` | generic TL072 (Aol 100 dB, GBW 3 MHz, clamps 1.5 V inside the rails). Used by the two blocks below; in Multisim you can instead build the amp from library TL072CPs — see the KiCad sheet |
| `video_amp.sub` | `VIDEO_AMP if audio vana vref gnd` | test card 1 — the whole video amplifier, full gain (R4 1k, R7 10k) |
| `vref_bias.sub` | `VREF_BIAS vana vref gnd` | test card 2 |
| `power_in.sub` | `POWER_IN vin vprot vana gnd` | test card 3 |
| `sync_div.sub` | `SYNC_DIV gpio sync sc gnd` | test card 4, includes the sound card's coupling |
| `fmcw_beat.sub` | `FMCW_BEAT tx leak_en beat gnd` | test card 6 — delay lines, gated leakage, POLY multiplier (the mixer), the amp's filters |

## Placing a block

1. Place › Component › Group **Basic** › Family **BASIC_VIRTUAL** (older
   versions: **Misc**) › **ARBITRARY_SPICE_BLOCK**.
2. Double-click it › **Value** tab › paste the contents of the `.sub` file
   (for `video_amp.sub` and `vref_bias.sub` paste `opamp_tl072.sub` first,
   then the block — the `.include` line does not resolve inside Multisim, so
   delete it and paste the op-amp subcircuit above the block's `.subckt`).
3. Set the block's **pin names** to the `.subckt` pin list, in order.
4. Wire the external parts below to those pins.

## Per block: what to add outside, what to run, what you should read

### 1 · VIDEO_AMP
- **Outside:** `AC_VOLTAGE` V_IF → **50 Ω resistor** → `if`. `DC_POWER` 11.4 V → `vana`; `DC_POWER` 5.7 V → `vref` (or the VREF_BIAS block's output). 10 kΩ from `audio` to ground (sound-card load). Ground → `gnd`.
- **Run:** AC Analysis 1 Hz – 100 kHz, output `V(audio)`; Transient 40–60 ms with V_IF = **0.5 mVpk 1 kHz**.
- **Read:** 54.5 dB at 1 kHz, ~48.7 dB at 159 Hz (−6), ~50.7 dB at 15.9 kHz (−4). Transient: 0.5 mVpk → **~0.27 Vpk** at `audio`. 10 mVpk clips at ±4.2 V — that is the full-gain block; for the first-power-up gain edit `R4 am vref 4.7k` and `R7 bout bm 0.001` in the pasted text (then 10 mVpk → 107 mVpk).
- **Radar test:** two AC_VOLTAGE in series: 8 mVpk 12.5 Hz + 40 µVpk 417 Hz → Fourier on `audio`: ~27 mV at 12.5 Hz, ~19 mV at 417 Hz.

### 2 · VREF_BIAS
- **Outside:** `DC_POWER` 11.4 V → `vana`; 2.2 kΩ from `vref` to ground.
- **Run:** DC Operating Point; then AC/transient with 100 mVpk 150 kHz added to `vana`.
- **Read:** `vref` = **5.58–5.70 V** (5.58 with the generic op-amp's 100 Ω output; 5.70 with TL072CP), ripple < 1 µV.

### 3 · POWER_IN
- **Outside:** `DC_POWER` 12 V → `vin`; 60 Ω from `vprot` to ground (the buck's load), 1.1 kΩ from `vana` to ground (the op-amps).
- **Run:** DC OP; transient with 100 mVpk 150 kHz on `vin`; DC OP again with **−12 V**.
- **Read:** `vprot` **11.68 V**, `vana` **11.58 V**; ripple on `vana` ~4 mVpp; reversed: `vprot` ≈ −0.1 mV.

### 4 · SYNC_DIV
- **Outside:** `PULSE_VOLTAGE` 0 → 3.3 V, pulse width 6.4 ms, period 7.4 ms, 10 ns edges → `gpio`.
- **Run:** Transient 0–60 ms, probe `sync` and `sc`.
- **Read:** `sync` **283 mV** high / 0 low; `sc` **+201 mV** plateau that droops, **−100 mV** retrace pulse. (That is what the laptop sees; the software detects edges, not levels.)

### 5 · FMCW_BEAT — the radar
- **Outside:** `PIECEWISE_LINEAR_VOLTAGE` (0 V at 0, 1 V at 6.4 ms, repeat) → `VOLTAGE_CONTROLLED_SINE_WAVE` (0 V → 1 MHz, 1 V → 5 MHz, 1 Vpk) → `tx`. `DC_POWER` **0 V** → `leak_en` (1 V to switch the leakage path on).
- **Run:** Transient, TMAX **10 ns**, stop 12.8 ms. Fourier Analysis on `beat` over the **second chirp** (6.72–12.8 ms), Hanning.
- **Read:** peak at **≈ 415 Hz, ~3 mV**. Change T1's `TD=667n` to `333n` → 208 Hz; `1.33u` → 833 Hz. `leak_en` = 1 V: the 417 Hz line stays, the floor near DC rises — the reason the software subtracts chirp-to-chirp.
- Why it is scaled: the beat is `B × TD / T` and the carrier cancels. Real radar B = 40 MHz, TD = 66.7 ns at 10 m; here B = 4 MHz, TD = 667 ns — same 417 Hz, and Multisim can step at 10 ns instead of 20 ps.

## Not importable, by nature
Everything to the right of the mixer's IF port — ADF4351, SPF5189Z amplifiers, splitter, mixer at 2.44 GHz, the horns. No models exist at that frequency in Multisim; those stages are measured on the bench (`docs/radar-hardware.md` checkpoints 7–8).

## Reproduce the reference numbers
```
cd hardware/spice/multisim
ngspice -b _h_video.cir   # etc. — the harnesses wrap each .sub with the same sources listed above
```
