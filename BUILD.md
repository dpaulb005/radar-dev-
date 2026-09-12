# Build order — what to make, and what to test, in what order

The four build documents teach the radar in the order it makes sense to *explain*
it. This page puts it in the order it makes sense to *build* it, which is not the
same: the expensive mistakes and the long lead times are not spread evenly, so
this is sorted by **what can kill the project** and **what you are waiting on**.

Read it once before you spend anything.

---

## The short version

| when | do | why now |
|---|---|---|
| **today, $0** | Phase 0 — run the simulator and the suite | Proves the DSP and teaches you the numbers before a single part is ordered |
| **order day** | Phase 1 — the mixer first, then everything else | It is the one part with no substitute and the worst stock |
| **while parts ship** | Phase 2 — horns, breadboard, power, firmware | All four need nothing from the RF order, and the horns are the longest job |
| **as parts land** | Phase 3 — bench each block on its own | A block tested alone takes minutes; the same fault inside a finished chain takes an evening |
| **first assembly** | Phase 4 — the chain, up to the leakage tone | One tone proves seven subsystems at once |
| **first measurement** | Phase 5 — walk at the horns | This is a working radar. You do not need the drone for it |
| **before you trust anything** | Phase 6 — measure your room | **The single number most likely to decide whether this works** |
| **last** | Phase 7 — the drone | It is a target. Everything else must already work |

**The two things most likely to stop you**, and neither is the electronics:

1. **Your room's clutter cancellation** (Phase 6). Every SNR figure in this repo
   assumes an empty universe. Indoors a 1 m² patch of wall is 26 dB above the
   drone and shares its range cell. You need about **55 dB** of cancellation at
   10 m, it is a mechanical and stability problem rather than a software one, and
   **nothing in this repo can predict yours**. Measure it the day the chain first
   works — it costs nothing and it tells you whether to believe every other
   number here.
2. **The ZX05-43MH-S+ mixer.** No substitute, and stock has been thin. Order it
   before anything else, or commit to the $25 generic module up front.

---

## Phase 0 — Prove it in software. Today, before you spend anything

Twenty minutes, no hardware, and it is the cheapest confidence you will ever buy
on this project. It also teaches you what the numbers mean, which makes every
later measurement readable.

```bash
cd ground_station && pip install -r requirements.txt
python radar_acquire.py --selftest            # synthetic drone through the live DSP
python test_radar.py                          # the suite, 22 cases
python server.py --demo                       # the console, no radar needed
```

The self-test synthesises exactly what the sound card will record — single-ended
beat, AC-coupled sync with droop, TX leakage at 35 dB isolation, thermal noise,
the stepped ADF4351 waveform — and runs it through the same code that will run
live. `--demo` drives the console off a synthetic target so you can see what a
detection is supposed to look like before you have one.

Then read the two numbers that set everything else: **1.80 m** range cell and
**0.13 m/s** velocity resolution, in [`docs/radar-software.md`](docs/radar-software.md) § 1.

> **Gate.** `SELFTEST PASS`, 22/22, and the console drawing a target closing.
> Checkpoint 1 in [`docs/radar-software.md`](docs/radar-software.md).

**Also decide now, because it changes what you buy:** are you ever going to want
azimuth? Stage 1 records two channels and runs on any line-level 2-input
interface, including one you already own. Azimuth needs four channels on one
sample clock, which is a different box — see [`stage2/README.md`](stage2/README.md).
Deciding late costs you the 2-input interface, and nothing else.

---

## Phase 1 — Order, in this order

Full list with links and checked prices: [`hardware/ORDER.md`](hardware/ORDER.md).
The reasoning behind each choice: [`hardware/BOM.md`](hardware/BOM.md).

1. **The mixer.** Critical path. Order it on its own if that gets it moving.
2. **Everything else RF** — ADF4351 board, SPF5189Z 4-pack, splitter, 3 dB pad,
   band-pass filter, SMA jumpers **in one batch**, adapters.
3. **Copper sheet, SMA flanges, brass rod, solder** — these arrive fast and
   Phase 2 starts the moment they do.
4. **ESP32, TL072 ×2, breadboard, passives, LM2596 ×2.**
5. **The drone's 915 MHz link** — only if you are flying indoors. Skip it
   outdoors and fly from the phone on a 40 MHz sweep.

> **Gate.** Checkpoint 1 in [`docs/radar-hardware.md`](docs/radar-hardware.md):
> everything on the bench before the chain goes together.

---

## Phase 2 — While the RF parts are in transit

None of this needs the RF order. Do it in parallel, not after.

### 2a. The horns — start these first, they are the longest job

Three of them, in one session, from one marked-out sheet.
[`docs/radar-hardware.md`](docs/radar-hardware.md) § 2 has the cut list.

Three, not two, even though this build uses one TX and one RX: the third is what
makes azimuth a bolt-on later instead of a rebuild, the materials are already in
the bill, and two horns cut months apart will not match. Cutting all three while
the jig is set up costs you an afternoon and nothing else.

> **Gate.** Checkpoint 2: three horns, every seam continuous, probe at
> 43.7 / 28 mm, panel-to-panel below 0.5 Ω. An ohm-meter does that one — a gap
> in a seam is an RF leak, and leaks come back later as a mystery noise floor.

### 2b. The breadboard

[`hardware/breadboard/ASSEMBLY.md`](hardware/breadboard/ASSEMBLY.md) — 17 steps,
a picture at each, and something to measure before you move on. Power first, then
the op-amps, then the signal left to right, then the digital side.

> **Gate.** Step 17: with the supply disconnected, GND-to-VANA, GND-to-V5 and
> GND-to-3V3 all read open. Then Checkpoint 5 in
> [`docs/radar-hardware.md`](docs/radar-hardware.md): a finger on the input gives
> a hum, and a 1 kHz tone in gives the 107 mV out that the simulation predicted.

### 2c. Simulate the blocks before you trust them

[`hardware/spice/README.md`](hardware/spice/README.md) has one test card per
block — values, stimulus, and the reading to expect. Six blocks: video amp,
half-rail reference, 12 V input and protection, sync divider, mixer IF input, and
the radar itself scaled down so SPICE can run it.

Worth doing even after the board is built: when a measurement disagrees with the
card, one of the two is wrong and you now know where to look.

### 2d. Power, on its own

Set the LM2596 to **5.00 V before it is connected to anything**. A buck delivered
at 12 V into the ADF4351 board is an expensive thirty seconds.

> **Gate.** Checkpoint 4: 5.00 V at every module's supply pin, ESP32 enumerates
> over USB.

### 2e. Firmware, with almost nothing attached

The ESP32 and the ADF4351 board are enough to do this — no horns, no chain.

```
?          -> {"fw":"radar_ctl", ... ,"lock":1}
```

`"lock":1` is the synthesiser's own lock-detect pin. If it is 0 the problem is
`F_REF_HZ` (25 MHz on nearly all boards, printed on the can), or LE/CLK/DATA
swapped, or CE not tied high — and it is far easier to find now than with a whole
chain hanging off it.

> **Gate.** Checkpoint 2 in [`docs/radar-software.md`](docs/radar-software.md),
> part 1: `lock:1`, `rf:0`. The board boots silent and radiates nothing until
> you tell it to.

---

## Phase 3 — Bench each RF block as it arrives

Resist the urge to assemble the whole chain and then switch it on. Every block
you can check alone, check alone.

| block | test |
|---|---|
| ADF4351 | `CW 2460`, then look for the tone on an RTL-SDR behind a 30 dB pad, or a power meter |
| PA | +14 ± 2 dBm out |
| splitter | roughly equal on both arms, about 3.5 dB down |
| LNA | powered, drawing current, not oscillating |
| band-pass | passes 2.4 GHz, kills 2.2 and 2.8 |

> **Gate.** Checkpoint 2 in [`docs/radar-software.md`](docs/radar-software.md),
> part 2: +10.5 ± 2 dBm at the splitter's LO arm.

---

## Phase 4 — Assemble the chain, and find the leakage tone

Lay the parts out in signal order on the plywood, torque every SMA by hand plus
an eighth of a turn ([`docs/radar-hardware.md`](docs/radar-hardware.md) § 3),
mount the horns on the frame (§ 7), wire the sync divider to the sound card's
right channel (§ 6).

> **Gate first — Checkpoint 3.** The whole chain wired VCO→…→TX and RX→…→IF,
> every SMA torqued, and **nothing powered yet**. Finger-tight SMA is about a
> 1 dB loss, and you will chase it for an evening once there is a signal to blame
> it on.

Then the single most valuable test in the whole build:

> **Gate — Checkpoint 7.** `SWEEP 1`, open the sound card monitor, and look for a
> **low tone with a strong ~26 Hz component** on the left channel. That is the
> transmitter leaking straight into the receiver, and it proves the PLL, the PA,
> the splitter, the LO drive, the LNA, the mixer and the video amp are **all
> alive, in one shot**. No tone means work backwards, LO drive first.

Nothing downstream is worth attempting until this tone is there.

> Also Checkpoint 6: the right channel shows a clean ~135 Hz square wave.
> `# no sync` from the software later is almost always this.

---

## Phase 5 — Your first real measurement

```bash
python radar_acquire.py --device N --ctl /dev/ttyUSB0 --server http://localhost:8080
```

**Walk toward the horns from 5 m.** Range counts down, velocity goes negative and
reads about your walking speed. Walk away and it goes positive. Stand still and
you vanish — that is not a fault, that is zero-Doppler being subtracted with the
room. Wave an arm and you come back.

That is a working radar, and it is the whole of this build. The drone is not
involved and does not need to be.

> **Gate.** Checkpoint 3 in [`docs/radar-software.md`](docs/radar-software.md):
> at 3, 5 and 8 m against a tape measure, the printed range is within 0.4 m.
> Then Checkpoint 4: the same three spots show up on the console.

---

## Phase 6 — The measurement that decides it

Do this the day the chain first works. It costs nothing, it takes ten minutes,
and it is worth more than every SNR figure in this repo put together.

1. Point the radar at a static scene.
2. Record a block. Record another a few seconds later.
3. Subtract the range profiles. The ratio of the strongest clutter peak to what
   is left **is** your clutter cancellation, in dB.

| you measure | what it means |
|---|---|
| **above 50 dB** | the link budget here means something; carry on |
| 40–50 dB | marginal at 10 m, fine closer in |
| **around 30 dB** | no amount of DSP will find a 25 g drone at 10 m indoors |

If it is low, the fix is **mechanical, not software**: a rigid mount, mass, no
fan, no air currents, nobody walking about, and a chain that does not drift over
the 0.47 s dwell. Full method in
[`docs/radar-software.md`](docs/radar-software.md) § 8.

A second surprise from the same section, worth knowing before you plan your
flying: in a **small** room clutter cancellation stops mattering — 30 dB is as
good as 60 dB at 2.5 m, because the echo goes as R⁻⁴ and the drone is close. What
bites instead is that the far wall shares the drone's range cell. Multipath in a
small room is **not modelled anywhere in this repo**; expect returns that are not
the drone.

---

## Phase 7 — The drone, last

The radar is finished and proven before the drone is ever in the air. Build it to
the kit's own guide, then make the one change that is not in that guide: the
control link moves to **915 MHz** so the radar can have the whole ISM band.

- [`docs/drone-hardware.md`](docs/drone-hardware.md) — the airframe, the 915 MHz
  receiver, its four pads and its antenna. Checkpoints 2, 4, 5, 7.
- [`docs/drone-software.md`](docs/drone-software.md) — ExpressLRS on both ends,
  EdgeTX, esp-fc, and the failsafe test. Checkpoints 1 through 5.

> **Do this before the drone and the radar are ever on together** — Checkpoint 7
> in [`docs/drone-software.md`](docs/drone-software.md): the drone must emit
> **nothing** in 2.4 GHz, and with `SWEEP 1` running and the beam on it, link
> quality must stay at 100 and RSSI must not move. It should not — the link is
> 1.5 GHz away — but you are betting an aircraft on it.

Then fly. In a small room the drone must keep moving **toward or away** at
**≥ 0.10 m/s**; a pure hover is subtracted along with the walls.

> **Gate.** Checkpoint 8 in [`docs/drone-software.md`](docs/drone-software.md):
> a two-minute hover in the beam, LQ 100 throughout, and a continuous track on
> the console.

---

## Phase 8 — Only then, if you want azimuth

Everything in Phase 2 was built so this is a bolt-on rather than a rebuild: the
third horn is already cut, the frame already has the empty bay, the spare LNA is
already in the 4-pack and the second TL072 is already on the board.

What it needs, what it costs and what it buys:
[`stage2/README.md`](stage2/README.md). The code is written and passes its own
27-case suite; none of it is built.

---

## If you are short of money or space

- **No turntable.** It points the beam at a wider sector and takes no part in
  measuring anything. Skip it first; it is also the cheapest way to measure your
  horn's real beam pattern later.
- **No VNA.** The link has ~54 dB of margin and a badly tuned pair of horns costs
  2.5 dB of it. Tune the probe against the radar's own detection SNR instead —
  [`docs/radar-hardware.md`](docs/radar-hardware.md) § 2c.
- **Outdoors or in a large space?** Skip the $122 915 MHz link entirely, fly from
  the phone on WiFi channel 1 and sweep 2440–2480 MHz. A 3.75 m range cell is a
  small fraction of a large scene. Do **not** take that option in a bedroom: a
  4 m room is one range cell deep at 40 MHz.
