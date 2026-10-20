# radar-dev — simulation results

Results for the 2.4 GHz FMCW radar I'm building to track a small drone: the horn antenna in
Ansys HFSS and the baseband electronics in NI Multisim. Nothing RF is built yet. The short
write-up with all the plots is [`report/simulation-report.pdf`](report/simulation-report.pdf).

## Horn antenna (HFSS)

| what | simulated | needed |
|---|---|---|
| match (S11), worst across 2400–2483.5 MHz | −24.3 dB | below −10 dB |
| gain | 13.2–13.3 dBi | 12.5–14 dBi (theory 13.4) |
| beam width | 34° × 36° | theory 33° × 35° |
| TX to RX leakage, horns 290 mm apart | −49.4 dB | below −35 dB |
| match with the probe off by ±1 mm | −14.5 dB worst | below −10 dB |
| finer mesh / real copper instead of perfect metal | gain moves 0.14 dB / 0.01 dB | under 0.2 dB |

What it means: the horn does what the textbook says it should, and less than 0.4 % of the
power bounces back into the transmitter. A finer mesh or real copper gives the same answer.

The textbook probe position (28 mm long, 43.7 mm from the back wall) only reached −5.2 dB,
about 30 % reflected. A 1 mm sweep moved it to **27 mm long, 17.7 mm from the back wall**.
Data and plots in [`hfss/`](hfss/).

## Baseband electronics (Multisim)

| card | block | result | expected |
|---|---|---|---|
| 1 | video amp | 54.5 dB at 1 kHz, 48.7 dB at 159 Hz, 50.9 dB at 15.9 kHz | 54.5 / 48.7 / 50.6 dB |
| 1 | video amp, two tones | 870 Hz tone out at 21.1 mV | 21.2 mV |
| 2 | half-rail reference | 5.70 V / 5.58 V | 5.70 / 5.58–5.72 V |
| 3 | 12 V input | 11.62 V analog rail, 3.2 mV ripple | 11.58 V, about 4 mV |
| 4 | reverse polarity | −11 mV gets through with −12 V in | under 0.5 V |
| 5 | sync divider | 275 mV pulse into the sound card | 270–300 mV |
| 6 | IF input | −57.7 dB at 2.44 GHz | −57.7 dB |
| 7 | scaled radar | beat tone at 5 / 10 / 15 m: 435.0 / 870.7 / 1305.8 Hz | 435.2 / 870.4 / 1305.6 Hz |
| 8 | everything on one sheet | gain within 0.15 dB of card 1, settles in 0.53 s at power-up | within 0.3 dB, under 1 s |

What it means: every block gives the number it was designed for, and the beat tone tracks
distance within 0.05 %. Card 8 caught two real problems: two op-amp supply pins weren't wired
(the amp sat stuck at the rail), and then the gain was up to 6.4 dB low because the half-rail
reference moved with the signal. Wiring the pins and raising C6 from 47 µF to 3.3 mF fixed both.
Data and plots in [`multisim/`](multisim/).
