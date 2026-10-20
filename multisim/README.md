# Multisim — baseband board simulation

Each block of the breadboard drawn in NI Multisim 14.2 with library parts (TL072CP, 1N5822,
real resistor and capacitor values), plus one sheet with everything together (card 8).
The projects are in [`projects/`](projects/), the exported data and plots in [`results/`](results/),
and every check is in [`results/multisim-measurements.csv`](results/multisim-measurements.csv).

## Results

| card | project | what I checked | result | expected |
|---|---|---|---|---|
| 1 | `01_video_amp` | DC: outputs sit at the half rail | within 1.1 mV | within 150 mV |
| 1 | `01_video_amp` | gain at 159 Hz / 1 kHz / 15.9 kHz | 48.7 / 54.5 / 50.9 dB | 48.7 / 54.5 / 50.6 dB |
| 1 | `01_video_amp` | 0.5 mV, 1 kHz in | 0.266 V out | 0.27 V |
| 1 | `01_video_amp` | clipping | ±4.06 V | about ±4.2 V |
| 1 | `01b_first_powerup` | low-gain build, 10 mV in | 106.8 mV out | 107 mV |
| 1 | `01d_two_tone` | leakage tone + echo tone (417 / 870 Hz) | 19.1 / 21.1 mV | 19.0 / 21.2 mV |
| 2 | `02_vref_bias` | divider / buffered half rail | 5.70 / 5.58 V | 5.70 / 5.58–5.72 V |
| 2 | `02_vref_bias` | 150 kHz switcher ripple reaching vref | −162 dB | below −100 dB |
| 3 | `03_power_in` | 12 V in: protected rail / analog rail | 11.72 / 11.62 V | 11.68 / 11.58 V |
| 3 | `03_power_in` | ripple on the analog rail | 3.2 mV | about 4 mV |
| 4 | `04_power_reverse` | −12 V plugged in backwards | −11 mV gets through | under 0.5 V |
| 5 | `05_sync_div` | sweep sync pulse into the sound card | 275 mV | 270–300 mV |
| 6 | `06_if_input` | IF input at 417 Hz / 2.44 GHz | −6.6 / −57.7 dB | −6.6 / −57.7 dB |
| 7 | `07_fmcw_radar` | beat tone at 5 / 10 / 15 m | 435.0 / 870.7 / 1305.8 Hz | 435.2 / 870.4 / 1305.6 Hz |
| 8 | `08_baseband_system` | DC: outputs at the half rail | within 1.1 mV | within 150 mV |
| 8 | `08_baseband_system` | gain vs card 1, 10 Hz–50 kHz | within 0.15 dB | within 0.3 dB |
| 8 | `08_baseband_system` | two-tone, 870 Hz line | 21.0 mV | 21.2 mV |
| 8 | `08_baseband_system` | 150 kHz ripple at the output | 0.06 µV | under 1 mV |
| 8 | `08_baseband_system` | power-up from 6 V | settles in 0.53 s, no latch-up | under 1 s |

## What it means

- **The amplifier does its job.** 54.5 dB of gain at 1 kHz, fairly flat up to about 15 kHz, and
  it rolls off below 159 Hz to block the strong leakage tone near DC.
- **The supply and reference are clean.** The switcher's 150 kHz ripple never shows up at the
  amplifier.
- **Range comes out right.** Card 7 is a scaled-down version of the whole radar. The beat tone
  lands within 0.05 % of the formula at every distance, and it stays put with leakage turned on.
- **Card 8 found two real problems:**
  - When all the blocks were on one sheet, the amp was stuck against the rail. The exported
    netlist showed that two op-amp supply pins (U1A V− and U1B V+) had no wire after copying
    the blocks together. Wiring them fixed it.
  - Then the gain was up to 6.4 dB low around 200 Hz (2.8 dB at 1 kHz). The signal current was
    moving the half-rail reference, and the first stage amplified that because its 1 kΩ gain
    resistor returns to it. Raising **C6 from 47 µF to 3.3 mF** brings it within 0.15 dB of card 1.
    [`results/08_baseband_system/08_ac_vs_card1.png`](results/08_baseband_system/08_ac_vs_card1.png)
    shows both.

## Notes

- The analog rail reads 11.49 V on card 8 instead of 11.5–11.7 V. That's because the TI op-amp
  model draws 5.7 mA per amp, while the TL072 datasheet says 1.4 mA typical. With real chips it
  should be about 11.6 V.
- The op-amp model can't be solved below about 4.4 V of supply, so power-up starts at 6 V
  instead of 0 V. Worth power-cycling the real board a few times.
- For the long card 8 runs I set the 150 kHz ripple source to 0 V (Multisim otherwise shrinks
  the time step to fit 150 kHz and the run fails). The ripple check is its own 2 ms run.
- `08_schematic.png` is the screenshot from before the two supply wires were added.
- The longest transient exports (card 7 and the 1 s+ runs) are too big for GitHub and aren't
  in `raw/`.
- [`import/`](import/) and [`blocks/`](blocks/) are the SPICE netlists I started from.
