# The front end

Everything between the antenna and the sound card, which at 24 GHz is one chip
instead of eight coax modules.

---

## What the 2.4 GHz chain becomes

```
  2.4 GHz, as built                          24 GHz
  ─────────────────────────────────────      ────────────────────────────
  ADF4351 PLL board            $27       ┐
  3 dB SMA pad                  $9       │
  SPF5189Z PA                   $6       │
  2-way splitter               $13       ├─►  BGT24LTR22          $15.26
  ZX05-43MH mixer              $73       │    ADF4159 ramp PLL    $20.48
  SPF5189Z LNA                  $6       │    (both on the antenna board)
  2400-2500 band-pass          $29       │
  SMA jumpers + adapters       $30       ┘
  three folded horns           $95       ───►  printed on the same board
  TL072 video amp               $8       ───►  integrated baseband, on the die
  ─────────────────────────────────────
                              ~$296            ~$36 of silicon
```

The band-pass disappears with the band: there is no WiFi at 24 GHz, so there is
nothing to reject and nothing to protect the receiver from.

The video amplifier disappears into the MMIC. The BGT24LTR22's integrated
analog baseband is a high-pass with selectable 20/50/80/100 kHz corners, a
variable gain amplifier adjustable to 30 dB in 5 dB steps, and a 600 kHz
anti-alias filter — which is a better version of the TL072 stage in
[`../radar-hardware.md`](../radar-hardware.md), programmable over SPI, and
already inside the part.

---

## Why the BGT24LTR22

Four candidate architectures, judged against the same three tests as everything
else in this repo, plus one more: *does the data still come out as analog IF?*
Because if it does not, the entire DSP this project has written stops being
reachable.

| | BGT24LTR11 | **BGT24LTR22** | BGT24ATR22 | ADF5901+5904+4159 |
|---|---|---|---|---|
| price qty 1 | $6.41 | **$15.26** | $11.49 | $149.05 |
| stock (Sept 2026) | yes | **1580** | 130 | yes |
| TX / RX | 1 / 1 | **2 / 2** | 2 / 2 | 2 / 4 |
| receivers simultaneous? | — | **yes** | **no** — combined into one mixer | yes |
| analog IF on pins? | yes | **yes, differential I and Q** | **no** — "DFT not recommend to be used by customers" | yes |
| ramp control | VTUNE + /16 divider | **VTUNE + /16 divider, driver sized for an external PLL** | VTUNE + /16, internal AFC | ADF4159 + /2 |
| package | TSNP-16 | **eWLB-52, 3.63 mm** | VQFN-32 | 3 × LFCSP |
| azimuth possible? | **no** | **yes** | only by interleaving | yes, 4 channels |

**BGT24LTR11 is out on one receiver.** One receiver is one phase measurement,
and one phase measurement is not an interferometer. Two chips would be two
free-running VCOs with no common phase reference, which is worse than useless.

**BGT24ATR22 is out on the IF pins**, and this is the finding that took the
longest to establish. It looks ideal on paper — 2 TX, 2 RX, VQFN-32 you could
hand-solder, an integrated 12-bit ADC, $11.49. Then the pin table says IFI and
IFQ are *"DFT not recommend to be used by customers"*, so the only way data
leaves the chip is through its internal ADC over a **400 kbit/s I²C** bus, out
of a sequencer and an on-chip FFT unit designed for kick sensors. Its two
receivers are also combined into a single mixer and meant to be interleaved.
Choosing it would mean deleting the video amplifier, the sound card, the
segmentation, the range-Doppler processing and the interferometer, and writing
somebody else's frame format instead. That is a different project.

**The Analog Devices chipset works** and gives four receivers, which would
support two independent baselines. It costs $149 against $36 and adds two more
fine-pitch parts to place. Worth revisiting if two receivers ever turn out not
to be enough; not the place to start.

**BGT24MTR12 is what everybody used** — 1 TX, 2 RX, two independent IQ
receivers, a /64 divider sized for the ADF4159, and the part behind Infineon's
own Distance2Go reference. It is marked **obsolete** at DigiKey. The LTR22 is
its replacement and is strictly better here (2 TX, selectable divider ratios,
integrated baseband).

### The datasheet lines this decision rests on

From the BGT24LTR22 user guide, revision 1.30:

- *"Two single-ended transmit (TX) channels … up to +5 dBm typical output power"*
- *"Two single-ended receive (RX) channels … typical maximum voltage conversion
  gain 26 dB, with typical single-sideband noise figure 8 dB"*
- *"The chip features **two quadrature receiver stages**. Each receive section
  uses a low-noise amplifier in front of a quadrature homodyne down conversion
  mixer"* — simultaneous, not interleaved
- *"For frequency stabilization and **FMCW ramp generation**, the chip includes
  a frequency divider block … A driver amplifier in the divider circuit ensures
  that the divider provides sufficient output power to drive the **external
  RF-PLL chip** under all operating conditions"*
- *"Integrated ABB section for FMCW radar application — high-pass filter with
  tunable cut-off … variable-gain amplifiers with up to 30 dB gain … anti-aliasing
  filter with 600 kHz cut-off"*
- *"Excellent on-chip TX-to-RX isolation above 40 dB"*
- *"Single supply voltage 1.5 V"*
- IF pins: `IF1I/IF1Ix`, `IF1Q/IF1Qx`, `IF2I/IF2Ix`, `IF2Q/IF2Qx` —
  *"Complementary … downconverter IF output … DC coupled"*

**"Single-ended" is the word that matters.** The RF terminals are 50 Ω pins
meant for a microstrip trace on the board they are soldered to. That is why
this project can own the antenna at 24 GHz at all.

---

## Generating the ramp

The current build steps an ADF4351 through 64 discrete frequencies over SPI,
because a stepped PLL is linear by construction and needs no calibration
([`../signal-chain.md`](../signal-chain.md) § the one idea). That architecture
ports directly.

```
   ESP32 ──SPI──► ADF4159 ─┬─ charge pump ─► loop filter ─► VTUNE ─► BGT24LTR22
     │                     │                                            │
     │                     └──────── RF input ◄── DIV_AO ── /16 ────────┘
     │                                            1.508 GHz
     └──► SYNC out ────────────────────────────────────────► interface ch 3
```

The MMIC's VCO runs free at 24 GHz; the /16 divider brings it down to
**1.508 GHz**, comfortably inside the ADF4159's 13 GHz input range, and the
PLL closes the loop back onto VTUNE. This is Infineon's own recommended
topology and the reason the divider exists.

Two ways to drive it, and the choice is not obvious:

| | stepped, as today | ADF4159's internal ramp |
|---|---|---|
| how | ESP32 writes 64 frequencies | ESP32 arms one ramp, hardware sweeps it |
| linearity | exact by construction | exact by construction |
| firmware change | small — same loop, different registers | larger, but simpler steady state |
| SPI traffic | 64 writes per 1.4 ms chirp | one arm per chirp |

At 6.4 ms per chirp the ESP32 has 100 µs per step and that is comfortable. At
**1.4 ms** it has **21.9 µs**, which is tight for an SPI write plus PLL settling.
The ADF4159's internal ramp generator exists precisely for this and is the
better answer at 24 GHz — but it is a real firmware rewrite, not a port, and
that should be said plainly rather than discovered later.

Either way the **sync channel stays**. The DSP measures T_up and PRI from it
every block ([`../radar-software.md`](../radar-software.md)) because the sound
card's clock and the radar's clock are independent, and that is still true.

---

## The IF path, and the one thing that does not fit

The BGT24LTR22 gives **four** analog signals for azimuth — RX1 I, RX1 Q, RX2 I,
RX2 Q — all differential, all DC-coupled. Plus the sync channel makes five. The
UMC404HD has four inputs.

| option | inputs | what you get | cost |
|---|---|---|---|
| **A. I only from each receiver, plus sync** | 3 of 4 | exactly today's real-valued beat, full azimuth, 0.60 m cells. Doppler sign still ambiguous | **$0** |
| B. all four IF channels, no sync | 4 of 4 | signed Doppler and 3 dB of image rejection, but chirp timing has to be trusted rather than measured | $0 |
| C. eight-input interface | 5 of 8 | everything | ~$300 |

**Start with A.** It is the configuration the DSP already expects, it needs no
new hardware, and it still delivers the two things this build is for: a 0.60 m
range cell and azimuth unambiguous over the whole pattern. Option B trades a
measured clock for a signed velocity, which is the wrong trade given the sync
channel is what makes the range scale trustworthy. Option C is right eventually
and can wait until A is working.

The IF outputs are differential and DC-coupled, so each channel needs a series
DC block and an attenuator into the interface's balanced input. That is two
capacitors and two resistors per channel, and it is the whole interface
circuit — the amplification is already done on the die.

---

## Power, clock and the rest of the board

| | |
|---|---|
| **1.5 V** | single supply for the MMIC. Needs a low-noise LDO with good PSRR — VCO phase noise lands directly in the beat spectrum |
| **3.3 V** | ADF4159 and the ESP32 side |
| **reference** | 25 MHz TCXO into the ADF4159's REFIN. The ADF4351 board's 25 MHz TCXO is the same part and the same choice |
| **loop filter** | passive third-order between the ADF4159's charge pump and VTUNE; a handful of 0402s, values from ADIsimPLL |
| **SPI** | ESP32 → ADF4159. The MMIC's own control is SPI too, from the same bus with a second chip select |
| **13 V input, fuse, reverse protection** | unchanged from [`../radar-hardware.md`](../radar-hardware.md) |

Nothing here is exotic. The exotic part is that all of it shares a board with
antennas that care about every millimetre of copper around them, which is why
the antenna geometry in [`antenna.md`](antenna.md) fixes the board outline
before the supporting circuitry gets placed, not after.
