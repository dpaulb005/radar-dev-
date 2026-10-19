# HFSS results

All runs are of the final horn (probe 27 mm long, 17.7 mm from the back wall) unless noted.

| file | what |
|---|---|
| `horn-measurements.csv` | every check in one table, with pass/fail |
| `s11.csv`, `s11.png`, `smith.png` | match vs frequency, 2.2–2.7 GHz |
| `gain-eplane.csv`, `gain-hplane.csv`, `patterns.png`, `patterns_polar.png` | radiation pattern cuts at 2.45 GHz |
| `gain-vs-freq-boresight.csv`, `gain_vs_freq.png` | gain straight ahead across the band |
| `isolation.csv`, `isolation.png` | leakage from the TX horn into the RX horn, 290 mm apart |
| `scan-table.csv`, `scan_heatmap.png` | the 1 mm probe sweep (57 runs): worst match in band for each length and position |
| `scan_diagnosis.png` | why the original probe position didn't match |
| `robustness.csv`, `robust_mesh.png`, `robust_copper.png` | same horn with coarser/finer mesh and with copper walls |
| `convergence.png` | how the mesh refinement settled |
