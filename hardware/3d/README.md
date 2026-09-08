# hardware/3d — the bench model

`radar-bench.html` is a self-contained Three.js page (open it in a browser;
it loads three.js r128 from cdnjs). It shows every row of `hardware/BOM.md`
as an object on a plywood bench, the 830-point breadboard populated
component by component from the KiCad schematic, the three build stages,
and the drone 3 m out in the room.

- Buttons: stage 1 / 2 / 3, Bench / Breadboard / Room views, labels, coax.
- The BOM panel on the right: click a row → the camera flies to the part and
  it pulses; hover any object for its name; click an object → its BOM row.
- Rows marked *consumable* / *tool* (solder, flux, snips) are listed but not
  modelled; the copper sheet **is** the horns, the flanges and brass rod are
  the horn feeds.

Screenshots: `radar-bench-bench.png`, `radar-bench-breadboard.png`,
`radar-bench-stage3.png`, `radar-bench-room.png`.

The breadboard in this model is a schematic-order placement to give the
bench a sense of scale. The hole-level, netlist-verified layout to build from
is `hardware/breadboard/` (`WIRING.md`, `breadboard.svg`, `breadboard.html`);
the electrical reference is `hardware/kicad/radar_multisim.kicad_sch`.
