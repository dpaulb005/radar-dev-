# Can this radar sense 3D? — measured answer

**Short answer: no, not altitude — and you don't need it to.** Your three
ground nodes give excellent horizontal position and essentially *no* usable
altitude. The fix isn't a better solver or more nodes; it's to take altitude
from the **barometer already on the drone** and let the radar do what its
geometry is actually good at (x, y).

Everything below is measured with the tools in this repo, not asserted:
`ground_station/geometry.py` (geometry analysis) and
`ground_station/digital_twin.py` (full 3D closed-loop twin).

---

## 1. Why altitude fails: the nodes are coplanar

Multilateration converts *range* error into *position* error by a factor set
purely by geometry. For nodes at `p_i` and a drone at `p`, the unit
line-of-sight vectors `u_i = (p − p_i)/|p − p_i|` form the geometry matrix
`G`; with per-node range sigma `s_i` the position covariance is
`C = (Gᵀ W G)⁻¹`, `W = diag(1/s_i²)`.

When every node sits at the same height (~1 m) and the drone flies near that
height, **every line of sight is nearly horizontal**, so `∂range/∂z ≈ 0` —
range barely changes as the drone moves up or down. The vertical term of `C`
blows up.

`python geometry.py` (1-sigma error in **metres**, 3 dB RSSI noise):

| Layout | node heights | drone @1.5 m | σ_h | σ_v | verdict |
|---|---|---|---|---|---|
| **your config** | all 1.0 m | | **2.11 m** | **9.8 m** | unusable altitude |
| 4 nodes, all 1.0 m | all 1.0 m | | 2.11 m | **11.1 m** | *worse* — node count doesn't help |
| staggered 0.3/3.0 m | two heights | | 2.23 m | 4.3 m | poor |
| 3 ground + **1 on a 5 m mast** | 1.0 / 5.0 m | | 2.12 m | **1.5 m** | good |

Two things worth noticing:

* **The predicted σ_h = 2.11 m matches the ~2 m horizontal accuracy measured
  independently in `pursuit_sim.py`.** The model is calibrated against reality.
* **Adding a 4th node at the same height makes altitude slightly *worse*.**
  The problem is coplanarity, not node count. Only *vertical spread* helps.

### The mirror ambiguity (the deeper problem)

With all anchors in one plane, a drone at height `+h` above that plane and its
mirror image at `−h` produce **identical ranges to every node**. The data
literally cannot distinguish them.

Tested directly — solve for altitude from different starting guesses
(true altitude 1.5 m, nodes at 1.0 m):

```
[flat3]  z guess  ->  z solved
           -2.0   ->    -0.02     ) locks BELOW the node plane
            0.0   ->     0.04     )
            1.5   ->     2.12     ) locks ABOVE the node plane
            4.0   ->     1.97     )
            8.0   ->     2.16     )

[mast]     -2.0   ->     2.04     ) single stable solution
            0.0   ->     2.00     ) from every starting point
            8.0   ->     2.02     )   (1% spread)
```

The flat array converges to one of **two** mirror solutions (≈0.0 or ≈2.1
about the 1 m plane) depending purely on where the solver starts — and
neither is the true 1.5 m. In Monte-Carlo, the solution lands on the wrong
side of the node plane **40–50 % of the time**: the altitude *sign* is a coin
toss. The mast layout collapses this to one stable answer.

> Note: a naive RMS-error number *understates* this, because the optimizer
> parks near the node plane and truth happens to be close by. The
> bimodality and the flip rate are the honest diagnostics — which is why
> `geometry.py` prints a COPLANAR warning rather than just a sigma.

---

## 2. The fix: altitude comes from the barometer

Your ESP-BLAST already carries a **BMP280 barometer**, and ESP-FC already
fuses it (that's what its ALTHOLD mode runs on). Relative altitude from baro
is good to roughly ±0.4 m — *far* better than anything the coplanar radar can
produce — and it costs nothing extra: you only need to telemeter it down
alongside the heading downlink (`docs/interception.md` §4).

So the architecture is: **radar solves (x, y); barometer supplies z.** This is
exactly what the code already does — `locate.solve_position(..., solve_3d=False)`
with a fixed `drone_z` — so nothing needs rewriting; it just needs the baro
value wired in instead of a constant.

### Measured, end-to-end, in the digital twin

`python digital_twin.py --compare-alt` — full 3D closed loop, target at
3 m/s, 20 trials each:

| altitude source | arrival <2.5 m | **contact <1 m** | median 3D miss | alt error |
|---|---|---|---|---|
| perfect (upper bound) | 100 % | **95 %** | 0.98 m | 0.00 m |
| **barometer** | 100 % | **90 %** | 0.99 m | 0.41 m |
| radar-solved (coplanar) | 85 % | **20 %** | 1.71 m | 1.88 m |

**The barometer is within 5 points of perfect knowledge; radar-solved
altitude collapses the contact rate from 90 % to 20 %.** That is the whole
argument in one table.

---

## 3. What about 3D *angle* (AoA)?

Worth separating two different things:

* **Angle-of-arrival** (what a phased array or rotating antenna measures)
  needs multiple phase-coherent receive channels per site. Not available on
  an ESP32 — this is the RF-seeker payload discussed and rejected in
  `docs/interception.md` §1.
* **What you actually need** is *position*, and multilateration gives you
  that from ranges alone, no angle required. Elevation angle to the target
  then falls out of the position solution for free (once altitude comes from
  baro).

So there's no need to chase AoA hardware. Ranges + baro → full 3D state.

---

## 4. Recommendations

1. **Keep the radar 2D.** Continue solving (x, y) only (`solve_3d=False`).
   Don't add nodes hoping for altitude — a 4th coplanar node makes it worse.
2. **Downlink the barometer** from both drones, alongside the AHRS heading
   you already need. This single change gives you the full 3D state.
3. **If you ever do want radar altitude** (e.g. as a cross-check, or if a
   baro downlink fails): put **one node up high** — a 5 m mast, a roof, a
   balcony. That alone takes σ_v from 9.8 m to 1.5 m and kills the mirror
   ambiguity. Staggering nodes across 0.3–3 m helps but much less.
4. **Barometer caveats to respect in the field:** baro measures *pressure*,
   so it drifts with weather over tens of minutes and is disturbed by
   propwash and wind gusts. Zero it at takeoff and use it as a *relative*
   altitude. Since both drones carry one and you only care about their
   altitude *difference*, common-mode weather drift largely cancels — a
   nice property for this application.

---

## 5. Tools

```bash
cd ground_station
python geometry.py                     # DOP/observability for each layout
python geometry.py --layout mast       # check a specific layout
python geometry.py --map               # HDOP/VDOP map over the area

python digital_twin.py                 # one 3D run
python digital_twin.py --compare-alt   # the table above
python digital_twin.py --trials 40     # Monte-Carlo
python digital_twin.py --plot twin.png # 3D trajectory plot
```
