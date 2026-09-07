/*
 * commander.ino — ground-side "autopilot uplink" for the interceptor drone.
 *
 * This ESP32 is the interceptor's RADIO. It speaks the espnow-rclink
 * *transmitter* protocol (rtlopez/espnow-rclink) to the interceptor's
 * ESP-FC receiver, and it takes its stick commands from the laptop over
 * USB serial. The ground station's guidance loop (ground_station/autopilot.py)
 * computes channel values from the radar fix and streams them here; this
 * firmware relays them to the drone at a steady rate and enforces a
 * fail-safe if that stream stops.
 *
 * IMPORTANT — binding is exclusive: an espnow-rclink receiver binds to the
 * first transmitter it hears after power-up and ignores others until it is
 * power-cycled. So the interceptor must be powered with THIS commander
 * running (and the handheld TX off) so it binds here. Manual override is
 * provided *through* this link (see ARM/MODE channels + the host-side
 * gamepad path in autopilot.py), not by a second transmitter.
 *
 * Serial protocol (115200 baud), one line per update from the host:
 *     C,<ch0>,<ch1>,...,<ch7>\n      set channels (microseconds, 880-2120)
 * e.g.  C,1500,1500,1100,1500,1000,1000,1000,1000
 * Order is whatever your ESP-FC rc map expects (default AETR):
 *     ch0 roll  ch1 pitch  ch2 throttle  ch3 yaw  ch4..7 AUX (arm/mode/...)
 * The host must send at >= 20 Hz; if no valid line arrives for
 * FAILSAFE_MS, the commander drives the fail-safe frame (throttle low,
 * sticks centered, ARM low) so the drone disarms/levels instead of
 * flying blind.
 *
 * Requires the espnow-rclink library installed in the Arduino/PlatformIO
 * project (it pulls in the WifiEspNow dependency).
 */

#include <Arduino.h>
#include <EspNowRcLink/Transmitter.h>

// ---------------- configuration ----------------
#define NUM_CH        8
#define SEND_MS       20        // 50 Hz uplink (matches the tx example)
#define FAILSAFE_MS   200       // no host data for this long -> fail-safe
#define CH_MIN        880
#define CH_MID        1500
#define CH_MAX        2120
// Fail-safe frame: centered sticks, throttle to minimum, all AUX low
// (ch2 = throttle in AETR; adjust if your map differs).
static const unsigned int FAILSAFE[NUM_CH] =
    {CH_MID, CH_MID, CH_MIN, CH_MID, CH_MIN, CH_MIN, CH_MIN, CH_MIN};
// -----------------------------------------------

EspNowRcLink::Transmitter tx;

static unsigned int channels[NUM_CH];
static uint32_t lastHostMs = 0;
static uint32_t lastSendMs = 0;
static uint32_t lastStateMs = 0;
static char line[96];
static uint8_t linePos = 0;

static void applyFailsafe() {
  for (int i = 0; i < NUM_CH; i++) channels[i] = FAILSAFE[i];
}

// Parse "C,1500,1500,..." into channels[]. Returns true on a full valid frame.
static bool parseLine(char *s) {
  if (s[0] != 'C' || s[1] != ',') return false;
  char *p = s + 2;
  for (int i = 0; i < NUM_CH; i++) {
    char *end;
    long v = strtol(p, &end, 10);
    if (end == p) return false;               // no number parsed
    if (v < CH_MIN) v = CH_MIN;
    if (v > CH_MAX) v = CH_MAX;
    channels[i] = (unsigned int)v;
    p = end;
    if (*p == ',') p++;
  }
  return true;
}

static void readHost() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      line[linePos] = '\0';
      if (linePos > 0 && parseLine(line))
        lastHostMs = millis();
      linePos = 0;
    } else if (linePos < sizeof(line) - 1) {
      line[linePos++] = c;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  applyFailsafe();
  // begin(true): bring up the hidden softAP the receiver pairs against.
  if (!tx.begin(true)) {
    Serial.println("# commander: tx.begin failed");
  }
  Serial.println("# commander up. stream 'C,ch0,...,ch7' at >=20Hz.");
}

void loop() {
  tx.update();                 // service the ESP-NOW link every loop
  readHost();

  uint32_t now = millis();
  if (now - lastHostMs > FAILSAFE_MS) applyFailsafe();

  if (now - lastSendMs >= SEND_MS) {
    lastSendMs = now;
    for (size_t c = 0; c < NUM_CH; c++)
      tx.setChannel(c, channels[c]);
    tx.commit();               // queue this channel frame for transmission
  }

  if (now - lastStateMs >= 500) {       // status heartbeat to the host
    lastStateMs = now;
    bool paired = (tx.update() == EspNowRcLink::Transmitter::TRANSMITTING);
    bool fs = (now - lastHostMs > FAILSAFE_MS);
    Serial.printf("# state=%s failsafe=%d\n",
                  paired ? "LINKED" : "DISCOVERING", fs ? 1 : 0);
  }
}
