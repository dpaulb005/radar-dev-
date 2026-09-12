# stage2/ — azimuth. Written, passing, not built.

Stage 1 is the radar that exists: **one TX horn, one RX horn**, which gives
**range and radial velocity** and nothing else. All of that lives in
`../ground_station`.

Stage 2 adds **a second RX horn** and reads **azimuth from the phase between
the two receivers** inside a single dwell. None of it is built yet — it needs
the second horn, a second receive chain (or an RF switch) and a four-input
interface that puts beat A, beat B and sync on one sample clock. The code is
here, and it passes its own suite, because it was written and measured against
the simulator before the parts were ordered; quarantining it was cheaper than
deleting work that is correct.

Nothing in `../ground_station` imports anything from this directory. The
dependency runs one way only.

## Files

| file | what it is |
| --- | --- |
| `interferometer.py` | The heart of stage 2: bearing from the phase difference at one range-Doppler cell, the ±π ambiguity cone, the calibration constant for the fixed chain offset, the TDM (switched) split and its motion correction, and the quality gate that makes it **abstain** instead of guessing. `--selftest` runs 26 unit checks. |
| `acquire_az.py` | The live CLI with azimuth: the azimuth half of `radar_acquire.py`, taken out when stage 1 was cut back. `--interferometer` (two chains, simultaneous), `--switched` (one chain, RF switch), `--calibrate`. `--selftest` needs no hardware. |
| `scanning.py` | `ScanningRadar`: step the beam across a sector, detect per dwell, and `centroid()` the amplitude across beams into an azimuth. The *old* way of getting bearing, kept because it models a hovering target correctly — a scan takes seconds, so it needs the drone slower than ~0.1 m/s. |
| `radar_twin.py` | The digital-twin demo built on `scanning.py`: one sweep, a PPI plot, or `--track N` for N seconds of scanning plus Kalman tracking (~0.09 m RMS). |
| `scan_design.py` | Sizing a scan: beamwidth, beam step, dwell, sweep time, revisit rate, and the interferometer ambiguity detail (`--interf`). No dependencies. |
| `sar.py` | Synthetic aperture along a rail: design numbers, simulation and back-projection imaging. Design and simulation only. |
| `patch24.py` | The 24 GHz study (moved out of `antenna/`): a 4-patch column, its feed and match, the board, and why λ/2 at 24 GHz makes the interferometer unambiguous across the whole pattern. |
| `test_stage2.py` | The stage-2 suite: `geometry`, `azimuth`, `calibration`, `refusal`, `limits`. No hardware, no pytest, no network. |

## Running it

```sh
cd stage2
python3 test_stage2.py            # the suite; exit 0 means all 27 cases pass
python3 interferometer.py --selftest
python3 acquire_az.py --selftest --st-az -8 --st-vel -1.8
python3 acquire_az.py --selftest --switched --st-az 12 --st-vel 0.9
python3 radar_twin.py --track 20
python3 sar.py --selftest
python3 patch24.py --selftest
python3 scan_design.py
```

## How it depends on stage 1

Every module here that needs stage-1 code does the same plain thing at the top
of the file:

```python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "ground_station"))
```

and then imports normally. There is no package, no installation step and no
`PYTHONPATH` to set; the only requirement is that `stage2/` stays a sibling of
`ground_station/`. What it imports from there:

* `fmcw_sim` — `RadarSpec`, `range_doppler`, `simulate`, and
  `DEFAULT_BASELINE_M = 0.1931` (the horns' E-plane aperture, i.e. how close
  two rotated horns can sit). That constant is **defined once**, in stage 1, and
  `interferometer.py` imports it from there.
* `dsp` — `cfar_detect`, `beam_gain`. Stage 1 owns the detector.
* `synth` — `SynthSource`, `segment_chirps`. One signal generator for both
  stages. Its `n_rx`, `switched`, `cal_rad`, `marker` and `baseline_m`
  parameters exist for *this* directory; stage 1 always passes `n_rx=1`, which
  makes them inert.
* `radar_acquire` — `AudioSource`, `WavSource`, `Ctl`, `post_fix`.
* `tracker` — `TrackKF`, for the twin's tracking demo.

## Bringing it back

1. Build the second receive chain: the second RX horn (rotated 90°, E-plane
   apertures touching, 193.1 mm between centres), its LNA and mixer, and a
   four-input interface, of which three channels are used — beat A, beat B and
   sync (one UMC404HD, not two UCA202s — two cards cannot hold
   phase). The switched variant instead needs one chain plus an RF switch, and
   `radar_ctl` flashed with `SWMODE 1` so the sync carries the frame marker.
2. Match the coax: `interferometer.py` reports 0.43° of bearing per mm of cable
   mismatch, so the 2.5° budget is about 6 mm.
3. Calibrate once against a boresight reflector:
   `python3 acquire_az.py --interferometer --calibrate --cal-az 0` writes
   `interferometer_cal.json`, which later runs reload.
4. Run `python3 acquire_az.py --interferometer --server http://HOST` for live
   bearings. Note that its POST body is the *old* fix-shaped payload
   (`{x, y, range, az, vel, snr, beams, t}`); stage 1 now posts the range-Doppler
   payload documented in the repo README, so the console's `/api/radar` has to
   learn the azimuth shape again before this is wired back in.
5. Fold the bearing into the console and the tracker, and move `azimuth`,
   `calibration`, `refusal` back into the main suite if stage 2 becomes the
   build that ships.
