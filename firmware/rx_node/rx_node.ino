/*
 * rx_node.ino — ground sniffer node (build 3-4 of these).
 *
 * Receive-only localization sensor: sits in WiFi promiscuous (monitor)
 * mode on WIFI_CHANNEL, filters every frame whose transmitter address
 * matches DRONE_MAC, and records the hardware RSSI of each one. Every
 * REPORT_MS it sends the median RSSI + sample count to the hub node
 * over ESP-NOW (unicast on the same channel, so sniffing continues
 * uninterrupted).
 *
 * The node never transmits anything toward the drone — from the
 * drone's point of view this system is completely passive.
 *
 * Per-node config: set NODE_ID (1..N, unique) and the two MACs below.
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

// ---------------- configuration ----------------
#define NODE_ID        1        // UNIQUE per node: 1, 2, 3, 4...
#define WIFI_CHANNEL   6        // must match drone_beacon / hub_node

// STA MAC printed by drone_beacon.ino at boot:
static const uint8_t DRONE_MAC[6] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00};
// MAC printed by hub_node.ino at boot:
static const uint8_t HUB_MAC[6]   = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x01};

#define REPORT_MS      250      // report interval → 4 Hz position updates
#define MAX_SAMPLES    64       // ring buffer per report window
// -----------------------------------------------

typedef struct __attribute__((packed)) {
  uint8_t  node_id;
  int8_t   rssi_median;   // dBm
  uint8_t  n_samples;
  uint32_t millis_ts;
} report_t;

static volatile int8_t  samples[MAX_SAMPLES];
static volatile uint8_t sampleCount = 0;

// Minimal 802.11 MAC header: addr2 (transmitter) lives at bytes 10..15
// for management and data frames.
static void IRAM_ATTR snifferCb(void *buf, wifi_promiscuous_pkt_type_t type) {
  if (type != WIFI_PKT_MGMT && type != WIFI_PKT_DATA) return;
  const wifi_promiscuous_pkt_t *pkt = (const wifi_promiscuous_pkt_t *)buf;
  const uint8_t *addr2 = pkt->payload + 10;
  if (memcmp(addr2, DRONE_MAC, 6) != 0) return;
  if (sampleCount < MAX_SAMPLES) {
    samples[sampleCount++] = pkt->rx_ctrl.rssi;
  }
}

static int cmpInt8(const void *a, const void *b) {
  return *(const int8_t *)a - *(const int8_t *)b;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) {
    Serial.println("esp_now_init failed, rebooting");
    delay(1000);
    ESP.restart();
  }
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, HUB_MAC, 6);
  peer.channel = WIFI_CHANNEL;
  peer.ifidx   = WIFI_IF_STA;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  wifi_promiscuous_filter_t filter = {
    .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA
  };
  esp_wifi_set_promiscuous_filter(&filter);
  esp_wifi_set_promiscuous_rx_cb(snifferCb);
  esp_wifi_set_promiscuous(true);

  Serial.printf("rx_node %d up on channel %d, MAC %s\n",
                NODE_ID, WIFI_CHANNEL, WiFi.macAddress().c_str());
}

void loop() {
  static uint32_t lastReport = 0;
  if (millis() - lastReport < REPORT_MS) return;
  lastReport = millis();

  // Snapshot + reset the buffer with the sniffer briefly paused so the
  // ISR can't write mid-copy.
  esp_wifi_set_promiscuous(false);
  uint8_t n = sampleCount;
  int8_t local[MAX_SAMPLES];
  memcpy(local, (const void *)samples, n);
  sampleCount = 0;
  esp_wifi_set_promiscuous(true);

  if (n == 0) return;  // drone not heard this window; hub treats silence as "no fix"

  qsort(local, n, sizeof(int8_t), cmpInt8);
  report_t r = {NODE_ID, local[n / 2], n, millis()};
  esp_now_send(HUB_MAC, (const uint8_t *)&r, sizeof(r));
}
