# radar-dev

A 2.4 GHz FMCW radar I'm building to find and track a small drone (a 25 g ESP-Fly) indoors.
It's based on the MIT "coffee can" radar, but with copper horn antennas instead of cans and
my own baseband board.

**Nothing RF is built yet.** Everything below is simulation: the horn antenna in Ansys HFSS and
the baseband electronics in NI Multisim. The short write-up with all the plots is
[`report/simulation-report.pdf`](report/simulation-report.pdf).

## How it works

The ESP32 sweeps an ADF4351 from 2400 to 2483.5 MHz every 6.4 ms. That goes out the TX horn,
bounces off the drone and comes back into the RX horn, where it gets mixed with what is being
sent at that moment. The mixer output is a tone whose pitch depends on distance: about 87 Hz
per meter, so 870 Hz for a drone 10 m away. A two-stage op amp (TL072) boosts that tone into a
USB sound card and the laptop does the FFT.

## Horn antenna (HFSS)

| what | simulated | needed |
|---|---|---|
| match (S11), worst across 2400–2483.5 MHz | −24.3 dB | below −10 dB |
| gain | 13.2–13.3 dBi | 12.5–14 dBi (theory says 13.4) |
| beam width | 34° × 36° | theory 33° × 35° |
| TX to RX leakage, horns 290 mm apart | −49.4 dB | below −35 dB |
| match if the probe is off by ±1 mm | −14.5 dB worst | below −10 dB |
| finer mesh / real copper instead of perfect metal | gain moves 0.14 dB / 0.01 dB | under 0.2 dB |

What it means: the horn does what the textbook says it should, and less than 0.4 % of the
power bounces back into the transmitter. The answer doesn't change with a finer mesh or with
real copper, so it isn't a simulation artifact.

The probe position from the usual rule (28 mm long, 43.7 mm from the back wall) only reached
−5.2 dB, so about 30 % of the power was reflected. I swept the probe on a 1 mm grid and moved
it to **27 mm long, 17.7 mm from the back wall**. The build guide and waterjet files use the new
position. More in [`antenna/`](antenna/).

## Baseband board (Multisim)

Each block was drawn in Multisim with real library parts (TL072CP, 1N5822, etc.), then all of
them together on one sheet (card 8).

| card | block | result | expected |
|---|---|---|---|
| 1 | video amp | 54.5 dB gain at 1 kHz, 48.7 dB at 159 Hz, 50.9 dB at 15.9 kHz | 54.5 / 48.7 / 50.6 dB |
| 1 | video amp, two tones | 870 Hz tone comes out at 21.1 mV | 21.2 mV |
| 2 | half-rail reference | 5.70 V / 5.58 V | 5.70 / 5.58–5.72 V |
| 3 | 12 V input | 11.62 V on the analog rail, 3.2 mV ripple | 11.58 V, about 4 mV |
| 4 | reverse polarity | −11 mV gets through with −12 V in | under 0.5 V |
| 5 | sync divider | 275 mV pulse into the sound card | 270–300 mV |
| 6 | IF input | −57.7 dB at 2.44 GHz | −57.7 dB |
| 7 | scaled radar | beat tone at 5 / 10 / 15 m: 435.0 / 870.7 / 1305.8 Hz | 435.2 / 870.4 / 1305.6 Hz |
| 8 | everything on one sheet | gain within 0.15 dB of card 1, outputs settle in 0.53 s at power-up | within 0.3 dB, under 1 s |

What it means: every block gives the number it was designed for, and the beat tone tracks
distance within 0.05 %. Card 8 is the one that caught real problems:

- The amp came out stuck against the rail. Two op-amp supply pins had no wire after I pasted
  the blocks together. Wiring them fixed it.
- After that, the gain was up to 6.4 dB low around 200 Hz. The half-rail reference was moving
  with the signal and the first stage amplified it. Raising **C6 from 47 µF to 3.3 mF** fixed it.
  The Multisim projects have the new value.

More in [`multisim/`](multisim/).

## How to set it up (from the numbers above)

- Horns side by side with the mouths flush, turned so the 264 mm side is vertical, TX 290 mm
  above RX (center to center).
- Fly the drone 3–10 m out. Under about 2 m the tone drops below the amp's 159 Hz corner.
  Past 10 m the tone is fine, but the echo gets weak (4× weaker each time the distance
  doubles), and noise isn't in these simulations.
- The beam is about 3 m wide at 5 m and 6 m wide at 10 m, so keep the drone near the middle.

## What's here

| | |
|---|---|
| [`report/`](report/) | the simulation write-up (LaTeX + PDF) and its figures |
| [`antenna/`](antenna/) | horn design, HFSS results, the build guide and the waterjet cut files |
| [`multisim/`](multisim/) | the Multisim projects, exported data, plots and results table |
| [`3d/`](3d/) | 3D models of the radar bench and the drone |
| [`BOM_Radar_Build.xlsx`](BOM_Radar_Build.xlsx) | parts list with prices |

Firmware, the signal processing and the scripts that make the plots are on the
[`dev`](https://github.com/dpaulb005/radar-dev-/tree/dev) branch.

## Next

1. Cut the three horns (waterjet files are ready) and solder them.
2. Build the breadboard and check it against the Multisim numbers.
3. Bench test: check the horn match with a VNA, power-cycle the board, then a walk test.
