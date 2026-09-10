# Archive — background, history, superseded plans

Kept because the numbers in the live guides were derived here. Not needed to
build or test the radar.

**Analyses behind the current design**
- `scanning.md` — why one TX + one RX horn gives range only; beam-step sizing (12°, 3× oversample); the 0.12 m twin result
- `antenna.md` — the optimum pyramidal horn, pe == ph, aperture bound, HFSS/openEMS methodology
- `tracking.md` — the Kalman filter and when it beats an EMA
- `mit-radar.md` — the original build plan and its constraints (band, ISM edge, jamming)
- `LLM-DESIGN-PROMPT.md` — prompt pack for a design partner; §3 is the full horn test plan
- `reviews/radar-carrier-v1.md` — review of an external carrier-PCB package (it found four errors in our numbers, since fixed)

**Fallbacks and alternatives**
- `drone-915.md`, `drone-915-esp-fc.md` — **promoted** to `docs/drone-link.md` and `docs/drone-link-espfc.md`: the 915 MHz control link is now the plan, not the fallback
- `mmwave.md` — 60 GHz module path (the likely phase 2 for a radar that can fly)
- `ROADMAP-experimental.md`

**The passive RF system this project replaced** (sniffer nodes multilaterating the drone's own WiFi; ~2 m accuracy, could not see altitude)
- `feasibility.md`, `espfly.md`, `espblast.md`, `SETUP.md`, `BUILD.md`, `3d-sensing.md`, `interception.md`
- code: `firmware/archive/{drone_beacon,rx_node,rx_node_ftm,hub_node,mac_scanner,commander}` (moved out of the live firmware tree), `ground_station/{locate,calibrate,geometry,guidance,pursuit_sim,autopilot,digital_twin}.py` (still imported by the console)
- `firmware/archive/espfly-915/` — **promoted** to `firmware/espfly-915/`
