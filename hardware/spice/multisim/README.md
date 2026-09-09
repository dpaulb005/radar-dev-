# Multisim — opening the radar blocks

Multisim cannot open a KiCad schematic, but it takes SPICE two ways
([NI: Importing a SPICE Netlist](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA03q000000YG0ACAW&l=en-US)).
Pick by what you want on the sheet.

## Route A — File ▸ Open a netlist, get a drawn schematic  ← start here

`import/*.cir` are flat netlists written for this: **no `.control` block, no
B-sources, no `.include`, everything in one file.** The `.cir` files in
`hardware/spice/` (one level up) are *not* importable — they are ngspice decks
whose `.control` blocks and behavioural sources Multisim rejects. Use `import/`.

1. **File ▸ Open**, set the file-type dropdown to **SPICE netlist files
   (\*.cir)**, pick the file. Multisim converts the netlist into a drawn
   schematic; passives arrive as virtual parts.
2. Multisim ignores the `.ac` / `.tran` / `.op` lines at the bottom. Set the
   analysis yourself in **Simulate ▸ Analyses and Simulation** — each file's
   header comment says which analysis and what number to expect.
3. Probe with **Place ▸ Probe** or a virtual instrument, then **Run**.

| file | what it is | run | expect |
|---|---|---|---|
| `import/01_video_amp.cir` | the whole video amp, full gain, 0.5 mVpk 1 kHz in | AC 1 Hz–100 kHz; Transient 40–60 ms | **54.5 dB** at 1 kHz, 48.7 at 159 Hz, 50.6 at 15.9 kHz; **0.27 Vpk** at `audio` |
| `import/02_vref_bias.cir` | buffered half rail, 150 kHz ripple on VANA | DC Operating Point | `vdiv` **5.70 V**, `vref` **5.58 V** |
| `import/03_power_in.cir` | 12 V, D1, R15/C13 | DC OP; Transient 200–300 µs | `vprot` **11.68 V**, `vana` **11.58 V** |
| `import/04_power_reverse.cir` | −12 V applied | DC OP | `vprot` **−0.11 mV** |
| `import/05_sync_div.cir` | GPIO25 → 10k/1k → sound card | Transient 0–60 ms | `sync` **283 mV**, `sc` +274 mV falling to **−100 mV** on retrace |
| `import/06_if_input.cir` | 49.9 Ω + 1 nF at the mixer IF | AC 10 Hz–10 GHz | **−6.7 dB** at 417 Hz, **−57.7 dB** at 2.44 GHz |

Every one of those numbers was produced by running the file itself in ngspice.

The op-amp in files 01 and 02 is a generic macro (Aol 100 dB, GBW 3 MHz,
diode output clamps) defined at the top of the file. For a better answer,
delete that subcircuit after import and drop in Multisim's own **TL072CP**
from Place ▸ Component ▸ Group **Analog** ▸ Family **OPAMP**.

## Route B — Arbitrary SPICE Block, one black box on your own sheet

Use this when you want Multisim's sources and instruments around a block, or
for `fmcw_beat.sub`, which needs a real VCO in front of it and so cannot be a
plain netlist. The `.sub` files are plain SPICE 3 (R, C, D, E incl. POLY, T,
V, X) — no B-sources, no ngspice syntax — and each has been run through
ngspice via the `_h_*.cir` harnesses to prove it parses and gives the
test-card numbers.

| file | subcircuit · pins | stands for |
|---|---|---|
| `opamp_tl072.sub` | `TL072X inp inn vcc vee out` | generic TL072 (Aol 100 dB, GBW 3 MHz, clamps 1.5 V inside the rails). Used by the two blocks below; in Multisim you can instead build the amp from library TL072CPs — see the KiCad sheet |
| `video_amp.sub` | `VIDEO_AMP if audio vana vref gnd` | test card 1 — the whole video amplifier, full gain (R4 1k, R7 10k) |
| `vref_bias.sub` | `VREF_BIAS vana vref gnd` | test card 2 |
| `power_in.sub` | `POWER_IN vin vprot vana gnd` | test card 3 |
| `sync_div.sub` | `SYNC_DIV gpio sync sc gnd` | test card 4, includes the sound card's coupling |
| `fmcw_beat.sub` | `FMCW_BEAT tx leak_en beat gnd` | test card 6 — delay lines, gated leakage, POLY multiplier (the mixer), the amp's filters |

### Placing a block

1. Place › Component › Group **Basic** › Family **BASIC_VIRTUAL** (older
   versions: **Misc**) › **ARBITRARY_SPICE_BLOCK**.
2. Double-click it › **Value** tab › paste the contents of the `.sub` file
   (for `video_amp.sub` and `vref_bias.sub` paste `opamp_tl072.sub` first,
   then the block — the `.include` line does not resolve inside Multisim, so
   delete it and paste the op-amp subcircuit above the block's `.subckt`).
3. Set the block's **pin names** to the `.subckt` pin list, in order.
4. Wire the external parts below to those pins.

### Per block: what to add outside, what to run, what you should read

#### 1 · VIDEO_AMP
- **Outside:** `AC_VOLTAGE` V_IF → **50 Ω resistor** → `if`. `DC_POWER` 11.4 V → `vana`; `DC_POWER` 5.7 V → `vref` (or the VREF_BIAS block's output). 10 kΩ from `audio` to ground (sound-card load). Ground → `gnd`.
- **Run:** AC Analysis 1 Hz – 100 kHz, output `V(audio)`; Transient 40–60 ms with V_IF = **0.5 mVpk 1 kHz**.
- **Read:** 54.5 dB at 1 kHz, ~48.7 dB at 159 Hz (−6), ~50.7 dB at 15.9 kHz (−4). Transient: 0.5 mVpk → **~0.27 Vpk** at `audio`. 10 mVpk clips at ±4.2 V — that is the full-gain block; for the first-power-up gain edit `R4 am vref 4.7k` and `R7 bout bm 0.001` in the pasted text (then 10 mVpk → 107 mVpk).
- **Radar test:** two AC_VOLTAGE in series: 8 mVpk 12.5 Hz + 40 µVpk 417 Hz → Fourier on `audio`: ~27 mV at 12.5 Hz, ~19 mV at 417 Hz.

#### 2 · VREF_BIAS
- **Outside:** `DC_POWER` 11.4 V → `vana`; 2.2 kΩ from `vref` to ground.
- **Run:** DC Operating Point; then AC/transient with 100 mVpk 150 kHz added to `vana`.
- **Read:** `vref` = **5.58–5.70 V** (5.58 with the generic op-amp's 100 Ω output; 5.70 with TL072CP), ripple < 1 µV.

#### 3 · POWER_IN
- **Outside:** `DC_POWER` 12 V → `vin`; 60 Ω from `vprot` to ground (the buck's load), 1.1 kΩ from `vana` to ground (the op-amps).
- **Run:** DC OP; transient with 100 mVpk 150 kHz on `vin`; DC OP again with **−12 V**.
- **Read:** `vprot` **11.68 V**, `vana` **11.58 V**; ripple on `vana` ~4 mVpp; reversed: `vprot` ≈ −0.1 mV.

#### 4 · SYNC_DIV
- **Outside:** `PULSE_VOLTAGE` 0 → 3.3 V, pulse width 6.4 ms, period 7.4 ms, 10 ns edges → `gpio`.
- **Run:** Transient 0–60 ms, probe `sync` and `sc`.
- **Read:** `sync` **283 mV** high / 0 low; `sc` **+201 mV** plateau that droops, **−100 mV** retrace pulse. (That is what the laptop sees; the software detects edges, not levels.)

#### 5 · FMCW_BEAT — the radar
- **Outside:** `PIECEWISE_LINEAR_VOLTAGE` (0 V at 0, 1 V at 6.4 ms, repeat) → `VOLTAGE_CONTROLLED_SINE_WAVE` (0 V → 1 MHz, 1 V → 5 MHz, 1 Vpk) → `tx`. `DC_POWER` **0 V** → `leak_en` (1 V to switch the leakage path on).
- **Run:** Transient, TMAX **10 ns**, stop 12.8 ms. Fourier Analysis on `beat` over the **second chirp** (6.72–12.8 ms), Hanning.
- **Read:** peak at **≈ 415 Hz, ~3 mV**. Change T1's `TD=667n` to `333n` → 208 Hz; `1.33u` → 833 Hz. `leak_en` = 1 V: the 417 Hz line stays, the floor near DC rises — the reason the software subtracts chirp-to-chirp.
- Why it is scaled: the beat is `B × TD / T` and the carrier cancels. Real radar B = 40 MHz, TD = 66.7 ns at 10 m; here B = 4 MHz, TD = 667 ns — same 417 Hz, and Multisim can step at 10 ns instead of 20 ps.

## Not importable, by nature
Everything to the right of the mixer's IF port — ADF4351, SPF5189Z amplifiers, splitter, mixer at 2.44 GHz, the horns. No models exist at that frequency in Multisim; those stages are measured on the bench (`docs/radar-hardware.md` checkpoints 7–8).

## Reproduce the reference numbers
```
cd hardware/spice/multisim
ngspice -b import/03_power_in.cir    # the import files run as-is
ngspice -b _h_video.cir              # the harnesses wrap each .sub with the sources listed above
```

## If Multisim refuses a file
- **"Unrecognized command" / it stops at a line** — you opened one of the
  ngspice decks in `hardware/spice/`, not `import/`. They contain `.control`.
- **Nothing appears after File ▸ Open** — the file-type dropdown was still on
  Multisim files; it must say SPICE netlist (\*.cir).
- **The subcircuit did not come through** — paste it into an Arbitrary SPICE
  Block instead (route B), or rebuild that stage from library parts.
