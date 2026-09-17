# 3d — the two models

Two self-contained Three.js pages. Open either in a browser (each loads
three.js from a CDN, so it needs an internet connection the first time).
Between them they draw every part in `BOM_Radar_Build.xlsx` as a real object.

| page | what it is |
|---|---|
| [`radar-bench.html`](radar-bench.html) | the radar: the three-horn frame, the RF chain, the 830-point breadboard wired hole by hole, the USB interface and laptop, the optional turntable, and the room with the drone 3 m out. A second button adds the azimuth upgrade, so the model can show what would change. |
| [`drone.html`](drone.html) | the target: a Seeed ESP-FLY with the 915 MHz receiver fitted, every part, every pad, every wire, and what each one weighs. |

Both share the same conventions: click a panel row and the camera flies to the
part and it pulses; hover any object for its name; hover a pin or pad for its
net; click an object and its panel row scrolls into view.

## Rendered views

Still images from each model, in [`renders/`](renders/).

| [`renders/radar-bench/`](renders/radar-bench/) | |
|---|---|
| [`room.png`](renders/radar-bench/room.png) | the room, drone 3 m out |
| [`desk.png`](renders/radar-bench/desk.png) | the desk |
| [`bench.png`](renders/radar-bench/bench.png) | the bench and horn frame |
| [`plan.png`](renders/radar-bench/plan.png) | plan view |
| [`breadboard.png`](renders/radar-bench/breadboard.png) | the breadboard, wired |
| [`stage2.png`](renders/radar-bench/stage2.png) | with the azimuth upgrade |

| [`renders/drone/`](renders/drone/) | |
|---|---|
| [`overview.png`](renders/drone/overview.png) | the ESP-FLY as fitted |
| [`top.png`](renders/drone/top.png) | from above |
| [`underside.png`](renders/drone/underside.png) | from below |
| [`receiver.png`](renders/drone/receiver.png) | the 915 MHz receiver fitted |
| [`exploded.png`](renders/drone/exploded.png) | exploded |

The models are generated and geometry-checked by scripts on the `dev` branch
(`hardware/3d/`); edit there, not here.
