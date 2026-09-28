# HFSS results

Drop the Ansys HFSS output here as it is produced. These are the names
`../hfss-design-guide.pdf` saves under, one file each:

| file | what |
|---|---|
| `horn.aedt` (or a `.aedtz` archive) | the project itself |
| `s11.csv` + `s11.png` | S11 vs frequency, 2.2–2.7 GHz, after the probe sweep |
| `gain-eplane.csv` / `gain-hplane.csv` + `patterns.png` | far-field cuts at 2.45 GHz |
| `probe-sweep.csv` | S11 for every probe length and back-wall distance in the sweep |
| `isolation.csv` | S21 from the TX horn into the RX horn, 290 mm apart |
| `horn-report.pdf` (+ its `.tex`) | the LaTeX write-up: gain, beamwidths, S11, chosen probe position, and whether each passes the accept-if line in `../README.md` |

Keep the numbers next to the pictures: a screenshot without the CSV behind it
cannot be re-plotted.
