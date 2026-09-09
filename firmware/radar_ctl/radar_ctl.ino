/*
 * radar_ctl.ino — the radar's control ESP32 (NOT the drone).
 *
 * Replaces the MIT design's XR-2206 ramp generator + analog VCO with an
 * ADF4351 PLL board stepped over SPI, and adds the azimuth drive for the
 * scanning stages. Three jobs:
 *
 *   1. SWEEP   step the ADF4351 from F_START to F_START+BW in N_STEPS, over
 *              and over. This is the FMCW chirp. Stepped, not analog: every
 *              step is locked to the board's 25 MHz TCXO, so sweep
 *              linearity is not a tuning problem any more.
 *   2. SYNC    drive SYNC_PIN HIGH for the whole up-chirp and LOW during the
 *              retrace. Goes (through a 10k/1k divider) into the sound
 *              card's RIGHT channel so the host can cut the beat signal into
 *              chirps and measure the true chirp time. Same scheme as MIT.
 *   3. AZ      point the horn pair: A4988 stepper (default) or hobby servo.
 *
 * Serial protocol, 115200 8N1, one command per line:
 *   ?              -> status JSON  (boots with RF OFF and sweep stopped)
 *   SWEEP 0|1      -> stop (RF off) / start chirping
 *   CW <MHz>       -> park the synthesiser on one frequency, RF on (antenna tests)
 *   RFOFF          -> RF output off
 *   AZ <deg>       -> move to azimuth, replies "OK AZ <deg>" when settled
 *   HOME           -> AZ 0
 *   SET steps <n>  -> steps per chirp     (8..256)
 *   SET step_us <n>-> dwell per step, us  (40..2000)
 *   SET retrace_us <n>
 *   SWMODE 0|1   -> stage 2 switched azimuth: alternate the RX antennas chirp
 *                   by chirp on PIN_RXSEL and mark each block with a skipped
 *                   chirp so the laptop can tell the antennas apart
 *   SWBLOCK <n>  -> chirps per marker, match radar_acquire.py --n-chirps
 *   SET f0_mhz <f> / SET bw_mhz <b>  -> sweep edges (kept inside 2400-2483.5)
 *
 * Wiring (ESP32 devkit, VSPI):
 *   ADF4351  CLK -> GPIO18   DATA -> GPIO23   LE -> GPIO5   CE -> 3V3
 *            LD  -> GPIO19 (optional, lock detect)   board 5V in <- 5 V
 *   SYNC     GPIO25 -> 10k -> sound card R tip ; 1k from tip to GND
 *   A4988    STEP GPIO26  DIR GPIO27  EN GPIO14 (LOW = enabled)  [optional turntable]
 *   RX SW    GPIO32 -> SPDT RF switch select (LOW = antenna A)  [SWMODE builds]
 *   Servo    GPIO26 (if AZ_MODE_SERVO)
 *
 * Board: "ESP32 Dev Module" in Arduino IDE with the esp32 core (2.x or 3.x).
 * The ADF4351 is 3.3 V logic — do not level-shift.
 */

#include <SPI.h>

// ---------------- configuration ----------------
#define F_REF_HZ        25000000ULL   // the board's TCXO; check yours (25 MHz is usual)
#define ISM_LO_HZ       2400000000ULL // 2.4 GHz ISM band edges: the sweep never leaves them
#define ISM_HI_HZ       2483500000ULL
// Default sweep: 2400-2480 MHz. The top 3.5 MHz of the ISM band is left as
// an emission-mask margin (a CW tone parked at 2483.5 has no allowance for
// phase noise or spurs). If the drone is flown over its own WiFi AP (phone
// control), park the AP on channel 1 and sweep ABOVE it with a guard band:
//   SET f0_mhz 2440  /  SET bw_mhz 40      (docs/drone-software.md)
// The last step sits at f_start + bw - bw/N_STEPS, so the slope is exactly
// bw / T_up and the software's beat->range scale needs no N/(N-1) fudge.
#define F_START_HZ      2400000000ULL
#define SWEEP_BW_HZ     80000000ULL
#define ISM_MARGIN_HZ   3500000ULL    // sweep top must stay <= 2483.5 - this
#define MOD_DEFAULT     4000          // fractional modulus -> 6.25 kHz resolution

#define AZ_MODE_STEPPER 1             // 1 = A4988 stepper, 0 = hobby servo
#define STEPS_PER_DEG   8.889f        // 200 steps x 16 microsteps / 360 = 8.889 (1:1 turntable)
#define AZ_LIMIT_DEG    90.0f
#define STEP_PULSE_US   400           // stepper speed; ~280 deg/s at 8.9 steps/deg

// pins
#define PIN_SCK   18
#define PIN_MOSI  23
#define PIN_LE     5
#define PIN_LD    19
#define PIN_SYNC  25
#define PIN_STEP  26
#define PIN_DIR   27
#define PIN_EN    14
#define PIN_SERVO 26
#define PIN_RXSEL 32           // stage 2, SWITCHED build: SPDT RF switch select.
                               // LOW = antenna A, HIGH = antenna B.
// -----------------------------------------------

static uint64_t f_start    = F_START_HZ;
static uint64_t sweep_bw   = SWEEP_BW_HZ;
static uint16_t n_steps    = 64;      // 64 steps x 100 us = 6.4 ms up-chirp
static uint32_t step_us    = 100;     // PLL relock per step; see docs/radar-software.md
static uint32_t retrace_us = 1000;    // hold at F_START between chirps
// ---- stage 2, SWITCHED azimuth build ----
// One receive chain, an RF switch alternating antennas chirp by chirp. The
// laptop has to know WHICH antenna each chirp came from, and a block of audio
// starts at an arbitrary point in the alternation, so parity cannot be
// recovered from the data: read B as A and every bearing comes out negated.
// The marker below fixes that. Once per block the sweep SKIPS one chirp --
// SYNC stays low for a whole extra PRI -- and the switch then returns to
// antenna A. That doubled gap is unmistakable in the edge times, and
// ground_station/interferometer.py:tdm_parity() keys off it.
// Costs one chirp in 65, which is 1.5 % of the dwell.
static bool     sw_mode      = false;   // SWMODE 1 to enable
static uint16_t sw_block     = 64;      // chirps per marked block (match --n-chirps)
static uint16_t sw_count     = 0;       // chirps since the last marker
static bool     sw_ant_b     = false;   // which antenna is selected right now
static bool     sweeping   = false;   // boot SILENT: RF output off until SWEEP 1 / CW
static bool     rf_on      = false;
static float    az_deg     = 0.0f;
static long     az_steps   = 0;

// ---------------- ADF4351 ----------------
// Register images. Only R0 changes per step; everything else is fixed for
// a 25 MHz PFD, fundamental feedback, output divider 1, +5 dBm out.
static uint32_t reg_r0(uint32_t INT, uint32_t FRAC) {
  return (INT << 15) | (FRAC << 3) | 0x0;
}
static uint32_t reg_r1(uint32_t MOD) {
  // prescaler 8/9 (INT >= 75 is guaranteed here), phase = 1
  return (1UL << 27) | (1UL << 15) | (MOD << 3) | 0x1;
}
static const uint32_t R2 = (0UL << 29)     // low-noise mode
                         | (6UL << 26)     // MUXOUT = digital lock detect
                         | (1UL << 14)     // R counter = 1  -> PFD = 25 MHz
                         | (7UL << 9)      // charge pump 2.5 mA: faster lock
                         | (1UL << 6)      // PD polarity positive (passive loop filter)
                         | 0x2;
static const uint32_t R3 = (1UL << 23)     // band-select clock mode: HIGH (fast)
                         | (150UL << 3)    // clock divider value (unused, CLK DIV mode off)
                         | 0x3;
static const uint32_t R4_BASE = (1UL << 23) // feedback: fundamental
                         | (0UL << 20)     // RF divider 1  (2.2-4.4 GHz direct)
                         | (50UL << 12)    // band-select clock div: 25 MHz/50 = 500 kHz
                         | (3UL << 3)      // output power +5 dBm
                         | 0x4;
static uint32_t reg_r4(bool rf_enable) { return R4_BASE | ((rf_enable ? 1UL : 0UL) << 5); }
static const uint32_t R5 = 0x00580005UL;   // LD pin = digital lock detect

static void adf_write(uint32_t v) {
  digitalWrite(PIN_LE, LOW);
  SPI.transfer((v >> 24) & 0xFF);
  SPI.transfer((v >> 16) & 0xFF);
  SPI.transfer((v >>  8) & 0xFF);
  SPI.transfer( v        & 0xFF);
  digitalWrite(PIN_LE, HIGH);        // latch on LE rising edge
  delayMicroseconds(1);
  digitalWrite(PIN_LE, LOW);
}

// f -> (INT, FRAC) at the current MOD. f must be 2200-4400 MHz (divider 1).
static void adf_tune(uint64_t f_hz) {
  uint32_t INT  = (uint32_t)(f_hz / F_REF_HZ);
  uint64_t rem  = f_hz - (uint64_t)INT * F_REF_HZ;
  uint32_t FRAC = (uint32_t)((rem * MOD_DEFAULT + F_REF_HZ / 2) / F_REF_HZ);
  if (FRAC >= MOD_DEFAULT) { FRAC = 0; INT++; }
  adf_write(reg_r0(INT, FRAC));      // R0 write also triggers VCO band select
}

static void adf_rf(bool on) {
  rf_on = on;
  adf_write(reg_r4(on));            // RF output enable lives in R4
}

static void adf_init() {
  adf_write(R5); adf_write(reg_r4(false)); adf_write(R3); adf_write(R2);
  adf_write(reg_r1(MOD_DEFAULT));
  adf_tune(f_start);                // locked and parked, output OFF
}

// ---------------- azimuth ----------------
#if !AZ_MODE_STEPPER
static void servo_write_deg(float deg) {
  // 50 Hz, 1000..2000 us over -90..+90
  uint32_t us = (uint32_t)(1500.0f + deg * (500.0f / 90.0f));
  ledcWrite(0, (uint32_t)((us / 20000.0f) * 65535.0f));
}
#endif

static void az_goto(float deg) {
  if (deg >  AZ_LIMIT_DEG) deg =  AZ_LIMIT_DEG;
  if (deg < -AZ_LIMIT_DEG) deg = -AZ_LIMIT_DEG;
#if AZ_MODE_STEPPER
  long target = lroundf(deg * STEPS_PER_DEG);
  long delta  = target - az_steps;
  digitalWrite(PIN_EN, LOW);
  digitalWrite(PIN_DIR, delta >= 0 ? HIGH : LOW);
  delayMicroseconds(5);
  for (long i = 0; i < labs(delta); i++) {
    digitalWrite(PIN_STEP, HIGH); delayMicroseconds(STEP_PULSE_US / 2);
    digitalWrite(PIN_STEP, LOW);  delayMicroseconds(STEP_PULSE_US / 2);
  }
  az_steps = target;
  az_deg = az_steps / STEPS_PER_DEG;
  delay(120);                        // let the horns stop ringing before the dwell
#else
  servo_write_deg(deg);
  az_deg = deg;
  delay(350);                        // servo settle
#endif
}

// ---------------- sweep ----------------
static void one_chirp() {
  const uint64_t df = sweep_bw / (uint64_t)n_steps;   // exact slope bw/T_up
  digitalWrite(PIN_SYNC, HIGH);
  uint32_t t0 = micros();
  for (uint16_t k = 0; k < n_steps; k++) {
    adf_tune(f_start + df * k);
    // hold the step for step_us measured from the chirp start, so SPI time
    // does not stretch the chirp
    while ((int32_t)(micros() - (t0 + (uint32_t)step_us * (k + 1))) < 0) { }
  }
  digitalWrite(PIN_SYNC, LOW);
  adf_tune(f_start);
  delayMicroseconds(retrace_us);

  if (sw_mode) {
    if (++sw_count >= sw_block) {
      // block marker: hold SYNC low for one whole extra chirp period, then
      // restart the alternation on antenna A. The receiver finds this gap and
      // uses it to tell the two antennas apart.
      sw_count = 0;
      delayMicroseconds((uint32_t)n_steps * step_us + retrace_us);
      sw_ant_b = false;
    } else {
      sw_ant_b = !sw_ant_b;
    }
    digitalWrite(PIN_RXSEL, sw_ant_b ? HIGH : LOW);
  }
}

static float chirp_ms() { return n_steps * step_us / 1000.0f; }

static void status() {
  Serial.printf("{\"fw\":\"radar_ctl\",\"f0_mhz\":%.1f,\"bw_mhz\":%.1f,\"steps\":%u,"
                "\"step_us\":%lu,\"t_chirp_ms\":%.3f,\"retrace_us\":%lu,"
                "\"sweep\":%d,\"rf\":%d,\"az\":%.2f,\"lock\":%d,"
                "\"sw_mode\":%d,\"sw_block\":%u}\n",
                f_start / 1e6, sweep_bw / 1e6, n_steps,
                (unsigned long)step_us, chirp_ms(), (unsigned long)retrace_us,
                sweeping ? 1 : 0, rf_on ? 1 : 0, az_deg, digitalRead(PIN_LD),
                sw_mode ? 1 : 0, sw_block);
}

static void handle(String line) {
  line.trim();
  if (line.length() == 0) return;
  if (line == "?") { status(); return; }
  if (line.startsWith("SWEEP")) {
    sweeping = line.substring(5).toInt() != 0;
    digitalWrite(PIN_SYNC, LOW); adf_tune(f_start);
    adf_rf(sweeping);                 // SWEEP 0 = RF output off, not just parked
    Serial.printf("OK SWEEP %d\n", sweeping ? 1 : 0); return;
  }
  if (line.startsWith("CW")) {
    double mhz = line.substring(2).toFloat();
    if (mhz < 2400 || mhz > 2483.5) { Serial.println("ERR CW must be inside 2400-2483.5 MHz"); return; }
    sweeping = false; digitalWrite(PIN_SYNC, LOW);
    adf_tune((uint64_t)(mhz * 1e6)); adf_rf(true);
    Serial.printf("OK CW %.3f\n", mhz); return;
  }
  if (line == "RFOFF") { sweeping = false; digitalWrite(PIN_SYNC, LOW); adf_rf(false); Serial.println("OK RFOFF"); return; }
  if (line.startsWith("SWMODE")) {                 // stage 2, switched azimuth
    int v = line.substring(6).toInt();
    sw_mode = (v != 0);
    sw_count = 0; sw_ant_b = false;
    digitalWrite(PIN_RXSEL, LOW);
    Serial.printf("OK SWMODE %d (block %u; run radar_acquire.py --switched)\n",
                  sw_mode ? 1 : 0, sw_block);
    return;
  }
  if (line.startsWith("SWBLOCK")) {                // chirps per marker; match --n-chirps
    int v = line.substring(7).toInt();
    if (v < 8 || v > 1024) { Serial.println("ERR SWBLOCK 8..1024"); return; }
    sw_block = (uint16_t)v; sw_count = 0;
    Serial.printf("OK SWBLOCK %u\n", sw_block); return;
  }
  if (line.startsWith("AZ")) {
    float d = line.substring(2).toFloat();
    bool was = sweeping; sweeping = false; digitalWrite(PIN_SYNC, LOW);
    az_goto(d);
    sweeping = was;
    Serial.printf("OK AZ %.2f\n", az_deg); return;
  }
  if (line == "HOME") { handle("AZ 0"); return; }
  if (line.startsWith("SET")) {
    int sp = line.indexOf(' ', 4);
    String key = line.substring(4, sp), val = line.substring(sp + 1);
    long v = val.toInt();
    if (key == "f0_mhz" || key == "bw_mhz") {
      // sweep edges: validated together so the sweep can never leave ISM
      uint64_t f0 = f_start, bw = sweep_bw;
      if (key == "f0_mhz") f0 = (uint64_t)(val.toFloat() * 1e6);
      else                 bw = (uint64_t)(val.toFloat() * 1e6);
      if (f0 < ISM_LO_HZ || f0 + bw > ISM_HI_HZ - ISM_MARGIN_HZ || bw < 10000000ULL) {
        Serial.println("ERR sweep must stay within 2400-2480 MHz (3.5 MHz top margin), bw >= 10"); return;
      }
      f_start = f0; sweep_bw = bw; adf_tune(f_start);
      Serial.printf("OK SET %s %.1f\n", key.c_str(), key == "f0_mhz" ? f0 / 1e6 : bw / 1e6); return;
    }
    if (key == "steps" && v >= 8 && v <= 256)          n_steps = v;
    else if (key == "step_us" && v >= 40 && v <= 2000) step_us = v;
    else if (key == "retrace_us" && v >= 100 && v <= 20000) retrace_us = v;
    else { Serial.println("ERR SET steps|step_us|retrace_us|f0_mhz|bw_mhz"); return; }
    Serial.printf("OK SET %s %ld\n", key.c_str(), v); return;
  }
  Serial.println("ERR ? SWEEP CW AZ HOME SET");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LE, OUTPUT);   digitalWrite(PIN_LE, LOW);
  pinMode(PIN_LD, INPUT);
  pinMode(PIN_SYNC, OUTPUT); digitalWrite(PIN_SYNC, LOW);
  pinMode(PIN_RXSEL, OUTPUT); digitalWrite(PIN_RXSEL, LOW);   // antenna A
#if AZ_MODE_STEPPER
  pinMode(PIN_STEP, OUTPUT); pinMode(PIN_DIR, OUTPUT); pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, LOW);
#else
  ledcSetup(0, 50, 16); ledcAttachPin(PIN_SERVO, 0);
  servo_write_deg(0);
#endif
  SPI.begin(PIN_SCK, -1, PIN_MOSI, PIN_LE);
  SPI.beginTransaction(SPISettings(10000000, MSBFIRST, SPI_MODE0));
  delay(50);
  adf_init();
  delay(20);
  status();
}

static String buf;

void loop() {
  if (sweeping) one_chirp();
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { handle(buf); buf = ""; }
    else if (buf.length() < 64)  buf += c;
  }
  if (!sweeping) delay(2);
}
