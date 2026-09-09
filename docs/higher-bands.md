# What K-band or V-band would cost

> **Read [`goal.md`](goal.md) first.** This project's point is a radar whose
> antenna you designed. Every module priced below ships with its antenna
> already designed and soldered shut, so none of them passes that test on its
> own. The costs here are real and worth knowing; the recommendation at the
> bottom has been corrected accordingly.

Kevin's suggestion, in his words: *"consider other antenna designs that might be
more conducive to drone platforms, especially when considering size and weight…
I've seen other DIY drone radar applications in the higher frequency ranges.
Typically either K band or V band. Electrically smaller antennas with more
narrow beams. Less interference potential."*

He is right on every count, and the honest answer on cost is **$60 for the
cheapest useful version, up to $1,271 for the one that keeps this project's
character.** Which number applies depends entirely on whether you still want to
write the signal processing yourself.

Prices are US street, checked September 2026.

---

## What the physics actually buys

| | 2.4 GHz, now | 24 GHz (K) | 60 GHz (V) |
|---|---|---|---|
| wavelength | 121.9 mm | 12.4 mm | 4.9 mm |
| usable bandwidth | 40 MHz (83.5 without the drone's WiFi) | 250 MHz | 4 GHz and up |
| **range cell** | **3.75 m** | **0.60 m** | **0.04 m** |
| horn for the same 13.4 dBi | 263 × 193 mm | **27 × 20 mm** | **11 × 8 mm** |
| gain if you kept a 264 × 193 mm aperture | 13.4 dBi, 32° | 33.3 dBi, 3.3° | 41.4 dBi, 1.3° |
| WiFi in the band | yes, and it is the drone's own link | no | no |

Three of those matter enough to restate.

**Range resolution improves six-fold at 24 GHz and a hundred-fold at 60.** The
3.75 m cell is the single worst number in the current design — a drone and the
wall behind it land in the same cell. At 24 GHz they do not.

**The interference problem disappears.** There is no WiFi at 24 or 60 GHz, so
the entire coexistence story goes away: no band-pass filter, no turning the
drone's access point down to 10 dBm, no giving up half the sweep. And that last
one is what caused the azimuth variance problem in the first place, because
halving the bandwidth pushed the target from 5.3 FFT bins from DC to 2.7
([`signal-chain.md`](signal-chain.md) § stage 10).

**Smaller antennas cost echo, but you have it to spare.** The radar equation
carries a λ² term, so at the same antenna *gain* a 24 GHz echo is 19.8 dB weaker
and a 60 GHz one 28 dB weaker. Against the 54 dB the link has at 10 m that
leaves 34 dB and 26 dB. Both close comfortably. The trade only bites if you also
want much more range.

---

## Four ways to do it, costed

### A. 24 GHz, one module, range and velocity — **$60**

An RFbeam K-LC6 is a complete 24 GHz transceiver on one board: patch antenna
array, transmitter, low-noise amplifier, mixer, quadrature IF outputs, and an FM
input for FMCW. It replaces the entire 2.4 GHz RF chain — PLL, pad, amplifier,
splitter, mixer, LNA, band-pass and both horns — with a single part.

| item | $ |
|---|---|
| RFbeam K-LC6 (DigiKey) | 55 |
| MCP4725 12-bit DAC to drive the FM tuning input | 5 |
| **total** | **60** |

Everything else you have already built and tested is reused unchanged: the video
amplifier, the reference, the power, the sound card, the ESP32, and every line
of the DSP.

Better than what you have now, for free: the K-LC6 gives **I and Q**, not a
single-ended mixer output, so Doppler comes out signed. No more losing the
direction of travel.

**What you give up, and it is real.** The ADF4351 steps a PLL locked to a
25 MHz crystal, so the sweep is exactly linear by construction. The K-LC6's FM
input is an analog VCO tuning voltage, so sweep linearity becomes a calibration
problem again — which is precisely the headache the current design was chosen to
avoid. Budget an evening to characterise the tuning curve and build a lookup
table in `radar_ctl`.

### B. 24 GHz with azimuth — **$110 to $250**

Two K-LC6 modules side by side is the obvious move and it half-works. Each
module is about 25 mm wide, so the closest baseline is 25 mm, which is four
wavelengths, which is unambiguous only to **±14.4°**. Workable only if the
module's beam is narrower than that.

The clean answer is an RFbeam **K-MC4**, a 24 GHz transceiver with **two receive
antennas specifically for angle**, at the right spacing, on one board. Around
$250 (its sibling K-MC1 is $247.84 at DigiKey). That is the interferometer you
just built, integrated, and `interferometer.py` drives it with only the baseline
constant changed.

### C. 60 GHz, point cloud out — **$283**

A TI IWR6843ISK is a 60–64 GHz radar with **3 transmitters and 4 receivers** on
the board, a 120° azimuth field of view, and point-cloud output over USB. It
does range, velocity, azimuth *and* elevation, all of it, with no DSP to write.

$282.98 at DigiKey, though stock was empty when checked with a December 2026
estimate — check Mouser too.

This is the cheapest way to get a working drone tracker and by a wide margin the
best performance. It is also the option that ends the project as a radar
project: you would be integrating someone else's radar rather than building one.
Whether that is a feature depends on what you want out of this.

### D. 60 GHz with raw data — **$1,271**

If you want the IWR6843's raw ADC samples so you can keep writing your own
processing, you need the DCA1000EVM capture card: $987.96 at Mouser.

| item | $ |
|---|---|
| IWR6843ISK | 283 |
| DCA1000EVM | 988 |
| **total** | **1,271** |

That is nearly twice the whole 2.4 GHz build, for the privilege of keeping the
part of the project you have already done.

### Not an option: the $25 modules

Seeed's 60 GHz boards are $24.90 and look tempting. They are fixed-function fall
detection and breathing sensors, tuned for 0.4–6 m on a human torso, with no
meaningful raw access. They will not track a drone at 10 m.

---

## What I would do — corrected

An earlier version of this page recommended option A, the $60 module, on the
grounds that it reuses everything downstream of the mixer. That reasoning is
sound and the conclusion is still wrong, because **the K-LC6's antenna is an
integrated patch array with no external port**. Buying it hands the most
interesting part of this project to RFbeam. Same objection, harder, for the TI
boards: the IWR6843ISK's antenna is etched on its evaluation board and the
AOPEVM's is inside the chip package.

Against [`goal.md`](goal.md)'s first test — *is the antenna mine?* — every
option on this page fails.

What survives is Kevin's physics, which is worth having:

1. **Finish the 2.4 GHz build.** Range, velocity, azimuth. Everything downstream
   of the mixer's IF is band-independent and you only get to write it once. It
   is written and tested.
2. **Then research a 24 GHz front end with an external antenna port.** That is
   the missing piece, and it is the difference between a band swap and a real
   second antenna project. The cheap modules do not have one.
3. **If you find one, design the 24 GHz antenna yourself.** A 27 × 20 mm horn is
   too small to fold from sheet, which is the point: a patch array on $5 FR-4 is
   a deeper design exercise than the horn was, and λ/2 = 6.2 mm spacing gives a
   fully unambiguous interferometer instead of the ±18.4° you have now.

Buy the IWR6843 only if what you want is a drone tracker rather than a radar you
built. It is better than anything on this list, it is available today, and it is
a different project.

---

Sources: [RFbeam K-LC6](https://www.digikey.com/en/products/detail/rfbeam-microwave-gmbh/K-LC6-RFB-00D/13151981),
[K-LC5](https://www.digikey.com/en/products/detail/rfbeam-microwave-gmbh/K-LC5-RFB-00C/13151976),
[K-MC4](https://rfbeam.ch/product/k-mc4-radar-transceiver/),
[K-MC1 price](https://www.digikey.com/en/products/detail/rfbeam-microwave-gmbh/K-MC1-RFB-00D/13151975),
[IWR6843ISK](https://www.digikey.com/en/products/detail/texas-instruments/IWR6843ISK/10434492),
[IWR6843ISK specs](https://www.ti.com/tool/IWR6843ISK),
[DCA1000EVM](https://www.mouser.com/ProductDetail/Texas-Instruments/DCA1000EVM),
[Seeed MR60 modules](https://www.seeedstudio.com/MR60FDA2-60GHz-mmWave-Sensor-Fall-Detection-Module-p-5946.html)
