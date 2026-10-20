# HFSS results

Horn with the final probe (27 mm long, 17.7 mm from the back wall). Every check is in
`horn-measurements.csv`.

| file | what |
|---|---|
| `s11.csv`, `s11.png`, `smith.png` | match vs frequency |
| `gain-eplane.csv`, `gain-hplane.csv`, `patterns.png`, `patterns_polar.png` | radiation pattern at 2.45 GHz |
| `gain-vs-freq-boresight.csv`, `gain_vs_freq.png` | gain straight ahead across the band |
| `isolation.csv`, `isolation.png` | leakage from the TX horn into the RX horn, 290 mm apart |
| `scan-table.csv`, `scan_heatmap.png` | the 1 mm probe sweep (57 runs) |
| `scan_diagnosis.png` | why the original probe position didn't match |
| `robustness.csv`, `robust_mesh.png`, `robust_copper.png` | coarser/finer mesh and copper walls |
| `convergence.png` | mesh refinement |
