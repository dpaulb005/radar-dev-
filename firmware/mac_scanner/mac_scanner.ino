/*
 * mac_scanner.ino — helper for finding your drone's MAC and WiFi channel.
 *
 * Flash to any spare ESP32, open the serial monitor at 115200. It sits in
 * promiscuous mode, dwelling DWELL_MS on each channel 1-13, and every pass
 * prints a table of transmitter MACs seen with frame count and average
 * RSSI per channel.
 *
 * How to spot the drone:
 *   - power ONLY the drone (and its transmitter if testing the paired
 *     link) so the airwaves are otherwise your neighbors' steady APs;
 *   - the drone is the MAC whose frame count matches its transmit rate
 *     (5 Hz pair requests unpaired; 1 Hz stock alive; 25 Hz if you applied
 *     the esp-fc patch or use the beacon board — see docs/espblast.md);
 *   - power-cycle the drone and watch that MAC disappear/reappear.
 *
 * Once identified, fix WIFI_CHANNEL in a second run (set SCAN_SINGLE_CHANNEL)
 * to confirm the rate, then copy the MAC into rx_node.ino's DRONE_MAC.
 */

#include <WiFi.h>
#include <esp_wifi.h>

// ---------------- configuration ----------------
#define DWELL_MS            500   // time per channel per sweep
#define SCAN_SINGLE_CHANNEL 0     // 0 = sweep 1-13; else lock to that channel
#define MAX_MACS            32    // table size per sweep
#define MIN_FRAMES_TO_SHOW  2     // hide one-off noise
// -----------------------------------------------

typedef struct {
  uint8_t  mac[6];
  uint32_t frames;
  int32_t  rssiSum;
} entry_t;

static volatile entry_t table_[MAX_MACS];
static volatile uint8_t tableLen = 0;

static void IRAM_ATTR snifferCb(void *buf, wifi_promiscuous_pkt_type_t type) {
  if (type != WIFI_PKT_MGMT && type != WIFI_PKT_DATA) return;
  const wifi_promiscuous_pkt_t *pkt = (const wifi_promiscuous_pkt_t *)buf;
  const uint8_t *addr2 = pkt->payload + 10;
  for (uint8_t i = 0; i < tableLen; i++) {
    if (memcmp((const void *)table_[i].mac, addr2, 6) == 0) {
      table_[i].frames++;
      table_[i].rssiSum += pkt->rx_ctrl.rssi;
      return;
    }
  }
  if (tableLen < MAX_MACS) {
    memcpy((void *)table_[tableLen].mac, addr2, 6);
    table_[tableLen].frames = 1;
    table_[tableLen].rssiSum = pkt->rx_ctrl.rssi;
    tableLen++;
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_promiscuous_rx_cb(snifferCb);
  esp_wifi_set_promiscuous(true);
  Serial.println("mac_scanner: sweeping channels 1-13 (or locked, see config)");
}

void loop() {
  int chFirst = SCAN_SINGLE_CHANNEL ? SCAN_SINGLE_CHANNEL : 1;
  int chLast  = SCAN_SINGLE_CHANNEL ? SCAN_SINGLE_CHANNEL : 13;

  for (int ch = chFirst; ch <= chLast; ch++) {
    esp_wifi_set_promiscuous(false);
    tableLen = 0;
    esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(true);
    delay(DWELL_MS);

    esp_wifi_set_promiscuous(false);
    uint8_t n = tableLen;
    Serial.printf("--- channel %2d (%d ms) ---\n", ch, DWELL_MS);
    for (uint8_t i = 0; i < n; i++) {
      if (table_[i].frames < MIN_FRAMES_TO_SHOW) continue;
      float hz = table_[i].frames * 1000.0f / DWELL_MS;
      Serial.printf("  %02X:%02X:%02X:%02X:%02X:%02X  frames=%3lu (%5.1f Hz)  avg RSSI=%d\n",
                    table_[i].mac[0], table_[i].mac[1], table_[i].mac[2],
                    table_[i].mac[3], table_[i].mac[4], table_[i].mac[5],
                    (unsigned long)table_[i].frames, hz,
                    (int)(table_[i].rssiSum / (int32_t)table_[i].frames));
    }
    esp_wifi_set_promiscuous(true);
  }
}
